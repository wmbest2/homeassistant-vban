"""Test VBAN VoiceMeeter init."""
from unittest.mock import patch, MagicMock
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState

from custom_components.vban.const import DOMAIN
from aiovban.enums import VoicemeeterType

from pytest_homeassistant_custom_component.common import MockConfigEntry

async def test_setup_unload_entry(hass: HomeAssistant, mock_vban_client, mock_voicemeeter_remote) -> None:
    """Test setting up and unloading a config entry."""
    # Setup mock device
    mock_device = MagicMock()
    mock_device.address = "1.1.1.1"
    mock_device._streams = {}
    mock_vban_client.register_device.return_value = mock_device
    
    # Setup mock remote
    mock_voicemeeter_remote.type = VoicemeeterType.POTATO
    mock_voicemeeter_remote.strips = []
    mock_voicemeeter_remote.buses = []

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "1.1.1.1",
            "port": 6980,
            "command_stream": "Command1",
        },
        entry_id="test_entry",
    )
    config_entry.add_to_hass(hass)

    with patch("custom_components.vban.AsyncVBANClient", return_value=mock_vban_client), \
         patch("custom_components.vban.VoicemeeterRemote", return_value=mock_voicemeeter_remote):
        
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    # Modern check: runtime_data should exist
    assert config_entry.runtime_data is not None
    assert config_entry.runtime_data.remote == mock_voicemeeter_remote
    
    # Test unload
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    
    assert config_entry.state is ConfigEntryState.NOT_LOADED
