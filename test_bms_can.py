#!/usr/bin/env python3
"""Test BMS via CAN forwarding.

Based on search results, BMS data might come via CAN bus, not UART.
Let's try forwarding COMM_BMS_GET_VALUES to different CAN IDs.
"""
import asyncio
import struct
from pathlib import Path

VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03
COMM_FW_VERSION = 0
COMM_FORWARD_CAN = 34
COMM_BMS_GET_VALUES = 96


class BMSTester:
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
        print("✓ Connected")

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

    async def _send_command(self, command: int, data: bytes = b'', timeout: float = 2.0):
        payload = bytes([command]) + data
        packet = self._pack_payload(payload)
        self.writer.write(packet)
        await self.writer.drain()

        try:
            return await asyncio.wait_for(self._read_packet(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def _read_packet(self):
        try:
            while True:
                byte = await self.reader.readexactly(1)
                if byte[0] == VESC_PACKET_START_BYTE:
                    break

            len_byte = await self.reader.readexactly(1)
            if len_byte[0] < 128:
                payload_len = len_byte[0]
            else:
                len_low = await self.reader.readexactly(1)
                payload_len = ((len_byte[0] & 0x7F) << 8) | len_low[0]

            payload = await self.reader.readexactly(payload_len)
            crc_bytes = await self.reader.readexactly(2)
            stop_byte = await self.reader.readexactly(1)

            received_crc = struct.unpack('>H', crc_bytes)[0]
            calculated_crc = self._calculate_crc16(payload)

            if stop_byte[0] != VESC_PACKET_STOP_BYTE or calculated_crc != received_crc:
                return None

            return payload
        except:
            return None

    async def test_bms_can_id(self, can_id: int):
        """Test BMS request via CAN forwarding."""
        print(f"\n{'='*60}")
        print(f"Testing BMS via CAN ID {can_id}")
        print('='*60)

        # Forward COMM_BMS_GET_VALUES to this CAN ID
        can_data = bytes([can_id, COMM_BMS_GET_VALUES])
        response = await self._send_command(COMM_FORWARD_CAN, can_data)

        if response:
            print(f"✓ Got response! ({len(response)} bytes)")
            print(f"  Hex: {response[:60].hex(' ')}")

            if response[0] == COMM_BMS_GET_VALUES:
                print(f"  ✓✓✓ THIS IS BMS DATA! ✓✓✓")
                self._parse_bms(response)
                return True
            else:
                print(f"  Command: 0x{response[0]:02x}")
        else:
            print(f"✗ No response")

        return False

    def _parse_bms(self, data: bytes):
        """Quick BMS parse."""
        payload = data[1:]

        def read_float32(offset):
            return struct.unpack('>f', payload[offset:offset+4])[0]

        try:
            print(f"\n  📊 BMS Data:")
            print(f"    Total Voltage: {read_float32(0):.2f} V")
            print(f"    Charge Voltage: {read_float32(4):.2f} V")
            print(f"    Current In: {read_float32(8):.3f} A")
            print(f"    Current IC: {read_float32(12):.3f} A")
        except:
            pass


async def main():
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
    print("Testing BMS via CAN Forwarding")
    print("="*60)

    tester = BMSTester("veschub.vedder.se", 65101, vesc_id, password)

    try:
        await tester.connect()

        # Test CAN IDs that commonly have BMS
        can_ids = [0, 1, 10, 20, 84, 124, 125, 126, 127]

        for can_id in can_ids:
            found = await tester.test_bms_can_id(can_id)
            if found:
                print(f"\n🎯 FOUND BMS ON CAN ID {can_id}!")
                break
            await asyncio.sleep(0.3)

    finally:
        await tester.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
