#!/usr/bin/env python3
"""Final comprehensive BMS test - try every possible method."""
import asyncio
import struct
from pathlib import Path

VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03

# All possible BMS-related commands
COMM_FW_VERSION = 0
COMM_GET_VALUES = 4
COMM_FORWARD_CAN = 34
COMM_BMS_GET_VALUES = 96
COMM_BMS_SET_CHARGE_ALLOWED = 97
COMM_GET_VALUES_SETUP = 36
COMM_GET_VALUES_SELECTIVE = 35
COMM_BMS_FWD_CAN_RX = 37
COMM_GET_APPCONF = 21


class ComprehensiveBMSTester:
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

    async def test_method(self, name: str, command: int, data: bytes = b''):
        """Test a specific method."""
        print(f"→ {name}...", end=" ")
        response = await self._send_command(command, data, timeout=1.0)

        if response:
            print(f"✓ {len(response)} bytes - Cmd: 0x{response[0]:02x}")
            if response[0] == COMM_BMS_GET_VALUES or len(response) > 50:
                print(f"  Hex: {response[:40].hex(' ')}")
                return True
        else:
            print("✗ Timeout")
        return False

    async def run_all_tests(self):
        """Try every possible way to get BMS data."""
        print("="*70)
        print("COMPREHENSIVE BMS TEST - Trying Every Method")
        print("="*70)

        # Test 1: Direct BMS command
        print("\n📍 TEST 1: Direct COMM_BMS_GET_VALUES")
        print("-"*70)
        await self.test_method("Direct BMS request", COMM_BMS_GET_VALUES)

        # Test 2: BMS via CAN forwarding (special IDs)
        print("\n📍 TEST 2: BMS via CAN Forwarding (Local Device IDs)")
        print("-"*70)
        # Try special/reserved CAN IDs that might mean "local"
        special_ids = [0, 254, 255]  # 254 = broadcast, 255 = invalid/special
        for can_id in special_ids:
            can_data = bytes([can_id, COMM_BMS_GET_VALUES])
            await self.test_method(f"CAN ID {can_id} BMS", COMM_FORWARD_CAN, can_data)

        # Test 3: GET_VALUES (might contain BMS data)
        print("\n📍 TEST 3: COMM_GET_VALUES (might embed BMS)")
        print("-"*70)
        response = await self.test_method("GET_VALUES direct", COMM_GET_VALUES)

        # Test 4: GET_VALUES via CAN to local
        print("\n📍 TEST 4: GET_VALUES via CAN to local device")
        print("-"*70)
        for can_id in [0, 254, 255]:
            can_data = bytes([can_id, COMM_GET_VALUES])
            await self.test_method(f"CAN ID {can_id} GET_VALUES", COMM_FORWARD_CAN, can_data)

        # Test 5: GET_VALUES_SETUP
        print("\n📍 TEST 5: COMM_GET_VALUES_SETUP")
        print("-"*70)
        await self.test_method("GET_VALUES_SETUP", COMM_GET_VALUES_SETUP)

        # Test 6: Selective values with BMS mask
        print("\n📍 TEST 6: COMM_GET_VALUES_SELECTIVE with mask")
        print("-"*70)
        # Try requesting specific value mask (bit flags for what to return)
        for mask in [0xFFFFFFFF, 0x00000001, 0x80000000]:
            mask_data = struct.pack('>I', mask)
            await self.test_method(f"Selective mask 0x{mask:08x}", COMM_GET_VALUES_SELECTIVE, mask_data)

        # Test 7: Passive listening
        print("\n📍 TEST 7: Passive Receive (15 second listen)")
        print("-"*70)
        print("Listening for any pushed data...")

        start_time = asyncio.get_event_loop().time()
        packet_count = 0

        while (asyncio.get_event_loop().time() - start_time) < 15.0:
            try:
                response = await asyncio.wait_for(self._read_packet(), timeout=0.5)
                if response:
                    packet_count += 1
                    print(f"  📦 Packet #{packet_count}: Cmd 0x{response[0]:02x}, {len(response)} bytes")
                    if response[0] == COMM_BMS_GET_VALUES:
                        print(f"     ✓✓✓ BMS DATA FOUND!")
                        break
            except asyncio.TimeoutError:
                # Send a BMS request every 2 seconds while listening
                if int(asyncio.get_event_loop().time() - start_time) % 2 == 0:
                    await self._send_command(COMM_BMS_GET_VALUES, timeout=0.1)
                continue

        if packet_count == 0:
            print("  ✗ No packets received")

        # Test 8: Try app config query
        print("\n📍 TEST 8: Query App Configuration (might enable BMS)")
        print("-"*70)
        await self.test_method("GET_APPCONF", COMM_GET_APPCONF)

        print("\n" + "="*70)
        print("TESTS COMPLETE")
        print("="*70)


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

    tester = ComprehensiveBMSTester("veschub.vedder.se", 65101, vesc_id, password)

    try:
        await tester.connect()
        await tester.run_all_tests()
    finally:
        await tester.disconnect()
        print("\n✓ Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
