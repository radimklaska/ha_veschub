# Installation Guide

## Prerequisites

- Home Assistant 2023.1.0 or newer
- VESC controller with BMS support
- VESCHub accessible on your network
- VESC firmware that supports BMS commands

## Option 1: HACS Installation (Recommended)

### Step 1: Add Custom Repository

1. Open HACS in Home Assistant
2. Click on **Integrations**
3. Click the **⋮** menu (three dots) in the top right
4. Select **Custom repositories**
5. Enter repository URL: `https://github.com/YOUR_USERNAME/ha_veschub`
   (Replace with your actual GitHub repository URL)
6. Category: **Integration**
7. Click **Add**

### Step 2: Install Integration

1. Search for "VESC Hub BMS" in HACS
2. Click **Download**
3. Restart Home Assistant

### Step 3: Configure

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "VESC Hub BMS"
4. Follow the configuration wizard

## Option 2: Manual Installation

### Step 1: Copy Files

Copy the `custom_components/veschub` directory to your Home Assistant config directory:

```bash
# SSH into your Home Assistant instance
cd /config

# Create custom_components if it doesn't exist
mkdir -p custom_components

# Copy the integration
# (You'll need to transfer the files via SCP, Samba, or your preferred method)
```

Your directory structure should look like:
```
/config/
├── custom_components/
│   └── veschub/
│       ├── __init__.py
│       ├── config_flow.py
│       ├── const.py
│       ├── manifest.json
│       ├── sensor.py
│       ├── strings.json
│       ├── vesc_protocol.py
│       └── translations/
│           └── en.json
```

### Step 2: Restart Home Assistant

Restart Home Assistant to load the new integration.

### Step 3: Configure

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "VESC Hub BMS"
4. Enter connection details:
   - **Host**: VESCHub IP address or hostname
   - **Port**: TCP port (default: 65102)
   - **Update Interval**: Polling interval in seconds (default: 5)

## Verification

After installation, verify:

1. **Check Integration Status**:
   - Go to **Settings** → **Devices & Services**
   - Look for "VESC Hub BMS" integration
   - Status should be "OK" with a device count

2. **Check Device**:
   - Click on the integration
   - You should see a "VESC BMS" device
   - Click on the device to see all sensors

3. **Check Sensors**:
   - Verify sensors are updating with values
   - Check entity names start with `sensor.vesc_bms_`

## Configuration Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| Host | Yes | - | IP address or hostname of VESCHub |
| Port | No | 65102 | TCP port for VESCHub connection |
| Update Interval | No | 5 | Polling interval in seconds (1-300) |

## Network Requirements

- VESCHub must be accessible from Home Assistant
- TCP port (default 65102) must be open
- No authentication required (ensure VESCHub is on trusted network)

## Firewall Configuration

If you have a firewall between Home Assistant and VESCHub:

```bash
# Allow outgoing TCP connections to VESCHub port
# Example for ufw on Ubuntu:
sudo ufw allow out to VESCHUB_IP port 65102 proto tcp
```

## VESCHub Setup

Ensure your VESCHub is configured:

1. **Network Connection**: VESCHub connected to same network as Home Assistant
2. **VESC Connection**: VESCHub properly connected to VESC controller
3. **TCP Server**: VESCHub TCP server enabled and listening
4. **Port Configuration**: Note the port number (usually 65102 for local, 65101 for public hub)

## Testing Connection

Before adding to Home Assistant, test connectivity:

```bash
# Test network connectivity
ping YOUR_VESCHUB_IP

# Test TCP port (should connect without error)
telnet YOUR_VESCHUB_IP 65102

# Or use nc (netcat)
nc -zv YOUR_VESCHUB_IP 65102
```

## Updating

### HACS Update
1. HACS will notify you of updates
2. Click **Update** in HACS
3. Restart Home Assistant

### Manual Update
1. Download latest release
2. Replace files in `custom_components/veschub/`
3. Restart Home Assistant

## Uninstallation

1. Remove integration:
   - **Settings** → **Devices & Services**
   - Click **⋮** on VESC Hub BMS integration
   - Select **Delete**

2. Remove files (if manually installed):
   ```bash
   rm -rf /config/custom_components/veschub
   ```

3. Restart Home Assistant

## Troubleshooting Installation

### Integration Not Appearing

- Clear browser cache
- Restart Home Assistant
- Check logs for errors: **Settings** → **System** → **Logs**
- Verify files are in correct location

### Import Errors

Check Home Assistant logs for:
- Missing dependencies (none required for this integration)
- Python syntax errors
- File permission issues

### Configuration Issues

- Verify VESCHub IP is correct
- Test network connectivity
- Check VESCHub is powered on and connected
- Review port number (different for local vs. public hub)

## Getting Help

If you encounter issues:

1. Check Home Assistant logs
2. Enable debug logging (see DEBUG.md)
3. Test VESCHub with VESC Tool
4. Open GitHub issue with:
   - Home Assistant version
   - Integration version
   - Error logs
   - VESCHub model/version
   - VESC firmware version

## Next Steps

After successful installation:
- Read [QUICKSTART.md](QUICKSTART.md) for usage guide
- Set up dashboard cards
- Create automations
- Configure alerts
