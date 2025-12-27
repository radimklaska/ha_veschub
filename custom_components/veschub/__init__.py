"""The VESC Hub BMS integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_CAN_SCAN_END,
    CONF_CAN_SCAN_START,
    CONF_PASSWORD,
    CONF_SCAN_CAN_BUS,
    CONF_UPDATE_INTERVAL,
    CONF_VESC_ID,
    DEFAULT_CAN_SCAN_END,
    DEFAULT_CAN_SCAN_START,
    DEFAULT_SCAN_CAN_BUS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .vesc_protocol import VESCProtocol

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VESC Hub BMS from a config entry."""
    # Log version for debugging
    from .manifest import MANIFEST
    version = MANIFEST.get("version", "unknown")
    _LOGGER.warning(f"VESC Hub BMS Integration v{version} starting...")

    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    vesc_id = entry.data.get(CONF_VESC_ID)
    password = entry.data.get(CONF_PASSWORD)
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    scan_can_bus = entry.data.get(CONF_SCAN_CAN_BUS, DEFAULT_SCAN_CAN_BUS)
    can_scan_start = entry.data.get(CONF_CAN_SCAN_START, DEFAULT_CAN_SCAN_START)
    can_scan_end = entry.data.get(CONF_CAN_SCAN_END, DEFAULT_CAN_SCAN_END)

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
        "scan_can_bus": scan_can_bus,
        "can_scan_start": can_scan_start,
        "can_scan_end": can_scan_end,
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
