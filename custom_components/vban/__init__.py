"""The VBAN VoiceMeeter integration."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady

from aiovban.asyncio import AsyncVBANClient, VoicemeeterRemote

from .const import DOMAIN, CONF_HOST, CONF_PORT, CONF_COMMAND_STREAM

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.BUTTON,
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VBAN VoiceMeeter from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    stream = entry.data[CONF_COMMAND_STREAM]

    _LOGGER.info("Initializing VBAN integration for %s:%s", host, port)

    client = AsyncVBANClient()
    try:
        _LOGGER.debug("Starting VBAN client listener on 0.0.0.0:6980")
        await client.listen("0.0.0.0", 6980)
    except Exception as err:
        _LOGGER.error("Failed to start VBAN listener: %s", err)
        raise ConfigEntryNotReady(f"Failed to listen on VBAN port: {err}") from err

    _LOGGER.debug("Registering device %s:%s", host, port)
    device = await client.register_device(host, port)
    
    _LOGGER.debug("Subscribing to RT packets for %s", host)
    await device.rt_stream(update_interval=0xFF)
    
    remote = VoicemeeterRemote(device, stream)
    
    _LOGGER.info("Waiting for VoiceMeeter topology discovery for %s...", host)
    attempts = 0
    while not remote.type and attempts < 100: # Increase to 10s timeout
        await asyncio.sleep(0.1)
        attempts += 1
        if attempts % 20 == 0:
            _LOGGER.debug("Still waiting for discovery (%s/100)...", attempts)

    if not remote.type:
        _LOGGER.error("Timed out waiting for VoiceMeeter RT packet from %s. Check VBAN Outgoing configuration.", host)
        # We continue anyway, but entities might not be created correctly
    else:
        _LOGGER.info("Discovered VoiceMeeter %s (%s) at %s", remote.type.name, remote.version, host)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "remote": remote,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_send_raw_command(call: ServiceCall):
        command = call.data.get("command")
        _LOGGER.debug("Service call send_raw_command: %s", command)
        await remote.send_command(command)

    async def handle_set_gain(call: ServiceCall):
        kind, index, gain = call.data.get("kind"), call.data.get("index"), call.data.get("gain")
        _LOGGER.debug("Service call set_gain: %s[%s]=%s", kind, index, gain)
        obj = remote.strips[index] if kind == "strip" else remote.buses[index]
        await obj.set_gain(gain)

    async def handle_set_mute(call: ServiceCall):
        kind, index, mute = call.data.get("kind"), call.data.get("index"), call.data.get("mute")
        _LOGGER.debug("Service call set_mute: %s[%s]=%s", kind, index, mute)
        obj = remote.strips[index] if kind == "strip" else remote.buses[index]
        await obj.set_mute(mute)

    hass.services.async_register(DOMAIN, "send_raw_command", handle_send_raw_command)
    hass.services.async_register(DOMAIN, "set_gain", handle_set_gain)
    hass.services.async_register(DOMAIN, "set_mute", handle_set_mute)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading VBAN integration for %s", entry.data[CONF_HOST])
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        data["client"].close()
    return unload_ok
