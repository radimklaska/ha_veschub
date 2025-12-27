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

from .const import DOMAIN
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

    # Create data update coordinator
    coordinator = VESCDataUpdateCoordinator(
        hass,
        vesc,
        update_interval,
    )

    # Fetch initial data (allow to fail - VESC may not be transmitting yet)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning(
            "Could not fetch initial BMS data - this is normal if VESC is not currently active. "
            "Sensors will populate when data becomes available. Error: %s", err
        )

    # Create sensors
    sensors: list[SensorEntity] = []

    # Main BMS sensors
    sensors.extend([
        VESCBMSSensor(
            coordinator,
            entry,
            "v_tot",
            "Total Voltage",
            UnitOfElectricPotential.VOLT,
            SensorDeviceClass.VOLTAGE,
            SensorStateClass.MEASUREMENT,
            "mdi:flash",
        ),
        VESCBMSSensor(
            coordinator,
            entry,
            "v_charge",
            "Charge Voltage",
            UnitOfElectricPotential.VOLT,
            SensorDeviceClass.VOLTAGE,
            SensorStateClass.MEASUREMENT,
            "mdi:flash-outline",
        ),
        VESCBMSSensor(
            coordinator,
            entry,
            "i_in",
            "Input Current",
            UnitOfElectricCurrent.AMPERE,
            SensorDeviceClass.CURRENT,
            SensorStateClass.MEASUREMENT,
            "mdi:current-dc",
        ),
        VESCBMSSensor(
            coordinator,
            entry,
            "i_in_ic",
            "Input Current IC",
            UnitOfElectricCurrent.AMPERE,
            SensorDeviceClass.CURRENT,
            SensorStateClass.MEASUREMENT,
            "mdi:current-dc",
        ),
        VESCBMSSensor(
            coordinator,
            entry,
            "ah_cnt",
            "Amp Hours",
            "Ah",
            None,
            SensorStateClass.TOTAL_INCREASING,
            "mdi:counter",
        ),
        VESCBMSSensor(
            coordinator,
            entry,
            "wh_cnt",
            "Watt Hours",
            UnitOfEnergy.WATT_HOUR,
            SensorDeviceClass.ENERGY,
            SensorStateClass.TOTAL_INCREASING,
            "mdi:counter",
        ),
        VESCBMSSensor(
            coordinator,
            entry,
            "soc",
            "State of Charge",
            PERCENTAGE,
            SensorDeviceClass.BATTERY,
            SensorStateClass.MEASUREMENT,
            "mdi:battery",
        ),
        VESCBMSSensor(
            coordinator,
            entry,
            "soh",
            "State of Health",
            PERCENTAGE,
            None,
            SensorStateClass.MEASUREMENT,
            "mdi:battery-heart",
        ),
        VESCBMSSensor(
            coordinator,
            entry,
            "capacity_ah",
            "Capacity",
            "Ah",
            None,
            SensorStateClass.MEASUREMENT,
            "mdi:battery-medium",
        ),
    ])

    # Add cell voltage sensors
    if coordinator.data and "cell_voltages" in coordinator.data:
        cell_count = len(coordinator.data["cell_voltages"])
        for i in range(cell_count):
            sensors.append(
                VESCCellVoltageSensor(
                    coordinator,
                    entry,
                    i,
                )
            )

    # Add temperature sensors
    if coordinator.data and "temperatures" in coordinator.data:
        temp_count = len(coordinator.data["temperatures"])
        for i in range(temp_count):
            sensors.append(
                VESCTemperatureSensor(
                    coordinator,
                    entry,
                    i,
                )
            )

    # Add balance state sensor
    sensors.append(
        VESCBMSSensor(
            coordinator,
            entry,
            "bal_state",
            "Balance State",
            None,
            None,
            None,
            "mdi:scale-balance",
        )
    )

    async_add_entities(sensors)


class VESCDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching VESC BMS data."""

    def __init__(
        self,
        hass: HomeAssistant,
        vesc: VESCProtocol,
        update_interval: int,
    ) -> None:
        """Initialize."""
        self.vesc = vesc
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from VESC BMS."""
        try:
            # Ensure connection
            if not self.vesc.is_connected:
                _LOGGER.info("Connecting to VESCHub...")
                if not await self.vesc.connect():
                    raise UpdateFailed("Failed to connect to VESCHub")
                _LOGGER.info("Connected successfully")

            # TEST: Try COMM_GET_VALUES (motor/system data) - might include BMS on Express
            _LOGGER.warning("[TEST] Trying COMM_GET_VALUES (0x04) for motor/system data...")
            motor_response = await self.vesc._send_command(4)  # COMM_GET_VALUES
            if motor_response:
                _LOGGER.warning(f"[TEST] GET_VALUES response: {len(motor_response)} bytes")
                _LOGGER.warning(f"[TEST] First 60 bytes: {motor_response[:60].hex()}")
            else:
                _LOGGER.error("[TEST] No response to GET_VALUES command")

            # Get BMS data
            _LOGGER.warning("[BMS] Requesting BMS values with COMM_BMS_GET_VALUES (0x32)...")
            bms_data = await self.vesc.get_bms_values()

            if bms_data is None:
                _LOGGER.warning("No BMS data received - VESC may not be transmitting")
                # Return empty data instead of failing - VESC may not be active
                return {}

            _LOGGER.debug(f"BMS data received: {len(bms_data)} fields")
            return bms_data

        except Exception as err:
            # Disconnect on error
            if self.vesc.is_connected:
                await self.vesc.disconnect()
            _LOGGER.error(f"Error during update: {err}")
            raise UpdateFailed(f"Error communicating with VESCHub: {err}") from err


class VESCBMSSensor(CoordinatorEntity, SensorEntity):
    """Representation of a VESC BMS sensor."""

    def __init__(
        self,
        coordinator: VESCDataUpdateCoordinator,
        entry: ConfigEntry,
        data_key: str,
        name: str,
        unit: str | None,
        device_class: SensorDeviceClass | None,
        state_class: SensorStateClass | None,
        icon: str | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._data_key = data_key
        self._attr_name = f"VESC BMS {name}"
        self._attr_unique_id = f"{entry.entry_id}_{data_key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="VESC BMS",
            manufacturer="VESC Project",
            model="VESC BMS",
        )

    @property
    def native_value(self) -> float | int | str | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)


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
