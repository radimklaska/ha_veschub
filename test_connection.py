#!/usr/bin/env python3
"""Test script for VESC Hub connection."""
import asyncio
import logging
import struct
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)


# Constants
COMM_BMS_GET_VALUES = 50
VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03


class VESCProtocol:
    """VESC protocol handler for TCP communication."""

    def __init__(self, host: str, port: int, vesc_id: str = None, password: str = None):
        """Initialize VESC protocol handler."""
        self.host = host
        self.port = port
        self.vesc_id = vesc_id
        self.password = password
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to VESCHub via TCP."""
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10
            )
            _LOGGER.info(f"Connected to VESCHub at {self.host}:{self.port}")

            # Authenticate if credentials provided
            if self.vesc_id and self.password:
                auth_string = f"VESCTOOL:{self.vesc_id}:{self.password}\n"
                _LOGGER.debug(f"Sending auth: VESCTOOL:{self.vesc_id}:***")
                self.writer.write(auth_string.encode('utf-8'))
                await self.writer.drain()

                # Wait for auth response and initial data
                await asyncio.sleep(1.0)
                _LOGGER.info("Authentication sent")

            self._connected = True
            return True
        except Exception as e:
            _LOGGER.error(f"Failed to connect to VESCHub: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        """Disconnect from VESCHub."""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                _LOGGER.error(f"Error disconnecting: {e}")
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self._connected

    @staticmethod
    def _calculate_crc16(data: bytes) -> int:
        """Calculate CRC16 checksum for VESC protocol."""
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
        """Pack payload with VESC protocol framing."""
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

    async def _send_command(self, command: int, data: bytes = b'') -> Optional[bytes]:
        """Send a command to VESC and wait for response."""
        if not self._connected or not self.writer or not self.reader:
            _LOGGER.error("Not connected to VESCHub")
            return None

        try:
            payload = bytes([command]) + data
            packet = self._pack_payload(payload)

            _LOGGER.debug(f"Sending packet: {packet.hex()}")
            self.writer.write(packet)
            await self.writer.drain()

            response = await asyncio.wait_for(
                self._read_packet(),
                timeout=10.0
            )

            return response

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout waiting for response")
            return None
        except Exception as e:
            _LOGGER.error(f"Error sending command: {e}")
            return None

    async def _read_packet(self) -> Optional[bytes]:
        """Read a VESC protocol packet from the stream."""
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
            received_crc = struct.unpack('>H', crc_bytes)[0]
            stop_byte = await self.reader.readexactly(1)

            if stop_byte[0] != VESC_PACKET_STOP_BYTE:
                _LOGGER.error("Invalid stop byte")
                return None

            calculated_crc = self._calculate_crc16(payload)
            if calculated_crc != received_crc:
                _LOGGER.error(f"CRC mismatch: {calculated_crc:04x} != {received_crc:04x}")
                return None

            _LOGGER.debug(f"Received payload: {payload.hex()}")
            return payload

        except Exception as e:
            _LOGGER.error(f"Error reading packet: {e}")
            return None

    async def get_bms_values(self, passive=False) -> Optional[dict]:
        """Get BMS values from VESC.

        If passive=True, just wait for pushed data instead of sending a command.
        """
        if passive:
            # Just wait for incoming data
            response = await asyncio.wait_for(self._read_packet(), timeout=10.0)
        else:
            response = await self._send_command(COMM_BMS_GET_VALUES)

        if not response or len(response) < 2:
            return None

        try:
            if response[0] != COMM_BMS_GET_VALUES:
                _LOGGER.error(f"Unexpected response command: {response[0]}")
                return None

            data = response[1:]
            index = 0

            def read_float32(offset):
                return struct.unpack('>f', data[offset:offset+4])[0]

            def read_uint16(offset):
                return struct.unpack('>H', data[offset:offset+2])[0]

            def read_uint8(offset):
                return data[offset]

            bms_data = {
                "v_tot": read_float32(index),
                "v_charge": read_float32(index + 4),
                "i_in": read_float32(index + 8),
                "i_in_ic": read_float32(index + 12),
                "ah_cnt": read_float32(index + 16),
                "wh_cnt": read_float32(index + 20),
            }

            index += 24

            if len(data) > index + 1:
                cell_num = read_uint8(index)
                index += 1

                cells = []
                for i in range(min(cell_num, 32)):
                    if len(data) >= index + 2:
                        cell_v = read_uint16(index) / 1000.0
                        cells.append(cell_v)
                        index += 2

                bms_data["cell_voltages"] = cells
                bms_data["cell_num"] = cell_num

            if len(data) > index + 4:
                bms_data["bal_state"] = struct.unpack('>I', data[index:index+4])[0]
                index += 4

            if len(data) > index + 1:
                temp_adc_num = read_uint8(index)
                index += 1

                temps = []
                for i in range(min(temp_adc_num, 10)):
                    if len(data) >= index + 2:
                        temp = read_uint16(index) / 10.0
                        temps.append(temp)
                        index += 2

                bms_data["temperatures"] = temps
                bms_data["temp_adc_num"] = temp_adc_num

            if len(data) >= index + 4:
                bms_data["soc"] = read_float32(index)
                index += 4

            if len(data) >= index + 4:
                bms_data["soh"] = read_float32(index)
                index += 4

            if len(data) >= index + 4:
                bms_data["capacity_ah"] = read_float32(index)

            _LOGGER.debug(f"Parsed BMS data: {bms_data}")
            return bms_data

        except Exception as e:
            _LOGGER.error(f"Error parsing BMS values: {e}")
            return None


async def test_connection():
    """Test connection to VESCHub."""
    # TODO: Replace with your actual credentials
    host = "veschub.vedder.se"
    port = 65101
    vesc_id = "your-vesc-id"
    password = "your-password"

    print(f"Testing connection to {host}:{port}")
    print(f"VESC ID: {vesc_id}")
    print("-" * 50)

    vesc = VESCProtocol(host, port, vesc_id, password)

    print("Connecting...")
    if await vesc.connect():
        print("✓ Connected successfully")

        print("\nWaiting for BMS values (passive mode)...")
        bms_data = await vesc.get_bms_values(passive=True)

        if bms_data:
            print("✓ BMS data received:")
            print("-" * 50)
            for key, value in bms_data.items():
                if isinstance(value, list):
                    print(f"{key}:")
                    for i, v in enumerate(value):
                        print(f"  [{i}]: {v}")
                else:
                    print(f"{key}: {value}")
        else:
            print("✗ Failed to get BMS data")
            print("Might require authentication or different command.")

        await vesc.disconnect()
        print("\n✓ Disconnected")
    else:
        print("✗ Connection failed")


if __name__ == "__main__":
    asyncio.run(test_connection())
