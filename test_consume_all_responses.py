#!/usr/bin/env python3
"""Test that properly consumes all responses."""
import asyncio
import struct
from pathlib import Path

VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03


class ProperVESCTester:
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
        print("✓ Connected\n")

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

    async def _send_and_consume_all(self, payload: bytes, label: str):
        """Send command and consume ALL responses."""
        packet = self._pack_payload(payload)
        print(f"{label}")
        print(f"  TX: {packet.hex(' ')}")

        self.writer.write(packet)
        await self.writer.drain()

        # Read ALL responses (may be multiple)
        responses = []
        while True:
            try:
                resp = await asyncio.wait_for(self._read_one_packet(), timeout=0.5)
                if resp:
                    responses.append(resp)
                    print(f"  RX: {len(resp)} bytes, cmd 0x{resp[0]:02x}")
                else:
                    break
            except asyncio.TimeoutError:
                break

        if not responses:
            print(f"  (no response)")

        return responses

    async def _read_one_packet(self):
        """Read exactly one packet, handling errors gracefully."""
        try:
            # Find start byte
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

            # Read rest
            payload = await self.reader.readexactly(payload_len)
            crc_bytes = await self.reader.readexactly(2)
            stop_byte = await self.reader.readexactly(1)

            # Validate
            if stop_byte[0] != VESC_PACKET_STOP_BYTE:
                print(f"    ⚠ Bad stop byte: {stop_byte[0]:02x}, skipping...")
                return None

            received_crc = struct.unpack('>H', crc_bytes)[0]
            calculated_crc = self._calculate_crc16(payload)

            if calculated_crc != received_crc:
                print(f"    ⚠ CRC mismatch, skipping...")
                return None

            return payload

        except asyncio.IncompleteReadError:
            return None

    async def test_sequence(self):
        """Test the full sequence."""
        print("="*70)
        print("TESTING WITH PROPER RESPONSE HANDLING")
        print("="*70 + "\n")

        # 1. FW_VERSION
        await self._send_and_consume_all(bytes([0x00]), "1. FW_VERSION")
        await asyncio.sleep(0.1)

        # 2. GET_CUSTOM_CONFIG
        await self._send_and_consume_all(bytes([0x5d, 0x00]), "2. GET_CUSTOM_CONFIG + 0x00")
        await asyncio.sleep(0.1)

        # 3. PING_CAN
        await self._send_and_consume_all(bytes([0x3e]), "3. PING_CAN")
        await asyncio.sleep(0.1)

        # 4. BMS_GET_VALUES
        print("4. BMS_GET_VALUES ⭐")
        responses = await self._send_and_consume_all(bytes([0x60]), "")

        for resp in responses:
            if resp[0] == 0x60:
                print("\n" + "="*70)
                print("🎉 BMS DATA RECEIVED!")
                print("="*70)
                self._parse_bms(resp)
                return True

        return False

    def _parse_bms(self, data: bytes):
        """Parse BMS."""
        payload = data[1:]
        def read_float32(offset):
            return struct.unpack('>f', payload[offset:offset+4])[0]

        print(f"\n  Total Voltage:  {read_float32(0):.2f} V")
        print(f"  Charge Voltage: {read_float32(4):.2f} V")
        print(f"  Current In:     {read_float32(8):.3f} A")


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

    tester = ProperVESCTester("veschub.vedder.se", 65101, vesc_id, password)

    try:
        await tester.connect()
        await tester.test_sequence()
    finally:
        await tester.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
