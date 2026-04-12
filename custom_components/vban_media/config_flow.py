"""Config flow for VBAN Media Player integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, CONF_DEVICE, CONF_STREAM_NAME, DEFAULT_STREAM_NAME
from custom_components.vban.const import DOMAIN as VBAN_DOMAIN

class VBANMediaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VBAN Media Player."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # We don't really need a unique ID here as multiple media players 
            # could theoretically point to the same VBAN device if they use different stream names
            # but for now, one per device/stream combo is good.
            await self.async_set_unique_id(f"{user_input[CONF_DEVICE]}_{user_input[CONF_STREAM_NAME]}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"VBAN Media ({user_input[CONF_STREAM_NAME]})",
                data=user_input,
            )

        # Get existing VBAN entries
        vban_entries = self.hass.config_entries.async_entries(VBAN_DOMAIN)
        if not vban_entries:
            return self._show_no_vban_error()

        device_options = [
            selector.SelectOptionDict(value=entry.entry_id, label=entry.title)
            for entry in vban_entries
        ]

        data_schema = vol.Schema({
            vol.Required(CONF_DEVICE): selector.SelectSelector(
                selector.SelectSelectorConfig(options=device_options)
            ),
            vol.Optional(CONF_STREAM_NAME, default=DEFAULT_STREAM_NAME): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @callback
    def _show_no_vban_error(self):
        """Show error if no VBAN devices are configured."""
        return self.async_abort(reason="no_vban_devices")
