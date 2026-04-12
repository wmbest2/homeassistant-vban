"""VBAN Media Player entity."""
from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import Any

import miniaudio
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)
from homeassistant.components.media_source import async_browse_media, async_resolve_media
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_HOST, CONF_PORT, CONF_MEDIA_STREAM, DEFAULT_PORT, DEFAULT_MEDIA_STREAM
from . import VBANConfigEntry

_LOGGER = logging.getLogger(__name__)

# VBAN Constants
VBAN_PROTOCOL_AUDIO = 0x00
SAMPLE_RATE_48000 = 3
BIT_RESOLUTION_INT16 = 1
CODEC_PCM = 0x00

async def async_setup_entry(
    hass: HomeAssistant,
    entry: VBANConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VBAN Media Player from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.options.get(CONF_PORT, entry.data.get(CONF_PORT, DEFAULT_PORT))
    stream_name = entry.options.get(CONF_MEDIA_STREAM, entry.data.get(CONF_MEDIA_STREAM, DEFAULT_MEDIA_STREAM))

    async_add_entities([VBANMediaPlayer(hass, entry, host, port, stream_name)])

class VBANMediaPlayer(MediaPlayerEntity):
    """Representation of a VBAN Media Player."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA |
        MediaPlayerEntityFeature.STOP |
        MediaPlayerEntityFeature.BROWSE_MEDIA
    )

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VBANConfigEntry,
        host: str,
        port: int,
        stream_name: str,
    ) -> None:
        """Initialize the media player."""
        self.hass = hass
        self._entry = entry
        self._host = host
        self._port = port
        self._stream_name = stream_name
        self._attr_name = f"VBAN Media ({stream_name})"
        self._attr_unique_id = f"{entry.entry_id}_media_player"
        self._state = MediaPlayerState.IDLE
        self._current_task: asyncio.Task | None = None

        # Link to the main VBAN device
        data = entry.runtime_data.remote.device.connected_application_data
        host_id = data.host_name if data and data.host_name else host
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, host_id)},
        )

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the player."""
        return self._state

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Implement the browsing of media."""
        return await async_browse_media(self.hass, media_content_id, content_filter=lambda item: item.media_content_type.startswith("audio/"))

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play media."""
        _LOGGER.debug("Play media requested: %s (%s)", media_id, media_type)
        
        # Resolve media source if necessary
        if media_id.startswith("media-source://"):
            media_source = await async_resolve_media(self.hass, media_id, self.entity_id)
            media_url = media_source.url
        else:
            media_url = media_id

        media_url = async_process_play_media_url(self.hass, media_url)

        await self.async_stop()
        self._state = MediaPlayerState.PLAYING
        self.async_write_ha_state()
        
        self._current_task = asyncio.create_task(self._stream_audio(media_url))

    async def async_stop(self) -> None:
        """Stop playback."""
        if self._current_task:
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass
            self._current_task = None
        
        self._state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def _stream_audio(self, media_url: str) -> None:
        """Background task to stream audio via VBAN."""
        try:
            # VBAN Packet Header setup
            # subprotocol (bits 5-7) | data (bits 0-4)
            # For audio, subprotocol is 0x00. Sample rate index is bits 0-4.
            sub_byte = VBAN_PROTOCOL_AUDIO | SAMPLE_RATE_48000
            
            samples_per_packet = 256
            sp_byte = samples_per_packet - 1
            ch_byte = 1 # Stereo (2-1)
            fmt_byte = BIT_RESOLUTION_INT16 | (CODEC_PCM << 4)
            
            stream_name_bytes = self._stream_name.encode('utf-8')[:16].ljust(16, b'\x00')
            
            header_prefix = b'VBAN' + struct.pack('BBBB', sub_byte, sp_byte, ch_byte, fmt_byte) + stream_name_bytes
            
            _LOGGER.debug("Starting miniaudio stream for %s to %s:%s", media_url, self._host, self._port)
            
            # miniaudio.stream_any can take a filename or URL
            stream = miniaudio.stream_any(
                media_url,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=2,
                sample_rate=48000
            )
            
            frame_counter = 0
            
            loop = asyncio.get_running_loop()
            transport, _ = await loop.create_datagram_endpoint(
                lambda: asyncio.DatagramProtocol(),
                remote_addr=(self._host, self._port)
            )
            
            try:
                start_time = time.monotonic()
                frames_sent = 0
                chunk_size = samples_per_packet * 2 * 2
                
                for chunk in stream:
                    for i in range(0, len(chunk), chunk_size):
                        payload = chunk[i:i+chunk_size]
                        if len(payload) < chunk_size:
                            payload = payload.ljust(chunk_size, b'\x00')
                        
                        packet = header_prefix + struct.pack('<I', frame_counter) + payload
                        transport.sendto(packet)
                        
                        frame_counter = (frame_counter + 1) % 0xFFFFFFFF
                        frames_sent += samples_per_packet
                        
                        expected_time = start_time + (frames_sent / 48000)
                        now = time.monotonic()
                        sleep_time = expected_time - now
                        
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)
                        elif sleep_time < -0.1:
                            pass
                            
            finally:
                transport.close()
                
        except asyncio.CancelledError:
            _LOGGER.debug("Audio stream cancelled")
        except Exception:
            _LOGGER.exception("Error in VBAN audio stream")
        finally:
            self._state = MediaPlayerState.IDLE
            self.async_write_ha_state()
