"""Sensors exposing the NetTest ČTÚ measurement results."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfDataRate, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DISCLAIMER
from .coordinator import CtuNetTestConfigEntry, CtuNetTestCoordinator
from .entity import CtuNetTestEntity
from .rmbt_runner import RmbtResult


@dataclass(frozen=True, kw_only=True)
class CtuNetTestSensorDescription(SensorEntityDescription):
    """Describes a NetTest ČTÚ sensor."""

    value: Callable[[RmbtResult], StateType | datetime]
    attributes: Callable[[RmbtResult], dict[str, Any]] | None = None


SENSORS: tuple[CtuNetTestSensorDescription, ...] = (
    CtuNetTestSensorDescription(
        key="download",
        translation_key="download",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda result: result.download_mbps,
        attributes=lambda result: {
            "bytes_transferred": result.bytes_download,
            "threads": result.download_threads,
        },
    ),
    CtuNetTestSensorDescription(
        key="upload",
        translation_key="upload",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda result: result.upload_mbps,
        attributes=lambda result: {
            "bytes_transferred": result.bytes_upload,
            "threads": result.upload_threads,
        },
    ),
    CtuNetTestSensorDescription(
        key="ping",
        translation_key="ping",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda result: result.ping_ms,
        attributes=lambda result: {
            "ping_median_ms": result.ping_median_ms,
            "ping_count": result.ping_count,
        },
    ),
    CtuNetTestSensorDescription(
        key="jitter",
        translation_key="jitter",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda result: result.jitter_ms,
        attributes=lambda result: {"ping_count": result.ping_count},
    ),
    CtuNetTestSensorDescription(
        key="last_test",
        translation_key="last_test",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda result: result.timestamp,
        attributes=lambda result: {
            "test_server": result.server_address,
            "duration_seconds": result.duration_seconds,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CtuNetTestConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the NetTest ČTÚ sensors."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        CtuNetTestSensor(coordinator, description) for description in SENSORS
    )


class CtuNetTestSensor(CtuNetTestEntity, SensorEntity):
    """A single measured value of the last completed test."""

    entity_description: CtuNetTestSensorDescription

    def __init__(
        self,
        coordinator: CtuNetTestCoordinator,
        description: CtuNetTestSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description)
        self._value: StateType | datetime = None
        self._attributes: dict[str, Any] = {"disclaimer": DISCLAIMER}

    @property
    @override
    def native_value(self) -> StateType | datetime:
        """Return the value of the last completed measurement."""
        if self.coordinator.data is not None:
            self._value = self.entity_description.value(self.coordinator.data)
        return self._value

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the measurement details plus the permanent disclaimer."""
        if self.coordinator.data is not None and self.entity_description.attributes:
            self._attributes.update(
                self.entity_description.attributes(self.coordinator.data)
            )
        return self._attributes
