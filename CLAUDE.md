# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Home Assistant HACS integration** for reading BMS (Battery Management System) data from VESC controllers through VESCHub via TCP/IP. The integration is in active development (v0.2.x) targeting VESC Express devices with CAN bus motor controllers.

**BMS Data Retrieval**: Successfully implemented using rapid-fire command sequence (FW_VERSION → GET_CUSTOM_CONFIG → PING_CAN → BMS_GET_VALUES). Direct BMS commands fail, but sending all 4 commands rapidly without waiting for responses works reliably.

## Architecture

### Communication Flow
```
Home Assistant → VESCHub (TCP) → VESC Express → CAN Bus → Motor Controller (BMS)
                veschub.vedder.se:65101
                Auth: VESCTOOL:UUID:PASSWORD
```

### Core Components

**`vesc_protocol.py`** - VESC protocol over TCP
- Packet framing: `[0x02][length][payload][CRC16][0x03]`
- CRC16 calculation (polynomial 0x1021)
- VESCHub authentication
- Command/response handling with 5s timeout
- **Critical**: Only FW_VERSION (0x00) works; other commands close connection

**`sensor.py`** - HA sensor platform
- `VESCDataUpdateCoordinator` - Polling coordinator
- Dynamic sensor creation (cells, temperatures)
- Connection management with auto-reconnect
- **Testing code present**: [TEST], [CAN], [BMS] logging prefixes

**`config_flow.py`** - HA UI configuration
- VESCHub host/port (default: veschub.vedder.se:65101)
- Optional VESC ID & password for public hub
- Connection validation (connect only, no data required)

**`const.py`** - Command constants
- COMM_FW_VERSION = 0 (works)
- COMM_GET_VALUES = 4 (fails - connection closes)
- COMM_FORWARD_CAN = 33 (for CAN devices)
- COMM_BMS_GET_VALUES = 50 (fails)

## Version Management

**Manual Workflow:**

1. Update version in `manifest.json`
2. Commit your code changes with detailed message
3. Create and push git tag:
   ```bash
   git tag -a v0.2.10 -m "Description of changes"
   git push origin v0.2.10
   ```

**Version display**: Integration logs version on startup with 🚀 emoji for easy identification in HA logs.

## Testing in Home Assistant

### Local Connection Testing

Before deploying to Home Assistant, test your VESCHub connection:

```bash
# Create .env file with credentials
cat > .env << EOF
VESC_ID=your-vesc-id
VESC_PASSWORD=your-password
EOF

# Run proof of concept script
python3 proof_of_concept.py
```

### Installation
```bash
# Manual update (example for v0.2.9)
cd /config/custom_components
rm -rf veschub
wget https://github.com/radimklaska/ha_veschub/archive/refs/tags/v0.2.9.zip
unzip v0.2.9.zip
mv ha_veschub-0.2.9/custom_components/veschub .
rm -rf ha_veschub-0.2.9 v0.2.9.zip
```

### Debug Logging
Add to HA `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.veschub: debug
```

Look for tagged log messages:
- `[CONNECT]` - TCP connection
- `[AUTH]` - VESCHub authentication
- `[CMD]` - Command send/receive
- `[TEST]` - Test/diagnostic code
- `[CAN]` - CAN forwarding attempts
- `[BMS]` - BMS data requests

## Current State (v0.2.9)

**What Works:**
- ✅ TCP connection to VESCHub with authentication
- ✅ BMS data retrieval using rapid-fire command sequence
- ✅ Cell voltage sensors (20 cells) displaying correct values
- ✅ Temperature sensors (3 temps) displaying correct values
- ✅ Summary sensors (Battery Voltage, Cell Min/Max/Delta)
- ✅ CAN device discovery for user-configured IDs
- ✅ Options flow for updating monitored CAN IDs
- ✅ Fresh connection per BMS request to avoid stale state

**Tested Hardware:**
- ✅ **Floatwheel ADV2** - Primary testing platform
- ✅ VESC Express with 20S BMS (UART-based)
- ⏳ **CAN-enabled BMS** - Pending testing with proper CAN BMS
- ⏳ BMS on CAN bus devices (not direct UART)

**BMS Data Format (v0.2.9):**
- Cell voltages: uint16 big-endian at offset 25, millivolts (÷1000 for V)
- Cell count: uint8 at offset 24 (typically 20 cells)
- Balance flags: 20×uint8 starting at offset 65 (one per cell)
- **Temperature count: uint8 at offset 85** (number of temp sensors)
- **Temperature values: uint16 big-endian, centidegrees Celsius (÷100 for °C)**
  - Offset 86: First temp sensor
  - Offset 88: Second temp sensor
  - Offset 90: Third temp sensor

**Critical Implementation Details:**
- Must create fresh TCP connection for each BMS request
- Must wait 1 second after auth before sending commands
- Must read for full 3 seconds to capture delayed BMS packet
- BMS packet is 168 bytes (0xa8), command byte 0x60
- Sensor data access: `coordinator.data[can_id]["cell_voltages"]` (not `coordinator.data["cell_voltages"]`)

## VESC Protocol Notes

For complete protocol details, command sequences, and BMS data format, see **TECHNICAL.md**.

### Packet Structure
- Short: `[0x02][len][payload][crc_h][crc_l][0x03]` (len < 128)
- Long: `[0x02][len_h][len_l][payload][crc_h][crc_l][0x03]` (len ≥ 128)

### CAN Forwarding
```python
# Forward BMS request to CAN ID 124
can_id = 124
wrapped_cmd = bytes([50])  # COMM_BMS_GET_VALUES
can_data = bytes([can_id]) + wrapped_cmd
response = await vesc._send_command(33, can_data)  # COMM_FORWARD_CAN
```

## Recent Fixes (v0.2.9)

**Cell & Temperature Sensor Data Access Bug:**
- Problem: Sensors accessed `coordinator.data["cell_voltages"]` directly
- Solution: Must access via CAN ID: `coordinator.data[0]["cell_voltages"]`
- Impact: All individual cell and temperature sensors now display values

**Temperature Parsing Correction:**
- Problem: Dividing by 10 (decidegrees) showed 303.4°C instead of 30.34°C
- Solution: Divide by 100 (centidegrees) for correct temperature values
- Also fixed: Now reads temperature count byte before parsing temp values

**Other Fixes:**
- `OptionsFlowHandler` missing `__init__` method (TypeError on options access)
- `manifest.py` blocking I/O warning during async context
- Removed undefined `SERVICE_RESCAN` reference in cleanup code

## Future Development Ideas

1. **State of Charge (SOC) sensor** - Parse SOC data from BMS packet
2. **State of Health (SOH) sensor** - Parse battery health metrics
3. **Balance status indicators** - Show which cells are being balanced
4. **CAN device auto-discovery UI** - Button to scan and add new devices
5. **Multiple BMS support** - Handle BMS on CAN devices (not just local VESC)

## License

CC BY-NC 4.0 (Non-commercial with attribution). Commercial use requires permission from copyright holder.

## Documentation

- **README.md** - User-facing documentation (installation, features, troubleshooting)
- **TECHNICAL.md** - Complete protocol reference and BMS solution deep-dive
- **CLAUDE.md** - This file (development guide)

## Testing Credentials

Store credentials in `.env` file (gitignored):
```
VESC_ID=your-vesc-id
VESC_PASSWORD=your-password
```

Test endpoint:
- Host: veschub.vedder.se
- Port: 65101
