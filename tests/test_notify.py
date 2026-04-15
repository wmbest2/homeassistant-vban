"""Test VBAN VoiceMeeter notify."""
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, device_registry as dr

from custom_components.vban.const import DOMAIN
from aiovban.enums import VoicemeeterType

from pytest_homeassistant_custom_component.common import MockConfigEntry

async def test_notify_setup(hass: HomeAssistant, mock_vban_client, mock_voicemeeter_remote) -> None:
    """Test notify entity is created."""
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

    # Get the runtime_data to find the actual chat object used
    runtime_data = config_entry.runtime_data
    mock_chat = runtime_data.chat

    # Check registry
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get("notify.voicemeeter_vm_host_chat")
    assert entry

    # Test sending message
    await hass.services.async_call(
        "notify", "send_message", {"entity_id": "notify.voicemeeter_vm_host_chat", "message": "Hello VoiceMeeter"}, blocking=True
    )
    mock_chat.send_chat.assert_called_once_with("Hello VoiceMeeter")

    # Test sending with title
    mock_chat.send_chat.reset_mock()
    await hass.services.async_call(
        "notify", "send_message", {"entity_id": "notify.voicemeeter_vm_host_chat", "message": "Content", "title": "Alert"}, blocking=True
    )
    mock_chat.send_chat.assert_called_once_with("Alert: Content")
