# Development Guide

## Architecture

This integration follows Home Assistant's best practices for custom integrations:

```
veschub/
├── __init__.py           # Integration setup and platform loading
├── config_flow.py        # UI configuration flow
├── const.py              # Constants and configuration
├── sensor.py             # Sensor platform implementation
├── vesc_protocol.py      # VESC protocol over TCP
├── manifest.json         # Integration metadata
├── strings.json          # UI strings
└── translations/
    └── en.json          # English translations
```

## VESC Protocol Implementation

### Protocol Overview

The VESC protocol uses a packet-based structure:

```
[Start Byte] [Length] [Payload] [CRC16] [Stop Byte]
     0x02    1-2 bytes  N bytes  2 bytes    0x03
```

### Packet Formats

**Short Format** (payload ≤ 256 bytes):
```
[0x02] [len] [payload] [crc_high] [crc_low] [0x03]
```

**Long Format** (payload > 256 bytes):
```
[0x02] [len_high] [len_low] [payload] [crc_high] [crc_low] [0x03]
```

### CRC Calculation

Uses CRC16 with polynomial 0x1021 (same as XMODEM):

```python
def _calculate_crc16(data: bytes) -> int:
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

## BMS Data Structure

### COMM_BMS_GET_VALUES Response

The BMS data is parsed from the response payload:

```
Offset | Type    | Field
-------|---------|----------------
0      | float32 | Total voltage (V)
4      | float32 | Charge voltage (V)
8      | float32 | Input current (A)
12     | float32 | Input current IC (A)
16     | float32 | Amp-hour counter (Ah)
20     | float32 | Watt-hour counter (Wh)
24     | uint8   | Number of cells
25+    | uint16  | Cell 1 voltage (mV)
27+    | uint16  | Cell 2 voltage (mV)
...    | ...     | ...
N      | uint32  | Balance state (bitmask)
N+4    | uint8   | Number of temp sensors
N+5    | uint16  | Temp 1 (0.1°C)
...    | ...     | ...
M      | float32 | State of Charge (%)
M+4    | float32 | State of Health (%)
M+8    | float32 | Capacity (Ah)
```

Note: Actual structure may vary based on VESC firmware version.

## Key Components

### VESCProtocol (vesc_protocol.py)

Handles TCP communication with VESCHub:

- `connect()` - Establish TCP connection
- `disconnect()` - Close connection
- `get_bms_values()` - Request and parse BMS data
- `_send_command()` - Send VESC protocol command
- `_read_packet()` - Read and validate response packet
- `_pack_payload()` - Create VESC protocol packet

### VESCDataUpdateCoordinator (sensor.py)

Manages polling and data updates:

- Implements Home Assistant's DataUpdateCoordinator
- Handles connection management
- Updates all sensors atomically
- Manages update interval and errors

### Sensor Entities

- `VESCBMSSensor` - Basic BMS metrics
- `VESCCellVoltageSensor` - Individual cell voltages (dynamic)
- `VESCTemperatureSensor` - Temperature sensors (dynamic)

## Testing

### Local Testing

1. **Set up test environment**:
   ```bash
   # Clone repository
   git clone https://github.com/YOUR_USERNAME/ha_veschub
   cd ha_veschub
   ```

2. **Test protocol locally**:
   ```python
   import asyncio
   from custom_components.veschub.vesc_protocol import VESCProtocol

   async def test():
       vesc = VESCProtocol("YOUR_VESCHUB_IP", 65102)
       if await vesc.connect():
           data = await vesc.get_bms_values()
           print(data)
           await vesc.disconnect()

   asyncio.run(test())
   ```

### Integration Testing

1. **Install in development mode**:
   - Copy to Home Assistant `custom_components/`
   - Enable debug logging

2. **Enable debug logging**:
   ```yaml
   # configuration.yaml
   logger:
     default: info
     logs:
       custom_components.veschub: debug
   ```

3. **Monitor logs**:
   - Watch for connection events
   - Verify data parsing
   - Check update cycles

### Unit Tests

To add unit tests (future enhancement):

```python
# tests/test_vesc_protocol.py
import pytest
from custom_components.veschub.vesc_protocol import VESCProtocol

