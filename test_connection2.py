#!/usr/bin/env python3
"""Test script that receives pushed BMS data from VESCHub."""
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)


async def test_passive_receive():
    """Connect and passively receive data from VESCHub."""
    # TODO: Replace with your actual credentials
    host = "veschub.vedder.se"
    port = 65101
    vesc_id = "your-vesc-id"
    password = "your-password"

    print(f"Connecting to {host}:{port}")
    print(f"VESC ID: {vesc_id}")
    print("-" * 50)

    # Connect
    reader, writer = await asyncio.open_connection(host, port)
    print("✓ Connected")

    # Authenticate
    auth_string = f"VESCTOOL:{vesc_id}:{password}\n"
    writer.write(auth_string.encode('utf-8'))
    await writer.drain()
    print("✓ Authentication sent")

    # Wait and receive data
    print("\nWaiting for data...")
    try:
        for i in range(5):  # Receive 5 packets
            data = await asyncio.wait_for(reader.read(4096), timeout=10.0)
            if data:
                print(f"\n--- Packet {i+1} ({len(data)} bytes) ---")
                print(f"Hex: {data.hex()}")
                print(f"First 20 bytes: {data[:20].hex(' ')}")

                # Check if it starts with VESC packet start byte
                if data[0] == 0x02:
                    print("✓ Looks like a VESC packet!")
                    if len(data) > 2 and data[1] == 0x32:  # COMM_BMS_GET_VALUES
                        print("✓ This appears to be BMS data!")
                else:
                    print(f"First byte: {data[0]:02x}")
    except asyncio.TimeoutError:
        print("Timeout - no more data")

    writer.close()
    await writer.wait_closed()
    print("\n✓ Disconnected")


if __name__ == "__main__":
    asyncio.run(test_passive_receive())
