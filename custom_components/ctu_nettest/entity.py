"""Shared entity base for the ČTÚ NetTest integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import CtuNetTestCoordinator

DEVICE_NAME = "ČTÚ NetTest"


class CtuNetTestEntity(CoordinatorEntity[CtuNetTestCoordinator]):
    """Base entity tying all measurements to one service device."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: CtuNetTestCoordinator, description: EntityDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=DEVICE_NAME,
            manufacturer="Český telekomunikační úřad (neoficiální integrace)",
            model="RMBT",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://nettest.ctu.gov.cz/",
        )
