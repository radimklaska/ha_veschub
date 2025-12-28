#!/usr/bin/env python3
"""Interactive VESC data exploration script.

This script connects to veschub.vedder.se and systematically explores:
1. Firmware version (known to work)
2. Direct GET_VALUES command
3. Direct BMS_GET_VALUES command
4. CAN forwarding with different IDs
5. Passive data listening

Results are logged to exploration_notes.md
"""
import asyncio
import logging
import struct
import sys
import os
from datetime import datetime
from typing import Optional
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)

# VESC Protocol Constants
VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03

# VESC Commands
COMM_FW_VERSION = 0
COMM_GET_VALUES = 4
COMM_FORWARD_CAN = 34
COMM_BMS_GET_VALUES = 96

# Results storage
exploration_results = []


def log_result(test_name: str, success: bool, details: str, raw_data: bytes = None):
    """Log exploration result."""
    result = {
        'timestamp': datetime.now().isoformat(),
        'test': test_name,
        'success': success,
        'details': details,
        'raw_hex': raw_data.hex(' ') if raw_data else None
    }
    exploration_results.append(result)

    status = "✓" if success else "✗"
    print(f"\n{status} {test_name}")
    print(f"  {details}")
    if raw_data and len(raw_data) <= 100:
        print(f"  Raw: {raw_data.hex(' ')}")


