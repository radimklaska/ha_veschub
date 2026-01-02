"""Config flow for VESC Hub BMS integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_CAN_ID_LIST,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_VESC_ID,
    DEFAULT_CAN_ID_LIST,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .vesc_protocol import VESCProtocol

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_VESC_ID): str,
        vol.Optional(CONF_PASSWORD): str,
        vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
            int, vol.Range(min=1, max=300)
        ),
        vol.Required("can_id_list_str", default="0"): str,  # Required: User must specify CAN IDs
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    vesc = VESCProtocol(
        data[CONF_HOST],
        data[CONF_PORT],
        data.get(CONF_VESC_ID),
        data.get(CONF_PASSWORD),
    )

    if not await vesc.connect():
        raise CannotConnect

    # Connection successful - disconnect for now
    # Note: BMS data will be fetched during normal operation
    # No need to wait for data during setup as VESC may not be transmitting
    await vesc.disconnect()

    # Return info to be stored in the config entry
    return {
        "title": f"VESC Hub {data[CONF_HOST]}",
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VESC Hub BMS."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "OptionsFlowHandler":
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Parse CAN ID list from user input (required field)
            can_id_str = user_input.pop("can_id_list_str", "0")
            try:
                can_id_list = sorted(set(
                    int(x.strip())
                    for x in can_id_str.split(",")
                    if x.strip().isdigit() and 0 <= int(x.strip()) <= 253
                ))
                if not can_id_list:
                    errors["base"] = "invalid_can_ids"
                    can_id_list = DEFAULT_CAN_ID_LIST.copy()
            except ValueError:
                errors["base"] = "invalid_can_ids"
                can_id_list = DEFAULT_CAN_ID_LIST.copy()

            user_input[CONF_CAN_ID_LIST] = can_id_list

            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create unique ID based on host and port
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}_{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for VESC Hub BMS."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        try:
            if user_input is not None:
                # Parse CAN ID list from comma-separated string
                can_id_str = user_input.get("can_id_list_str", "")
                try:
                    can_id_list = sorted(set(
                        int(x.strip())
                        for x in can_id_str.split(",")
                        if x.strip().isdigit() and 0 <= int(x.strip()) <= 253
                    ))
                except (ValueError, AttributeError):
                    can_id_list = DEFAULT_CAN_ID_LIST.copy()

                # Update entry.data (not entry.options)
                new_data = {**self.config_entry.data}
                new_data[CONF_UPDATE_INTERVAL] = user_input[CONF_UPDATE_INTERVAL]
                new_data[CONF_CAN_ID_LIST] = can_id_list

                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=new_data
                )

                # Reload integration to apply changes
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)

                return self.async_create_entry(title="", data={})

            # Get current values with safe defaults
            current_can_ids = self.config_entry.data.get(CONF_CAN_ID_LIST, DEFAULT_CAN_ID_LIST)
            current_interval = self.config_entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

            # Ensure current_can_ids is a list
            if not isinstance(current_can_ids, list):
                current_can_ids = DEFAULT_CAN_ID_LIST.copy()

            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=current_interval
                    ): vol.All(int, vol.Range(min=1, max=300)),
                    vol.Required(
                        "can_id_list_str",
                        default=",".join(str(x) for x in current_can_ids)
                    ): str,
                }),
                description_placeholders={
                    "current_monitored": ", ".join(str(x) for x in current_can_ids),
                }
            )
        except Exception as e:
            _LOGGER.exception(f"Error in options flow: {e}")
            # Return a safe error form
            return self.async_abort(reason="unknown_error")
