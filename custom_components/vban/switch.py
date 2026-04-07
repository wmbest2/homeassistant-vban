"""Switch platform for VBAN VoiceMeeter."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import VBANBaseEntity

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the VBAN switches."""
    data = hass.data[DOMAIN][entry.entry_id]
    remote = data["remote"]

    entities = []
    for strip in remote.strips:
        entities.append(VBANMuteSwitch(remote, "strip", strip.index))
        entities.append(VBANSoloSwitch(remote, strip.index))
        for bus_id in ["A1", "A2", "A3", "B1", "B2", "B3"]:
            entities.append(VBANRoutingSwitch(remote, strip.index, bus_id))
            
    for bus in remote.buses:
        entities.append(VBANMuteSwitch(remote, "bus", bus.index))

    async_add_entities(entities)

class VBANMuteSwitch(VBANBaseEntity, SwitchEntity):
    """Mute switch for VBAN."""

    def __init__(self, remote, kind, index):
        super().__init__(remote, kind, index)
        self._attr_unique_id = f"%s_%s_%s_mute" % (remote.device.address, kind, index)
        # Keep generic ID but clean up display name
        self._attr_suggested_object_id = f"%s_%s_mute" % (kind, index + 1)

    @property
    def name(self):
        label = self.obj.label or f"%s %s" % (self.kind.capitalize(), self.index + 1)
        return f"%s Mute" % label

    @property
    def is_on(self):
        return self.obj.mute

    async def async_turn_on(self, **kwargs):
        await self.obj.set_mute(True)

    async def async_turn_off(self, **kwargs):
        await self.obj.set_mute(False)

class VBANSoloSwitch(VBANBaseEntity, SwitchEntity):
    """Solo switch for VBAN."""

    def __init__(self, remote, index):
        super().__init__(remote, "strip", index)
        self._attr_unique_id = f"%s_strip_%s_solo" % (remote.device.address, index)
        self._attr_suggested_object_id = f"strip_%s_solo" % (index + 1)

    @property
    def name(self):
        label = self.obj.label or f"Strip %s" % (self.index + 1)
        return f"%s Solo" % label

    @property
    def is_on(self):
        return self.obj.solo

    async def async_turn_on(self, **kwargs):
        await self.obj.set_solo(True)

    async def async_turn_off(self, **kwargs):
        await self.obj.set_solo(False)

class VBANRoutingSwitch(VBANBaseEntity, SwitchEntity):
    """Routing switch for VBAN."""

    def __init__(self, remote, index, bus_id):
        super().__init__(remote, "strip", index)
        self.bus_id = bus_id.lower()
        self._attr_unique_id = f"%s_strip_%s_route_%s" % (remote.device.address, index, self.bus_id)
        self._attr_suggested_object_id = f"strip_%s_route_%s" % (index + 1, self.bus_id)

    @property
    def name(self):
        label = self.obj.label or f"Strip %s" % (self.index + 1)
        return f"%s -> %s" % (label, self.bus_id.upper())

    @property
    def is_on(self):
        return getattr(self.obj, self.bus_id)

    async def async_turn_on(self, **kwargs):
        await self.obj.set_bus_routing(self.bus_id, True)

    async def async_turn_off(self, **kwargs):
        await self.obj.set_bus_routing(self.bus_id, False)
