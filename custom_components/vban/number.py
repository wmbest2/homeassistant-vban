"""Number platform for VBAN VoiceMeeter."""
from __future__ import annotations

import logging
from homeassistant.components.number import NumberEntity
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
    """Set up the VBAN numbers."""
    data = entry.runtime_data
    remote = data.remote
    coordinator = data.coordinator

    entities = []
    for strip in remote.strips:
        entities.append(VBANGainNumber(coordinator, "strip", strip.index))
    for bus in remote.buses:
        entities.append(VBANGainNumber(coordinator, "bus", bus.index))

    async_add_entities(entities)

class VBANGainNumber(VBANBaseEntity, NumberEntity):
    """Gain number for VBAN."""
    _attr_translation_key = "gain"
    _attr_native_min_value = -60.0
    _attr_native_max_value = 12.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "dB"

    def __init__(self, coordinator: VBANUpdateCoordinator, kind: str, index: int) -> None:
        super().__init__(coordinator, kind, index)
        self._attr_unique_id = f"{self.remote.device.address}_{kind}_{index}_gain"

    @property
    def native_value(self):
        return self.obj.gain

    async def async_set_native_value(self, value: float):
        _LOGGER.info("Setting gain for %s to %.1f", self.identifier, value)
        await self.obj.set_gain(value)
