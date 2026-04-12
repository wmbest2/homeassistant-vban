# Home Assistant VBAN VoiceMeeter Integration

This integration allows you to control VoiceMeeter via VBAN from Home Assistant.

## Screenshots

### Top Level Device
![Top level device showing VoiceMeeter components](docs/top_level_device.png)
The top-level device view provides a comprehensive overview of all your VoiceMeeter strips, buses, and global controls directly within Home Assistant. It's designed to give you a quick "at-a-glance" status of your entire audio setup.

### Single Strip View
![Single strip view with ergonomic controls](docs/single_strip.png)
The single strip view offers precise, ergonomic control over individual inputs and outputs. Adjust gain levels with sliders and toggle solo or mute states with a single tap, making it ideal for real-time audio management.

## Features

- **Bidirectional Control:** Sync mute, solo, and gain levels between Home Assistant and VoiceMeeter.
- **VBAN Audio Streaming:** Stream audio (TTS, music, alerts) directly to VoiceMeeter using the VBAN protocol.
- **High Efficiency:** Uses `miniaudio` for native, low-latency audio decoding and resampling without requiring external binaries like FFmpeg.
- **Ergonomic UI:** Automatically generates interactive controls for all your VoiceMeeter strips and buses.
- **Global Commands:** Support for Restart Engine and Show/Hide Window commands.
- **Real-time Updates:** Stay in sync with VoiceMeeter via VBAN RT packets.

## Installation

### HACS (Recommended)
1. Add this repository as a custom repository in HACS.
2. Search for "VBAN VoiceMeeter" and click Install.
3. Restart Home Assistant.

## Configuration

1. In Home Assistant, go to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **VBAN VoiceMeeter**.
3. Enter your VoiceMeeter host IP and port (default is 6980).
4. Configure your **Command Stream Name** (must match the 'VBAN Text Incoming Stream' in VoiceMeeter).
5. Configure your **Media Stream Name** (must match a 'VBAN Audio Incoming Stream' in VoiceMeeter).
