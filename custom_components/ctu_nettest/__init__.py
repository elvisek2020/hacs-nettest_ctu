"""NetTest ČTÚ — orientační měření rychlosti internetu proti RMBT serverům ČTÚ."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_UPDATE_INTERVAL_MINUTES,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    LEGACY_CONF_UPDATE_INTERVAL_HOURS,
    MAX_UPDATE_INTERVAL_MINUTES,
    SERVICE_RUN_TEST,
)
from .coordinator import (
    CtuNetTestConfigEntry,
    CtuNetTestCoordinator,
    measurement_interval,
)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration services."""

    async def handle_run_test(call: ServiceCall) -> None:
        """Run a measurement on every loaded entry."""
        entries: list[CtuNetTestConfigEntry] = hass.config_entries.async_loaded_entries(
            DOMAIN
        )
        if not entries:
            raise HomeAssistantError("Integrace NetTest ČTÚ není nastavená")
        for entry in entries:
            await entry.runtime_data.async_run_test()

    hass.services.async_register(DOMAIN, SERVICE_RUN_TEST, handle_run_test)
    return True


def _interval_in_minutes(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Return the settings with the hour based interval expressed in minutes."""
    migrated = dict(settings)
    hours = migrated.pop(LEGACY_CONF_UPDATE_INTERVAL_HOURS, None)
    if hours is None:
        return migrated
    migrated[CONF_UPDATE_INTERVAL_MINUTES] = min(
        int(hours) * 60, MAX_UPDATE_INTERVAL_MINUTES
    )
    return migrated


async def async_migrate_entry(
    hass: HomeAssistant, config_entry: CtuNetTestConfigEntry
) -> bool:
    """Migrate an entry created when the interval was still measured in hours."""
    if config_entry.version > CONFIG_ENTRY_VERSION:
        return False

    if config_entry.version < CONFIG_ENTRY_VERSION:
        hass.config_entries.async_update_entry(
            config_entry,
            data=_interval_in_minutes(config_entry.data),
            options=_interval_in_minutes(config_entry.options),
            version=CONFIG_ENTRY_VERSION,
        )

    return True


async def async_setup_entry(
    hass: HomeAssistant, config_entry: CtuNetTestConfigEntry
) -> bool:
    """Set up NetTest ČTÚ from a config entry."""
    coordinator = CtuNetTestCoordinator(hass, config_entry)
    await coordinator.history.async_load()
    config_entry.runtime_data = coordinator

    async def finish_startup(hass: HomeAssistant) -> None:
        """Measure once Home Assistant is up; a test saturates the link."""
        if measurement_interval(config_entry) is None:
            return
        if config_entry.state is ConfigEntryState.LOADED:
            await coordinator.async_refresh()
        else:
            await coordinator.async_config_entry_first_refresh()

    async_at_started(hass, finish_startup)

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    config_entry.async_on_unload(config_entry.add_update_listener(async_entry_updated))

    return True


async def async_entry_updated(
    hass: HomeAssistant, config_entry: CtuNetTestConfigEntry
) -> None:
    """Apply a changed interval in place, without triggering a measurement."""
    config_entry.runtime_data.apply_options()


async def async_unload_entry(
    hass: HomeAssistant, config_entry: CtuNetTestConfigEntry
) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    await config_entry.runtime_data.history.async_flush()
    return unloaded
