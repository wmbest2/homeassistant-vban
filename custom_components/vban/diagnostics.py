"""Diagnostics support for VBAN VoiceMeeter."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.diagnostics import async_redact_data

from .const import DOMAIN, CONF_HOST

TO_REDACT = {CONF_HOST}

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    vban_data = hass.data[DOMAIN]
    remote = vban_data.remotes[entry.entry_id]

    diagnostics_data = {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "device_info": {
            "type": remote.type.name if remote.type else "Unknown",
            "version": remote.version,
            "online": remote.online,
            "last_update": remote.last_update,
        },
        "strips": [
            {
                "index": s.index,
                "label": s.label,
                "gain": s.gain,
                "mute": s.mute,
                "solo": s.solo,
            }
            for s in remote.strips
        ],
        "buses": [
            {
                "index": b.index,
                "label": b.label,
                "gain": b.gain,
                "mute": b.mute,
            }
            for b in remote.buses
        ],
    }

    return diagnostics_data
