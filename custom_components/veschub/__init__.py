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
    CONF_INITIAL_SCAN_DONE,
    CONF_PASSWORD,
    CONF_SCAN_CAN_BUS,
    CONF_UPDATE_INTERVAL,
    CONF_VESC_ID,
    DEFAULT_CAN_ID_LIST,
    DEFAULT_SCAN_CAN_BUS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .vesc_protocol import VESCProtocol

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]
SERVICE_RESCAN = "rescan_can_bus"


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
    can_id_list = entry.data.get(CONF_CAN_ID_LIST, DEFAULT_CAN_ID_LIST)
    initial_scan_done = entry.data.get(CONF_INITIAL_SCAN_DONE, False)

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
        "can_id_list": can_id_list,
        "initial_scan_done": initial_scan_done,
    }

    # Forward setup to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register rescan service (once, not per entry)
    if not hass.services.has_service(DOMAIN, SERVICE_RESCAN):
        async def handle_rescan(call):
            """Handle rescan service call."""
            # Trigger full scan by resetting flag
            new_data = {**entry.data}
            new_data[CONF_INITIAL_SCAN_DONE] = False
            hass.config_entries.async_update_entry(entry, data=new_data)

            # Reload integration (background scan will run on reload)
            await hass.config_entries.async_reload(entry.entry_id)

            _LOGGER.info(f"CAN bus rescan triggered for entry {entry.entry_id}")

        hass.services.async_register(
            DOMAIN,
            SERVICE_RESCAN,
            handle_rescan,
            schema=vol.Schema({})
        )

    # Schedule background full scan if not done yet
    if not initial_scan_done:
        async def run_background_scan():
            """Run full CAN scan in background."""
            await asyncio.sleep(5)  # Wait for setup to complete

            coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
            if coordinator:
                _LOGGER.warning("[DISC] Starting background full CAN scan (0-254)...")
                newly_discovered = await coordinator.discover_can_devices(full_scan=True)

                if newly_discovered:
                    discovered_can_ids = sorted(list(coordinator.discovered_devices.keys()))

                    # Update config with discovered devices
                    new_data = {**entry.data}
                    new_data[CONF_CAN_ID_LIST] = discovered_can_ids
                    new_data[CONF_INITIAL_SCAN_DONE] = True
                    hass.config_entries.async_update_entry(entry, data=new_data)

                    _LOGGER.warning(
                        f"[DISC] Background scan complete. Added {len(discovered_can_ids)} "
                        f"CAN IDs to monitored list: {discovered_can_ids}"
                    )

                    # Reload integration to create entities for new devices
                    await hass.config_entries.async_reload(entry.entry_id)

        # Run in background (don't block setup)
        hass.async_create_task(run_background_scan())

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

        # Unregister service if this is the last entry
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_RESCAN)

    return unload_ok
