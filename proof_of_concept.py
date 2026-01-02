#!/usr/bin/env python3
"""Rapid-fire BMS test using raw byte reading (like SOLUTION.md)."""
import asyncio
import struct
from pathlib import Path

VESC_PACKET_START = 0x02
VESC_PACKET_STOP = 0x03

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

def pack_vesc_packet(payload: bytes) -> bytes:
    """Pack payload into VESC packet format."""
    if len(payload) <= 256:
        packet = bytes([VESC_PACKET_START, len(payload)])
    else:
        packet = bytes([VESC_PACKET_START, (len(payload) >> 8) & 0xFF, len(payload) & 0xFF])
    packet += payload
    crc = calculate_crc16(payload)
    packet += struct.pack('>H', crc)
    packet += bytes([VESC_PACKET_STOP])
    return packet

def find_bms_in_stream(data: bytes) -> bytes:
    """Find BMS packet (0x60) in raw data stream."""
    i = 0
    while i < len(data):
        if data[i] == VESC_PACKET_START:
            # Found packet start
            if i + 1 >= len(data):
                break

            # Get length (VESC protocol: if byte >= 256, use extended format)
            # But actually: short format if len < 256, long format if len >= 256
            # The len_byte itself: if < 128, it's the length; if >= 128, extended
            # Actually, VESC uses: short if length fits in one byte (0-255)
            # Since 0xa8 = 168 < 256, it should be short format
            len_byte = data[i + 1]
            if len_byte <= 256:  # Short format
                payload_len = len_byte
                payload_start = i + 2
            else:  # Long format (this shouldn't happen for our case)
                if i + 2 >= len(data):
                    break
                payload_len = ((len_byte & 0x7F) << 8) | data[i + 2]
                payload_start = i + 3

            # Extract payload
            payload_end = payload_start + payload_len
            if payload_end + 3 > len(data):
                # Not enough data for full packet
                i += 1
                continue

            payload = data[payload_start:payload_end]

            # Check if this is BMS packet (starts with 0x60)
            if len(payload) > 0 and payload[0] == 0x60:
                return payload

            # Move to next potential packet start
            i = payload_end + 3  # Skip CRC + stop byte
        else:
            i += 1

    return None

def parse_bms(data: bytes):
    """Parse BMS data packet."""
    if data[0] != 0x60:
        return

    payload = data[1:]

    def read_float32(offset):
        return struct.unpack('>f', payload[offset:offset+4])[0]

    def read_uint16(offset):
        return struct.unpack('>H', payload[offset:offset+2])[0]

    print(f"\n{'='*70}")
    print("🎉🎉🎉 BMS DATA SUCCESSFULLY RETRIEVED! 🎉🎉🎉")
    print(f"{'='*70}\n")

    print(f"📊 BMS Data (total payload length: {len(data)} bytes, data after 0x60: {len(payload)} bytes):\n")
    print(f"  Raw hex dump of full payload:")
    for i in range(0, min(len(data), 200), 16):
        hex_str = ' '.join(f'{b:02x}' for b in data[i:i+16])
        print(f"    Offset {i:3d}: {hex_str}")
    print()

    try:
        # Based on actual hex dump, the format is:
        # Byte 0: 0x60 (command ID, already stripped from payload)
        # Bytes 0-23: Unknown/status data
        # Byte 24: Cell count (0x14 = 20 decimal)
        # Bytes 25+: Cell voltages (uint16, mV, big-endian)

        if len(payload) >= 25:
            num_cells = payload[24]
            print(f"  Number of Cells:      {num_cells}")

            if len(payload) >= 25 + num_cells * 2:
                print(f"\n  Cell Voltages:")
                cell_voltages = []
                for i in range(num_cells):
                    offset = 25 + i * 2
                    cell_mv = read_uint16(offset)
                    cell_v = cell_mv / 1000.0
                    cell_voltages.append(cell_v)
                    print(f"    Cell {i+1:2d}: {cell_v:.3f} V ({cell_mv} mV)")

                # Statistics
                if cell_voltages:
                    avg = sum(cell_voltages) / len(cell_voltages)
                    min_v = min(cell_voltages)
                    max_v = max(cell_voltages)
                    delta = max_v - min_v

                    print(f"\n  Statistics:")
                    print(f"    Average:  {avg:.3f} V")
                    print(f"    Minimum:  {min_v:.3f} V")
                    print(f"    Maximum:  {max_v:.3f} V")
                    print(f"    Delta:    {delta*1000:.1f} mV")

                    if delta < 0.010:
                        print(f"    Balance:  ✓ Excellent")
                    elif delta < 0.050:
                        print(f"    Balance:  ✓ Good")
                    else:
                        print(f"    Balance:  ⚠ Needs balancing")
    except Exception as e:
        print(f"  Error parsing BMS data: {e}")

    print(f"\n{'='*70}\n")

