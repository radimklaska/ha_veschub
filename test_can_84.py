#!/usr/bin/env python3
"""Test CAN ID 84 specifically."""
import asyncio
import logging
import struct
from pathlib import Path

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
_LOGGER = logging.getLogger(__name__)

VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03
COMM_FW_VERSION = 0
COMM_GET_VALUES = 4
COMM_FORWARD_CAN = 34
COMM_BMS_GET_VALUES = 96


class VESCTester:
    def __init__(self, host: str, port: int, vesc_id: str, password: str):
        self.host = host
        self.port = port
        self.vesc_id = vesc_id
        self.password = password
        self.reader = None
        self.writer = None

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        auth_string = f"VESCTOOL:{self.vesc_id}:{self.password}\n"
        self.writer.write(auth_string.encode('utf-8'))
        await self.writer.drain()
        await asyncio.sleep(1.0)
        print(f"✓ Connected and authenticated")

    async def disconnect(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

    @staticmethod
    def _calculate_crc16(data: bytes) -> int:
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
        if len(payload) <= 256:
            packet = bytes([VESC_PACKET_START_BYTE, len(payload)])
        else:
            packet = bytes([VESC_PACKET_START_BYTE, (len(payload) >> 8) & 0xFF, len(payload) & 0xFF])
        packet += payload
        crc = self._calculate_crc16(payload)
        packet += struct.pack('>H', crc)
        packet += bytes([VESC_PACKET_STOP_BYTE])
        return packet

    async def _send_command(self, command: int, data: bytes = b'', timeout: float = 5.0):
        payload = bytes([command]) + data
        packet = self._pack_payload(payload)
        print(f"→ Sending: {packet.hex(' ')}")
        self.writer.write(packet)
        await self.writer.drain()

        try:
            response = await asyncio.wait_for(self._read_packet(), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            print(f"✗ Timeout after {timeout}s")
            return None

    async def _read_packet(self):
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

        # Read payload, CRC, stop
        payload = await self.reader.readexactly(payload_len)
        crc_bytes = await self.reader.readexactly(2)
        stop_byte = await self.reader.readexactly(1)

        received_crc = struct.unpack('>H', crc_bytes)[0]
        calculated_crc = self._calculate_crc16(payload)

        if stop_byte[0] != VESC_PACKET_STOP_BYTE:
            print(f"✗ Invalid stop byte: 0x{stop_byte[0]:02x}")
            return None

        if calculated_crc != received_crc:
            print(f"✗ CRC mismatch: {calculated_crc:04x} != {received_crc:04x}")
            return None

        print(f"← Received ({len(payload)} bytes): {payload.hex(' ')}")
        return payload

    async def test_can_forward(self, can_id: int, wrapped_cmd: int):
        print(f"\n{'='*60}")
        print(f"CAN Forward: ID={can_id} (0x{can_id:02x}), Command=0x{wrapped_cmd:02x}")
        print('='*60)

        can_data = bytes([can_id, wrapped_cmd])
        response = await self._send_command(COMM_FORWARD_CAN, can_data)

        if response:
            print(f"✓ Got response!")
            print(f"  Command byte: 0x{response[0]:02x}")
            print(f"  Data length: {len(response)} bytes")

            # Parse if it's a forwarded response
            if response[0] == COMM_FORWARD_CAN and len(response) > 1:
                can_id_response = response[1]
                inner_payload = response[2:]
                print(f"  CAN ID in response: {can_id_response}")
                print(f"  Inner payload: {inner_payload.hex(' ')}")

                if len(inner_payload) > 0:
                    print(f"  Inner command: 0x{inner_payload[0]:02x}")

                    # Try to parse as FW_VERSION
                    if inner_payload[0] == COMM_FW_VERSION and len(inner_payload) > 2:
                        fw_major = inner_payload[1]
                        fw_minor = inner_payload[2]
                        fw_name = inner_payload[3:].decode('utf-8', errors='ignore').rstrip('\x00')
                        print(f"  ✓ Firmware: v{fw_major}.{fw_minor} - {fw_name}")

            return response
        else:
            print(f"✗ No response")
            return None


async def main():
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

    print("="*60)
    print("Testing CAN ID 84")
    print("="*60)
    print(f"VESC ID: {vesc_id}\n")

    tester = VESCTester("veschub.vedder.se", 65101, vesc_id, password)

    try:
        await tester.connect()

        # Test CAN ID 84 with different commands
        commands_to_test = [
            (COMM_FW_VERSION, "FW_VERSION"),
            (COMM_GET_VALUES, "GET_VALUES"),
            (COMM_BMS_GET_VALUES, "BMS_GET_VALUES"),
        ]

        for cmd, name in commands_to_test:
            result = await tester.test_can_forward(84, cmd)
            await asyncio.sleep(0.5)

            if result is None:
                print(f"⚠ Reconnecting...")
                await tester.disconnect()
                await tester.connect()

    finally:
        await tester.disconnect()
        print("\n✓ Done")


if __name__ == "__main__":
    asyncio.run(main())
