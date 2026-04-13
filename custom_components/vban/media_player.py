"""VBAN Media Player entity."""
from __future__ import annotations

import asyncio
import logging
import struct
import time
import socket
import os
import tempfile
import urllib.request
from typing import Any
import concurrent.futures

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
        self._stop_event = asyncio.Event()

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
        self._stop_event.clear()
        self.async_write_ha_state()
        
        self._current_task = asyncio.create_task(self._stream_audio_wrapper(media_url))

    async def async_stop(self) -> None:
        """Stop playback."""
        self._stop_event.set()
        if self._current_task:
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass
            self._current_task = None
        
        self._state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def _stream_audio_wrapper(self, media_url: str) -> None:
        """Wrapper to run the blocking stream in a thread."""
        loop = asyncio.get_running_loop()
        try:
            with concurrent.futures.ThreadPoolExecutor() as pool:
                await loop.run_in_executor(pool, self._stream_audio_sync, media_url)
        except Exception:
            _LOGGER.exception("Error in VBAN audio stream")
        finally:
            self._state = MediaPlayerState.IDLE
            self.hass.add_job(self.async_write_ha_state)

    def _stream_audio_sync(self, media_url: str) -> None:
        """Synchronous audio streaming to avoid asyncio timing issues."""
        temp_file = None
        try:
            # If it's a URL, download to a temporary file first for miniaudio
            if media_url.startswith(("http://", "https://")):
                _LOGGER.debug("Downloading media to temporary file")
                with urllib.request.urlopen(media_url) as response:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as tmp:
                        tmp.write(response.read())
                        temp_file = tmp.name
                stream_source = temp_file
            else:
                stream_source = media_url

            # VBAN Packet Header setup
            sub_byte = VBAN_PROTOCOL_AUDIO | SAMPLE_RATE_48000
            samples_per_packet = 128 # Reduced from 256 for lower latency/jitter
            sp_byte = samples_per_packet - 1
            ch_byte = 1 # Stereo (2-1)
            fmt_byte = BIT_RESOLUTION_INT16 | (CODEC_PCM << 4)
            
            stream_name_bytes = self._stream_name.encode('utf-8')[:16].ljust(16, b'\x00')
            header_prefix = b'VBAN' + struct.pack('BBBB', sub_byte, sp_byte, ch_byte, fmt_byte) + stream_name_bytes
            
            _LOGGER.debug("Starting VBAN stream to %s:%s", self._host, self._port)
            
            stream = miniaudio.stream_file(
                stream_source,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=2,
                sample_rate=48000
            )
            
            frame_counter = 0
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            try:
                # Pre-buffer: load some data before starting
                time.sleep(1.0)
                start_time = time.perf_counter()
                frames_sent = 0
                chunk_size = samples_per_packet * 2 * 2 # 2 channels * 2 bytes
                
                for chunk in stream:
                    if self._stop_event.is_set():
                        break
                    
                    for i in range(0, len(chunk), chunk_size):
                        if self._stop_event.is_set():
                            break
                            
                        payload = chunk[i:i+chunk_size]
                        if len(payload) < chunk_size:
                            payload = payload.ljust(chunk_size, b'\x00')
                        
                        packet = header_prefix + struct.pack('<I', frame_counter) + payload
                        sock.sendto(packet, (self._host, self._port))
                        
                        frame_counter = (frame_counter + 1) % 0xFFFFFFFF
                        frames_sent += samples_per_packet
                        
                        # High precision pacing
                        expected_time = start_time + (frames_sent / 48000)
                        now = time.perf_counter()
                        sleep_time = expected_time - now
                        
                        if sleep_time > 0:
                            time.sleep(sleep_time)
                        elif sleep_time < -0.05:
                            # We're lagging, reset start_time to current to avoid catch-up burst
                            start_time = now - (frames_sent / 48000)
                
                _LOGGER.debug("Finished VBAN stream: %d packets sent", frame_counter)
                            
            finally:
                sock.close()
                
        except Exception:
            _LOGGER.exception("Error in VBAN audio stream sync")
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
