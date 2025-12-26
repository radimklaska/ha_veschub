# Testing Notes

## Connection Test Results

The integration has been tested against the public VESCHub endpoint:
- **Host**: veschub.vedder.se
- **Port**: 65101
- **Status**: Successfully connects and authenticates

### Authentication

The VESCHub authentication protocol has been successfully implemented:
- Format: `VESCTOOL:UUID:PASSWORD\n`
- Authentication is sent immediately after TCP connection
- The integration now supports both authenticated (public hub) and unauthenticated (local hub) connections

### Current Status

The VESC is online and pingable, but was not actively transmitting BMS data during testing. This is expected behavior - VESC devices typically send data when:
1. Actively in use (motor running, battery charging/discharging)
2. Configured to push telemetry periodically
3. Responding to commands from VESC Tool

## What's Implemented

✅ **TCP Connection**: Successfully connects to VESCHub
✅ **Authentication**: Supports VESC ID and password for public VESCHub
✅ **VESC Protocol**: Implements packet framing with CRC16 validation
✅ **BMS Data Parser**: Parses all BMS values including:
   - Total voltage, charge voltage
   - Input current (with IC measurement)
   - Amp-hour and watt-hour counters
   - Individual cell voltages (dynamic, up to 32 cells)
   - Temperature sensors (dynamic, up to 10 sensors)
   - State of Charge (SoC) and State of Health (SoH)
   - Battery capacity
   - Balance state

✅ **Home Assistant Integration**:
   - Config flow with UI setup
   - Optional authentication fields
   - Data update coordinator with configurable polling
   - Dynamic sensor creation
   - Proper entity naming and device info

✅ **HACS Compatible**:
   - Proper manifest.json
   - Translation files
   - Documentation

## Testing Needed

To fully test the integration, we need to capture BMS data when your VESC is actively transmitting. This happens when:

### Scenario 1: Active Use
- Turn on your VESC-powered device
- Start the motor/load
- Monitor battery activity
- BMS data should flow

### Scenario 2: VESC Tool Connection
- Connect to the same VESC with VESC Tool
- Open the BMS view
- This should trigger data transmission

### Scenario 3: Periodic Telemetry
- Some VESC configurations send periodic updates
- May need to configure this in VESC Tool settings

## How to Test When VESC Is Active

### Option 1: Using Test Script

When your VESC is actively transmitting, run:

```bash
cd /home/radimklaska/Documents/ha_veschub
python3 test_receive_loop.py
```

This will:
- Connect and authenticate
- Wait for incoming BMS packets
- Parse and display the data
- Help verify the parsing logic is correct

### Option 2: Install in Home Assistant

1. Copy integration to Home Assistant:
   ```bash
   cp -r custom_components/veschub /config/custom_components/
   ```

2. Restart Home Assistant

3. Add integration:
   - Settings → Devices & Services
   - Add Integration → VESC Hub BMS
   - Enter:
     - Host: `veschub.vedder.se` (or your local VESCHub IP)
     - Port: `65101` (public hub) or `65102` (local hub)
     - VESC ID: `your-vesc-id` (for public hub)
     - Password: `your-password` (for public hub)
     - Update Interval: `5` seconds

4. Monitor logs:
   ```yaml
   # configuration.yaml
   logger:
     default: info
     logs:
       custom_components.veschub: debug
   ```

5. Check for sensors:
   - Go to the VESC BMS device
   - Verify sensors are created
   - Check if they update with values

## Expected Sensors

Once BMS data is received, you should see:

### Main Sensors
- `sensor.vesc_bms_total_voltage`
- `sensor.vesc_bms_charge_voltage`
- `sensor.vesc_bms_input_current`
- `sensor.vesc_bms_input_current_ic`
- `sensor.vesc_bms_amp_hours`
- `sensor.vesc_bms_watt_hours`
- `sensor.vesc_bms_state_of_charge`
- `sensor.vesc_bms_state_of_health`
- `sensor.vesc_bms_capacity`
- `sensor.vesc_bms_balance_state`

### Dynamic Sensors (Based on Your BMS Configuration)
- `sensor.vesc_bms_cell_1_voltage` through `sensor.vesc_bms_cell_N_voltage`
- `sensor.vesc_bms_temperature_1` through `sensor.vesc_bms_temperature_N`

## Known Behaviors

### Passive vs. Active Polling

The current implementation uses **active polling**:
- Sends `COMM_BMS_GET_VALUES` command
- Waits for response
- Parses and updates sensors

An alternative approach (for future enhancement) could be **passive listening**:
- Connect and authenticate
- Listen for pushed data
- Parse incoming packets
- This might work better with VESCHub

### Connection Persistence

The integration maintains a persistent connection:
- Connects during setup
- Keeps connection alive
- Reconnects on errors
- Disconnects on unload

## Troubleshooting

### No Data Received

If sensors show "Unknown" or "Unavailable":

1. **Check VESC is transmitting**:
   ```bash
   python3 test_receive_loop.py
   ```
   Wait 30 seconds to see if any data arrives

2. **Try with VESC Tool**:
   - Connect with VESC Tool simultaneously
   - Check if BMS data appears in tool
   - This confirms VESC is working

3. **Check logs**:
   ```bash
   # In Home Assistant
   grep veschub home-assistant.log
   ```
   Look for:
   - Connection errors
   - Timeout messages
   - Parse errors

### Timeout Errors

If you see timeout errors:
- VESC might not be connected to hub
- VESC might be in sleep mode
- Increase update interval to 30-60 seconds
- Try when VESC is actively in use

### Authentication Errors

If connection fails:
- Verify VESC ID and password
- Test with PING script:
  ```bash
  python3 test_ping.py
  ```
- Check VESCHub account settings

## Next Steps

1. **Test with Active VESC**: Run tests when your VESC is actively transmitting
2. **Verify Parsing**: Ensure all BMS values are correctly parsed
3. **Adjust Timeouts**: May need to increase timeouts if data is infrequent
4. **Consider Passive Mode**: Might switch to passive listening if active polling doesn't work
5. **Add Error Handling**: Enhance error messages based on real-world issues

## Contact

Once you've had a chance to test with an active VESC, let me know:
- What sensors appear
- What values you see
- Any errors in the logs
- Whether data updates regularly

This will help fine-tune the integration for optimal performance!
