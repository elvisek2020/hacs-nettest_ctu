"""Tests for the migration of entries created before the minute interval."""

from datetime import timedelta

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ctu_nettest.const import (
    CONF_AUTO_UPDATE_ENABLED,
    CONF_CLIENT_UUID,
    CONF_CONTROL_SERVER_URL,
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_CONTROL_SERVER_URL,
    DOMAIN,
    LEGACY_CONF_UPDATE_INTERVAL_HOURS,
    MAX_UPDATE_INTERVAL_MINUTES,
)

from .conftest import CLIENT_UUID


def _legacy_entry(hours: int, option_hours: int | None = None) -> MockConfigEntry:
    """Return an entry as it was stored while the interval was in hours."""
    options = (
        {}
        if option_hours is None
        else {
            LEGACY_CONF_UPDATE_INTERVAL_HOURS: option_hours,
            CONF_AUTO_UPDATE_ENABLED: True,
        }
    )
    return MockConfigEntry(
        domain=DOMAIN,
        title="NetTest ČTÚ",
        version=1,
        data={
            CONF_CONTROL_SERVER_URL: DEFAULT_CONTROL_SERVER_URL,
            CONF_CLIENT_UUID: CLIENT_UUID,
            LEGACY_CONF_UPDATE_INTERVAL_HOURS: hours,
            CONF_AUTO_UPDATE_ENABLED: False,
        },
        options=options,
    )


async def test_hours_are_converted_to_minutes(
    hass: HomeAssistant, mock_run_test
) -> None:
    """An existing installation keeps measuring at the same interval."""
    config_entry = _legacy_entry(12)
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.version == 2
    assert LEGACY_CONF_UPDATE_INTERVAL_HOURS not in config_entry.data
    assert config_entry.data[CONF_UPDATE_INTERVAL_MINUTES] == 720
    assert config_entry.data[CONF_CLIENT_UUID] == CLIENT_UUID


async def test_options_are_migrated_too(hass: HomeAssistant, mock_run_test) -> None:
    """Options override the entry data, so they have to be converted as well."""
    config_entry = _legacy_entry(12, option_hours=6)
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert LEGACY_CONF_UPDATE_INTERVAL_HOURS not in config_entry.options
    assert config_entry.options[CONF_UPDATE_INTERVAL_MINUTES] == 360
    assert config_entry.runtime_data.update_interval == timedelta(minutes=360)


async def test_an_interval_beyond_the_maximum_is_clamped(
    hass: HomeAssistant, mock_run_test
) -> None:
    """The old maximum of 168 hours is the new maximum, longer ones are cut."""
    config_entry = _legacy_entry(300)
    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert (
        config_entry.data[CONF_UPDATE_INTERVAL_MINUTES] == MAX_UPDATE_INTERVAL_MINUTES
    )
