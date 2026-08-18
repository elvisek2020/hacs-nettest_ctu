"""ČTÚ NetTest — orientační měření rychlosti internetu proti RMBT serverům ČTÚ."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, SERVICE_RUN_TEST
from .coordinator import (
    CtuNetTestConfigEntry,
    CtuNetTestCoordinator,
    measurement_interval,
)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration services."""

    async def handle_run_test(call: ServiceCall) -> None:
        """Run a measurement on every loaded entry."""
        entries: list[CtuNetTestConfigEntry] = hass.config_entries.async_loaded_entries(
            DOMAIN
        )
        if not entries:
            raise HomeAssistantError("Integrace ČTÚ NetTest není nastavená")
        for entry in entries:
            await entry.runtime_data.async_run_test()

    hass.services.async_register(DOMAIN, SERVICE_RUN_TEST, handle_run_test)
    return True


async def async_setup_entry(
    hass: HomeAssistant, config_entry: CtuNetTestConfigEntry
) -> bool:
    """Set up ČTÚ NetTest from a config entry."""
    coordinator = CtuNetTestCoordinator(hass, config_entry)
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
    return await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
