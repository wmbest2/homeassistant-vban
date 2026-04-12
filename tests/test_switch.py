"""Test VBAN VoiceMeeter switches."""
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.helpers import entity_registry as er, device_registry as dr

from custom_components.vban.const import DOMAIN
from aiovban.enums import VoicemeeterType

from pytest_homeassistant_custom_component.common import MockConfigEntry

async def test_switches(hass: HomeAssistant, mock_vban_client, mock_voicemeeter_remote) -> None:
    """Test switch entities are created."""
    # Setup mock remote with one strip and one bus
    mock_strip = MagicMock()
    mock_strip.index = 0
    mock_strip.label = "Mic"
    mock_strip.mute = False
    mock_strip.solo = False
    mock_strip.A1 = True
    mock_strip.A2 = False
    mock_strip.A3 = False
    mock_strip.B1 = False
    mock_strip.B2 = False
    mock_strip.B3 = False
    mock_strip.set_mute = AsyncMock()
    mock_strip.set_solo = AsyncMock()
    
    mock_bus = MagicMock()
    mock_bus.index = 0
    mock_bus.label = "Main"
    mock_bus.mute = True
    mock_bus.set_mute = AsyncMock()

    mock_voicemeeter_remote.strips = [mock_strip]
    mock_voicemeeter_remote.buses = [mock_bus]
    mock_voicemeeter_remote._all_strips = [mock_strip]
    mock_voicemeeter_remote._all_buses = [mock_bus]
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
        identifiers={(DOMAIN, "VM-HOST")},
        name="VoiceMeeter (VM-HOST)",
    )

    with patch("custom_components.vban.AsyncVBANClient", return_value=mock_vban_client), \
         patch("custom_components.vban.VoicemeeterRemote", return_value=mock_voicemeeter_remote):
        
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # Check registry
    ent_reg = er.async_get(hass)
    
    # ID is derived from device name "Strip 1 (Mic)" and entity name "Mute"
    entry = ent_reg.async_get("switch.strip_1_mic_mute")
    assert entry
    assert hass.states.get("switch.strip_1_mic_mute").state == STATE_OFF
    
    # Strip Solo
    entry = ent_reg.async_get("switch.strip_1_mic_solo")
    assert entry
    
    # Bus Mute - Device name is "A1 (Main)"
    entry = ent_reg.async_get("switch.a1_main_mute")
    assert entry
    assert hass.states.get("switch.a1_main_mute").state == STATE_ON

    # Test toggling
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.strip_1_mic_mute"}, blocking=True
    )
    mock_strip.set_mute.assert_called_once_with(True)