def test_crc_calculation():
    protocol = VESCProtocol("localhost", 65102)
    # Test known CRC values
    data = b'\x32\x00\x00\x00'
    crc = protocol._calculate_crc16(data)
    assert crc == 0x1234  # Replace with actual expected value
```

## Debugging

### Enable Packet Logging

Uncomment debug logs in `vesc_protocol.py`:

```python
_LOGGER.debug(f"Sending packet: {packet.hex()}")
_LOGGER.debug(f"Received payload: {payload.hex()}")
```

### Wireshark Capture

Capture TCP traffic to analyze protocol:

```bash
# Capture VESCHub traffic
sudo tcpdump -i any -w veschub.pcap host YOUR_VESCHUB_IP and port 65102

# Analyze in Wireshark
wireshark veschub.pcap
```

### Common Issues

1. **CRC Mismatch**:
   - Verify CRC calculation matches VESC implementation
   - Check byte order (big-endian for VESC)

2. **Parse Errors**:
   - Firmware version differences
   - Different BMS models
   - Add defensive parsing with length checks

3. **Connection Timeouts**:
   - Network latency
   - VESCHub busy
   - Adjust timeout values

## Extending the Integration

### Adding New Sensors

1. **Add constant** in `const.py`:
   ```python
   SENSOR_NEW_VALUE = "new_value"
   ```

2. **Update BMS parser** in `vesc_protocol.py`:
   ```python
   bms_data["new_value"] = read_float32(index)
   ```

3. **Add sensor** in `sensor.py`:
   ```python
   VESCBMSSensor(
       coordinator,
       entry,
       "new_value",
       "New Value",
       "unit",
       SensorDeviceClass.VOLTAGE,
       SensorStateClass.MEASUREMENT,
       "mdi:icon",
   )
   ```

### Supporting Different VESC Firmware Versions

Add version detection and conditional parsing:

```python
async def get_firmware_version(self) -> str:
    response = await self._send_command(COMM_FW_VERSION)
    # Parse firmware version
    return version

async def get_bms_values(self) -> Optional[dict]:
    # Parse differently based on firmware version
    if self.firmware_version >= "5.0":
        # New format
    else:
        # Old format
```

### Adding Binary Sensors

Create `binary_sensor.py` for boolean states:

```python
# binary_sensor.py
class VESCBMSBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for BMS states."""

    @property
    def is_on(self) -> bool:
        # Return True/False based on BMS state
        return self.coordinator.data.get("charging", False)
```

Update `__init__.py`:
```python
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
```

## Code Style

Follow Home Assistant's style guide:

- Use `black` for formatting
- Use `pylint` for linting
- Type hints for all functions
- Docstrings for public methods

```bash
# Format code
black custom_components/veschub/

# Lint code
pylint custom_components/veschub/
```

## Contributing

1. Fork repository
2. Create feature branch
3. Make changes
4. Test thoroughly
5. Submit pull request

### Pull Request Checklist

- [ ] Code follows Home Assistant style guide
- [ ] All functions have type hints
- [ ] Docstrings added/updated
- [ ] Tested with real hardware
- [ ] No new dependencies added (or justified)
- [ ] Updated README if needed
- [ ] Debug logging added for troubleshooting

## Resources

- [VESC Project](https://vesc-project.com/)
- [VESC Tool Source](https://github.com/vedderb/vesc_tool)
- [VESC BMS Firmware](https://github.com/vedderb/vesc_bms_fw)
- [Home Assistant Developer Docs](https://developers.home-assistant.io/)
- [Home Assistant Integration Quality Scale](https://developers.home-assistant.io/docs/integration_quality_scale_index/)

## Version History

### 1.0.0 (2025-12-26)
- Initial release
- TCP connection to VESCHub
- BMS data sensors
- Config flow UI
- HACS compatibility

## License

Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0) - See LICENSE file
