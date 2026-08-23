"""Button starting a NetTest ČTÚ measurement on demand."""

from __future__ import annotations

from typing import override

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import CtuNetTestConfigEntry
from .entity import CtuNetTestEntity

RUN_TEST = ButtonEntityDescription(
    key="run_test",
    translation_key="run_test",
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: CtuNetTestConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the NetTest ČTÚ button."""
    async_add_entities([CtuNetTestRunButton(config_entry.runtime_data, RUN_TEST)])


class CtuNetTestRunButton(CtuNetTestEntity, ButtonEntity):
    """Runs a measurement outside of the configured schedule."""

    @override
    async def async_press(self) -> None:
        """Run a measurement and surface a failure to the caller."""
        await self.coordinator.async_run_test()

    @property
    @override
    def available(self) -> bool:
        """Stay pressable so that a failed measurement can be retried."""
        return True
