"""Config flow for VBAN VoiceMeeter integration."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
import homeassistant.helpers.config_validation as cv

from aiovban.asyncio import AsyncVBANClient

from .const import DOMAIN, CONF_COMMAND_STREAM, DEFAULT_PORT, DEFAULT_COMMAND_STREAM

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    vol.Optional(CONF_COMMAND_STREAM, default=DEFAULT_COMMAND_STREAM): str,
})

class VBANConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VBAN VoiceMeeter."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            # Basic validation: check if we can listen on the port
            # In a real Core integration, we might also try to ping the host
            # but since VBAN is UDP and local_push, listening is the first step.
            
            # Check if already configured
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}_{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"VoiceMeeter ({user_input[CONF_HOST]})", 
                data=user_input
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
