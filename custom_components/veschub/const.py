"""Constants for the VESC Hub BMS integration."""

DOMAIN = "veschub"

# Configuration
CONF_HOST = "host"
CONF_PORT = "port"
CONF_VESC_ID = "vesc_id"
CONF_PASSWORD = "password"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_CAN_ID_LIST = "can_id_list"  # List[int] - monitored CAN IDs (user-provided only)

# Defaults
DEFAULT_HOST = "veschub.vedder.se"
DEFAULT_PORT = 65101
DEFAULT_UPDATE_INTERVAL = 5  # seconds
DEFAULT_CAN_ID_LIST = [0]  # Only local VESC by default

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
