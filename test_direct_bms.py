#!/usr/bin/env python3
"""Test BMS commands directly on VESC Express (no CAN forwarding)."""
import asyncio
import logging
import struct
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
_LOGGER = logging.getLogger(__name__)

VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03
COMM_FW_VERSION = 0
COMM_GET_VALUES = 4
COMM_BMS_GET_VALUES = 96


class DirectBMSTester:
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

    async def _send_command(self, command: int, data: bytes = b'', timeout: float = 5.0):
        payload = bytes([command]) + data
        packet = self._pack_payload(payload)
        print(f"→ Sending command 0x{command:02x}: {packet.hex(' ')}")
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
            print(f"✗ Invalid stop byte")
            return None

        if calculated_crc != received_crc:
            print(f"✗ CRC mismatch")
            return None

        print(f"← Received ({len(payload)} bytes): {payload.hex(' ')}")
        return payload

    async def listen_passive(self, duration: float = 10.0):
        """Listen for any pushed data."""
        print(f"\n{'='*60}")
        print(f"Listening for {duration}s for any pushed data...")
        print('='*60)

        start_time = asyncio.get_event_loop().time()
        packet_count = 0

        while (asyncio.get_event_loop().time() - start_time) < duration:
            try:
                response = await asyncio.wait_for(self._read_packet(), timeout=1.0)
                if response:
                    packet_count += 1
                    print(f"\n📦 Packet #{packet_count}")
                    print(f"   Command: 0x{response[0]:02x}")
                    print(f"   Length: {len(response)} bytes")

                    if response[0] == COMM_BMS_GET_VALUES:
                        print("   ✓ This is BMS data!")
                        self.parse_bms_data(response)
            except asyncio.TimeoutError:
                continue

        print(f"\n{'='*60}")
        print(f"Received {packet_count} packet(s)")
        print('='*60)

    def parse_bms_data(self, data):
        """Parse BMS data."""
        if data[0] != COMM_BMS_GET_VALUES:
            return

        payload = data[1:]
        idx = 0

        def read_float32(offset):
            return struct.unpack('>f', payload[offset:offset+4])[0]

        def read_uint16(offset):
            return struct.unpack('>H', payload[offset:offset+2])[0]

        def read_uint8(offset):
            return payload[offset]

        try:
            print(f"\n   📊 BMS Data:")
            print(f"      Total Voltage: {read_float32(0):.2f}V")
            print(f"      Charge Voltage: {read_float32(4):.2f}V")
            print(f"      Current In: {read_float32(8):.3f}A")
            print(f"      Current IC: {read_float32(12):.3f}A")
            print(f"      Ah Counter: {read_float32(16):.3f}Ah")
            print(f"      Wh Counter: {read_float32(20):.3f}Wh")

            idx = 24
            if len(payload) > idx:
                cell_num = read_uint8(idx)
                idx += 1
                print(f"      Cells: {cell_num}")

                for i in range(min(cell_num, 32)):
                    if len(payload) >= idx + 2:
                        cell_v = read_uint16(idx) / 1000.0
                        print(f"        Cell {i+1}: {cell_v:.3f}V")
                        idx += 2

            if len(payload) > idx + 4:
                bal_state = struct.unpack('>I', payload[idx:idx+4])[0]
                print(f"      Balance State: 0x{bal_state:08x}")
                idx += 4

            if len(payload) > idx:
                temp_num = read_uint8(idx)
                idx += 1
                print(f"      Temperatures: {temp_num}")

                for i in range(min(temp_num, 10)):
                    if len(payload) >= idx + 2:
                        temp = read_uint16(idx) / 10.0
                        print(f"        Temp {i+1}: {temp:.1f}°C")
                        idx += 2

            if len(payload) >= idx + 4:
                soc = read_float32(idx)
                print(f"      State of Charge: {soc:.1f}%")
                idx += 4

            if len(payload) >= idx + 4:
                soh = read_float32(idx)
                print(f"      State of Health: {soh:.1f}%")
                idx += 4

            if len(payload) >= idx + 4:
                capacity = read_float32(idx)
                print(f"      Capacity: {capacity:.2f}Ah")

        except Exception as e:
            print(f"   ✗ Error parsing: {e}")


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
    print("Testing Direct BMS Access (No CAN Forwarding)")
    print("="*60)

    tester = DirectBMSTester("veschub.vedder.se", 65101, vesc_id, password)

    try:
        await tester.connect()

        # Test 1: FW Version (confirm connection)
        print("\n" + "="*60)
        print("TEST 1: FW Version")
        print("="*60)
        fw_response = await tester._send_command(COMM_FW_VERSION)
        if fw_response:
            print("✓ Connection working")

        # Test 2: Direct BMS command
        print("\n" + "="*60)
        print("TEST 2: Direct BMS_GET_VALUES (no CAN)")
        print("="*60)
        bms_response = await tester._send_command(COMM_BMS_GET_VALUES, timeout=5.0)

        if bms_response:
            print("✓ Got BMS response!")
            tester.parse_bms_data(bms_response)
        else:
            print("✗ No BMS response from direct command")

        # Test 3: Listen for pushed data
        await tester.listen_passive(duration=15.0)

    finally:
        await tester.disconnect()
        print("\n✓ Done")


if __name__ == "__main__":
    asyncio.run(main())
