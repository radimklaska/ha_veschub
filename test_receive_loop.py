#!/usr/bin/env python3
"""Test receiving data in a loop from VESCHub."""
import asyncio
import struct


async def read_vesc_packet(reader):
    """Read one VESC packet."""
    # Wait for start byte
    while True:
        byte = await reader.readexactly(1)
        if byte[0] == 0x02:
            break

    # Read length
    len_byte = await reader.readexactly(1)

    if len_byte[0] < 128:
        payload_len = len_byte[0]
    else:
        len_low = await reader.readexactly(1)
        payload_len = ((len_byte[0] & 0x7F) << 8) | len_low[0]

    # Read payload
    payload = await reader.readexactly(payload_len)

    # Read CRC
    crc_bytes = await reader.readexactly(2)

    # Read stop byte
    stop_byte = await reader.readexactly(1)

    return payload


def parse_bms_data(data):
    """Parse BMS data payload."""
    if data[0] != 0x32:  # COMM_BMS_GET_VALUES
        return None

    data = data[1:]  # Skip command byte
    index = 0

    def read_float32(offset):
        return struct.unpack('>f', data[offset:offset+4])[0]

    def read_uint16(offset):
        return struct.unpack('>H', data[offset:offset+2])[0]

    def read_uint8(offset):
        return data[offset]

    bms_data = {
        "v_tot": read_float32(index),
        "v_charge": read_float32(index + 4),
        "i_in": read_float32(index + 8),
        "i_in_ic": read_float32(index + 12),
        "ah_cnt": read_float32(index + 16),
        "wh_cnt": read_float32(index + 20),
    }

    index += 24

    if len(data) > index + 1:
        cell_num = read_uint8(index)
        index += 1

        cells = []
        for i in range(min(cell_num, 32)):
            if len(data) >= index + 2:
                cell_v = read_uint16(index) / 1000.0
                cells.append(cell_v)
                index += 2

        bms_data["cell_voltages"] = cells
        bms_data["cell_num"] = cell_num

    if len(data) > index + 4:
        bms_data["bal_state"] = struct.unpack('>I', data[index:index+4])[0]
        index += 4

    if len(data) > index + 1:
        temp_adc_num = read_uint8(index)
        index += 1

        temps = []
        for i in range(min(temp_adc_num, 10)):
            if len(data) >= index + 2:
                temp = read_uint16(index) / 10.0
                temps.append(temp)
                index += 2

        bms_data["temperatures"] = temps
        bms_data["temp_adc_num"] = temp_adc_num

    if len(data) >= index + 4:
        bms_data["soc"] = read_float32(index)
        index += 4

    if len(data) >= index + 4:
        bms_data["soh"] = read_float32(index)
        index += 4

    if len(data) >= index + 4:
        bms_data["capacity_ah"] = read_float32(index)

    return bms_data


async def test_receive_loop():
    """Connect and wait for data."""
    # TODO: Replace with your actual credentials
    host = "veschub.vedder.se"
    port = 65101
    vesc_id = "your-vesc-id"
    password = "your-password"

    print(f"Connecting to {host}:{port}")
    reader, writer = await asyncio.open_connection(host, port)
    print("✓ Connected")

    # Authenticate
    auth_string = f"VESCTOOL:{vesc_id}:{password}\n"
    writer.write(auth_string.encode('utf-8'))
    await writer.drain()
    print("✓ Authenticated")

    print("\nWaiting for BMS data packets...")
    print("(Press Ctrl+C to stop)")
    print("-" * 60)

    try:
        packet_count = 0
        while packet_count < 3:  # Collect 3 packets
            try:
                payload = await asyncio.wait_for(read_vesc_packet(reader), timeout=30.0)
                packet_count += 1

                print(f"\n=== Packet {packet_count} ===")
                print(f"Payload length: {len(payload)} bytes")
                print(f"Command ID: 0x{payload[0]:02x}")

                if payload[0] == 0x32:  # BMS data
                    bms_data = parse_bms_data(payload)
                    if bms_data:
                        print("\n✓ BMS Data:")
                        for key, value in bms_data.items():
                            if isinstance(value, list):
                                print(f"  {key}: {len(value)} items")
                                if key == "cell_voltages":
                                    for i, v in enumerate(value):
                                        print(f"    Cell {i+1}: {v:.3f}V")
                                elif key == "temperatures":
                                    for i, v in enumerate(value):
                                        print(f"    Temp {i+1}: {v:.1f}°C")
                            else:
                                print(f"  {key}: {value}")
                else:
                    print(f"Other packet type: 0x{payload[0]:02x}")
                    print(f"First 40 bytes: {payload[:40].hex(' ')}")

            except asyncio.TimeoutError:
                print("\nTimeout waiting for next packet")
                break

    except KeyboardInterrupt:
        print("\n\nStopped by user")

    writer.close()
    await writer.wait_closed()
    print("\n✓ Disconnected")


if __name__ == "__main__":
    asyncio.run(test_receive_loop())
