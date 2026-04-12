"""Config flow for VBAN VoiceMeeter integration."""
import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
import homeassistant.helpers.config_validation as cv

from aiovban.asyncio import AsyncVBANClient

from homeassistant.core import callback

from .const import (
    DOMAIN, 
    CONF_COMMAND_STREAM, 
    CONF_MEDIA_STREAM,
    DEFAULT_PORT, 
    DEFAULT_COMMAND_STREAM,
    DEFAULT_MEDIA_STREAM
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
    vol.Optional(CONF_COMMAND_STREAM, default=DEFAULT_COMMAND_STREAM): str,
    vol.Optional(CONF_MEDIA_STREAM, default=DEFAULT_MEDIA_STREAM): str,
})

class VBANConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VBAN VoiceMeeter."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return VBANOptionsFlowHandler()


class VBANOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle VBAN options."""

    async def async_step_init(self, user_input=None):
        """Manage the VBAN options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {
            vol.Optional(
                CONF_PORT,
                default=self.config_entry.options.get(
                    CONF_PORT, self.config_entry.data.get(CONF_PORT, DEFAULT_PORT)
                ),
            ): cv.port,
            vol.Optional(
                CONF_COMMAND_STREAM,
                default=self.config_entry.options.get(
                    CONF_COMMAND_STREAM, 
                    self.config_entry.data.get(CONF_COMMAND_STREAM, DEFAULT_COMMAND_STREAM)
                ),
            ): str,
            vol.Optional(
                CONF_MEDIA_STREAM,
                default=self.config_entry.options.get(
                    CONF_MEDIA_STREAM, 
                    self.config_entry.data.get(CONF_MEDIA_STREAM, DEFAULT_MEDIA_STREAM)
                ),
            ): str,
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))
