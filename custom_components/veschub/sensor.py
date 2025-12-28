"""Sensor platform for VESC Hub BMS."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, COMM_FORWARD_CAN, COMM_BMS_GET_VALUES
from .vesc_protocol import VESCProtocol

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VESC Hub BMS sensors from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    vesc: VESCProtocol = data["vesc"]
    update_interval = data["update_interval"]
    scan_can_bus = data.get("scan_can_bus", True)
    can_scan_start = data.get("can_scan_start", 0)
    can_scan_end = data.get("can_scan_end", 127)

    # Create data update coordinator
    coordinator = VESCDataUpdateCoordinator(
        hass,
        vesc,
        update_interval,
        scan_can_bus,
        can_scan_start,
        can_scan_end,
    )

    # Discover CAN devices first
    try:
        await coordinator.discover_can_devices()
    except Exception as err:
        _LOGGER.warning(
            "Could not complete CAN device discovery - this is normal if VESC is not currently active. Error: %s", err
        )

    # Fetch initial data (allow to fail - VESC may not be transmitting yet)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning(
            "Could not fetch initial data - this is normal if VESC is not currently active. "
            "Sensors will populate when data becomes available. Error: %s", err
        )

    # Create sensors for each discovered device
    sensors: list[SensorEntity] = []

    for can_id, device_info in coordinator.discovered_devices.items():
        device_name = device_info.get("firmware_name", f"CAN Device {can_id}")
        is_main = device_info.get("is_main", False)

        # Create basic sensors for each device
        sensors.extend([
            VESCDeviceSensor(
                coordinator,
                entry,
                can_id,
                "firmware_name",
                "Firmware Name",
                None,
                None,
                None,
                "mdi:label",
            ),
            VESCDeviceSensor(
                coordinator,
                entry,
                can_id,
                "online",
                "Online Status",
                None,
                None,
                None,
                "mdi:connection",
            ),
        ])

        # Add BMS sensors for CAN ID 0 (VESC Express with BMS)
        if can_id == 0:
            _LOGGER.info(f"Adding BMS sensors for {device_name}")

            # Main BMS sensors
            sensors.extend([
                VESCDeviceSensor(
                    coordinator, entry, can_id,
                    "v_tot", "Battery Voltage",
                    UnitOfElectricPotential.VOLT,
                    SensorDeviceClass.VOLTAGE,
                    SensorStateClass.MEASUREMENT,
                    "mdi:battery",
                ),
                VESCDeviceSensor(
                    coordinator, entry, can_id,
                    "i_in", "Battery Current",
                    UnitOfElectricCurrent.AMPERE,
                    SensorDeviceClass.CURRENT,
                    SensorStateClass.MEASUREMENT,
                    "mdi:current-dc",
                ),
                VESCDeviceSensor(
                    coordinator, entry, can_id,
                    "soc", "State of Charge",
                    PERCENTAGE,
                    SensorDeviceClass.BATTERY,
                    SensorStateClass.MEASUREMENT,
                    "mdi:battery-50",
                ),
                VESCDeviceSensor(
                    coordinator, entry, can_id,
                    "cell_min", "Cell Min Voltage",
                    UnitOfElectricPotential.VOLT,
                    SensorDeviceClass.VOLTAGE,
                    SensorStateClass.MEASUREMENT,
                    "mdi:battery-minus",
                ),
                VESCDeviceSensor(
                    coordinator, entry, can_id,
                    "cell_max", "Cell Max Voltage",
                    UnitOfElectricPotential.VOLT,
                    SensorDeviceClass.VOLTAGE,
                    SensorStateClass.MEASUREMENT,
                    "mdi:battery-plus",
                ),
                VESCDeviceSensor(
                    coordinator, entry, can_id,
                    "cell_delta", "Cell Delta",
                    UnitOfElectricPotential.VOLT,
                    SensorDeviceClass.VOLTAGE,
                    SensorStateClass.MEASUREMENT,
                    "mdi:delta",
                ),
                VESCDeviceSensor(
                    coordinator, entry, can_id,
                    "ah_cnt", "Amp Hours Used",
                    "Ah",
                    None,
                    SensorStateClass.TOTAL_INCREASING,
                    "mdi:counter",
                ),
                VESCDeviceSensor(
                    coordinator, entry, can_id,
                    "wh_cnt", "Watt Hours Used",
                    UnitOfEnergy.WATT_HOUR,
                    SensorDeviceClass.ENERGY,
                    SensorStateClass.TOTAL_INCREASING,
                    "mdi:lightning-bolt",
                ),
            ])

        _LOGGER.info(f"Created sensors for device: {device_name} (CAN ID {can_id})")

    if not sensors:
        _LOGGER.warning("No CAN devices discovered - no sensors created")

    async_add_entities(sensors)


class VESCDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching VESC BMS data."""

    def __init__(
        self,
        hass: HomeAssistant,
        vesc: VESCProtocol,
        update_interval: int,
        scan_can_bus: bool = True,
        can_scan_start: int = 0,
        can_scan_end: int = 127,
    ) -> None:
        """Initialize."""
        self.vesc = vesc
        self.scan_can_bus = scan_can_bus
        self.can_scan_start = can_scan_start
        self.can_scan_end = can_scan_end
        self.discovered_devices: dict[int, dict[str, Any]] = {}  # CAN ID -> device info
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def discover_can_devices(self) -> None:
        """Discover CAN devices by scanning CAN IDs."""
        _LOGGER.warning("[DISC] Starting device discovery...")

        # Ensure we're connected before discovery
        if not self.vesc.is_connected:
            _LOGGER.warning("[DISC] Not connected, connecting before discovery...")
            if not await self.vesc.connect():
                _LOGGER.warning("[DISC] Failed to connect for discovery")
                return

        # Scan CAN bus if enabled
        if self.scan_can_bus:
            _LOGGER.warning(f"[DISC] Scanning CAN IDs {self.can_scan_start}-{self.can_scan_end}...")

            for can_id in range(self.can_scan_start, self.can_scan_end + 1):
                try:
                    # Reconnect if needed (timeouts may disconnect us)
                    if not self.vesc.is_connected:
                        _LOGGER.debug(f"Reconnecting before scanning CAN ID {can_id}...")
                        if not await self.vesc.connect():
                            _LOGGER.warning(f"Failed to reconnect during discovery at CAN ID {can_id}")
                            continue

                    # Try to get firmware version from this CAN ID (use 1s timeout for faster discovery)
                    wrapped_cmd = bytes([0])  # COMM_FW_VERSION
                    can_data = bytes([can_id]) + wrapped_cmd
                    response = await self.vesc._send_command(COMM_FORWARD_CAN, can_data, timeout=1.0)

                    if response:
                        _LOGGER.warning(f"[DISC] CAN ID {can_id} response: {len(response)} bytes - {response[:20].hex() if len(response) > 20 else response.hex()}")

                    if response and len(response) > 2:
                        # Device responded! Parse the response
                        # COMM_FORWARD_CAN returns raw CAN device response: [COMM_FW_VERSION=0][fw_major][fw_minor][name...]
                        device_info = {
                            "can_id": can_id,
                            "online": True,
                        }

                        # Parse firmware version from CAN response
                        fw_major = response[1] if len(response) > 1 else 0
                        fw_minor = response[2] if len(response) > 2 else 0

                        # Try to extract firmware name (starts at byte 3)
                        name_start = 3
                        name_bytes = []
                        for i in range(name_start, min(len(response), 35)):
                            if response[i] == 0:
                                break
                            if 32 <= response[i] <= 126:  # Printable ASCII
                                name_bytes.append(response[i])

                        fw_name = bytes(name_bytes).decode('ascii', errors='ignore') if name_bytes else f"CAN Device {can_id}"

                        device_info["firmware_version"] = f"{fw_major}.{fw_minor:02d}"
                        device_info["firmware_name"] = fw_name

                        self.discovered_devices[can_id] = device_info
                        _LOGGER.warning(f"[DISC] Discovered CAN device at ID {can_id}: {fw_name} v{fw_major}.{fw_minor}")

                except Exception as e:
                    # No response or error - device not present at this ID
                    continue

        # Always detect the directly connected VESC controller
        # This is the controller we're connected to via TCP (not through CAN forwarding)
        # Assign it to CAN ID 0 if not already discovered via CAN scan
        try:
            if 0 not in self.discovered_devices:
                fw_response = await self.vesc._send_command(0)  # Direct COMM_FW_VERSION
                if fw_response and len(fw_response) > 2:
                    fw_major = fw_response[1]
                    fw_minor = fw_response[2]

                    name_start = 3
                    name_bytes = []
                    for i in range(name_start, min(len(fw_response), 30)):
                        if fw_response[i] == 0:
                            break
                        if 32 <= fw_response[i] <= 126:
                            name_bytes.append(fw_response[i])

                    fw_name = bytes(name_bytes).decode('ascii', errors='ignore') if name_bytes else "VESC"

                    self.discovered_devices[0] = {
                        "can_id": 0,  # Local controller at CAN ID 0
                        "online": True,
                        "firmware_version": f"{fw_major}.{fw_minor:02d}",
                        "firmware_name": fw_name,
                        "is_local": True,  # This is the directly connected controller
                    }
                    _LOGGER.warning(f"[DISC] Local VESC controller: {fw_name} v{fw_major}.{fw_minor}")
        except Exception as e:
            _LOGGER.warning(f"[DISC] Could not get local VESC info: {e}")

        _LOGGER.warning(f"[DISC] Device discovery complete. Found {len(self.discovered_devices)} device(s)")

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data for all discovered devices."""
        try:
            # Ensure connection (reconnect if needed)
            if not self.vesc.is_connected:
                _LOGGER.info("Not connected, attempting to connect...")
                if not await self.vesc.connect():
                    raise UpdateFailed("Failed to connect to VESCHub")
                _LOGGER.info("Connection established")

            # Return data structure: {can_id: {sensor_data}}
            all_data = {}

            # Update each discovered device
            for can_id in self.discovered_devices.keys():
                device_data = {}

                try:
                    if can_id == 0:
                        # Local VESC controller - use rapid-fire BMS retrieval
                        _LOGGER.debug("[UPDATE] Fetching BMS data for local VESC Express...")

                        bms_data = await self.vesc.get_bms_values_rapid()

                        if bms_data:
                            _LOGGER.info(f"[UPDATE] BMS data retrieved: {bms_data.get('cell_num', 0)} cells, {bms_data.get('v_tot', 0):.2f}V total")

                            device_data = {
                                "firmware_name": "VESC Express",
                                "online": True,
                                # BMS data
                                "bms_available": True,
                                **bms_data,  # Include all BMS data
                            }
                        else:
                            _LOGGER.debug("[UPDATE] No BMS data received")
                            device_data = {
                                "firmware_name": "VESC Express",
                                "online": True,
                                "bms_available": False,
                            }

                    else:
                        # CAN device - use COMM_FORWARD_CAN
                        wrapped_cmd = bytes([0])  # COMM_FW_VERSION
                        can_data = bytes([can_id]) + wrapped_cmd
                        response = await self.vesc._send_command(COMM_FORWARD_CAN, can_data)

                        if response and len(response) > 2:
                            # Response format: [COMM_FW_VERSION=0][fw_major][fw_minor][name...]
                            fw_major = response[1]
                            fw_minor = response[2]

                            name_start = 3
                            name_bytes = []
                            for i in range(name_start, min(len(response), 35)):
                                if response[i] == 0:
                                    break
                                if 32 <= response[i] <= 126:
                                    name_bytes.append(response[i])

                            fw_name = bytes(name_bytes).decode('ascii', errors='ignore') if name_bytes else f"CAN Device {can_id}"

                            device_data = {
                                "firmware_version": f"{fw_major}.{fw_minor:02d}",
                                "firmware_name": fw_name,
                                "online": True,
                            }
                        else:
                            device_data = {"online": False}

                except Exception as e:
                    _LOGGER.debug(f"Error updating CAN device {can_id}: {e}")
                    device_data = {"online": False}

                all_data[can_id] = device_data

            return all_data

        except Exception as err:
            _LOGGER.error(f"Error during update: {err}")
            # Return offline status for all devices
            return {can_id: {"online": False} for can_id in self.discovered_devices.keys()}


class VESCDeviceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a VESC device sensor."""

    def __init__(
        self,
        coordinator: VESCDataUpdateCoordinator,
        entry: ConfigEntry,
        can_id: int,
        data_key: str,
        name: str,
        unit: str | None,
        device_class: SensorDeviceClass | None,
        state_class: SensorStateClass | None,
        icon: str | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._can_id = can_id
        self._data_key = data_key

        # Get device info from coordinator
        device_info = coordinator.discovered_devices.get(can_id, {})
        device_name = device_info.get("firmware_name", f"CAN Device {can_id}")
        is_local = device_info.get("is_local", False)

        # Create unique names based on device type
        if is_local:
            # This is the locally connected VESC controller (via TCP, not CAN)
            self._attr_name = f"VESC Local {name}"
            device_display_name = f"VESC Local Controller"
            model = device_name  # Use actual firmware name as model
        else:
            # This is a CAN bus device
            self._attr_name = f"VESC CAN {can_id} {name}"
            device_display_name = f"VESC CAN Device {can_id}"
            model = device_name  # Use actual firmware name as model

        self._attr_unique_id = f"{entry.entry_id}_can{can_id}_{data_key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon

        # Create separate device for each CAN ID
        # CAN devices are linked via the local controller (CAN 0) if it exists
        via_dev = None
        if not is_local and can_id != 0 and 0 in coordinator.discovered_devices:
            via_dev = (DOMAIN, f"{entry.entry_id}_can0")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_can{can_id}")},
            name=device_display_name,
            manufacturer="VESC Project",
            model=model,
            via_device=via_dev,
        )

    @property
    def native_value(self) -> float | int | str | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None

        # Get data for this specific CAN device
        device_data = self.coordinator.data.get(self._can_id, {})
        return device_data.get(self._data_key)


