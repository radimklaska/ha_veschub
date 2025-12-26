#!/usr/bin/env python3
"""Test PING command to check if VESC is online."""
import asyncio


async def test_ping():
    """Test PING command."""
    # TODO: Replace with your actual credentials
    host = "veschub.vedder.se"
    port = 65101
    vesc_id = "your-vesc-id"

    print(f"Connecting to {host}:{port}")
    reader, writer = await asyncio.open_connection(host, port)
    print("✓ Connected")

    # Send PING
    ping_string = f"PING:{vesc_id}:0\n"
    print(f"Sending PING for {vesc_id}...")
    writer.write(ping_string.encode('utf-8'))
    await writer.drain()

    # Read response
    try:
        response = await asyncio.wait_for(reader.readline(), timeout=5.0)
        print(f"Response: {response.decode('utf-8').strip()}")

        if response == b"PONG\n":
            print("✓ VESC is online!")
        elif response == b"NULL\n":
            print("✗ VESC not found or not connected")
        else:
            print(f"Unknown response: {response}")
    except asyncio.TimeoutError:
        print("✗ Timeout - no response")

    writer.close()
    await writer.wait_closed()


if __name__ == "__main__":
    asyncio.run(test_ping())
