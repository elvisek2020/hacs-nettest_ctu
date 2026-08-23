"""Tests for the averages calculated from the retained measurements."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ctu_nettest.const import (
    CONF_AUTO_UPDATE_ENABLED,
    CONF_AVERAGE_SAMPLE_COUNT,
    CONF_UPDATE_INTERVAL_HOURS,
    DOMAIN,
    SERVICE_RUN_TEST,
)
from custom_components.ctu_nettest.rmbt_runner import RmbtError, RmbtResult

AVERAGE_DOWNLOAD = "sensor.nettest_ctu_average_download"
AVERAGE_UPLOAD = "sensor.nettest_ctu_average_upload"


async def _setup(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


def _series(result: RmbtResult, rates: list[tuple[float, float]]) -> list[RmbtResult]:
    """Return measurements differing only in their rates and timestamps."""
    return [
        replace(
            result,
            timestamp=result.timestamp + timedelta(hours=index),
            download_mbps=download,
            upload_mbps=upload,
        )
        for index, (download, upload) in enumerate(rates)
    ]


async def _run_tests(hass: HomeAssistant, results: list[RmbtResult]) -> None:
    """Run one measurement per result, in order."""
    with patch(
        "custom_components.ctu_nettest.coordinator.run_test", side_effect=results
    ):
        for _ in results:
            await hass.services.async_call(DOMAIN, SERVICE_RUN_TEST, blocking=True)
            await hass.async_block_till_done()


async def test_average_starts_at_the_first_measurement(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_run_test
) -> None:
    """Without any measurement there is nothing to average yet."""
    await _setup(hass, config_entry)

    assert hass.states.get(AVERAGE_DOWNLOAD).state == "unknown"

    await hass.services.async_call(DOMAIN, SERVICE_RUN_TEST, blocking=True)
    await hass.async_block_till_done()

    assert hass.states.get(AVERAGE_DOWNLOAD).state == "194.56"
    assert hass.states.get(AVERAGE_UPLOAD).state == "208.05"


async def test_average_covers_every_retained_measurement(
    hass: HomeAssistant, config_entry: MockConfigEntry, result: RmbtResult
) -> None:
    """Each measurement is weighted equally."""
    await _setup(hass, config_entry)
    await _run_tests(
        hass, _series(result, [(100.0, 50.0), (200.0, 70.0), (300.0, 90.0)])
    )

    assert hass.states.get(AVERAGE_DOWNLOAD).state == "200.0"
    assert hass.states.get(AVERAGE_UPLOAD).state == "70.0"

    attributes = hass.states.get(AVERAGE_DOWNLOAD).attributes
    assert attributes["sample_count"] == 3
    assert attributes["sample_window"] == 10
    assert attributes["oldest_sample"] == result.timestamp.isoformat()
    assert "certifikovaným měřením" in attributes["disclaimer"]


async def test_measurements_beyond_the_window_are_dropped(
    hass: HomeAssistant, config_entry: MockConfigEntry, result: RmbtResult
) -> None:
    """Only the newest measurements count towards the average."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, CONF_AVERAGE_SAMPLE_COUNT: 2}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await _run_tests(
        hass, _series(result, [(10.0, 10.0), (200.0, 60.0), (300.0, 80.0)])
    )

    assert hass.states.get(AVERAGE_DOWNLOAD).state == "250.0"
    assert hass.states.get(AVERAGE_DOWNLOAD).attributes["sample_count"] == 2


async def test_smaller_window_is_applied_without_reload(
    hass: HomeAssistant, config_entry: MockConfigEntry, result: RmbtResult
) -> None:
    """A changed window recalculates in place, without measuring again."""
    await _setup(hass, config_entry)
    await _run_tests(
        hass, _series(result, [(100.0, 50.0), (200.0, 70.0), (300.0, 90.0)])
    )

    with patch("custom_components.ctu_nettest.coordinator.run_test") as run_test:
        hass.config_entries.async_update_entry(
            config_entry,
            options={
                CONF_AUTO_UPDATE_ENABLED: False,
                CONF_UPDATE_INTERVAL_HOURS: 12,
                CONF_AVERAGE_SAMPLE_COUNT: 2,
            },
        )
        await hass.async_block_till_done()

    run_test.assert_not_called()
    assert hass.states.get(AVERAGE_DOWNLOAD).state == "250.0"
    assert hass.states.get(AVERAGE_DOWNLOAD).attributes["sample_window"] == 2


async def test_history_survives_a_reload(
    hass: HomeAssistant, config_entry: MockConfigEntry, result: RmbtResult
) -> None:
    """The samples are persisted, so a restart keeps the average intact."""
    await _setup(hass, config_entry)
    await _run_tests(hass, _series(result, [(100.0, 50.0), (200.0, 70.0)]))

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(AVERAGE_DOWNLOAD).state == "150.0"
    assert hass.states.get(AVERAGE_DOWNLOAD).attributes["sample_count"] == 2


async def test_unreadable_stored_samples_are_ignored(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_run_test,
    hass_storage: dict,
) -> None:
    """A damaged store must not keep the integration from loading."""
    hass_storage[f"{DOMAIN}.{config_entry.entry_id}"] = {
        "version": 1,
        "data": [
            {"timestamp": "not-a-timestamp", "download_mbps": 1.0, "upload_mbps": 1.0},
            {"timestamp": datetime(2026, 8, 18, tzinfo=UTC).isoformat()},
            {
                "timestamp": datetime(2026, 8, 18, 12, tzinfo=UTC).isoformat(),
                "download_mbps": 150.0,
                "upload_mbps": 60.0,
            },
        ],
    }

    await _setup(hass, config_entry)

    assert hass.states.get(AVERAGE_DOWNLOAD).state == "150.0"
    assert hass.states.get(AVERAGE_DOWNLOAD).attributes["sample_count"] == 1


async def test_average_stays_available_after_a_failed_measurement(
    hass: HomeAssistant, config_entry: MockConfigEntry, result: RmbtResult
) -> None:
    """One dead control server must not hide an otherwise valid average."""
    await _setup(hass, config_entry)
    await _run_tests(hass, _series(result, [(100.0, 50.0), (200.0, 70.0)]))

    with patch(
        "custom_components.ctu_nettest.coordinator.run_test",
        side_effect=RmbtError("HTTP 502"),
    ):
        await config_entry.runtime_data.async_refresh()
        await hass.async_block_till_done()

    assert hass.states.get("sensor.nettest_ctu_download").state == "unavailable"
    assert hass.states.get(AVERAGE_DOWNLOAD).state == "150.0"
