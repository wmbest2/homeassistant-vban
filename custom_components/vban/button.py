"""Button platform for VBAN VoiceMeeter."""
from __future__ import annotations

import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VBANConfigEntry
from .coordinator import VBANUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: VBANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the VBAN buttons."""
    data = entry.runtime_data
    coordinator = data.coordinator

    async_add_entities([
        VBANRestartButton(coordinator),
        VBANShowWindowButton(coordinator),
    ])

class VBANBaseButton(CoordinatorEntity[VBANUpdateCoordinator], ButtonEntity):
    """Base class for VBAN buttons."""
    _attr_has_entity_name = True

    def __init__(self, coordinator: VBANUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self.remote = coordinator.remote
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.remote.device.address)},
            name=f"VoiceMeeter ({self.remote.device.address})",
            manufacturer="VB-Audio",
            model=self.remote.type.name if self.remote.type else "VoiceMeeter",
            sw_version=self.remote.version,
        )

    @property
    def available(self) -> bool:
        return self.remote.online and super().available

class VBANRestartButton(VBANBaseButton):
    """Button to restart VoiceMeeter audio engine."""
    _attr_translation_key = "restart_engine"
    _attr_icon = "mdi:restart"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VBANUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.remote.device.address}_restart_engine"

    async def async_press(self) -> None:
        _LOGGER.info("Restarting VoiceMeeter audio engine for %s", self.remote.device.address)
        await self.remote.restart()

class VBANShowWindowButton(VBANBaseButton):
    """Button to show VoiceMeeter window."""
    _attr_translation_key = "show_window"
    _attr_icon = "mdi:window-maximize"
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VBANUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.remote.device.address}_show_window"

    async def async_press(self) -> None:
        _LOGGER.info("Showing VoiceMeeter window for %s", self.remote.device.address)
        await self.remote.show()
