"""Switch platform for VBAN VoiceMeeter."""
import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import VBANBaseEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the VBAN switches."""
    vban_data = hass.data[DOMAIN]
    remote = vban_data.remotes[entry.entry_id]

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
    _attr_translation_key = "mute"

    def __init__(self, remote, kind, index):
        super().__init__(remote, kind, index)
        self._attr_unique_id = f"{remote.device.address}_{kind}_{index}_mute"
        self._attr_suggested_object_id = f"{kind}_{index + 1}_mute"

    @property
    def is_on(self):
        return self.obj.mute

    async def async_turn_on(self, **kwargs):
        _LOGGER.info("Turning ON %s for %s", self.identifier, self.remote.device.address)
        await self.obj.set_mute(True)

    async def async_turn_off(self, **kwargs):
        _LOGGER.info("Turning OFF %s for %s", self.identifier, self.remote.device.address)
        await self.obj.set_mute(False)

class VBANSoloSwitch(VBANBaseEntity, SwitchEntity):
    """Solo switch for VBAN."""
    _attr_translation_key = "solo"

    def __init__(self, remote, index):
        super().__init__(remote, "strip", index)
        self._attr_unique_id = f"{remote.device.address}_strip_{index}_solo"
        self._attr_suggested_object_id = f"strip_{index + 1}_solo"

    @property
    def is_on(self):
        return self.obj.solo

    async def async_turn_on(self, **kwargs):
        _LOGGER.info("Turning ON solo for %s at %s", self.identifier, self.remote.device.address)
        await self.obj.set_solo(True)

    async def async_turn_off(self, **kwargs):
        _LOGGER.info("Turning OFF solo for %s at %s", self.identifier, self.remote.device.address)
        await self.obj.set_solo(False)

class VBANRoutingSwitch(VBANBaseEntity, SwitchEntity):
    """Routing switch for VBAN."""
    _attr_translation_key = "bus_routing"

    def __init__(self, remote, index, bus_id):
        super().__init__(remote, "strip", index)
        self.bus_id = bus_id.lower()
        self._attr_unique_id = f"{remote.device.address}_strip_{index}_route_{self.bus_id}"
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
