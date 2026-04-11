"""Number platform for VBAN VoiceMeeter."""
from homeassistant.components.number import NumberEntity
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
    """Set up the VBAN numbers."""
    vban_data = hass.data[DOMAIN]
    remote = vban_data.remotes[entry.entry_id]

    entities = []
    for strip in remote.strips:
        entities.append(VBANGainNumber(remote, "strip", strip.index))
    for bus in remote.buses:
        entities.append(VBANGainNumber(remote, "bus", bus.index))

    async_add_entities(entities)

class VBANGainNumber(VBANBaseEntity, NumberEntity):
    """Gain number for VBAN."""
    _attr_native_min_value = -60.0
    _attr_native_max_value = 12.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "dB"

    def __init__(self, remote, kind, index):
        super().__init__(remote, kind, index)
        self._attr_unique_id = f"{remote.device.address}_{kind}_{index}_gain"
        self._attr_suggested_object_id = f"{kind}_{index + 1}_gain"

    @property
    def name(self):
        label = self.obj.label or f"{self.kind.capitalize()} {self.index + 1}"
        return f"{label} Gain"

    @property
    def native_value(self):
        return self.obj.gain

    async def async_set_native_value(self, value: float):
        from .__init__ import _LOGGER
        _LOGGER.info("Setting gain for %s to %.1f", self.name, value)
        await self.obj.set_gain(value)
