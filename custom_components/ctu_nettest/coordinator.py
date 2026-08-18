"""Coordinator scheduling ČTÚ NetTest RMBT measurements."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AUTO_UPDATE_ENABLED,
    CONF_CLIENT_UUID,
    CONF_CONTROL_SERVER_URL,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_CONTROL_SERVER_URL,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
    TEST_TIMEOUT_SECONDS,
)
from .rmbt_runner import RmbtError, RmbtOptions, RmbtResult, run_test

_LOGGER = logging.getLogger(__name__)

type CtuNetTestConfigEntry = ConfigEntry[CtuNetTestCoordinator]


def entry_settings(config_entry: ConfigEntry) -> dict[str, Any]:
    """Return the entry configuration with the options applied on top."""
    return {**config_entry.data, **config_entry.options}


def measurement_interval(config_entry: ConfigEntry) -> timedelta | None:
    """Return the automatic measurement interval, or None when disabled."""
    settings = entry_settings(config_entry)
    if not settings.get(CONF_AUTO_UPDATE_ENABLED, True):
        return None
    return timedelta(
        hours=settings.get(CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS)
    )


class CtuNetTestCoordinator(DataUpdateCoordinator[RmbtResult]):
    """Run RMBT measurements and publish the results to the entities."""

    config_entry: CtuNetTestConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: CtuNetTestConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        self._measurement: asyncio.Future[RmbtResult] | None = None
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=measurement_interval(config_entry),
        )

    @property
    def test_running(self) -> bool:
        """Return True while a measurement worker thread is still busy."""
        return self._measurement is not None and not self._measurement.done()

    def apply_options(self) -> None:
        """Pick up a changed interval without re-running the measurement."""
        self.update_interval = measurement_interval(self.config_entry)

    async def async_run_test(self) -> None:
        """Run a measurement outside of the schedule."""
        await self.async_refresh()
        if not self.last_update_success:
            raise HomeAssistantError(
                f"Měření se nepodařilo dokončit: {self.last_exception}"
            )

    @override
    async def _async_update_data(self) -> RmbtResult:
        if self.test_running:
            _LOGGER.warning("A measurement is already running, skipping this run")
            if self.data is None:
                raise UpdateFailed("A measurement is already running")
            return self.data

        settings = entry_settings(self.config_entry)
        options = RmbtOptions(
            control_server_url=settings.get(
                CONF_CONTROL_SERVER_URL, DEFAULT_CONTROL_SERVER_URL
            ),
            client_uuid=settings.get(CONF_CLIENT_UUID),
        )

        self._measurement = self.hass.async_add_executor_job(run_test, options)
        self.async_update_listeners()

        try:
            async with asyncio.timeout(TEST_TIMEOUT_SECONDS):
                # Shielded because a thread pool job cannot be cancelled; letting
                # the timeout propagate would only orphan it silently.
                result = await asyncio.shield(self._measurement)
        except TimeoutError as err:
            raise UpdateFailed(
                f"Měření se nedokončilo do {TEST_TIMEOUT_SECONDS} s"
            ) from err
        except RmbtError as err:
            raise UpdateFailed(f"Měření selhalo: {err}") from err

        self._persist_client_uuid(result.client_uuid)
        return result

    def _persist_client_uuid(self, client_uuid: str) -> None:
        """Reuse one client UUID so ČTÚ does not register a client per test."""
        if self.config_entry.data.get(CONF_CLIENT_UUID) == client_uuid:
            return
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_CLIENT_UUID: client_uuid},
        )
