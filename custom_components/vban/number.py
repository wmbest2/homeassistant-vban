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
        entities.append(VBANCompNumber(coordinator, strip.index))
        entities.append(VBANGateNumber(coordinator, strip.index))
        entities.append(VBANDenoiserNumber(coordinator, strip.index))
        
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
        self._attr_unique_id = f"{self.host_id}_{kind}_{index}_gain"
        self._attr_suggested_object_id = f"{kind}_{index + 1}_gain"

    @property
    def native_value(self):
        return self.obj.gain

    async def async_set_native_value(self, value: float):
        await self.obj.set_gain(value)

class VBANKnobNumber(VBANBaseEntity, NumberEntity):
    """Base for 0.0-10.0 knobs."""
    _attr_native_min_value = 0.0
    _attr_native_max_value = 10.0
    _attr_native_step = 0.1
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: VBANUpdateCoordinator, index: int, knob_type: str) -> None:
        super().__init__(coordinator, "strip", index)
        self.knob_type = knob_type
        self._attr_unique_id = f"{self.host_id}_strip_{index}_{knob_type}"
        self._attr_suggested_object_id = f"strip_{index + 1}_{knob_type}"
        self._attr_translation_key = knob_type

class VBANCompNumber(VBANKnobNumber):
    """Compressor knob."""
    def __init__(self, coordinator: VBANUpdateCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "compressor")

    @property
    def native_value(self):
        return self.obj.compressor

    async def async_set_native_value(self, value: float):
        await self.obj.set_compressor(value)

class VBANGateNumber(VBANKnobNumber):
    """Gate knob."""
    def __init__(self, coordinator: VBANUpdateCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "gate")

    @property
    def native_value(self):
        return self.obj.gate

    async def async_set_native_value(self, value: float):
        await self.obj.set_gate(value)

class VBANDenoiserNumber(VBANKnobNumber):
    """Denoiser knob."""
    def __init__(self, coordinator: VBANUpdateCoordinator, index: int) -> None:
        super().__init__(coordinator, index, "denoiser")

    @property
    def native_value(self):
        return self.obj.denoiser

    async def async_set_native_value(self, value: float):
        await self.obj.set_denoiser(value)
