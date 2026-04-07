"""The VBAN VoiceMeeter integration."""
import asyncio
import logging
from typing import Dict

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_platform, entity_registry as er, device_registry as dr
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.target import async_extract_referenced_entity_ids

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

    # --- Targeted Service Handlers ---

    async def get_remotes_for_call(call: ServiceCall):
        """Extract remotes targeted by the service call."""
        # Fix: Pass call.data, not the ServiceCall object
        referenced = async_extract_referenced_entity_ids(hass, call.data)
        target_remotes = set()
        
        # 1. Check direct device_ids (from service target selector)
        if "device_id" in call.data and call.data["device_id"]:
            dev_reg = dr.async_get(hass)
            device_ids = call.data["device_id"]
            if isinstance(device_ids, str):
                device_ids = [device_ids]
            for d_id in device_ids:
                d_entry = dev_reg.async_get(d_id)
                if d_entry:
                    for config_id in d_entry.config_entries:
                        if config_id in vban_data.remotes:
                            target_remotes.add(vban_data.remotes[config_id])

        # 2. Check entity_ids (includes those from area_id)
        all_ids = referenced.referenced | referenced.indirectly_referenced
        if all_ids:
            ent_reg = er.async_get(hass)
            for entity_id in all_ids:
                ent_entry = ent_reg.async_get(entity_id)
                if ent_entry and ent_entry.platform == DOMAIN:
                    if ent_entry.config_entry_id in vban_data.remotes:
                        target_remotes.add(vban_data.remotes[ent_entry.config_entry_id])
        
        return target_remotes

    async def handle_send_raw_command(call: ServiceCall):
        command = call.data.get("command")
        targets = await get_remotes_for_call(call)
        if not targets:
            _LOGGER.warning("No VoiceMeeter devices targeted for send_raw_command")
            return
        for r in targets:
            await r.send_command(command)

    async def get_objs_for_call(call: ServiceCall):
        """Extract specific strip/bus objects targeted by entity_id."""
        # Fix: Pass call.data, not the ServiceCall object
        referenced = async_extract_referenced_entity_ids(hass, call.data)
        all_ids = referenced.referenced | referenced.indirectly_referenced
        
        target_objs = []
        ent_reg = er.async_get(hass)
        for entity_id in all_ids:
            ent_entry = ent_reg.async_get(entity_id)
            if ent_entry and ent_entry.platform == DOMAIN:
                remote = vban_data.remotes.get(ent_entry.config_entry_id)
                if not remote: continue
                
                parts = ent_entry.unique_id.split("_")
                if len(parts) >= 3:
                    kind = parts[1]
                    index = int(parts[2])
                    obj = remote._all_strips[index] if kind == "strip" else remote._all_buses[index]
                    target_objs.append(obj)
        return target_objs

    async def handle_set_gain(call: ServiceCall):
        gain = call.data.get("gain")
        objs = await get_objs_for_call(call)
        if not objs:
            _LOGGER.warning("No VoiceMeeter entities targeted for set_gain")
            return
        for obj in objs:
            await obj.set_gain(gain)

    async def handle_set_mute(call: ServiceCall):
        mute = call.data.get("mute")
        objs = await get_objs_for_call(call)
        if not objs:
            _LOGGER.warning("No VoiceMeeter entities targeted for set_mute")
            return
        for obj in objs:
            await obj.set_mute(mute)

    if not hass.services.has_service(DOMAIN, "send_raw_command"):
        hass.services.async_register(DOMAIN, "send_raw_command", handle_send_raw_command, 
            schema=vol.Schema({
                vol.Required("command"): str,
                vol.Optional("entity_id"): cv.entity_ids,
                vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("area_id"): vol.All(cv.ensure_list, [cv.string]),
            }))
            
        hass.services.async_register(DOMAIN, "set_gain", handle_set_gain, 
            schema=vol.Schema({
                vol.Required("gain"): vol.Coerce(float),
                vol.Optional("entity_id"): cv.entity_ids,
                vol.Optional("device_id"): vol.All(cv.ensure_list, [cv.string]),
                vol.Optional("area_id"): vol.All(cv.ensure_list, [cv.string]),
            }))
            
        hass.services.async_register(DOMAIN, "set_mute", handle_set_mute, 
            schema=vol.Schema({
                vol.Required("mute"): bool,
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

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        listen_port = DEFAULT_PORT
        vban_data.ref_counts[listen_port] -= 1
        if vban_data.ref_counts[listen_port] <= 0:
            client = vban_data.clients.pop(listen_port)
            client.close()
            vban_data.ref_counts.pop(listen_port)

    return unload_ok
