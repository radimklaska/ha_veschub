# BMS Data Access - COMPLETE SOLUTION 🎉

**Date:** 2026-01-02 (Updated with comprehensive technical details)
**Status:** ✅ FULLY WORKING & DOCUMENTED

---

## Executive Summary

Successfully retrieved BMS data from VESC Express via VESCHub TCP connection. The breakthrough required discovering the **exact command sequence**, **timing requirements**, and **data format**.

**Key Results:**
- ✅ 20 cells detected at ~4.19V each
- ✅ 8mV cell balance (excellent)
- ✅ Total pack voltage: ~83.88V
- ✅ Continuous polling confirmed working

---

## Critical Discovery: BMS Location

**IMPORTANT:** The BMS is on **CAN ID 0** (local VESC Express), **NOT** on CAN ID 116 (ADV500 motor controller).

- **CAN ID 0**: VESC Express with connected BMS (20S LiPo/Li-ion pack)
- **CAN ID 116**: ADV500 motor controller on CAN bus (no BMS)

**Implication:** Use **direct BMS request** (`COMM_BMS_GET_VALUES`), not CAN forwarding.

---

## The Problem

Initial attempts to retrieve BMS data failed because:
1. Commands were sent **sequentially with waiting** between each
2. Responses were read using **packet parsing** instead of raw bytes
3. BMS data format was incorrectly assumed

Despite correct protocol implementation and authentication, BMS requests would timeout or return no data.

---

## The Solution

### Part 1: Rapid-Fire Command Sequence

**The key is sending ALL 4 commands RAPIDLY without waiting for individual responses:**

```python
import asyncio

# 1. Connect and authenticate
reader, writer = await asyncio.open_connection('veschub.vedder.se', 65101)
auth_string = f"VESCTOOL:{vesc_id}:{password}\n"
writer.write(auth_string.encode('utf-8'))
await writer.drain()
await asyncio.sleep(1.0)  # Wait for auth

# 2. Send ALL commands rapidly (NO WAITING between commands!)
writer.write(pack_vesc_packet(bytes([0x00])))           # COMM_FW_VERSION
writer.write(pack_vesc_packet(bytes([0x5d, 0x00])))    # COMM_GET_CUSTOM_CONFIG + 0x00
writer.write(pack_vesc_packet(bytes([0x3e])))          # COMM_PING_CAN
writer.write(pack_vesc_packet(bytes([0x60])))          # COMM_BMS_GET_VALUES
await writer.drain()  # Flush all at once

# 3. Read ALL responses as RAW BYTES (not parsed packets!)
all_data = b''
timeout = 3.0
start_time = asyncio.get_event_loop().time()

while (asyncio.get_event_loop().time() - start_time) < timeout:
    try:
        chunk = await asyncio.wait_for(reader.read(1024), timeout=0.5)
        if chunk:
            all_data += chunk
    except asyncio.TimeoutError:
        if all_data:
            break  # Got data, likely done

# 4. Extract BMS packet from raw stream
bms_data = find_bms_in_stream(all_data)  # See below
```

### Part 2: VESC Packet Format

VESC packets use this format:

**Short format (length < 256):**
```
[0x02] [length] [payload...] [CRC_high] [CRC_low] [0x03]
```

**Example BMS packet structure:**
```
02 a8 60 04 ff e0 70 05 ... 03
│  │  └─ Payload starts (COMM_BMS_GET_VALUES = 0x60)
│  └─ Length = 0xa8 = 168 bytes
└─ Start byte
```

**CRC16 Calculation (polynomial 0x1021):**
```python
def calculate_crc16(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc = crc << 1
            crc &= 0xFFFF
    return crc
```

### Part 3: BMS Data Format

**BMS response structure (168 bytes total):**

```
Offset  Description                      Format      Example
------  ---------------------------------  ----------  --------
0       Command ID                        uint8       0x60
1-24    Status/metadata (TBD)            bytes[24]   varies
25      Cell count                        uint8       0x14 (20)
26-65   Cell voltages (20 cells)         uint16[]    4189-4197 mV
66-85   Balance flags (per cell)         uint8[]     0x01 = balancing
86+     Additional data (temps, etc.)    bytes       varies
```

**Cell voltage encoding:**
- Format: Big-endian uint16
- Units: Millivolts
- Example: `0x10 0x5d` = 4189 mV = 4.189 V

