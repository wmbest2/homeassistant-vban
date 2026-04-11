"""Test VBAN VoiceMeeter config flow."""
from unittest.mock import patch
import pytest

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from custom_components.vban.const import DOMAIN, CONF_COMMAND_STREAM

async def test_user_form(hass: HomeAssistant) -> None:
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert not result.get("errors")

    with patch(
        "custom_components.vban.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_HOST: "1.1.1.1",
                CONF_PORT: 6980,
                CONF_COMMAND_STREAM: "Command1",
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == "VoiceMeeter (1.1.1.1)"
    assert result2["data"] == {
        CONF_HOST: "1.1.1.1",
        CONF_PORT: 6980,
        CONF_COMMAND_STREAM: "Command1",
    }
    assert len(mock_setup_entry.mock_calls) == 1
