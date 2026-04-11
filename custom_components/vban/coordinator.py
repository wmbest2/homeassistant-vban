"""Coordinator for VBAN VoiceMeeter updates."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from aiovban.asyncio import VoicemeeterRemote

_LOGGER = logging.getLogger(__name__)

class VBANUpdateCoordinator(DataUpdateCoordinator[None]):
    """Central coordinator for VBAN updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        remote: VoicemeeterRemote,
        host: str,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"vban_{host}",
            # We don't poll, we use push callbacks
            update_interval=None,
        )
        self.remote = remote
        self.host = host

    async def _async_setup(self) -> None:
        """Set up the coordinator."""
        self.remote.add_callback(self._handle_update)

    @callback
    def _handle_update(self, _remote: VoicemeeterRemote, _body: Any) -> None:
        """Handle pushed updates from the device."""
        self.async_set_updated_data(None)
