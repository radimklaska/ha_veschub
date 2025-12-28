#!/usr/bin/env python3
"""Scan all CAN IDs to find the BMS."""
import asyncio
import logging
import struct
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')
_LOGGER = logging.getLogger(__name__)

VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03
COMM_FW_VERSION = 0
COMM_FORWARD_CAN = 34
COMM_BMS_GET_VALUES = 96


class BMSScanner:
    def __init__(self, host: str, port: int, vesc_id: str, password: str):
        self.host = host
        self.port = port
        self.vesc_id = vesc_id
        self.password = password
        self.reader = None
        self.writer = None
        self.found_devices = []

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        auth_string = f"VESCTOOL:{self.vesc_id}:{self.password}\n"
        self.writer.write(auth_string.encode('utf-8'))
        await self.writer.drain()
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

    async def _send_command(self, command: int, data: bytes = b'', timeout: float = 1.0):
        payload = bytes([command]) + data
        packet = self._pack_payload(payload)
        self.writer.write(packet)
        await self.writer.drain()

        try:
            response = await asyncio.wait_for(self._read_packet(), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            return None

    async def _read_packet(self):
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

            # Read payload, CRC, stop
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

    async def test_can_id(self, can_id: int):
        """Test if CAN ID responds to FW_VERSION."""
        can_data = bytes([can_id, COMM_FW_VERSION])
        response = await self._send_command(COMM_FORWARD_CAN, can_data, timeout=0.5)

        if response and len(response) > 3:
            # Parse firmware name
            fw_name = response[3:].decode('utf-8', errors='ignore').split('\x00')[0]
            return fw_name
        return None

    async def test_bms(self, can_id: int):
        """Test if CAN ID responds to BMS_GET_VALUES."""
        can_data = bytes([can_id, COMM_BMS_GET_VALUES])
        response = await self._send_command(COMM_FORWARD_CAN, can_data, timeout=0.5)

        if response and len(response) > 10:
            return True
        return False

    async def scan_range(self, start: int, end: int):
        """Scan a range of CAN IDs."""
        print(f"\nScanning CAN IDs {start}-{end}...")
        print("="*60)

        for can_id in range(start, end + 1):
            # Check if device exists
            fw_name = await self.test_can_id(can_id)

            if fw_name:
                has_bms = await self.test_bms(can_id)

                device_info = {
                    'can_id': can_id,
                    'fw_name': fw_name,
                    'has_bms': has_bms
                }
                self.found_devices.append(device_info)

                bms_indicator = "✓ BMS" if has_bms else "  Motor"
                print(f"CAN ID {can_id:3d}: {bms_indicator} - {fw_name}")

        print("="*60)


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
    print("Scanning for BMS on CAN bus")
    print("="*60)
    print(f"VESC ID: {vesc_id}")

    scanner = BMSScanner("veschub.vedder.se", 65101, vesc_id, password)

    try:
        await scanner.connect()
        print("✓ Connected\n")

        # Scan common ranges
        # First, try around ID 84 (we found a motor controller there)
        await scanner.scan_range(80, 90)

        # Then try other common BMS IDs
        await scanner.scan_range(0, 10)
        await scanner.scan_range(120, 127)

        # Show summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"\nFound {len(scanner.found_devices)} device(s):")

        for device in scanner.found_devices:
            bms_marker = "🔋 BMS" if device['has_bms'] else "⚙️  Motor"
            print(f"  {bms_marker} CAN ID {device['can_id']}: {device['fw_name']}")

        bms_devices = [d for d in scanner.found_devices if d['has_bms']]
        if bms_devices:
            print(f"\n✓ Found {len(bms_devices)} device(s) with BMS data!")
            for device in bms_devices:
                print(f"  → Use CAN ID {device['can_id']} for BMS monitoring")
        else:
            print("\n✗ No BMS devices found on scanned IDs")
            print("  Try expanding the scan range or check if BMS is connected")

    finally:
        await scanner.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
