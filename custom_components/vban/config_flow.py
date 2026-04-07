"""Config flow for VBAN VoiceMeeter integration."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, CONF_HOST, CONF_PORT, CONF_COMMAND_STREAM, DEFAULT_PORT, DEFAULT_COMMAND_STREAM

class VBANConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VBAN VoiceMeeter."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            # Basic validation could be added here (e.g. pinging the device)
            return self.async_create_entry(title=f"VoiceMeeter (%s)" % user_input[CONF_HOST], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                vol.Optional(CONF_COMMAND_STREAM, default=DEFAULT_COMMAND_STREAM): str,
            }),
            errors=errors,
        )
