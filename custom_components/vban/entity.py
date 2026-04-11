"""Base class for VBAN VoiceMeeter entities."""
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.core import callback

from aiovban.enums import VoicemeeterType
from .const import DOMAIN

class VBANBaseEntity(Entity):
    """Common properties for VBAN entities."""
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, remote, kind, index):
        self.remote = remote
        self.kind = kind
        self.index = index
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, remote.device.address)},
            name=f"VoiceMeeter ({remote.device.address})",
            manufacturer="VB-Audio",
            model=remote.type.name if remote.type else "VoiceMeeter",
            sw_version=remote.version,
        )

    @property
    def available(self) -> bool:
        return self.remote.online

    @property
    def obj(self):
        if self.kind == "strip":
            return self.remote._all_strips[self.index]
        return self.remote._all_buses[self.index]

    @property
    def identifier(self) -> str:
        """Return a stable identifier like Strip 1 or A1."""
        if self.kind == "strip":
            return f"Strip {self.index + 1}"
        
        v_type = self.remote.type or VoicemeeterType.POTATO
        phys_limit = 2 if v_type == VoicemeeterType.VOICEMEETER else 3 if v_type == VoicemeeterType.BANANA else 5
        if self.index < phys_limit:
            return f"A{self.index + 1}"
        return f"B{self.index - phys_limit + 1}"

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.remote.add_callback(self._handle_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks."""
        self.remote.remove_callback(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self, remote, body) -> None:
        """Update the entity state."""
        self.async_write_ha_state()

    async def async_send_raw_command(self, command: str):
        """Service: send raw command."""
        from .__init__ import _LOGGER
        _LOGGER.info("Sending raw command to %s: %s", self.remote.device.address, command)
        await self.remote.send_command(command)

    async def async_set_gain(self, gain: float):
        """Service: set gain."""
        await self.obj.set_gain(gain)

    async def async_set_mute(self, mute: bool):
        """Service: set mute."""
        await self.obj.set_mute(mute)
