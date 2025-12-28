# Packet Capture Guide - VESCTool BMS Access

## Quick Method (tcpdump)

### 1. Start Capture
```bash
cd /home/radimklaska/Documents/ha_veschub
sudo tcpdump -i any -w vesc_bms_capture.pcap host veschub.vedder.se
```

### 2. In VESCTool
1. Connect to VESCHub (Connect TCP Hub)
2. Wait 2 seconds
3. Click "BMS Data" in left menu
4. Click "Stream BMS realtime data" button (toolbar)
5. Wait 5-10 seconds (let it stream)
6. Stop streaming button
7. Disconnect

### 3. Stop Capture
Press `Ctrl+C` in the tcpdump terminal

### 4. Analyze
```bash
# Install tshark if needed
sudo apt install tshark

# Show all packets
tshark -r vesc_bms_capture.pcap

# Show only data packets (filter TCP payload)
tshark -r vesc_bms_capture.pcap -T fields -e data -Y "tcp.len > 0"

# Or just send me the file
ls -lh vesc_bms_capture.pcap
```

---

## Alternative: Wireshark GUI

### 1. Install
```bash
sudo apt install wireshark
# Add yourself to wireshark group
sudo usermod -a -G wireshark $USER
# Log out and back in
```

### 2. Capture
1. Open Wireshark
2. Select interface (any)
3. Filter: `tcp.port == 65101`
4. Start capture
5. Do VESCTool steps above
6. Stop capture
7. Save as `vesc_bms_capture.pcapng`

### 3. Analyze
- Right-click packet → Follow → TCP Stream
- Look for patterns in client→server data
- Export as hex/text

---

## What We're Looking For

### Initial Connection
- Authentication string: `VESCTOOL:rk-adv2:trailsforbreakfast\n`
- Any commands BEFORE first BMS request

### BMS Streaming
- First packet after enabling stream
- Pattern of packets (command bytes)
- Any different packet format

### Key Questions
1. **Does VESCTool send anything other than 0x60 (BMS_GET_VALUES)?**
2. **Are there extra bytes in the BMS request we're missing?**
3. **Is there a device selection command?**
4. **What's the exact timing/sequence?**

---

## Quick Analysis Script

Save capture, then run:

```bash
python3 - << 'EOF'
import sys

# Read capture file hex dump
with open('vesc_bms_capture.pcap', 'rb') as f:
    data = f.read()

# Look for VESC packet markers
start_byte = 0x02
stop_byte = 0x03

print("Looking for VESC packets (0x02...0x03):")
i = 0
packet_num = 0
while i < len(data):
    if data[i] == start_byte:
        # Found potential packet
        start = i
        # Scan for stop byte (max 1000 bytes ahead)
        for j in range(i+1, min(i+1000, len(data))):
            if data[j] == stop_byte:
                packet_num += 1
                packet = data[start:j+1]
                print(f"\nPacket {packet_num} ({len(packet)} bytes):")
                print(f"  Hex: {packet.hex(' ')}")
                if len(packet) > 4:
                    cmd = packet[2] if len(packet) > 2 else None
                    if cmd == 0x60:
                        print(f"  → BMS_GET_VALUES request!")
                    elif cmd == 0x00:
                        print(f"  → FW_VERSION")
                    else:
                        print(f"  → Command: 0x{cmd:02x}")
                i = j
                break
        i += 1
    else:
        i += 1
EOF
```

---

## Share Results

Once you have the capture:

1. **Quick check:**
   ```bash
   strings vesc_bms_capture.pcap | grep -E "VESCTOOL|0x60"
   ```

2. **Share file:**
   - The .pcap file itself (I can analyze it)
   - Or paste hex dump of interesting packets

3. **Manual inspection:**
   - Look at first 10 packets after "VESCTOOL:..." auth
   - Note any repeated patterns
   - Check if 0x60 appears and what's around it
