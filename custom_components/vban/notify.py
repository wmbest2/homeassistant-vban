"""Notification platform for VBAN Chat."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.notify import (
    ATTR_TITLE,
    BaseNotificationService,
    NotifyEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo

from . import VBANConfigEntry
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: VBANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the VBAN notification entity."""
    async_add_entities([VBANNotifyEntity(entry)])

class VBANNotifyEntity(NotifyEntity):
    """Notification entity for VBAN Chat."""

    _attr_has_entity_name = True
    _attr_translation_key = "chat"

    def __init__(self, entry: VBANConfigEntry) -> None:
        """Initialize the entity."""
        self._entry = entry
        self._chat = entry.runtime_data.chat
        
        data = entry.runtime_data.remote.device.connected_application_data
        host_id = data.host_name if data and data.host_name else entry.data["host"]
        
        self._attr_unique_id = f"{entry.entry_id}_chat"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host_id)},
        )

    async def async_send_message(self, message: str, title: str | None = None, **kwargs: Any) -> None:
        """Send a message."""
        if title:
            message = f"{title}: {message}"
        
        _LOGGER.debug("Sending VBAN chat message: %s", message)
        await self._chat.send_chat(message)
