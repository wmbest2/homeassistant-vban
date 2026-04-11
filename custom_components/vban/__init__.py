"""The VBAN VoiceMeeter integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from dataclasses import dataclass
import logging
from typing import Dict, Callable, Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.target import async_extract_referenced_entity_ids, TargetSelection

from aiovban.asyncio import AsyncVBANClient, VoicemeeterRemote

from .const import DOMAIN, CONF_COMMAND_STREAM, DEFAULT_PORT
from .coordinator import VBANUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.BUTTON,
]

# Shared client state across all entries
class VBANSharedState:
    """Storage for shared VBAN clients."""
    def __init__(self) -> None:
        self.clients: Dict[int, AsyncVBANClient] = {}
        self.ref_counts: Dict[int, int] = {}

@dataclass
class VBANRuntimeData:
    """Data for a VBAN config entry."""
    remote: VoicemeeterRemote
    coordinator: VBANUpdateCoordinator
    unsub_watchdog: Callable[[], None]

type VBANConfigEntry = ConfigEntry[VBANRuntimeData]

async def async_setup_entry(hass: HomeAssistant, entry: VBANConfigEntry) -> bool:
    """Set up VBAN VoiceMeeter from a config entry."""
    host: str = entry.data[CONF_HOST]
    port: int = entry.data[CONF_PORT]
    stream: str = entry.data[CONF_COMMAND_STREAM]
    listen_port: int = DEFAULT_PORT 

    _LOGGER.debug("Initializing VBAN integration for %s:%s", host, port)

    # Use entry.runtime_data for entry-specific data
    # Use hass.data for cross-entry shared state
    shared_state: VBANSharedState = hass.data.setdefault(DOMAIN, VBANSharedState())

    if listen_port not in shared_state.clients:
        client = AsyncVBANClient()
        try:
            await client.listen("0.0.0.0", listen_port)
            shared_state.clients[listen_port] = client
            shared_state.ref_counts[listen_port] = 0
        except Exception as err:
            raise ConfigEntryNotReady(f"Failed to listen on VBAN port {listen_port}: {err}") from err
    
    client = shared_state.clients[listen_port]
    shared_state.ref_counts[listen_port] += 1

    device = await client.register_device(host, port)
    remote = VoicemeeterRemote(device, stream)
    await remote.start()
    
    # Wait for device to identify itself
    attempts = 0
    while not remote.type and attempts < 100:
        await asyncio.sleep(0.1)
        attempts += 1

    coordinator = VBANUpdateCoordinator(hass, remote, host)
    await coordinator._async_setup()

    # --- Online Watchdog (HA Synchronized) ---
    async def check_connection(_now: Any) -> None:
        """Watchdog to re-register for RT packets if device goes offline."""
        if not remote.online:
            _LOGGER.debug("VBAN device %s offline, re-registering for RT packets", host)
            rt_stream = device._streams.get("Voicemeeter-RTP")
            if rt_stream and hasattr(rt_stream, "register_for_updates"):
                try:
                    await rt_stream.register_for_updates()
                except Exception as err:
                    _LOGGER.warning("Failed to re-register VBAN device %s: %s", host, err)

    unsub_watchdog = async_track_time_interval(
        hass, check_connection, timedelta(seconds=30)
    )

    entry.runtime_data = VBANRuntimeData(
        remote=remote,
        coordinator=coordinator,
        unsub_watchdog=unsub_watchdog,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --- Global Service: send_raw_command (Target by Device) ---

    async def handle_send_raw_command(call: ServiceCall) -> None:
        command: str = call.data["command"]
        _LOGGER.info("Service: send_raw_command called with %s", command)
        
        selection = TargetSelection(call.data)
        referenced = async_extract_referenced_entity_ids(hass, selection)
        
        target_remotes = []
        
        if not selection.has_any_target:
            # Broadcast to ALL entries
            for e in hass.config_entries.async_entries(DOMAIN):
                if hasattr(e, "runtime_data"):
                    target_remotes.append(e.runtime_data.remote)
        else:
            for d_id in referenced.referenced_devices:
                dev_reg = dr.async_get(hass)
                d_entry = dev_reg.async_get(d_id)
                if d_entry:
                    for config_id in d_entry.config_entries:
                        e = hass.config_entries.async_get_entry(config_id)
                        if e and e.domain == DOMAIN and hasattr(e, "runtime_data"):
                            target_remotes.append(e.runtime_data.remote)

        if not target_remotes:
            _LOGGER.warning("No VoiceMeeter hosts found for targeted devices")
            return

        for r in target_remotes:
            await r.send_command(command)

    if not hass.services.has_service(DOMAIN, "send_raw_command"):
        hass.services.async_register(
            DOMAIN, 
            "send_raw_command", 
            handle_send_raw_command, 
            schema=vol.Schema({
                vol.Required("command"): cv.string,
                vol.Optional("entity_id"): cv.entity_ids,
                vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("area_id"): vol.All(cv.ensure_list, [cv.string]),
            })
        )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: VBANConfigEntry) -> bool:
    """Unload a config entry."""
    data = entry.runtime_data
    await data.remote.stop()
    data.unsub_watchdog()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        shared_state: VBANSharedState = hass.data[DOMAIN]
        listen_port = DEFAULT_PORT
        shared_state.ref_counts[listen_port] -= 1
        if shared_state.ref_counts[listen_port] <= 0:
            client = shared_state.clients.pop(listen_port)
            client.close()
            shared_state.ref_counts.pop(listen_port)

    return unload_ok