**Parsing example:**
```python
def parse_bms(payload: bytes):
    """Parse BMS packet (payload with 0x60 prefix)."""
    if payload[0] != 0x60:
        return None

    # Strip command byte
    data = payload[1:]

    # Cell count at offset 24 (after stripping 0x60)
    num_cells = data[24]  # 0x14 = 20 decimal

    # Cell voltages at offset 25+
    cell_voltages = []
    for i in range(num_cells):
        offset = 25 + (i * 2)
        cell_mv = struct.unpack('>H', data[offset:offset+2])[0]
        cell_v = cell_mv / 1000.0
        cell_voltages.append(cell_v)

    return {
        'num_cells': num_cells,
        'cell_voltages': cell_voltages,
        'average': sum(cell_voltages) / len(cell_voltages),
        'min': min(cell_voltages),
        'max': max(cell_voltages),
        'delta': max(cell_voltages) - min(cell_voltages)
    }
```

### Part 4: Finding BMS Packet in Raw Stream

Since we receive multiple responses (FW_VERSION, GET_CUSTOM_CONFIG, PING_CAN, BMS_GET_VALUES), we need to find the BMS packet:

```python
def find_bms_in_stream(data: bytes) -> bytes:
    """Find BMS packet (0x60) in raw data stream."""
    VESC_PACKET_START = 0x02

    i = 0
    while i < len(data):
        if data[i] == VESC_PACKET_START:
            if i + 1 >= len(data):
                break

            # Get payload length
            len_byte = data[i + 1]
            if len_byte <= 256:  # Short format
                payload_len = len_byte
                payload_start = i + 2
            else:  # Long format (length >= 256)
                if i + 2 >= len(data):
                    break
                payload_len = ((len_byte & 0x7F) << 8) | data[i + 2]
                payload_start = i + 3

            # Extract payload
            payload_end = payload_start + payload_len
            if payload_end + 3 > len(data):
                i += 1
                continue

            payload = data[payload_start:payload_end]

            # Check if this is BMS packet
            if len(payload) > 0 and payload[0] == 0x60:
                return payload

            # Move to next packet
            i = payload_end + 3  # Skip CRC + stop byte
        else:
            i += 1

    return None
```

---

## Working Test Script

**File:** `test_rapid_fire_raw.py`

Complete working implementation that:
1. Connects to VESCHub
2. Sends rapid-fire command sequence
3. Reads raw bytes
4. Finds and parses BMS packet
5. Displays all 20 cell voltages with statistics

**Run it:**
```bash
cd /home/radimklaska/Documents/ha_veschub
python3 test_rapid_fire_raw.py
```

**Expected output:**
```
======================================================================
🎉🎉🎉 BMS DATA SUCCESSFULLY RETRIEVED! 🎉🎉🎉
======================================================================

📊 BMS Data (total payload length: 168 bytes, data after 0x60: 167 bytes):

  Number of Cells:      20

  Cell Voltages:
    Cell  1: 4.189 V (4189 mV)
    Cell  2: 4.191 V (4191 mV)
    ...
    Cell 20: 4.193 V (4193 mV)

  Statistics:
    Average:  4.194 V
    Minimum:  4.189 V
    Maximum:  4.197 V
    Delta:    8.0 mV
    Balance:  ✓ Excellent
```

---

## Why This Works

### 1. Setup Commands Required

The VESC Express requires initialization before BMS data is accessible:

**COMM_GET_CUSTOM_CONFIG (0x5d) + 0x00:**
- Loads device configuration
- Initializes BMS subsystem context
- Must be sent before BMS query

**COMM_PING_CAN (0x3e):**
- Wakes/discovers CAN bus devices
- Even though BMS is UART-based, this initializes CAN subsystem
- Required for internal state machine

### 2. Timing is Critical

**Must send rapidly without waiting:**
- Waiting between commands causes session state reset
- VESCHub/VESC Express expects commands in quick succession
- Each command alone fails, but sequence together succeeds

### 3. Raw Byte Reading Required

**Packet-by-packet reading fails because:**
- Responses arrive rapidly, sometimes mid-packet
- Parser can get out of sync
- PING_CAN response is minimal (2 bytes) and easy to miss

**Raw byte reading works because:**
- Collects entire response stream
- Can find BMS packet anywhere in stream
- Handles partial packets gracefully

