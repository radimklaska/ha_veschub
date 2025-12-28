#!/usr/bin/env python3
"""Get all available data from VESC Express directly."""
import asyncio
import logging
import struct
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(message)s')

VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03

# All VESC commands we can try
COMMANDS_TO_TEST = {
    0x00: "COMM_FW_VERSION",
    0x04: "COMM_GET_VALUES",
    0x11: "COMM_SET_MCCONF",  # Might return current config
    0x12: "COMM_GET_MCCONF",
    0x13: "COMM_GET_MCCONF_DEFAULT",
    0x14: "COMM_SET_APPCONF",
    0x15: "COMM_GET_APPCONF",
    0x16: "COMM_GET_APPCONF_DEFAULT",
    0x17: "COMM_SAMPLE_PRINT",
    0x1B: "COMM_GET_DECODED_PPM",
    0x1C: "COMM_GET_DECODED_ADC",
    0x1D: "COMM_GET_DECODED_CHUK",
    0x23: "COMM_GET_VALUES_SELECTIVE",
    0x24: "COMM_GET_VALUES_SETUP",
    0x25: "COMM_SET_MCCONF_TEMP",
    0x29: "COMM_GET_DECODED_BALANCE",
    0x2E: "COMM_GET_IMU_DATA",
    0x32: "COMM_BMS_GET_VALUES",
    0x60: "COMM_BMS_GET_VALUES_ALT",  # Try alternate BMS command
    0x50: "COMM_CUSTOM_APP_DATA",
}


class VESCExpressReader:
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
            response = await asyncio.wait_for(self._read_packet(), timeout=timeout)
            return response
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
    print("Probing VESC Express for All Available Commands")
    print("="*60)

    reader = VESCExpressReader("veschub.vedder.se", 65101, vesc_id, password)

    try:
        await reader.connect()
        print("✓ Connected\n")

        successful_commands = []

        for cmd_id, cmd_name in sorted(COMMANDS_TO_TEST.items()):
            print(f"Testing 0x{cmd_id:02x} {cmd_name}...", end=" ")

            response = await reader._send_command(cmd_id)

            if response and len(response) > 0:
                print(f"✓ {len(response)} bytes")
                successful_commands.append((cmd_id, cmd_name, response))
            else:
                print(f"✗ No response")

            # Small delay between commands
            await asyncio.sleep(0.2)

        # Show summary
        print("\n" + "="*60)
        print(f"SUCCESSFUL COMMANDS ({len(successful_commands)})")
        print("="*60)

        for cmd_id, cmd_name, response in successful_commands:
            print(f"\n0x{cmd_id:02x} {cmd_name}:")
            print(f"  Length: {len(response)} bytes")
            print(f"  First 100 bytes: {response[:100].hex(' ')}")

            # Special parsing for known commands
            if cmd_id == 0x00:  # FW_VERSION
                fw_name = response[3:].decode('utf-8', errors='ignore').split('\x00')[0]
                print(f"  Firmware: v{response[1]}.{response[2]} - {fw_name}")

            elif cmd_id == 0x04:  # GET_VALUES
                print(f"  → Contains motor/controller values (temp, current, voltage, etc.)")

            elif cmd_id in [0x32, 0x60]:  # BMS commands
                print(f"  → ✓✓✓ THIS MIGHT BE BMS DATA! ✓✓✓")

        # Save detailed hex dumps
        print("\n" + "="*60)
        print("Saving detailed responses to vesc_express_responses.txt")
        print("="*60)

        with open('vesc_express_responses.txt', 'w') as f:
            f.write("VESC Express Command Responses\n")
            f.write("="*60 + "\n\n")

            for cmd_id, cmd_name, response in successful_commands:
                f.write(f"0x{cmd_id:02x} {cmd_name}\n")
                f.write(f"Length: {len(response)} bytes\n")
                f.write(f"Hex: {response.hex(' ')}\n")
                f.write(f"ASCII: {response.decode('utf-8', errors='replace')}\n")
                f.write("\n" + "-"*60 + "\n\n")

        print("✓ Saved")

    finally:
        await reader.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
