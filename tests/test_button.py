"""Tests for the button running a NetTest ČTÚ measurement on demand."""

from unittest.mock import patch

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ctu_nettest.rmbt_runner import RmbtError

BUTTON = "button.nettest_ctu_run_test"


async def _setup(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def _press(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: BUTTON}, blocking=True
    )
    await hass.async_block_till_done()


async def test_press_runs_a_measurement(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_run_test
) -> None:
    """Pressing the button is the manual entry point next to the action."""
    await _setup(hass, config_entry)
    mock_run_test.assert_not_called()

    await _press(hass)

    mock_run_test.assert_called_once()
    assert hass.states.get("sensor.nettest_ctu_download").state == "194.56"


async def test_press_reports_a_failed_measurement(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A failure surfaces in the UI instead of passing silently."""
    with patch(
        "custom_components.ctu_nettest.coordinator.run_test",
        side_effect=RmbtError("HTTP 502"),
    ):
        await _setup(hass, config_entry)

        with pytest.raises(HomeAssistantError, match="nepodařilo"):
            await _press(hass)


async def test_button_stays_pressable_after_a_failed_measurement(
    hass: HomeAssistant, config_entry: MockConfigEntry, result
) -> None:
    """An unavailable button would leave no way to retry from the UI."""
    with patch(
        "custom_components.ctu_nettest.coordinator.run_test",
        side_effect=RmbtError("HTTP 502"),
    ):
        await _setup(hass, config_entry)
        await config_entry.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get("sensor.nettest_ctu_download").state == "unavailable"
    assert hass.states.get(BUTTON).state != "unavailable"

    with patch(
        "custom_components.ctu_nettest.coordinator.run_test", return_value=result
    ):
        await _press(hass)

    assert hass.states.get("sensor.nettest_ctu_download").state == "194.56"