class VESCExplorer:
    """VESC protocol explorer."""

    def __init__(self, host: str, port: int, vesc_id: str = None, password: str = None):
        self.host = host
        self.port = port
        self.vesc_id = vesc_id
        self.password = password
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to VESCHub."""
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10
            )
            _LOGGER.info(f"Connected to {self.host}:{self.port}")

            if self.vesc_id and self.password:
                auth_string = f"VESCTOOL:{self.vesc_id}:{self.password}\n"
                _LOGGER.info(f"Authenticating as VESCTOOL:{self.vesc_id}:***")
                self.writer.write(auth_string.encode('utf-8'))
                await self.writer.drain()
                await asyncio.sleep(1.0)

            self._connected = True
            log_result("Connection", True, f"Connected to {self.host}:{self.port}")
            return True

        except Exception as e:
            log_result("Connection", False, f"Failed: {e}")
            return False

    async def disconnect(self):
        """Disconnect from VESCHub."""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        self._connected = False

    @staticmethod
    def _calculate_crc16(data: bytes) -> int:
        """Calculate CRC16 for VESC protocol."""
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

    def _pack_payload(self, payload: bytes) -> bytes:
        """Pack payload with VESC framing."""
        if len(payload) <= 256:
            packet = bytes([VESC_PACKET_START_BYTE, len(payload)])
        else:
            packet = bytes([VESC_PACKET_START_BYTE,
                          (len(payload) >> 8) & 0xFF,
                          len(payload) & 0xFF])

        packet += payload
        crc = self._calculate_crc16(payload)
        packet += struct.pack('>H', crc)
        packet += bytes([VESC_PACKET_STOP_BYTE])
        return packet

    async def _send_command(self, command: int, data: bytes = b'', timeout: float = 5.0) -> Optional[bytes]:
        """Send command and wait for response."""
        if not self._connected:
            return None

        try:
            payload = bytes([command]) + data
            packet = self._pack_payload(payload)

            _LOGGER.debug(f"Sending: {packet.hex(' ')}")
            self.writer.write(packet)
            await self.writer.drain()

            response = await asyncio.wait_for(
                self._read_packet(),
                timeout=timeout
            )
            return response

        except asyncio.TimeoutError:
            _LOGGER.warning(f"Timeout after {timeout}s")
            return None
        except (ConnectionError, BrokenPipeError, OSError) as e:
            _LOGGER.error(f"Connection error: {e}")
            self._connected = False
            return None
        except Exception as e:
            _LOGGER.error(f"Error: {e}")
            return None

    async def _read_packet(self) -> Optional[bytes]:
        """Read VESC packet."""
        try:
            # Wait for start byte
            while True:
                byte = await self.reader.readexactly(1)
                if byte[0] == VESC_PACKET_START_BYTE:
                    break

            # Read length
            len_byte = await self.reader.readexactly(1)
            if len_byte[0] < 128:
                payload_len = len_byte[0]
            else:
                len_low = await self.reader.readexactly(1)
                payload_len = ((len_byte[0] & 0x7F) << 8) | len_low[0]

            # Read payload, CRC, stop byte
            payload = await self.reader.readexactly(payload_len)
            crc_bytes = await self.reader.readexactly(2)
            stop_byte = await self.reader.readexactly(1)

            # Validate
            received_crc = struct.unpack('>H', crc_bytes)[0]
            calculated_crc = self._calculate_crc16(payload)

            if stop_byte[0] != VESC_PACKET_STOP_BYTE:
                _LOGGER.error("Invalid stop byte")
                return None

            if calculated_crc != received_crc:
                _LOGGER.error(f"CRC mismatch: {calculated_crc:04x} != {received_crc:04x}")
                return None

            _LOGGER.debug(f"Received: {payload.hex(' ')}")
            return payload

        except Exception as e:
            _LOGGER.error(f"Read error: {e}")
            return None

    async def test_fw_version(self):
        """Test COMM_FW_VERSION (known to work)."""
        print("\n" + "="*60)
        print("TEST 1: Firmware Version (COMM_FW_VERSION = 0x00)")
        print("="*60)

        response = await self._send_command(COMM_FW_VERSION)

        if response:
            if response[0] == COMM_FW_VERSION:
                fw_data = response[1:]
                fw_major = fw_data[0] if len(fw_data) > 0 else 0
                fw_minor = fw_data[1] if len(fw_data) > 1 else 0
                fw_name = fw_data[2:].decode('utf-8', errors='ignore').rstrip('\x00')

                details = f"FW {fw_major}.{fw_minor} - {fw_name}"
                log_result("FW_VERSION", True, details, response)
            else:
                log_result("FW_VERSION", False, f"Unexpected command: 0x{response[0]:02x}", response)
        else:
            log_result("FW_VERSION", False, "No response or connection closed")

    async def test_get_values(self):
        """Test COMM_GET_VALUES."""
        print("\n" + "="*60)
        print("TEST 2: Get Values (COMM_GET_VALUES = 0x04)")
        print("="*60)

        response = await self._send_command(COMM_GET_VALUES)

        if response:
            log_result("GET_VALUES", True, f"Got {len(response)} bytes", response)
        else:
            log_result("GET_VALUES", False, "No response (connection may have closed)")

    async def test_bms_get_values(self):
        """Test COMM_BMS_GET_VALUES."""
        print("\n" + "="*60)
        print("TEST 3: BMS Get Values (COMM_BMS_GET_VALUES = 0x60)")
        print("="*60)

        response = await self._send_command(COMM_BMS_GET_VALUES)

        if response:
            log_result("BMS_GET_VALUES", True, f"Got {len(response)} bytes", response)
        else:
            log_result("BMS_GET_VALUES", False, "No response (connection may have closed)")

    async def test_can_forward(self, can_id: int, wrapped_command: int):
        """Test CAN forwarding."""
        print(f"\n{'='*60}")
        print(f"TEST: CAN Forward to ID {can_id} with command 0x{wrapped_command:02x}")
        print("="*60)

        # Format: [CAN_ID][wrapped_command]
        can_data = bytes([can_id, wrapped_command])
        response = await self._send_command(COMM_FORWARD_CAN, can_data)

        if response:
            log_result(f"CAN_FWD_{can_id}_0x{wrapped_command:02x}", True,
                      f"Got {len(response)} bytes", response)
            return response
        else:
            log_result(f"CAN_FWD_{can_id}_0x{wrapped_command:02x}", False, "No response")
            return None

    async def test_passive_receive(self, timeout: float = 10.0):
        """Wait for passive data."""
        print("\n" + "="*60)
        print(f"TEST: Passive Receive (wait {timeout}s for pushed data)")
        print("="*60)

        try:
            response = await asyncio.wait_for(self._read_packet(), timeout=timeout)
            if response:
                log_result("PASSIVE_RECEIVE", True, f"Got {len(response)} bytes", response)
                return response
            else:
                log_result("PASSIVE_RECEIVE", False, "Failed to read packet")
                return None
        except asyncio.TimeoutError:
            log_result("PASSIVE_RECEIVE", False, f"No data received in {timeout}s")
            return None


async def main():
    """Run exploration tests."""
    print("="*60)
    print("VESC DATA EXPLORATION")
    print("="*60)

    # Get credentials from .env file, command line, or prompt
    vesc_id = None
    password = None

    # Try to load from .env file
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        if key == 'VESC_ID':
                            vesc_id = value
                        elif key == 'VESC_PASSWORD':
                            password = value
        if vesc_id and password:
            print(f"✓ Loaded credentials from .env file")
            print(f"  VESC ID: {vesc_id}")

    # Override with command line args if provided
    if len(sys.argv) >= 3:
        vesc_id = sys.argv[1]
        password = sys.argv[2]
        print(f"✓ Using command line credentials")

    # Prompt if still missing
    if not vesc_id or not password:
        print("\nUsage: python3 explore_vesc.py <vesc_id> <password>")
        print("Or create a .env file with VESC_ID and VESC_PASSWORD")
        print("\nOr enter credentials now:")
        vesc_id = input("VESC ID: ").strip()
        password = input("Password: ").strip()

        if not vesc_id or not password:
            print("Error: Credentials required")
            return

    explorer = VESCExplorer("veschub.vedder.se", 65101, vesc_id, password)

    # Connect
    if not await explorer.connect():
        print("\n✗ Failed to connect")
        return

    try:
        # Test 1: FW Version (should work)
        await explorer.test_fw_version()
        await asyncio.sleep(0.5)

        # Test 2: Check if still connected after FW_VERSION
        if explorer._connected:
            print("\n✓ Connection still alive after FW_VERSION")

            # Test 3: Try GET_VALUES (known to close connection)
            await explorer.test_get_values()
            await asyncio.sleep(0.5)

            # Test 4: Check if still connected
            if not explorer._connected:
                print("\n✗ Connection closed after GET_VALUES")
                print("Reconnecting...")
                if not await explorer.connect():
                    print("Failed to reconnect")
                    return

            # Test 5: Try BMS_GET_VALUES
            await explorer.test_bms_get_values()
            await asyncio.sleep(0.5)

            # Reconnect if needed
            if not explorer._connected:
                print("\nReconnecting for CAN tests...")
                if not await explorer.connect():
                    print("Failed to reconnect")
                    return

            # Test 6: CAN forwarding with common IDs
            print("\n" + "="*60)
            print("Testing CAN Forwarding")
            print("="*60)

            common_can_ids = [0, 1, 124, 125, 126]  # Common BMS CAN IDs

            for can_id in common_can_ids:
                if not explorer._connected:
                    print(f"\nReconnecting before CAN ID {can_id}...")
                    if not await explorer.connect():
                        break

                # Try forwarding FW_VERSION command to this CAN ID
                await explorer.test_can_forward(can_id, COMM_FW_VERSION)
                await asyncio.sleep(0.5)

                # Also try BMS command if still connected
                if explorer._connected:
                    await explorer.test_can_forward(can_id, COMM_BMS_GET_VALUES)
                    await asyncio.sleep(0.5)

            # Test 7: Passive receive
            if not explorer._connected:
                print("\nReconnecting for passive test...")
                if await explorer.connect():
                    await explorer.test_passive_receive(timeout=15.0)

    finally:
        await explorer.disconnect()

        # Save results
        print("\n" + "="*60)
        print("SAVING RESULTS")
        print("="*60)

        with open('exploration_notes.md', 'w') as f:
            f.write(f"# VESC Data Exploration Results\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Host:** veschub.vedder.se:65101\n")
            f.write(f"**VESC ID:** {vesc_id}\n\n")

            f.write("## Summary\n\n")
            successes = sum(1 for r in exploration_results if r['success'])
            f.write(f"- Total tests: {len(exploration_results)}\n")
            f.write(f"- Successful: {successes}\n")
            f.write(f"- Failed: {len(exploration_results) - successes}\n\n")

            f.write("## Detailed Results\n\n")
            for result in exploration_results:
                status = "✓" if result['success'] else "✗"
                f.write(f"### {status} {result['test']}\n\n")
                f.write(f"- **Time:** {result['timestamp']}\n")
                f.write(f"- **Status:** {'Success' if result['success'] else 'Failed'}\n")
                f.write(f"- **Details:** {result['details']}\n")
                if result['raw_hex']:
                    f.write(f"- **Raw Data:**\n```\n{result['raw_hex']}\n```\n")
                f.write("\n")

        print(f"✓ Results saved to exploration_notes.md")
        print(f"✓ {len(exploration_results)} tests completed")


if __name__ == "__main__":
    asyncio.run(main())
