"""VBAN Media Player entity."""
from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import Any

import miniaudio
from homeassistant.components import ffmpeg
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICE, CONF_STREAM_NAME
from custom_components.vban.const import DOMAIN as VBAN_DOMAIN, CONF_HOST, CONF_PORT

_LOGGER = logging.getLogger(__name__)

# VBAN Constants
VBAN_PROTOCOL_AUDIO = 0x00
SAMPLE_RATE_48000 = 3
BIT_RESOLUTION_INT16 = 1
CODEC_PCM = 0x00

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VBAN Media Player from a config entry."""
    vban_entry_id = entry.data[CONF_DEVICE]
    vban_entry = hass.config_entries.async_get_entry(vban_entry_id)
    
    if not vban_entry:
        _LOGGER.error("VBAN device not found for media player")
        return

    host = vban_entry.data[CONF_HOST]
    port = vban_entry.options.get(CONF_PORT, vban_entry.data.get(CONF_PORT, 6980))
    stream_name = entry.data[CONF_STREAM_NAME]

    async_add_entities([VBANMediaPlayer(hass, entry, host, port, stream_name)])

class VBANMediaPlayer(MediaPlayerEntity):
    """Representation of a VBAN Media Player."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA |
        MediaPlayerEntityFeature.STOP
    )

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
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

        # Device Info links it to the main VBAN device
        self._attr_device_info = DeviceInfo(
            identifiers={(VBAN_DOMAIN, f"{host}_{port}")},
        )

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the player."""
        return self._state

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play media."""
        await self.async_stop()
        self._state = MediaPlayerState.PLAYING
        self.async_write_ha_state()
        
        self._current_task = asyncio.create_task(self._stream_audio(media_id))

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

    async def _stream_audio(self, media_id: str) -> None:
        """Background task to stream audio via VBAN."""
        try:
            # VBAN Packet Header setup
            # 4 bytes: 'VBAN'
            # 1 byte: Sample Rate (0x40 | index) - for audio, bit 5-7 is 000
            # 1 byte: Samples per frame - 1 (e.g. 256 samples = 0xFF)
            # 1 byte: Channels - 1 (e.g. 2 channels = 0x01)
            # 1 byte: Format (Bit 0-2: BitResolution, Bit 3: Unused, Bit 4-7: Codec)
            # 16 bytes: Stream Name (padded with nulls)
            # 4 bytes: Frame Counter (incremented for each packet)
            
            sr_byte = SAMPLE_RATE_48000 # 48000Hz index is 3
            samples_per_packet = 256
            sp_byte = samples_per_packet - 1
            ch_byte = 1 # Stereo (2-1)
            fmt_byte = BIT_RESOLUTION_INT16 | (CODEC_PCM << 4)
            
            stream_name_bytes = self._stream_name.encode('utf-8')[:16].ljust(16, b'\x00')
            
            header_prefix = b'VBAN' + struct.pack('BBBB', sr_byte, sp_byte, ch_byte, fmt_byte) + stream_name_bytes
            
            # Using miniaudio for decoding/resampling as fallback or primary
            # (In a real implementation we might prefer ffmpeg if available)
            _LOGGER.debug("Starting miniaudio stream for %s", media_id)
            
            # miniaudio.stream_any can take a filename or URL
            stream = miniaudio.stream_any(
                media_id,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=2,
                sample_rate=48000
            )
            
            frame_counter = 0
            
            # Create a socket for sending
            # In a real integration, we'd reuse the one from the core vban component
            # but for this barebones demo, a new UDP socket is fine.
            loop = asyncio.get_running_loop()
            transport, _ = await loop.create_datagram_endpoint(
                lambda: asyncio.DatagramProtocol(),
                remote_addr=(self._host, self._port)
            )
            
            try:
                start_time = time.monotonic()
                frames_sent = 0
                
                # Each VBAN packet will be 256 samples * 2 channels * 2 bytes = 1024 bytes payload
                chunk_size = samples_per_packet * 2 * 2
                
                for chunk in stream:
                    # miniaudio yields bytes. We need to chunk them to our samples_per_packet
                    for i in range(0, len(chunk), chunk_size):
                        payload = chunk[i:i+chunk_size]
                        if len(payload) < chunk_size:
                            # If the last chunk is small, pad it with silence
                            payload = payload.ljust(chunk_size, b'\x00')
                        
                        packet = header_prefix + struct.pack('<I', frame_counter) + payload
                        transport.sendto(packet)
                        
                        frame_counter = (frame_counter + 1) % 0xFFFFFFFF
                        frames_sent += samples_per_packet
                        
                        # Pacing: Calculate when this packet should be sent
                        # target_time = start_time + (total_samples / sample_rate)
                        expected_time = start_time + (frames_sent / 48000)
                        now = time.monotonic()
                        sleep_time = expected_time - now
                        
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)
                        elif sleep_time < -0.1:
                            # We're lagging, don't sleep
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