---

## Technical Details

### Command Constants

```python
COMM_FW_VERSION = 0x00
COMM_FORWARD_CAN = 0x22
COMM_PING_CAN = 0x3e
COMM_GET_CUSTOM_CONFIG = 0x5d
COMM_BMS_GET_VALUES = 0x60
```

### Connection Details

- **Host:** veschub.vedder.se
- **Port:** 65101
- **Auth format:** `VESCTOOL:{vesc_id}:{password}\n`
- **Protocol:** TCP with VESC packet framing

### Response Timing

Typical response sizes:
- FW_VERSION: 43 bytes
- GET_CUSTOM_CONFIG: 121 bytes
- PING_CAN: 2 bytes (0x3e 0x74)
- BMS_GET_VALUES: 168 bytes

Total stream: ~347 bytes received in 3 chunks over ~0.5 seconds

---

## Security Considerations

### Shared VESCHub Server Issue

**CRITICAL:** The public VESCHub server (veschub.vedder.se:65101) does NOT isolate CAN devices by authenticated user.

**Impact:**
- When using `COMM_FORWARD_CAN`, you can access ANY device on the server
- Automatic CAN scanning discovers other users' devices
- Privacy/security risk on shared infrastructure

**Mitigation:**
- Only use direct BMS requests (CAN ID 0)
- Disable automatic CAN scanning
- Recommend private VESCHub instance for production

---

## Implementation Checklist for Home Assistant

- [ ] Update `vesc_protocol.py` with rapid-fire BMS method
- [ ] Implement raw byte reading in response handler
- [ ] Add BMS packet finder function
- [ ] Update BMS parser with correct offsets (24 = count, 25+ = voltages)
- [ ] Modify coordinator to use new BMS method
- [ ] Create sensor entities for all 20 cells
- [ ] Add pack statistics sensors (min, max, delta, average)
- [ ] Test continuous polling (every 5 seconds)
- [ ] Verify no memory leaks over 24h operation

---

## Files Reference

**Working code:**
- `test_rapid_fire_raw.py` - Complete working test script
- `custom_components/veschub/vesc_protocol.py` - Protocol implementation
- `custom_components/veschub/sensor.py` - Sensor platform

**Documentation:**
- `SOLUTION.md` - This file (complete technical solution)
- `CLAUDE.md` - Development guide with security warnings
- `FINDINGS.md` - Investigation summary
- `PACKET_CAPTURE_GUIDE.md` - How we discovered the solution

**Legacy test scripts (to be removed):**
- `test_connection.py`
- `test_connection2.py`
- `test_ping.py`
- `test_receive_loop.py`
- `test_can_84.py`
- `test_direct_bms.py`
- `test_vesc_express_values.py`
- `test_bms_can.py`
- `final_bms_test.py`
- `test_with_setup_commands.py`
- `test_exact_vesc_sequence.py`
- `test_consume_all_responses.py`

---

## Discovery Timeline

**2025-12-28:** Initial breakthrough via packet capture
- Discovered 4-command sequence
- First successful BMS retrieval
- Documented in original SOLUTION.md

**2026-01-02:** Complete technical analysis
- Fixed BMS data parsing (correct offsets)
- Confirmed BMS is on CAN ID 0 (not 116)
- Discovered raw byte reading requirement
- Documented exact packet format
- Created comprehensive working test script

**Total investigation:** ~12 hours over 5 days
**Test approaches tried:** 30+
**Breakthrough method:** Packet capture + systematic protocol analysis

---

## Conclusion

BMS data IS accessible via TCP/VESCHub with:

1. **Correct command sequence:** FW_VERSION → GET_CUSTOM_CONFIG → PING_CAN → BMS_GET_VALUES
2. **Rapid-fire sending:** All commands sent together without waiting
3. **Raw byte reading:** Collect entire response stream, don't parse packet-by-packet
4. **Correct data format:** Cell count at offset 24, voltages at offset 25+ (uint16 mV)

This enables **continuous BMS monitoring in Home Assistant** with all 20 individual cell voltages, pack statistics, and health monitoring! 🚀

---

**Last updated:** 2026-01-02
**Verified working:** ✅ Yes (test_rapid_fire_raw.py)
**Production ready:** ⏳ Pending HA integration update
