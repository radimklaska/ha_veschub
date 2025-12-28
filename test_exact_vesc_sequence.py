#!/usr/bin/env python3
"""Exactly replicate VESCTool's byte sequence and timing."""
import asyncio
import struct
from pathlib import Path
import time

VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03

COMM_FW_VERSION = 0x00
COMM_PING_CAN = 0x3e
COMM_GET_CUSTOM_CONFIG = 0x5d
COMM_BMS_GET_VALUES = 0x60


class ExactVESCReplicator:
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
        print("✓ Connected and authenticated")

        # Wait like VESCTool does after auth
        await asyncio.sleep(1.0)

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

    async def _send_raw(self, payload: bytes):
        """Send raw payload and return response."""
        packet = self._pack_payload(payload)
        print(f"  → Sending: {packet.hex(' ')}")
        self.writer.write(packet)
        await self.writer.drain()

    async def _try_read_response(self, timeout: float = 5.0, consume_all: bool = False):
        """Try to read response packets."""
        responses = []
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = await asyncio.wait_for(
                    self._read_packet(),
                    timeout=max(0.1, timeout - (time.time() - start_time))
                )
                if response:
                    responses.append(response)
                    print(f"  ← Response: {len(response)} bytes, cmd 0x{response[0]:02x}, hex: {response[:40].hex(' ')}")
                    if not consume_all:
                        break
            except asyncio.TimeoutError:
                break

        if not responses:
            print(f"  ✗ No response (timeout {timeout}s)")

        return responses

    async def _read_packet(self):
        """Read one VESC packet."""
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

        # Validate
        received_crc = struct.unpack('>H', crc_bytes)[0]
        calculated_crc = self._calculate_crc16(payload)

        if stop_byte[0] != VESC_PACKET_STOP_BYTE:
            print(f"  ⚠ Invalid stop byte: {stop_byte[0]:02x}")
            return None

        if calculated_crc != received_crc:
            print(f"  ⚠ CRC mismatch: calc {calculated_crc:04x} != recv {received_crc:04x}")
            return None

        return payload

    async def exact_vesc_tool_sequence(self):
        """Replicate VESCTool's EXACT sequence from packet capture."""
        print("\n" + "="*70)
        print("EXACT VESCTool SEQUENCE REPLICATION")
        print("="*70)
        print("Matching timing and order from packet capture...\n")

        # Frame 6: FW_VERSION
        print("1. COMM_FW_VERSION (0x00)")
        await self._send_raw(bytes([0x00]))
        await self._try_read_response(timeout=5.0)
        await asyncio.sleep(0.05)  # Small delay like in capture

        # Frame 10: GET_CUSTOM_CONFIG with 0x00
        print("\n2. COMM_GET_CUSTOM_CONFIG (0x5d) + data 0x00")
        await self._send_raw(bytes([0x5d, 0x00]))
        responses = await self._try_read_response(timeout=5.0, consume_all=True)
        await asyncio.sleep(0.05)

        # Frame 11: PING_CAN
        print("\n3. COMM_PING_CAN (0x3e)")
        await self._send_raw(bytes([0x3e]))
        await self._try_read_response(timeout=5.0, consume_all=True)
        await asyncio.sleep(0.05)

        # Now try BMS (after setup commands)
        print("\n4. COMM_BMS_GET_VALUES (0x60) - THE MOMENT OF TRUTH")
        await self._send_raw(bytes([0x60]))
        responses = await self._try_read_response(timeout=5.0)

        if responses:
            for resp in responses:
                if resp[0] == 0x60:
                    print("\n" + "="*70)
                    print("🎉🎉🎉 BMS DATA RECEIVED! 🎉🎉🎉")
                    print("="*70)
                    self._parse_bms(resp)
                    return True

        return False

    def _parse_bms(self, data: bytes):
        """Parse BMS data."""
        if data[0] != 0x60:
            return

        payload = data[1:]
        def read_float32(offset):
            return struct.unpack('>f', payload[offset:offset+4])[0]

        print(f"\n📊 BMS Data:")
        print(f"  Total Voltage:   {read_float32(0):.2f} V")
        print(f"  Charge Voltage:  {read_float32(4):.2f} V")
        print(f"  Current In:      {read_float32(8):.3f} A")
        print(f"  Current IC:      {read_float32(12):.3f} A")


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

    print("="*70)
    print("EXACT VESCTool Sequence Test")
    print("="*70)

    replicator = ExactVESCReplicator("veschub.vedder.se", 65101, vesc_id, password)

    try:
        await replicator.connect()
        success = await replicator.exact_vesc_tool_sequence()

        if not success:
            print("\n" + "="*70)
            print("Still no BMS data - investigating further...")
            print("="*70)

    finally:
        await replicator.disconnect()
        print("\n✓ Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
