# Quick Start Guide - VESC Hub BMS Integration

## Installation Steps

### 1. Install via HACS

If you want to publish this to HACS:
1. Create a GitHub repository and push this code
2. Add the repository to HACS as a custom repository
3. Install through HACS UI

### 2. Manual Installation

Copy the `custom_components/veschub` folder to your Home Assistant configuration directory:

```bash
# On your Home Assistant system
cd /config
mkdir -p custom_components
cp -r /path/to/ha_veschub/custom_components/veschub custom_components/
```

### 3. Restart Home Assistant

After installation, restart Home Assistant to load the integration.

## Configuration

### 1. Find Your VESCHub IP Address

First, you need to know the IP address of your VESCHub. You can:
- Check your router's DHCP client list
- Use a network scanner
- Check the VESCHub documentation for connection details

### 2. Add the Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration** (bottom right)
3. Search for **VESC Hub BMS**
4. Enter your connection details:
   - **Host**: Your VESCHub IP (e.g., `192.168.1.100`)
   - **Port**: Default is `65102` (adjust if your VESCHub uses a different port)
   - **Update Interval**: `5` seconds (recommended, adjust based on your needs)

### 3. Verify Connection

After adding the integration:
- Check **Settings** → **Devices & Services** → **VESC Hub BMS**
- You should see a device called "VESC BMS"
- Click on the device to see all available sensors

## Available Sensors

Once configured, you'll have access to:

### Main Sensors
- `sensor.vesc_bms_total_voltage` - Total pack voltage
- `sensor.vesc_bms_state_of_charge` - Battery percentage (0-100%)
- `sensor.vesc_bms_input_current` - Current draw
- `sensor.vesc_bms_capacity` - Battery capacity in Ah
- `sensor.vesc_bms_amp_hours` - Total Ah used
- `sensor.vesc_bms_watt_hours` - Total Wh used
- `sensor.vesc_bms_state_of_health` - Battery health percentage

### Dynamic Sensors (based on your BMS)
- `sensor.vesc_bms_cell_1_voltage` through `sensor.vesc_bms_cell_N_voltage`
- `sensor.vesc_bms_temperature_1` through `sensor.vesc_bms_temperature_N`

## Creating Dashboards

### Simple Energy Card Example

```yaml
type: entities
title: VESC Battery
entities:
  - entity: sensor.vesc_bms_state_of_charge
    name: Battery Level
  - entity: sensor.vesc_bms_total_voltage
    name: Voltage
  - entity: sensor.vesc_bms_input_current
    name: Current
  - entity: sensor.vesc_bms_temperature_1
    name: Temperature
```

### Gauge Card for State of Charge

```yaml
type: gauge
entity: sensor.vesc_bms_state_of_charge
min: 0
max: 100
name: Battery Level
severity:
  green: 50
  yellow: 25
  red: 0
```

### Cell Voltage Monitoring

```yaml
type: entities
title: Cell Voltages
entities:
  - sensor.vesc_bms_cell_1_voltage
  - sensor.vesc_bms_cell_2_voltage
  - sensor.vesc_bms_cell_3_voltage
  - sensor.vesc_bms_cell_4_voltage
```

## Automation Examples

### Low Battery Alert

```yaml
automation:
  - alias: "VESC Battery Low Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.vesc_bms_state_of_charge
        below: 20
    action:
      - service: notify.mobile_app
        data:
          message: "VESC Battery is low: {{ states('sensor.vesc_bms_state_of_charge') }}%"
          title: "Battery Alert"
```

### High Temperature Warning

```yaml
automation:
  - alias: "VESC Temperature Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.vesc_bms_temperature_1
        above: 50
    action:
      - service: notify.mobile_app
        data:
          message: "VESC BMS temperature is high: {{ states('sensor.vesc_bms_temperature_1') }}°C"
          title: "Temperature Warning"
```

## Troubleshooting

### Connection Issues

If you can't connect:

1. **Verify VESCHub is accessible**:
   ```bash
   ping YOUR_VESCHUB_IP
   telnet YOUR_VESCHUB_IP 65102
   ```

2. **Check Home Assistant logs**:
   - Go to **Settings** → **System** → **Logs**
   - Look for errors from `veschub` component

3. **Common issues**:
   - Wrong IP address or port
   - VESCHub not connected to VESC controller
   - Firewall blocking the connection
   - VESC firmware doesn't support BMS commands

### No Data Showing

1. **Verify BMS is connected**: Use VESC Tool to confirm BMS connection
2. **Check update interval**: Try increasing to 10-30 seconds
3. **Review logs**: Look for timeout or parsing errors

### Missing Cell/Temperature Sensors

- Sensors are created dynamically based on BMS data
- If missing, the BMS might not be reporting that data
- Verify in VESC Tool that cell voltages/temperatures are visible

## VESCHub Connection Options

### Local VESCHub
If you have a local VESCHub device:
- Host: Local IP address (e.g., `192.168.1.100`)
- Port: Usually `65102`

### Remote VESCHub
For remote access via VESC Project's hub:
- Host: `veschub.vedder.se`
- Port: `65101`

Note: Remote access may have latency and require internet connection.

## Next Steps

1. Add sensors to your dashboard
2. Create automations for battery monitoring
3. Set up alerts for low battery or high temperature
4. Monitor cell balance and health over time

## Support

If you encounter issues:
1. Check the logs in Home Assistant
2. Verify VESCHub connection with VESC Tool
3. Open an issue on GitHub with logs and error messages

Enjoy monitoring your VESC BMS!
