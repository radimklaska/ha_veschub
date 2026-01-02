"""The VESC Hub BMS integration."""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_CAN_ID_LIST,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    CONF_VESC_ID,
    DEFAULT_CAN_ID_LIST,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .vesc_protocol import VESCProtocol

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VESC Hub BMS from a config entry."""
    _LOGGER.warning("VESC Hub BMS Integration starting...")

    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    vesc_id = entry.data.get(CONF_VESC_ID)
    password = entry.data.get(CONF_PASSWORD)
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    can_id_list = entry.data.get(CONF_CAN_ID_LIST, DEFAULT_CAN_ID_LIST)

    # Create VESC protocol instance
    vesc = VESCProtocol(host, port, vesc_id, password)

    # Test connection
    if not await vesc.connect():
        raise ConfigEntryNotReady(f"Unable to connect to VESCHub at {host}:{port}")

    # Disconnect for now - sensors will manage their own connections
    await vesc.disconnect()

    # Store protocol instance and config in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "vesc": vesc,
        "host": host,
        "port": port,
        "update_interval": update_interval,
        "can_id_list": can_id_list,
    }

    # Forward setup to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Cleanup
        data = hass.data[DOMAIN].pop(entry.entry_id)
        vesc = data["vesc"]
        if vesc.is_connected:
            await vesc.disconnect()

    return unload_ok
