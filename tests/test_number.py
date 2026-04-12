"""Test VBAN VoiceMeeter numbers."""
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, device_registry as dr

from custom_components.vban.const import DOMAIN
from aiovban.enums import VoicemeeterType

from pytest_homeassistant_custom_component.common import MockConfigEntry

async def test_numbers(hass: HomeAssistant, mock_vban_client, mock_voicemeeter_remote) -> None:
    """Test number entities are created."""
    # Setup mock remote with one strip
    mock_strip = MagicMock()
    mock_strip.index = 0
    mock_strip.label = "Mic"
    mock_strip.gain = -10.0
    mock_strip.set_gain = AsyncMock()

    mock_voicemeeter_remote.strips = [mock_strip]
    mock_voicemeeter_remote.buses = []
    mock_voicemeeter_remote._all_strips = [mock_strip]
    mock_voicemeeter_remote._all_buses = []
    mock_voicemeeter_remote.type = VoicemeeterType.VOICEMEETER

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

    # Pre-create the host device
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "1.1.1.1")},
        name="VoiceMeeter (1.1.1.1)",
    )

    with patch("custom_components.vban.AsyncVBANClient", return_value=mock_vban_client), \
         patch("custom_components.vban.VoicemeeterRemote", return_value=mock_voicemeeter_remote):
        
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # Check registry
    ent_reg = er.async_get(hass)
    # ID is derived from device name "Strip 1 (Mic)" and entity name "Gain"
    entry = ent_reg.async_get("number.strip_1_mic_gain")
    assert entry
    assert hass.states.get("number.strip_1_mic_gain").state == "-10.0"

    # Test setting value
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.strip_1_mic_gain", "value": -5.5}, blocking=True
    )
    mock_strip.set_gain.assert_called_once_with(-5.5)
