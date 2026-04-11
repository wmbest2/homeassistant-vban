"""The VBAN VoiceMeeter integration."""
import asyncio
from datetime import timedelta
import logging
from typing import Dict, Callable

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.target import async_extract_referenced_entity_ids, TargetSelection

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
        self.watchdogs: Dict[str, Callable] = {}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VBAN VoiceMeeter from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    stream = entry.data[CONF_COMMAND_STREAM]
    listen_port = DEFAULT_PORT 

    _LOGGER.info("Initializing VBAN integration for %s:%s", host, port)

    vban_data: VBANData = hass.data.setdefault(DOMAIN, VBANData())

    if listen_port not in vban_data.clients:
        client = AsyncVBANClient()
        try:
            await client.listen("0.0.0.0", listen_port)
            vban_data.clients[listen_port] = client
            vban_data.ref_counts[listen_port] = 0
        except Exception as err:
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

    vban_data.remotes[entry.entry_id] = remote

    _LOGGER.info("VBAN remote for %s initialized: online=%s, type=%s", host, remote.online, remote.type)

    # --- Online Watchdog (HA Synchronized) ---
    async def check_connection(_now):
        """Watchdog to re-register for RT packets if device goes offline."""
        _LOGGER.debug("Watchdog check for VBAN %s: online=%s, last_update=%s", host, remote.online, remote.last_update)
        if not remote.online:
            _LOGGER.info("VBAN device %s offline, re-registering for RT packets", host)
            rt_stream = device._streams.get("Voicemeeter-RTP")
            if rt_stream and hasattr(rt_stream, "register_for_updates"):
                try:
                    await rt_stream.register_for_updates()
                except Exception as err:
                    _LOGGER.warning("Failed to re-register VBAN device %s: %s", host, err)
            else:
                _LOGGER.warning("VBAN device %s has no active RT stream to register", host)

    # Use 30s interval to align with standard HA scan intervals
    vban_data.watchdogs[entry.entry_id] = async_track_time_interval(
        hass, check_connection, timedelta(seconds=30)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --- Global Service: send_raw_command (Target by Device) ---

    async def handle_send_raw_command(call: ServiceCall):
        command = call.data.get("command")
        _LOGGER.info("Service: send_raw_command called with %s", command)
        
        # Use proper TargetSelection to handle device_id, area_id, etc.
        selection = TargetSelection(call.data)
        referenced = async_extract_referenced_entity_ids(hass, selection)
        
        target_remotes = set()
        
        # If no target specified, broadcast to all
        if not selection.has_any_target:
            target_remotes = set(vban_data.remotes.values())
        else:
            # Map referenced devices/entities to our remotes
            # referenced.referenced_devices contains all device IDs (direct or from area/label)
            for d_id in referenced.referenced_devices:
                dev_reg = dr.async_get(hass)
                d_entry = dev_reg.async_get(d_id)
                if d_entry:
                    for config_id in d_entry.config_entries:
                        if config_id in vban_data.remotes:
                            target_remotes.add(vban_data.remotes[config_id])

        if not target_remotes:
            _LOGGER.warning("No VoiceMeeter hosts found for targeted devices")
            return

        for r in target_remotes:
            await r.send_command(command)

    if not hass.services.has_service(DOMAIN, "send_raw_command"):
        hass.services.async_register(DOMAIN, "send_raw_command", handle_send_raw_command, 
            schema=vol.Schema({
                vol.Required("command"): str,
                vol.Optional("entity_id"): cv.entity_ids,
                vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("area_id"): vol.All(cv.ensure_list, [cv.string]),
            }))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    vban_data: VBANData = hass.data[DOMAIN]
    remote = vban_data.remotes.pop(entry.entry_id)
    await remote.stop()

    if unsub_watchdog := vban_data.watchdogs.pop(entry.entry_id, None):
        unsub_watchdog()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        listen_port = DEFAULT_PORT
        vban_data.ref_counts[listen_port] -= 1
        if vban_data.ref_counts[listen_port] <= 0:
            client = vban_data.clients.pop(listen_port)
            client.close()
            vban_data.ref_counts.pop(listen_port)

    return unload_ok
