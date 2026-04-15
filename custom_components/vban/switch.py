"""Switch platform for VBAN VoiceMeeter."""
from __future__ import annotations

import logging
from homeassistant.components.switch import SwitchEntity
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
    """Set up the VBAN switches."""
    data = entry.runtime_data
    remote = data.remote
    coordinator = data.coordinator

    entities = []
    for strip in remote.strips:
        entities.append(VBANMuteSwitch(coordinator, "strip", strip.index))
        entities.append(VBANSoloSwitch(coordinator, strip.index))
        entities.append(VBANEQSwitch(coordinator, "strip", strip.index))
        entities.append(VBANMCSwitch(coordinator, strip.index))
        
        # Routing: A1-A5, B1-B3
        for i in range(1, 6):
            bus_id = f"A{i}"
            if hasattr(strip, bus_id.lower()):
                entities.append(VBANRoutingSwitch(coordinator, strip.index, bus_id))
        for i in range(1, 4):
            bus_id = f"B{i}"
            if hasattr(strip, bus_id.lower()):
                entities.append(VBANRoutingSwitch(coordinator, strip.index, bus_id))
            
    for bus in remote.buses:
        entities.append(VBANMuteSwitch(coordinator, "bus", bus.index))
        entities.append(VBANEQSwitch(coordinator, "bus", bus.index))

    async_add_entities(entities)

class VBANMuteSwitch(VBANBaseEntity, SwitchEntity):
    """Mute switch for VBAN."""
    _attr_translation_key = "mute"

    def __init__(self, coordinator: VBANUpdateCoordinator, kind: str, index: int) -> None:
        super().__init__(coordinator, kind, index)
        self._attr_unique_id = f"{self.host_id}_{kind}_{index}_mute"
        self._attr_suggested_object_id = f"{self.identifier}_mute"

    @property
    def is_on(self):
        return self.obj.mute

    async def async_turn_on(self, **kwargs):
        await self.obj.set_mute(True)

    async def async_turn_off(self, **kwargs):
        await self.obj.set_mute(False)

class VBANSoloSwitch(VBANBaseEntity, SwitchEntity):
    """Solo switch for VBAN."""
    _attr_translation_key = "solo"

    def __init__(self, coordinator: VBANUpdateCoordinator, index: int) -> None:
        super().__init__(coordinator, "strip", index)
        self._attr_unique_id = f"{self.host_id}_strip_{index}_solo"
        self._attr_suggested_object_id = f"strip_{index + 1}_solo"

    @property
    def is_on(self):
        return self.obj.solo

    async def async_turn_on(self, **kwargs):
        await self.obj.set_solo(True)

    async def async_turn_off(self, **kwargs):
        await self.obj.set_solo(False)

class VBANEQSwitch(VBANBaseEntity, SwitchEntity):
    """EQ switch for VBAN."""
    _attr_translation_key = "eq"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: VBANUpdateCoordinator, kind: str, index: int) -> None:
        super().__init__(coordinator, kind, index)
        self._attr_unique_id = f"{self.host_id}_{kind}_{index}_eq"
        self._attr_suggested_object_id = f"{self.identifier}_eq"

    @property
    def is_on(self):
        return self.obj.eq

    async def async_turn_on(self, **kwargs):
        await self.obj.set_eq(True)

    async def async_turn_off(self, **kwargs):
        await self.obj.set_eq(False)

class VBANMCSwitch(VBANBaseEntity, SwitchEntity):
    """MC (Multi-Channel) switch for VBAN."""
    _attr_translation_key = "mc"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: VBANUpdateCoordinator, index: int) -> None:
        super().__init__(coordinator, "strip", index)
        self._attr_unique_id = f"{self.host_id}_strip_{index}_mc"
        self._attr_suggested_object_id = f"strip_{index + 1}_mc"

    @property
    def is_on(self):
        return self.obj.mc

    async def async_turn_on(self, **kwargs):
        await self.obj.set_mc(True)

    async def async_turn_off(self, **kwargs):
        await self.obj.set_mc(False)

class VBANRoutingSwitch(VBANBaseEntity, SwitchEntity):
    """Routing switch for VBAN."""
    _attr_translation_key = "bus_routing"

    def __init__(self, coordinator: VBANUpdateCoordinator, index: int, bus_id: str) -> None:
        super().__init__(coordinator, "strip", index)
        self.bus_id = bus_id.lower()
        self._attr_unique_id = f"{self.host_id}_strip_{index}_route_{self.bus_id}"
        self._attr_suggested_object_id = f"strip_{index + 1}_route_{self.bus_id}"
        self._attr_translation_placeholders = {"bus": bus_id.upper()}

    @property
    def is_on(self):
        return getattr(self.obj, self.bus_id)

    async def async_turn_on(self, **kwargs):
        _LOGGER.info("Turning ON routing to %s for %s", self.bus_id.upper(), self.identifier)
        await self.obj.set_bus_routing(self.bus_id, True)

    async def async_turn_off(self, **kwargs):
        _LOGGER.info("Turning OFF routing to %s for %s", self.bus_id.upper(), self.identifier)
        await self.obj.set_bus_routing(self.bus_id, False)
