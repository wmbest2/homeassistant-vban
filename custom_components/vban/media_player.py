"""VBAN Media Player entity."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import urllib.request
import threading
import time
from typing import Any

import miniaudio
from aiovban import VBANSampleRate
from aiovban.packet import VBANPacket, BytesBody
from aiovban.packet.headers.audio import VBANAudioHeader, BitResolution, Codec
from aiovban.asyncio.streams import BufferedVBANOutgoingStream
from aiovban.asyncio.util import BackPressureStrategy

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
from homeassistant.util import dt as dt_util

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
        self._vban_stream: BufferedVBANOutgoingStream | None = None
        
        # Thread safety & State
        self._stop_event = threading.Event()
        self._stream_lock = threading.Lock()
        
        # Playback tracking
        self._media_duration: float | None = None
        self._media_position: float | None = None
        self._media_position_updated_at: dt_util.datetime | None = None

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

    @property
    def media_duration(self) -> float | None:
        """Duration of currently playing media in seconds."""
        return self._media_duration

    @property
    def media_position(self) -> float | None:
        """Position of currently playing media in seconds."""
        return self._media_position

    @property
    def media_position_updated_at(self) -> dt_util.datetime | None:
        """When was the position of the current playing media valid."""
        return self._media_position_updated_at

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

        # 1. Signal any existing thread to stop
        await self.async_media_stop()
        
        # 2. Reset state for new playback
        self._state = MediaPlayerState.PLAYING
        self._stop_event.clear()
        self._media_duration = None
        self._media_position = 0
        self._media_position_updated_at = dt_util.utcnow()
        self.async_write_ha_state()
        
        # 3. Start new playback task
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
        self._media_position = None
        self._media_duration = None
        self.async_write_ha_state()

    async def _async_stream_media(self, media_url: str) -> None:
        """Asynchronous task to manage media streaming."""
        temp_file = None
        loop = asyncio.get_running_loop()
        
        try:
            # 1. Download
            if media_url.startswith(("http://", "https://")):
                def download():
                    try:
                        with urllib.request.urlopen(media_url) as response:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".tmp") as tmp:
                                tmp.write(response.read())
                                return tmp.name
                    except Exception:
                        _LOGGER.exception("Failed to download media")
                        return None
                
                temp_file = await loop.run_in_executor(None, download)
                if not temp_file: return
                stream_source = temp_file
            else:
                stream_source = media_url

            # 2. Metadata Discovery (Duration)
            def get_info():
                try:
                    with miniaudio.File(stream_source) as f:
                        return f.duration
                except Exception:
                    return None
            
            self._media_duration = await loop.run_in_executor(None, get_info)

            # 3. Setup Persistent Stream
            if not self._vban_stream:
                device = self._entry.runtime_data.remote.device
                self._vban_stream = BufferedVBANOutgoingStream(
                    name=self._stream_name,
                    _client=device._client,
                    buffer_size=500,
                    back_pressure_strategy=BackPressureStrategy.BLOCK
                )
                await self._vban_stream.connect(self._host, self._port)

            # 4. Decoding and Streaming Worker
            def worker():
                if not self._stream_lock.acquire(timeout=5.0):
                    _LOGGER.warning("Could not acquire stream lock")
                    return

                try:
                    _LOGGER.debug("Starting VBAN worker thread for %s", stream_source)
                    stream = miniaudio.stream_file(
                        stream_source,
                        output_format=miniaudio.SampleFormat.SIGNED16,
                        nchannels=2,
                        sample_rate=48000
                    )
                    
                    samples_per_packet = 256
                    bytes_per_packet = samples_per_packet * 2 * 2
                    buffer = b""
                    total_samples_sent = 0
                    start_time = time.perf_counter()
                    last_ha_update = 0

                    for chunk in stream:
                        if self._stop_event.is_set():
                            break
                        
                        buffer += chunk
                        while len(buffer) >= bytes_per_packet:
                            if self._stop_event.is_set():
                                break
                                
                            payload = buffer[:bytes_per_packet]
                            buffer = buffer[bytes_per_packet:]
                            
                            packet = VBANPacket(
                                header=VBANAudioHeader(
                                    streamname=self._stream_name,
                                    sample_rate=VBANSampleRate.RATE_48000,
                                    codec=Codec.PCM,
                                    channels=2,
                                    bit_resolution=BitResolution.INT16,
                                    samples_per_frame=samples_per_packet,
                                ),
                                body=BytesBody(payload)
                            )
                            
                            self._vban_stream.send_packet_threadsafe(packet, loop)

                            total_samples_sent += samples_per_packet
                            
                            # High-precision pacing
                            now = time.perf_counter()
                            expected_time = start_time + (total_samples_sent / 48000)
                            sleep_time = expected_time - now
                            
                            if sleep_time > 0:
                                time.sleep(sleep_time)
                            elif sleep_time < -0.1:
                                start_time = now - (total_samples_sent / 48000)
                            
                            # Update HA position every second
                            if now - last_ha_update > 1.0:
                                self._media_position = total_samples_sent / 48000
                                self._media_position_updated_at = dt_util.utcnow()
                                self.hass.add_job(self.async_write_ha_state)
                                last_ha_update = now
                                
                except Exception:
                    _LOGGER.exception("Error in VBAN worker thread")
                finally:
                    self._stream_lock.release()
                    _LOGGER.debug("VBAN worker thread finished")

            await loop.run_in_executor(None, worker)

        except asyncio.CancelledError:
            self._stop_event.set()
        except Exception:
            _LOGGER.exception("Error in VBAN media player task")
        finally:
            if temp_file and os.path.exists(temp_file):
                try: os.remove(temp_file)
                except: pass
            
            if not self._stop_event.is_set():
                self._state = MediaPlayerState.IDLE
                self._media_position = None
                self.hass.add_job(self.async_write_ha_state)

    async def will_remove_from_hass(self) -> None:
        """Cleanup when entity is removed."""
        await self.async_media_stop()
        if self._vban_stream and self._vban_stream.send_task:
            self._vban_stream.send_task.cancel()
        await super().will_remove_from_hass()
