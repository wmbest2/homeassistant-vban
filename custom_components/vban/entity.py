"""Base class for VBAN VoiceMeeter entities."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from aiovban.enums import VoicemeeterType
from .const import DOMAIN
from .coordinator import VBANUpdateCoordinator

if TYPE_CHECKING:
    pass

_LOGGER = logging.getLogger(__name__)

class VBANBaseEntity(CoordinatorEntity[VBANUpdateCoordinator]):
    """Common properties for VBAN entities."""
    _attr_has_entity_name = True

    def __init__(self, coordinator: VBANUpdateCoordinator, kind: str, index: int) -> None:
        super().__init__(coordinator)
        self.remote = coordinator.remote
        self.kind = kind
        self.index = index
        
        # Base Device Info (The VoiceMeeter Host)
        host_id = (DOMAIN, self.remote.device.address)
        
        # Sub-device Info (The specific Strip or Bus)
        sub_id = (DOMAIN, f"{self.remote.device.address}_{kind}_{index}")
        
        self._attr_device_info = DeviceInfo(
            identifiers={sub_id},
            name=f"{self.identifier} ({self.obj.label})" if self.obj.label else self.identifier,
            manufacturer="VB-Audio",
            model=self.remote.type.name if self.remote.type else "VoiceMeeter",
            sw_version=self.remote.version,
            via_device=host_id,
        )

    @property
    def available(self) -> bool:
        return self.remote.online and super().available

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

    async def async_send_raw_command(self, command: str) -> None:
        """Service: send raw command."""
        _LOGGER.info("Sending raw command to %s: %s", self.remote.device.address, command)
        await self.remote.send_command(command)

    async def async_set_gain(self, gain: float) -> None:
        """Service: set gain."""
        await self.obj.set_gain(gain)

    async def async_set_mute(self, mute: bool) -> None:
        """Service: set mute."""
        await self.obj.set_mute(mute)
