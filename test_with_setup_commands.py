#!/usr/bin/env python3
"""Test BMS with the setup commands VESCTool sends."""
import asyncio
import struct
from pathlib import Path

VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03

# Commands discovered from packet capture
COMM_FW_VERSION = 0x00
COMM_PING_CAN = 0x3e  # 62 - VESCTool sends this!
COMM_GET_CUSTOM_CONFIG = 0x5d  # 93 - VESCTool sends this with data 0x00!
COMM_BMS_GET_VALUES = 0x60  # 96


class BMSTesterWithSetup:
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

    def _parse_bms(self, data: bytes):
        """Quick BMS parse."""
        if data[0] != COMM_BMS_GET_VALUES:
            return None

        payload = data[1:]
        def read_float32(offset):
            return struct.unpack('>f', payload[offset:offset+4])[0]

        try:
            bms_data = {
                'v_tot': read_float32(0),
                'v_charge': read_float32(4),
                'i_in': read_float32(8),
                'i_in_ic': read_float32(12),
            }
            print(f"\n  🔋 BMS Data:")
            print(f"    Total Voltage: {bms_data['v_tot']:.2f} V")
            print(f"    Charge Voltage: {bms_data['v_charge']:.2f} V")
            print(f"    Current In: {bms_data['i_in']:.3f} A")
            print(f"    Current IC: {bms_data['i_in_ic']:.3f} A")
            return bms_data
        except:
            return None

    async def test_with_vesc_sequence(self):
        """Replicate VESCTool's exact command sequence."""
        print("\n" + "="*70)
        print("REPLICATING VESCTool COMMAND SEQUENCE")
        print("="*70)

        # Step 1: FW_VERSION (like VESCTool)
        print("\n1️⃣  COMM_FW_VERSION (0x00)")
        response = await self._send_command(COMM_FW_VERSION)
        if response:
            print(f"   ✓ Got {len(response)} bytes")
        else:
            print(f"   ✗ Timeout")

        await asyncio.sleep(0.1)

        # Step 2: GET_CUSTOM_CONFIG with data 0x00 (NEW!)
        print("\n2️⃣  COMM_GET_CUSTOM_CONFIG (0x5d) with data 0x00")
        print("   (This might load BMS configuration!)")
        response = await self._send_command(COMM_GET_CUSTOM_CONFIG, bytes([0x00]))
        if response:
            print(f"   ✓ Got {len(response)} bytes")
            print(f"   Response: {response[:40].hex(' ')}")
        else:
            print(f"   ✗ Timeout")

        await asyncio.sleep(0.1)

        # Step 3: PING_CAN (NEW!)
        print("\n3️⃣  COMM_PING_CAN (0x3e)")
        print("   (This might discover/wake CAN devices!)")
        response = await self._send_command(COMM_PING_CAN)
        if response:
            print(f"   ✓ Got {len(response)} bytes")
            print(f"   Response: {response[:40].hex(' ')}")
        else:
            print(f"   ✗ Timeout")

        await asyncio.sleep(0.1)

        # Step 4: BMS_GET_VALUES (now it should work!)
        print("\n4️⃣  COMM_BMS_GET_VALUES (0x60)")
        print("   (After setup commands above...)")
        response = await self._send_command(COMM_BMS_GET_VALUES)

        if response:
            print(f"   ✓✓✓ GOT BMS RESPONSE! {len(response)} bytes ✓✓✓")
            print(f"   Command: 0x{response[0]:02x}")

            if response[0] == COMM_BMS_GET_VALUES:
                print(f"   🎉🎉🎉 BMS DATA CONFIRMED! 🎉🎉🎉")
                self._parse_bms(response)
                return True
            else:
                print(f"   Response hex: {response[:40].hex(' ')}")
        else:
            print(f"   ✗ Still timeout")

        return False


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
    print("🔬 Testing with VESCTool's Setup Commands")
    print("="*70)
    print(f"VESC ID: {vesc_id}")

    tester = BMSTesterWithSetup("veschub.vedder.se", 65101, vesc_id, password)

    try:
        await tester.connect()
        success = await tester.test_with_vesc_sequence()

        if success:
            print("\n" + "="*70)
            print("🎉 SUCCESS! We can now access BMS data!")
            print("="*70)
        else:
            print("\n" + "="*70)
            print("Still no BMS data - there might be more to it")
            print("="*70)

    finally:
        await tester.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
