"""Button platform for VBAN VoiceMeeter."""
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the VBAN buttons."""
    vban_data = hass.data[DOMAIN]
    remote = vban_data.remotes[entry.entry_id]

    async_add_entities([
        VBANRestartButton(remote),
        VBANShowWindowButton(remote),
    ])

class VBANBaseButton(ButtonEntity):
    """Base class for VBAN buttons."""
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, remote):
        self.remote = remote
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

    async def async_added_to_hass(self) -> None:
        self.remote.add_callback(self._handle_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        self.remote.remove_callback(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self, remote, body) -> None:
        self.async_write_ha_state()

class VBANRestartButton(VBANBaseButton):
    """Button to restart VoiceMeeter audio engine."""
    _attr_name = "Restart Audio Engine"
    _attr_icon = "mdi:restart"

    def __init__(self, remote):
        super().__init__(remote)
        self._attr_unique_id = f"{remote.device.address}_restart_engine"

    async def async_press(self) -> None:
        await self.remote.restart()

class VBANShowWindowButton(VBANBaseButton):
    """Button to show VoiceMeeter window."""
    _attr_name = "Show VM Window"
    _attr_icon = "mdi:window-maximize"
    _attr_entity_registry_enabled_default = False

    def __init__(self, remote):
        super().__init__(remote)
        self._attr_unique_id = f"{remote.device.address}_show_window"

    async def async_press(self) -> None:
        await self.remote.show()
