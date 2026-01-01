# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Home Assistant HACS integration** for reading BMS (Battery Management System) data from VESC controllers through VESCHub via TCP/IP. The integration is in active development (prerelease v0.0.x) targeting VESC Express devices with CAN bus motor controllers.

**Key Challenge**: VESC Express closes connections on direct data commands (GET_VALUES, BMS_GET_VALUES). Only COMM_FW_VERSION responds. BMS data is likely on CAN bus devices requiring COMM_FORWARD_CAN for access.

## ⚠️ CRITICAL SECURITY ISSUE - Shared VESCHub

**DISCOVERED 2026-01-02**: The public VESCHub server (veschub.vedder.se:65101) does NOT isolate CAN devices by authenticated user. When using `COMM_FORWARD_CAN`, you can access **ANY device** on the server, not just your own!

**Impact:**
- Automatic CAN scanning (0-254) discovers OTHER USERS' devices
- Integration was auto-adding 60+ foreign devices to monitored list
- Users could unintentionally poll/access other users' VESCs

**Mitigation (v0.2.4+):**
- ✅ Automatic background scanning **DISABLED by default**
- ✅ Default CAN ID list: `[0]` (local VESC only)
- ✅ Users MUST manually specify their CAN IDs in options
- ✅ UI warnings added about shared server risks
- ⚠️ Manual full scan still available but warns users

**Recommendations:**
- Use a **private VESCHub instance** for production
- On shared VESCHub: Only configure YOUR known CAN IDs (e.g., `[0, 116]`)
- Never enable automatic scanning on shared servers

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

**IMPORTANT**: Always use the automated script to keep versions in sync:

```bash
./tag_version.sh 0.0.8 "Description of changes"
```

This updates `manifest.json`, creates git tag, and pushes to GitHub automatically.

**Version display**: Integration logs version on startup with 🚀 emoji for easy identification in HA logs.

## Testing in Home Assistant

### Installation
```bash
# Manual update
cd /config/custom_components
rm -rf veschub
wget https://github.com/radimklaska/ha_veschub/archive/refs/tags/v0.0.X.zip
unzip v0.0.X.zip
mv ha_veschub-0.0.X/custom_components/veschub .
rm -rf ha_veschub-0.0.X v0.0.X.zip
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

## Current State (v0.0.7)

**What Works:**
- ✅ TCP connection to VESCHub
- ✅ Authentication (VESCTOOL:ID:PASSWORD)
- ✅ COMM_FW_VERSION (0x00) - returns 43 bytes "VESC Express T"

**What Doesn't Work:**
- ❌ COMM_GET_VALUES (0x04) - connection closes immediately
- ❌ COMM_BMS_GET_VALUES (0x32) - never tested (disconnected)
- ⏳ COMM_FORWARD_CAN (0x21) - implemented but needs testing

**Known Issue**: The old v0.0.6 test code is still running despite v0.0.7 version number. CAN forwarding code ([CAN] logs) not appearing in actual execution.

## VESC Protocol Notes

### Packet Structure
- Short: `[0x02][len][payload][crc_h][crc_l][0x03]` (len < 128)
- Long: `[0x02][len_h][len_l][payload][crc_h][crc_l][0x03]` (len ≥ 128)

### CAN Forwarding (Untested)
```python
# Forward BMS request to CAN ID 124
can_id = 124
wrapped_cmd = bytes([50])  # COMM_BMS_GET_VALUES
can_data = bytes([can_id]) + wrapped_cmd
response = await vesc._send_command(33, can_data)  # COMM_FORWARD_CAN
```

## Development Focus

1. **Fix code deployment issue** - v0.0.7 CAN code not executing
2. **Test CAN forwarding** - Try different CAN IDs (0-253, typical: 124)
3. **Parse CAN responses** - Handle COMM_FORWARD_CAN response format
4. **Add CAN device discovery** - Scan for BMS on CAN bus
5. **User configuration** - Let users select which CAN device's BMS to monitor

## License

CC BY-NC 4.0 (Non-commercial with attribution). Commercial use requires permission from copyright holder.

## Testing Credentials (Example)

Real endpoint for testing (credentials removed from code):
- Host: veschub.vedder.se
- Port: 65101
- Test logs should show `[CAN]` messages in v0.0.7+
