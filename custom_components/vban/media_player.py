"""VBAN Media Player entity."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import urllib.request
import threading
import time
import struct
from typing import Any

import miniaudio
from aiovban import VBANSampleRate
from aiovban.packet import VBANPacket, BytesBody
from aiovban.packet.headers.audio import VBANAudioHeader, BitResolution, Codec

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
        self._stream_task: asyncio.Task | None = None
        self._stop_event = threading.Event()

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

        await self.async_media_stop()
        self._state = MediaPlayerState.PLAYING
        self._stop_event.clear()
        self.async_write_ha_state()
        
        self._stream_task = asyncio.create_task(self._async_stream_media(media_url))

    async def async_media_stop(self) -> None:
        """Stop playback."""
        self._stop_event.set()
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        
        self._state = MediaPlayerState.IDLE
        self.async_write_ha_state()

    async def _async_stream_media(self, media_url: str) -> None:
        """Asynchronous task to stream media using direct client datagrams."""
        # Define constants for our VBAN format
        SAMPLE_RATE = 48000
        CHANNELS = 2
        SAMPLES_PER_PACKET = 256
        BYTES_PER_PACKET = SAMPLES_PER_PACKET * CHANNELS * 2 # 16-bit PCM

        _LOGGER.debug("Starting direct VBAN stream to %s:%s", self._host, self._port)

        device = self._entry.runtime_data.remote.device
        client = device._client
        loop = asyncio.get_running_loop()
        
        def download_decode_and_stream():
            temp_file = None
            try:
                # 1. Download (moved inside thread to avoid blocking loop)
                if media_url.startswith(("http://", "https://")):
                    try:
                        _LOGGER.debug("Downloading media to temporary file in worker thread")
                        with urllib.request.urlopen(media_url) as response:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as tmp:
                                tmp.write(response.read())
                                temp_file = tmp.name
                        stream_source = temp_file
                    except Exception:
                        _LOGGER.exception("Failed to download media in worker thread")
                        return
                else:
                    stream_source = media_url

                # 2. Decode and Stream
                try:
                    stream = miniaudio.stream_file(
                        stream_source,
                        output_format=miniaudio.SampleFormat.SIGNED16,
                        nchannels=CHANNELS,
                        sample_rate=SAMPLE_RATE
                    )
                except Exception:
                    _LOGGER.exception("Failed to open miniaudio stream")
                    return
                
                buffer = b""
                frames_sent = 0
                frame_counter = 0
                start_time = time.perf_counter()

                # Header is static except for frame counter
                header = VBANAudioHeader(
                    streamname=self._stream_name,
                    sample_rate=VBANSampleRate.RATE_48000,
                    codec=Codec.PCM,
                    channels=CHANNELS,
                    bit_resolution=BitResolution.INT16,
                    samples_per_frame=SAMPLES_PER_PACKET,
                )

                for chunk in stream:
                    if self._stop_event.is_set():
                        break
                    
                    buffer += chunk
                    while len(buffer) >= BYTES_PER_PACKET:
                        if self._stop_event.is_set():
                            break
                            
                        payload = buffer[:BYTES_PER_PACKET]
                        buffer = buffer[BYTES_PER_PACKET:]
                        
                        header.framecount = frame_counter
                        packet_bytes = header.pack() + payload
                        
                        # Send directly via client listener socket
                        client.send_datagram(packet_bytes, (self._host, self._port))

                        frame_counter = (frame_counter + 1) % 0xFFFFFFFF
                        frames_sent += SAMPLES_PER_PACKET
                        
                        # High-precision pacing
                        now = time.perf_counter()
                        expected_time = start_time + (frames_sent / SAMPLE_RATE)
                        sleep_time = expected_time - now
                        
                        if sleep_time > 0:
                            time.sleep(sleep_time)
                        elif sleep_time < -0.1:
                            start_time = now - (frames_sent / SAMPLE_RATE)
                            
            except Exception:
                _LOGGER.exception("Error in VBAN streaming thread")
            finally:
                if temp_file and os.path.exists(temp_file):
                    try: os.remove(temp_file)
                    except: pass

        await loop.run_in_executor(None, download_decode_and_stream)
        _LOGGER.debug("VBAN stream finished")
        self._state = MediaPlayerState.IDLE
        self.hass.add_job(self.async_write_ha_state)

    async def async_stop(self) -> None:
        """HA stop service calls this."""
        await self.async_media_stop()
