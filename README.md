# VESC Hub BMS Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

Home Assistant integration for reading Battery Management System (BMS) data from VESC controllers through VESCHub via TCP/IP.

## Features

- **Real-time BMS Monitoring**: Monitor all BMS data from your VESC controller
- **Comprehensive Data**: Access voltage, current, state of charge, individual cell voltages, temperatures, and more
- **Local Polling**: Direct TCP connection to your VESCHub for reliable local communication
- **Easy Setup**: Simple configuration through Home Assistant UI

## Supported Sensors

### Main BMS Sensors
- **Total Voltage** - Total battery pack voltage
- **Charge Voltage** - Charging voltage
- **Input Current** - Current flowing into the battery
- **Input Current IC** - Current measured by IC
- **Amp Hours** - Total amp-hours consumed/regenerated
- **Watt Hours** - Total watt-hours consumed/regenerated
- **State of Charge (SoC)** - Battery percentage (0-100%)
- **State of Health (SoH)** - Battery health percentage
- **Capacity** - Battery capacity in Ah
- **Balance State** - Cell balancing status

### Dynamic Sensors
- **Cell Voltages** - Individual voltage for each cell (dynamically created based on your pack)
- **Temperatures** - Temperature readings from each sensor (dynamically created)

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/radimklaska/ha_veschub`
6. Select category: "Integration"
7. Click "Add"
8. Find "VESC Hub BMS" in the integration list
9. Click "Download"
10. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/veschub` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **VESC Hub BMS**
4. Enter your VESCHub connection details:
   - **Host**: IP address or hostname of your VESCHub
   - **Port**: TCP port (default: 65102)
   - **Update Interval**: How often to poll for data (1-300 seconds, default: 5)

## VESCHub Setup

This integration requires a VESCHub to be accessible on your network. The VESCHub acts as a TCP bridge to your VESC controller.

### Connection Details

- **Default Port**: 65102 (local VESCHub)
- **Public VESCHub**: veschub.vedder.se:65101 (for remote access)

Make sure your VESCHub is:
1. Connected to your VESC controller
2. Accessible on your network
3. Configured to accept TCP connections

## Protocol Details

This integration implements the VESC communication protocol over TCP:
- Uses VESC packet framing with CRC16 checksums
- Supports both short and long packet formats
- Implements the `COMM_BMS_GET_VALUES` command for BMS data retrieval
- Compatible with VESC firmware that includes BMS support

## Troubleshooting

### Cannot Connect
- Verify VESCHub IP address and port
- Ensure VESCHub is powered on and connected to network
- Check that your VESC controller is connected to the VESCHub
- Verify firewall settings allow TCP connection to the VESCHub port

### No Data / Timeout
- Check that your VESC has a BMS connected
- Verify the VESC firmware supports BMS commands
- Try increasing the update interval
- Check VESCHub logs for errors

### Missing Sensors
- Cell voltage and temperature sensors are created dynamically based on your BMS configuration
- If sensors are missing, verify your BMS is properly configured in VESC Tool

## Compatibility

- **Home Assistant**: 2023.1.0 or newer
- **VESC Firmware**: Firmware with BMS support
- **VESCHub**: Any VESCHub device with TCP server capability

## Development

This integration uses:
- VESC communication protocol with CRC16 checksums
- Home Assistant's DataUpdateCoordinator for efficient polling
- Config Flow for easy setup
- Entity platform for sensor management

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0).

- Non-commercial use is permitted with attribution
- Commercial use requires permission from the copyright holder
- See LICENSE file for full terms

## Credits

- VESC Project by Benjamin Vedder
- Protocol implementation based on VESC firmware and VESC Tool source code

## Support

For issues, questions, or feature requests, please open an issue on [GitHub](https://github.com/radimklaska/ha_veschub/issues).

## Disclaimer

This integration is not officially affiliated with or endorsed by the VESC Project. Use at your own risk.
