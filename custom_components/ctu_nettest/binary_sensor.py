"""Binary sensor reporting whether a NetTest ČTÚ measurement is in progress."""

from __future__ import annotations

from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CtuNetTestConfigEntry
from .entity import CtuNetTestEntity

TEST_RUNNING = BinarySensorEntityDescription(
    key="test_running",
    translation_key="test_running",
    device_class=BinarySensorDeviceClass.RUNNING,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CtuNetTestConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the NetTest ČTÚ binary sensor."""
    async_add_entities(
        [CtuNetTestRunningSensor(config_entry.runtime_data, TEST_RUNNING)]
    )


class CtuNetTestRunningSensor(CtuNetTestEntity, BinarySensorEntity):
    """True while a measurement is in progress."""

    @property
    @override
    def is_on(self) -> bool:
        """Return True while a measurement worker is busy."""
        return self.coordinator.test_running

    @property
    @override
    def available(self) -> bool:
        """Stay available even when the last measurement failed."""
        return True
