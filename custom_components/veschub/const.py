"""Constants for the VESC Hub BMS integration."""

DOMAIN = "veschub"

# Configuration
CONF_HOST = "host"
CONF_PORT = "port"
CONF_VESC_ID = "vesc_id"
CONF_PASSWORD = "password"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_CAN_SCAN_START = "can_scan_start"
CONF_CAN_SCAN_END = "can_scan_end"
CONF_SCAN_CAN_BUS = "scan_can_bus"

# Defaults
DEFAULT_HOST = "veschub.vedder.se"
DEFAULT_PORT = 65101
DEFAULT_UPDATE_INTERVAL = 5  # seconds
DEFAULT_CAN_SCAN_START = 0  # Start of CAN ID range
DEFAULT_CAN_SCAN_END = 100  # End of CAN ID range (0-253 valid, 254 broadcast)
                            # With 1s timeout per ID, this takes max ~100s
DEFAULT_SCAN_CAN_BUS = True  # Scan CAN bus by default

# VESC Protocol Constants
VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03
VESC_PACKET_TERMINATOR = 0x03

# VESC Commands
COMM_FW_VERSION = 0
COMM_GET_VALUES = 4
COMM_FORWARD_CAN = 34  # Fixed: was 33
COMM_PING_CAN = 0x3e  # 62 - Required for BMS access
COMM_GET_CUSTOM_CONFIG = 0x5d  # 93 - Required for BMS access
COMM_BMS_GET_VALUES = 96  # Fixed: was 50
COMM_BMS_SET_CHARGE_ALLOWED = 51
COMM_BMS_SET_BALANCE_OVERRIDE = 52
COMM_BMS_RESET_COUNTERS = 53
COMM_BMS_FORCE_BALANCE = 54
COMM_BMS_ZERO_CURRENT_OFFSET = 55

# Sensor Types
SENSOR_VOLTAGE = "voltage"
SENSOR_CURRENT = "current"
SENSOR_STATE_OF_CHARGE = "state_of_charge"
SENSOR_CAPACITY_AH = "capacity_ah"
SENSOR_TEMPERATURE = "temperature"
SENSOR_CELL_VOLTAGE = "cell_voltage"
SENSOR_BALANCE_STATE = "balance_state"