class VESCCellVoltageSensor(CoordinatorEntity, SensorEntity):
    """Representation of a VESC BMS cell voltage sensor."""

    def __init__(
        self,
        coordinator: VESCDataUpdateCoordinator,
        entry: ConfigEntry,
        cell_index: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._cell_index = cell_index
        self._attr_name = f"VESC BMS Cell {cell_index + 1} Voltage"
        self._attr_unique_id = f"{entry.entry_id}_cell_{cell_index}"
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery-outline"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="VESC BMS",
            manufacturer="VESC Project",
            model="VESC BMS",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None

        cell_voltages = self.coordinator.data.get("cell_voltages", [])
        if self._cell_index < len(cell_voltages):
            return cell_voltages[self._cell_index]
        return None


class VESCTemperatureSensor(CoordinatorEntity, SensorEntity):
    """Representation of a VESC BMS temperature sensor."""

    def __init__(
        self,
        coordinator: VESCDataUpdateCoordinator,
        entry: ConfigEntry,
        temp_index: int,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._temp_index = temp_index
        self._attr_name = f"VESC BMS Temperature {temp_index + 1}"
        self._attr_unique_id = f"{entry.entry_id}_temp_{temp_index}"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:thermometer"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="VESC BMS",
            manufacturer="VESC Project",
            model="VESC BMS",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None

        temperatures = self.coordinator.data.get("temperatures", [])
        if self._temp_index < len(temperatures):
            return temperatures[self._temp_index]
        return None
