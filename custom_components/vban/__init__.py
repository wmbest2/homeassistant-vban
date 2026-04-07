"""The VBAN VoiceMeeter integration."""
import asyncio
import logging
from typing import Dict

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_platform

from aiovban.asyncio import AsyncVBANClient, VoicemeeterRemote

from .const import DOMAIN, CONF_HOST, CONF_PORT, CONF_COMMAND_STREAM, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.BUTTON,
]

class VBANData:
    """Storage for VBAN clients and remotes."""
    def __init__(self):
        self.clients: Dict[int, AsyncVBANClient] = {}
        self.remotes: Dict[str, VoicemeeterRemote] = {}
        self.ref_counts: Dict[int, int] = {}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VBAN VoiceMeeter from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    stream = entry.data[CONF_COMMAND_STREAM]
    listen_port = DEFAULT_PORT 

    _LOGGER.info("Initializing VBAN integration for %s:%s (Local port: %s)", host, port, listen_port)

    vban_data: VBANData = hass.data.setdefault(DOMAIN, VBANData())

    if listen_port not in vban_data.clients:
        _LOGGER.debug("Creating new VBAN client for local port %s", listen_port)
        client = AsyncVBANClient()
        try:
            await client.listen("0.0.0.0", listen_port)
            vban_data.clients[listen_port] = client
            vban_data.ref_counts[listen_port] = 0
        except Exception as err:
            _LOGGER.error("Failed to start VBAN listener on port %s: %s", listen_port, err)
            raise ConfigEntryNotReady(f"Failed to listen on VBAN port {listen_port}: {err}") from err
    
    client = vban_data.clients[listen_port]
    vban_data.ref_counts[listen_port] += 1

    device = await client.register_device(host, port)
    remote = VoicemeeterRemote(device, stream)
    await remote.start()
    
    attempts = 0
    while not remote.type and attempts < 100:
        await asyncio.sleep(0.1)
        attempts += 1

    if not remote.type:
        _LOGGER.warning("Timed out waiting for VoiceMeeter RT packet from %s.", host)
    else:
        _LOGGER.info("Discovered VoiceMeeter %s (%s) at %s", remote.type.name, remote.version, host)

    vban_data.remotes[entry.entry_id] = remote

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register entity-based services
    platform = entity_platform.async_get_current_platform()
    
    platform.async_register_entity_service(
        "send_raw_command",
        {vol.Required("command"): str},
        "async_send_raw_command",
    )
    platform.async_register_entity_service(
        "set_gain",
        {vol.Required("gain"): vol.Coerce(float)},
        "async_set_gain",
    )
    platform.async_register_entity_service(
        "set_mute",
        {vol.Required("mute"): bool},
        "async_set_mute",
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    vban_data: VBANData = hass.data[DOMAIN]
    remote = vban_data.remotes.pop(entry.entry_id)
    await remote.stop()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        listen_port = DEFAULT_PORT
        vban_data.ref_counts[listen_port] -= 1
        if vban_data.ref_counts[listen_port] <= 0:
            client = vban_data.clients.pop(listen_port)
            client.close()
            vban_data.ref_counts.pop(listen_port)

    return unload_ok
