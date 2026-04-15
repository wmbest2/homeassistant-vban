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

async def test_advanced_switches_disabled(hass: HomeAssistant, mock_vban_client, mock_voicemeeter_remote) -> None:
    """Test advanced switches are disabled by default."""
    mock_strip = MagicMock()
    mock_strip.index = 0
    mock_strip.label = "Mic"
    mock_strip.mute = False
    mock_strip.solo = False
    mock_strip.eq = False
    mock_strip.mc = False
    
    mock_voicemeeter_remote.strips = [mock_strip]
    mock_voicemeeter_remote.buses = []
    mock_voicemeeter_remote._all_strips = [mock_strip]
    mock_voicemeeter_remote._all_buses = []
    mock_voicemeeter_remote.type = VoicemeeterType.VOICEMEETER

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "1.1.1.1"},
        entry_id="test_entry",
    )
    config_entry.add_to_hass(hass)

    with patch("custom_components.vban.AsyncVBANClient", return_value=mock_vban_client), \
         patch("custom_components.vban.VoicemeeterRemote", return_value=mock_voicemeeter_remote):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    ent_reg = er.async_get(hass)
    
    # EQ should be disabled
    entry = ent_reg.async_get("switch.strip_1_mic_eq")
    assert entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION
    
    # MC should be disabled
    entry = ent_reg.async_get("switch.strip_1_mic_mc")
    assert entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION

async def test_potato_routing(hass: HomeAssistant, mock_vban_client, mock_voicemeeter_remote) -> None:
    """Test Potato routing switches (A4, A5)."""
    mock_strip = MagicMock()
    mock_strip.index = 0
    mock_strip.label = "Mic"
    mock_strip.a1 = True
    mock_strip.a2 = False
    mock_strip.a3 = False
    mock_strip.a4 = False
    mock_strip.a5 = False
    mock_strip.b1 = False
    mock_strip.b2 = False
    mock_strip.b3 = False
    
    mock_voicemeeter_remote.strips = [mock_strip]
    mock_voicemeeter_remote.buses = []
    mock_voicemeeter_remote._all_strips = [mock_strip]
    mock_voicemeeter_remote._all_buses = []
    mock_voicemeeter_remote.type = VoicemeeterType.POTATO

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "1.1.1.1"},
        entry_id="test_entry",
    )
    config_entry.add_to_hass(hass)

    with patch("custom_components.vban.AsyncVBANClient", return_value=mock_vban_client), \
         patch("custom_components.vban.VoicemeeterRemote", return_value=mock_voicemeeter_remote):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    ent_reg = er.async_get(hass)
    
    # Check A4 and A5
    assert ent_reg.async_get("switch.strip_1_mic_route_to_a4")
    assert ent_reg.async_get("switch.strip_1_mic_route_to_a5")
    # Check B3
    assert ent_reg.async_get("switch.strip_1_mic_route_to_b3")
