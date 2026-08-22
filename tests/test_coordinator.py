"""Tests for the NetTest ČTÚ coordinator, entities and service."""

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ctu_nettest.const import (
    CONF_AUTO_UPDATE_ENABLED,
    CONF_CLIENT_UUID,
    CONF_UPDATE_INTERVAL_HOURS,
    DOMAIN,
    SERVICE_RUN_TEST,
)
from custom_components.ctu_nettest.rmbt_runner import RmbtError

from .conftest import CLIENT_UUID


async def _setup(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_no_measurement_when_automatic_runs_are_disabled(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_run_test
) -> None:
    """With the schedule off, setup must not saturate the connection."""
    await _setup(hass, config_entry)

    mock_run_test.assert_not_called()
    assert hass.states.get("sensor.nettest_ctu_download").state == "unknown"
    assert hass.states.get("binary_sensor.nettest_ctu_test_running").state == "off"


async def test_scheduled_measurement_runs_after_startup(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_run_test
) -> None:
    """With the schedule on, the first measurement runs once HA is up."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, CONF_AUTO_UPDATE_ENABLED: True}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    mock_run_test.assert_called_once()
    assert config_entry.runtime_data.update_interval == timedelta(hours=12)


async def test_service_populates_all_sensors(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_run_test
) -> None:
    """The service is the manual entry point used by dashboards."""
    await _setup(hass, config_entry)

    await hass.services.async_call(DOMAIN, SERVICE_RUN_TEST, blocking=True)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.nettest_ctu_download").state == "194.56"
    assert hass.states.get("sensor.nettest_ctu_upload").state == "208.05"
    assert hass.states.get("sensor.nettest_ctu_ping").state == "9.65"
    assert hass.states.get("sensor.nettest_ctu_jitter").state == "1.97"
    assert (
        hass.states.get("sensor.nettest_ctu_last_test").state
        == "2026-08-18T08:22:21+00:00"
    )


async def test_sensor_attributes_exclude_the_public_ip(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_run_test
) -> None:
    """The measurement details are exposed, the public IP deliberately is not."""
    await _setup(hass, config_entry)
    await hass.services.async_call(DOMAIN, SERVICE_RUN_TEST, blocking=True)
    await hass.async_block_till_done()

    download = hass.states.get("sensor.nettest_ctu_download").attributes
    assert download["bytes_transferred"] == 253939712
    assert download["threads"] == 3
    assert "certifikovaným měřením" in download["disclaimer"]

    last_test = hass.states.get("sensor.nettest_ctu_last_test").attributes
    assert last_test["test_server"] == "m01v4-nettest.ctu.gov.cz"

    for state in hass.states.async_all():
        assert "client_remote_ip" not in state.attributes
        assert "ip" not in state.attributes


async def test_failed_measurement_keeps_the_integration_alive(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A dead control server must not raise out of the coordinator."""
    with patch(
        "custom_components.ctu_nettest.coordinator.run_test",
        side_effect=RmbtError("HTTP 502"),
    ):
        await _setup(hass, config_entry)
        coordinator = config_entry.runtime_data
        await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert hass.states.get("sensor.nettest_ctu_download").state == "unavailable"
    assert hass.states.get("binary_sensor.nettest_ctu_test_running").state == "off"


async def test_service_reports_a_failed_measurement(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A manual run surfaces the failure to the caller."""
    with patch(
        "custom_components.ctu_nettest.coordinator.run_test",
        side_effect=RmbtError("HTTP 502"),
    ):
        await _setup(hass, config_entry)

        with pytest.raises(HomeAssistantError, match="nepodařilo"):
            await hass.services.async_call(DOMAIN, SERVICE_RUN_TEST, blocking=True)


async def test_running_state_is_published_while_measuring(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_run_test, result
) -> None:
    """The binary sensor flips as soon as the measurement starts.

    The test harness runs executor jobs inline, so the worker future is driven
    by hand instead of by a real thread.
    """
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    in_flight: asyncio.Future = hass.loop.create_future()
    running = "binary_sensor.nettest_ctu_test_running"

    with patch.object(hass, "async_add_executor_job", return_value=in_flight):
        first = hass.async_create_task(coordinator.async_refresh())
        await asyncio.sleep(0)

        assert coordinator.test_running is True
        assert hass.states.get(running).state == "on"

        in_flight.set_result(result)
        await first

    assert coordinator.test_running is False
    assert coordinator.last_update_success is True
    assert coordinator.data == result
    assert hass.states.get(running).state == "off"


async def test_timed_out_measurement_still_blocks_the_next_run(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_run_test
) -> None:
    """A worker thread cannot be cancelled, so the slot stays reserved.

    Home Assistant serializes refreshes itself, so this orphaned worker is the
    only case where the coordinator's own overlap guard matters.
    """
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    in_flight: asyncio.Future = hass.loop.create_future()

    with (
        patch.object(hass, "async_add_executor_job", return_value=in_flight),
        patch("custom_components.ctu_nettest.coordinator.TEST_TIMEOUT_SECONDS", 0.05),
    ):
        await coordinator.async_refresh()

        assert coordinator.last_update_success is False
        assert "nedokončilo" in str(coordinator.last_exception)
        assert coordinator.test_running is True

        await coordinator.async_refresh()
        assert coordinator.last_update_success is False

        in_flight.cancel()
        await asyncio.sleep(0)

    assert coordinator.test_running is False


async def test_client_uuid_is_persisted_once(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_run_test
) -> None:
    """Reusing one UUID keeps ČTÚ from registering a client per test."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        data={
            key: value
            for key, value in config_entry.data.items()
            if key != CONF_CLIENT_UUID
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(DOMAIN, SERVICE_RUN_TEST, blocking=True)
    await hass.async_block_till_done()

    assert config_entry.data[CONF_CLIENT_UUID] == CLIENT_UUID


async def test_interval_change_is_applied_without_reload(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_run_test
) -> None:
    """The coordinator reschedules in place, so no measurement is triggered."""
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    assert coordinator.update_interval is None

    hass.config_entries.async_update_entry(
        config_entry,
        options={CONF_AUTO_UPDATE_ENABLED: True, CONF_UPDATE_INTERVAL_HOURS: 8},
    )
    await hass.async_block_till_done()

    assert coordinator.update_interval == timedelta(hours=8)
    mock_run_test.assert_not_called()


async def test_unload_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_run_test
) -> None:
    await _setup(hass, config_entry)

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.nettest_ctu_download").state == "unavailable"
