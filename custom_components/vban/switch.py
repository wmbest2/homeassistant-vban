"""Switch platform for VBAN VoiceMeeter."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

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
    for bus in remote.buses:
        entities.append(VBANMuteSwitch(remote, "bus", bus.index))

    async_add_entities(entities)

class VBANBaseEntity:
    """Common properties for VBAN entities."""
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, remote, kind, index):
        self.remote = remote
        self.kind = kind
        self.index = index

    @property
    def available(self) -> bool:
        return self.remote.online

    @property
    def obj(self):
        if self.kind == "strip":
            return self.remote._all_strips[self.index]
        return self.remote._all_buses[self.index]

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.remote.add_callback(self._handle_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks."""
        self.remote.remove_callback(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self, remote) -> None:
        """Update the entity state."""
        self.async_write_ha_state()

class VBANMuteSwitch(VBANBaseEntity, SwitchEntity):
    """Mute switch for VBAN."""

    def __init__(self, remote, kind, index):
        super().__init__(remote, kind, index)
        # Use the actual label if available, otherwise generic name
        label = self.obj.label or f"%s %s" % (kind.capitalize(), index + 1)
        self._attr_name = f"%s Mute" % label
        self._attr_unique_id = f"%s_%s_%s_mute" % (remote.device.address, kind, index)

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
        label = self.obj.label or f"Strip %s" % (index + 1)
        self._attr_name = f"%s Solo" % label
        self._attr_unique_id = f"%s_strip_%s_solo" % (remote.device.address, index)

    @property
    def is_on(self):
        return self.obj.solo

    async def async_turn_on(self, **kwargs):
        await self.obj.set_solo(True)

    async def async_turn_off(self, **kwargs):
        await self.obj.set_solo(False)
