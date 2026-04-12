"""Text platform for VBAN VoiceMeeter."""
from __future__ import annotations

import logging
from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VBANConfigEntry, VBANUpdateCoordinator
from .entity import VBANBaseEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: VBANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the VBAN text entities."""
    data = entry.runtime_data
    remote = data.remote
    coordinator = data.coordinator

    entities = []
    for strip in remote.strips:
        entities.append(VBANLabelText(coordinator, "strip", strip.index))
    for bus in remote.buses:
        entities.append(VBANLabelText(coordinator, "bus", bus.index))

    async_add_entities(entities)

class VBANLabelText(VBANBaseEntity, TextEntity):
    """Text entity for VBAN labels."""
    _attr_translation_key = "label"

    def __init__(self, coordinator: VBANUpdateCoordinator, kind: str, index: int) -> None:
        super().__init__(coordinator, kind, index)
        self._attr_unique_id = f"{self.remote.device.address}_{kind}_{index}_label"
        self._attr_suggested_object_id = f"{kind}_{index + 1}_label"

    @property
    def native_value(self) -> str | None:
        return self.obj.label

    async def async_set_value(self, value: str) -> None:
        _LOGGER.info("Setting label for %s to %s", self.identifier, value)
        await self.obj.set_label(value)
