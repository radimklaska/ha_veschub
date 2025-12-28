# VESC Express & BMS Data Exploration Summary

**Date:** 2025-12-28
**VESC ID:** rk-adv2
**Host:** veschub.vedder.se:65101

---

## Architecture Discovered

```
BMS (UART) ──→ VESC Express ──→ VESCHub (TCP) ──→ Home Assistant
                     ↓
                 CAN Bus
                     ↓
              ADV500 Motor Controller (CAN ID 84)
```

---

## Devices Found

### 1. VESC Express (Local Controller)
- **Firmware:** v6.5 - VESC Express T
- **Connection:** Direct TCP to VESCHub
- **BMS:** Connected via UART (requires streaming to be enabled)
- **Commands that work:**
  - ✓ `COMM_FW_VERSION (0x00)` - Returns firmware info
  - ✓ `COMM_SET_APPCONF (0x14)` - Returns 21 bytes (config confirmation?)
  - ✗ `COMM_GET_VALUES (0x04)` - Timeout
  - ✗ `COMM_BMS_GET_VALUES (0x60/0x32)` - Timeout

### 2. ADV500 Motor Controller (CAN ID 84)
- **Firmware:** v6.5 - ADV500
- **Connection:** CAN bus via VESC Express
- **Access Method:** COMM_FORWARD_CAN (0x22) with CAN ID 84
- **Commands that work:**
  - ✓ `COMM_FW_VERSION (0x00)` - Returns firmware info
  - ✓ `COMM_GET_VALUES (0x04)` - Returns motor values (74 bytes)
    - Temperature FET/Motor
    - Current (motor, input, filtered)
    - Voltage
    - RPM
    - Duty cycle
    - Amp/Watt hours
    - Tachometer
    - Fault code
  - ✗ `COMM_BMS_GET_VALUES (0x60)` - No BMS on motor controller

---

## Key Findings

### ✓ What Works:
1. **TCP connection to VESCHub** - Stable, doesn't close on failed commands
2. **FW_VERSION command** - Works on both VESC Express and CAN devices
3. **CAN forwarding** - Successfully communicates with CAN ID 84
4. **Motor controller data** - Full telemetry from ADV500 via CAN

### ✗ What Doesn't Work (Yet):
1. **Direct BMS commands** - Timeout (BMS streaming not enabled)
2. **Direct GET_VALUES on VESC Express** - Timeout
3. **Passive data reception** - No pushed data (streaming not enabled)

### 🔧 What's Required:
1. **Enable BMS data streaming in VESCTool configuration**
2. Once enabled, BMS data will likely:
   - Be pushed automatically (passive receive)
   - OR be available via COMM_BMS_GET_VALUES
   - OR be embedded in COMM_GET_VALUES

---

## BMS Data Streaming Setup

**User Notes:**
> "I have to enable bms data streaming in vesctool before seeing the data"

**Next Steps:**
1. Enable BMS data streaming in VESCTool app settings
2. Reconnect and listen for passive data
3. Test COMM_BMS_GET_VALUES again after enabling
4. Check if data appears in COMM_GET_VALUES

---

## VESC Protocol Details

### Packet Structure:
```
Short:  [0x02][len][payload][crc_h][crc_l][0x03]
Long:   [0x02][len_h][len_l][payload][crc_h][crc_l][0x03]
```

### CAN Forwarding:
```python
# Forward command to CAN device
payload = bytes([COMM_FORWARD_CAN, can_id, wrapped_command])
# Response comes back directly (not wrapped in FORWARD_CAN)
```

### Authentication:
```
Format: "VESCTOOL:{vesc_id}:{password}\n"
Sent immediately after TCP connection
```

---

## Command Reference

| Command | ID | Works Direct | Works CAN ID 84 | Notes |
|---------|----|--------------|-----------------| ------|
| COMM_FW_VERSION | 0x00 | ✓ | ✓ | Always works |
| COMM_GET_VALUES | 0x04 | ✗ | ✓ | Motor values from CAN device |
| COMM_SET_APPCONF | 0x14 | ✓ | ? | Returns 21 bytes |
| COMM_FORWARD_CAN | 0x22 | ✓ | N/A | For CAN devices |
| COMM_BMS_GET_VALUES | 0x60 | ✗ | ✗ | Needs streaming enabled |

---

## BMS Data Format (Expected)

Based on VESC protocol docs, BMS_GET_VALUES should return:

```python
struct BMS_Values {
    float v_tot;           // Total voltage
    float v_charge;        // Charge voltage
    float i_in;           // Input current
    float i_in_ic;        // Input current (IC)
    float ah_cnt;         // Amp-hour counter
    float wh_cnt;         // Watt-hour counter
    uint8_t cell_num;     // Number of cells
    uint16_t cells[32];   // Cell voltages (mV)
    uint32_t bal_state;   // Balance state bitmap
    uint8_t temp_num;     // Number of temp sensors
    uint16_t temps[10];   // Temperatures (0.1°C)
    float soc;            // State of charge (%)
    float soh;            // State of health (%)
    float capacity_ah;    // Capacity (Ah)
}
```

---

## Home Assistant Integration Plan

Once BMS streaming is enabled:

### Option A: Passive Receive (Recommended)
```python
# Listen for pushed BMS data
while True:
    packet = await read_packet()
    if packet[0] == COMM_BMS_GET_VALUES:
        parse_bms_data(packet)
```

### Option B: Request/Response
```python
# Poll for BMS data
response = await send_command(COMM_BMS_GET_VALUES)
if response:
    parse_bms_data(response)
```

### Option C: CAN Forwarding (If BMS has CAN interface)
```python
# Forward BMS request to specific CAN ID
can_data = bytes([bms_can_id, COMM_BMS_GET_VALUES])
response = await send_command(COMM_FORWARD_CAN, can_data)
```

---

## Files Created

- `explore_vesc.py` - Comprehensive exploration script
- `test_can_84.py` - CAN ID 84 specific tests
- `scan_for_bms.py` - CAN bus scanner
- `test_direct_bms.py` - Direct BMS command tests
- `test_vesc_express_values.py` - Command enumeration
- `parse_can84_response.py` - ADV500 data parser
- `.env` - Credentials (git ignored)
- `.env.example` - Credential template
- `exploration_notes.md` - Detailed test results

---

## Next Actions

1. **Enable BMS streaming in VESCTool:**
   - Connect with VESCTool app
   - Go to App Settings
   - Enable "BMS UART App" or similar streaming option
   - Save configuration to VESC Express

2. **Test passive receive:**
   ```bash
   python3 test_direct_bms.py
   # Should see BMS data packets now
   ```

3. **Update HA integration:**
   - Add passive receive mode to coordinator
   - Parse incoming BMS packets
   - Create sensors for BMS values

4. **Add CAN device support:**
   - Expose ADV500 motor controller data
   - Make CAN ID configurable
   - Support multiple CAN devices

---

## Questions for User

1. How to enable BMS streaming in VESCTool?
2. What type of BMS is connected?
3. Should we also expose motor controller (ADV500) data in HA?
4. Preferred update interval for BMS data?