async def test_rapid_fire():
    """Test rapid-fire BMS sequence."""
    # Load credentials
    env_file = Path(__file__).parent / '.env'
    vesc_id = None
    password = None

    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key == 'VESC_ID':
                        vesc_id = value
                    elif key == 'VESC_PASSWORD':
                        password = value

    # Connect
    reader, writer = await asyncio.open_connection('veschub.vedder.se', 65101)

    # Authenticate
    auth_string = f"VESCTOOL:{vesc_id}:{password}\n"
    writer.write(auth_string.encode('utf-8'))
    await writer.drain()
    await asyncio.sleep(1.0)

    print("✓ Connected and authenticated\n")

    # TEST 1: Direct BMS
    print("="*70)
    print("TEST 1: RAPID-FIRE DIRECT BMS (CAN ID 0)")
    print("="*70)
    print("\n→ Sending all 4 commands rapidly...")

    writer.write(pack_vesc_packet(bytes([0x00])))           # FW_VERSION
    writer.write(pack_vesc_packet(bytes([0x5d, 0x00])))    # GET_CUSTOM_CONFIG
    writer.write(pack_vesc_packet(bytes([0x3e])))          # PING_CAN
    writer.write(pack_vesc_packet(bytes([0x60])))          # BMS_GET_VALUES
    await writer.drain()

    print("✓ Commands sent! Reading raw responses...\n")

    # Read ALL raw bytes
    all_data = b''
    timeout = 3.0
    start_time = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start_time) < timeout:
        try:
            chunk = await asyncio.wait_for(reader.read(1024), timeout=0.5)
            if chunk:
                all_data += chunk
                print(f"  Received {len(chunk)} bytes (total: {len(all_data)} bytes)")
        except asyncio.TimeoutError:
            if all_data:
                break  # Got data, likely done

    print(f"\n✓ Total bytes received: {len(all_data)}")
    print(f"  Hex dump (first 200 bytes): {all_data[:200].hex(' ')}\n")

    # Look for BMS data
    bms_data = find_bms_in_stream(all_data)
    if bms_data:
        parse_bms(bms_data)
    else:
        print("✗ No BMS data found in direct response\n")

        # TEST 2: CAN Forwarding
        print("="*70)
        print("TEST 2: RAPID-FIRE CAN FORWARDING to ID 116 (ADV500)")
        print("="*70)
        print("\n→ Sending all 4 commands rapidly...")

        writer.write(pack_vesc_packet(bytes([0x00])))                    # FW_VERSION
        writer.write(pack_vesc_packet(bytes([0x5d, 0x00])))             # GET_CUSTOM_CONFIG
        writer.write(pack_vesc_packet(bytes([0x3e])))                   # PING_CAN
        writer.write(pack_vesc_packet(bytes([0x22, 116, 0x60])))        # FORWARD_CAN(116, BMS)
        await writer.drain()

        print("✓ Commands sent! Reading raw responses...\n")

        # Read ALL raw bytes
        all_data = b''
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                chunk = await asyncio.wait_for(reader.read(1024), timeout=0.5)
                if chunk:
                    all_data += chunk
                    print(f"  Received {len(chunk)} bytes (total: {len(all_data)} bytes)")
            except asyncio.TimeoutError:
                if all_data:
                    break

        print(f"\n✓ Total bytes received: {len(all_data)}")
        print(f"  Hex dump (first 200 bytes): {all_data[:200].hex(' ')}\n")

        # Look for BMS data
        bms_data = find_bms_in_stream(all_data)
        if bms_data:
            parse_bms(bms_data)
        else:
            print("✗ No BMS data found in CAN forwarding response either\n")

    # Cleanup
    writer.close()
    await writer.wait_closed()
    print("✓ Disconnected\n")

if __name__ == "__main__":
    asyncio.run(test_rapid_fire())
