# BMS Data Access - SOLUTION FOUND! 🎉

**Date:** 2025-12-28
**Status:** ✅ WORKING

---

## The Problem

BMS data was accessible in VESCTool but our implementation couldn't retrieve it despite:
- Correct protocol implementation
- Correct authentication
- Sending the right command (COMM_BMS_GET_VALUES = 0x60)

---

## The Discovery Process

### Packet Capture Analysis
Captured VESCTool's traffic to veschub.vedder.se and found:

**VESCTool sends 4 commands in sequence:**
1. `COMM_FW_VERSION` (0x00)
2. `COMM_GET_CUSTOM_CONFIG` (0x5d) with data `0x00` ⭐
3. `COMM_PING_CAN` (0x3e) ⭐
4. `COMM_BMS_GET_VALUES` (0x60)

Commands 2 and 3 were the missing setup commands!

---

## The Solution

**The key is sending ALL commands RAPIDLY without waiting for individual responses:**

### Rapid-Fire Sequence:
```python
# Connect and auth
writer.write(f"VESCTOOL:{vesc_id}:{password}\n".encode())

# Send ALL commands at once (no waiting!)
writer.write(pack_vesc_packet(bytes([0x00])))  # FW_VERSION
writer.write(pack_vesc_packet(bytes([0x5d, 0x00])))  # GET_CUSTOM_CONFIG + 0x00
writer.write(pack_vesc_packet(bytes([0x3e])))  # PING_CAN
writer.write(pack_vesc_packet(bytes([0x60])))  # BMS_GET_VALUES
await writer.drain()

# THEN read all responses
responses = []
while True:
    try:
        data = await asyncio.wait_for(reader.read(500), timeout=1.0)
        responses.append(data)
    except asyncio.TimeoutError:
        break
```

### Why This Works:

**Hypothesis:** The VESC Express/VESCHub requires the setup commands (GET_CUSTOM_CONFIG and PING_CAN) to initialize BMS access, but these commands must be sent rapidly in sequence. Waiting between commands causes a session state reset.

---

## The Result

**Successfully retrieved BMS data:**
- ✅ 20 cells at ~4.18V each
- ✅ Cell balance: 8mV delta (excellent!)
- ✅ Total voltage: ~83.6V
- ✅ All BMS fields accessible

**Sample output:**
```
Cell  1: 4.176 V
Cell  2: 4.178 V
...
Cell 20: 4.180 V

Statistics:
  Average:  4.180 V
  Minimum:  4.176 V
  Maximum:  4.184 V
  Delta:    8.0 mV
  Balance:  ✓ Excellent
```

---

## Implementation for Home Assistant

### Modified Update Sequence:

```python
async def _async_update_data(self):
    """Fetch BMS data using rapid-fire command sequence."""

    if not self.vesc.is_connected:
        await self.vesc.connect()

    # Send setup + BMS commands rapidly
    await self.vesc._send_raw(bytes([0x00]))  # FW (keep-alive)
    await self.vesc._send_raw(bytes([0x5d, 0x00]))  # Setup 1
    await self.vesc._send_raw(bytes([0x3e]))  # Setup 2
    await self.vesc._send_raw(bytes([0x60]))  # BMS request
    await self.vesc.writer.drain()

    # Collect all responses
    bms_data = None
    timeout = time.time() + 3.0

    while time.time() < timeout:
        try:
            data = await asyncio.wait_for(
                self.vesc.reader.read(500),
                timeout=0.5
            )

            # Find BMS packet (starts with 02 [len] 60...)
            if b'\x60' in data:
                bms_data = self._parse_bms_from_stream(data)
                if bms_data:
                    break

        except asyncio.TimeoutError:
            break

    return bms_data
```

---

## Key Commands Explained

### COMM_GET_CUSTOM_CONFIG (0x5d) + 0x00
- Retrieves custom hardware configuration
- Response contains device info, VESCHub settings
- **Purpose:** Initializes device context for BMS access

### COMM_PING_CAN (0x3e)
- Pings CAN bus devices
- Response indicates active CAN devices
- **Purpose:** Discovers/wakes CAN devices (even though BMS is UART-based)

### Why Both Are Needed:
The VESC Express likely uses these commands to:
1. Load the custom config that defines BMS presence
2. Initialize the CAN bus (which the BMS monitoring might depend on)

Without both commands in rapid succession, the BMS query returns no data.

---

## Testing

### Verification Script:
```bash
cd /home/radimklaska/Documents/ha_veschub
python3 << 'EOF'
# [See rapid-fire test script above]
EOF
```

**Expected output:**
- 3 responses (FW, CONFIG, BMS)
- Response 3 contains `0x60` (BMS marker)
- 20 cell voltages parsed correctly

---

## Next Steps

1. ✅ **Solution found and tested**
2. ⏳ **Update HA integration** with rapid-fire sequence
3. ⏳ **Add proper BMS sensor entities**
4. ⏳ **Test continuous polling** (does it keep working?)
5. ⏳ **Add motor controller (CAN 84)** data as bonus

---

## Files

**Test scripts that work:**
- Rapid-fire inline Python script (above)
- `bms_response.bin` - Captured BMS data

**Documentation:**
- This file (SOLUTION.md)
- FINDINGS.md - Investigation summary
- PACKET_CAPTURE_GUIDE.md - How we found it

---

## Credits

Solution found through:
1. VESCTool source code analysis
2. Packet capture of working VESCTool session
3. Systematic command testing
4. Discovery that rapid-fire sending works

**Total exploration time:** ~6 hours
**Number of test approaches:** 17+
**Breakthrough method:** Packet capture + rapid-fire command sending

---

## Conclusion

The BMS data IS accessible via TCP/VESCHub, but requires:
- Correct command sequence (0x00 → 0x5d+0x00 → 0x3e → 0x60)
- Rapid-fire sending (no waiting between commands)
- Reading all responses together

This can now be integrated into Home Assistant for continuous BMS monitoring! 🚀
