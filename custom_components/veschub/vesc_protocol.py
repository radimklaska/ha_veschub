"""VESC protocol implementation over TCP for VESCHub communication."""
import asyncio
import logging
import struct
from typing import Optional

from .const import (
    COMM_BMS_GET_VALUES,
    COMM_GET_VALUES,
    VESC_PACKET_START_BYTE,
    VESC_PACKET_STOP_BYTE,
)

_LOGGER = logging.getLogger(__name__)


class VESCProtocol:
    """VESC protocol handler for TCP communication."""

    def __init__(self, host: str, port: int, vesc_id: Optional[str] = None, password: Optional[str] = None):
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
        _LOGGER.warning(f"[CONNECT] Attempting connection to {self.host}:{self.port}")
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10
            )
            _LOGGER.warning(f"[CONNECT] TCP connection established to {self.host}:{self.port}")

            # Authenticate if credentials provided (for public VESCHub)
            if self.vesc_id and self.password:
                auth_string = f"VESCTOOL:{self.vesc_id}:{self.password}\n"
                _LOGGER.warning(f"[AUTH] Sending authentication for VESC ID: {self.vesc_id}")
                self.writer.write(auth_string.encode('utf-8'))
                await self.writer.drain()

                # Wait for authentication to process
                await asyncio.sleep(1.0)
                _LOGGER.warning("[AUTH] Authentication sent, waiting for response")
            else:
                _LOGGER.warning("[CONNECT] No credentials provided, skipping authentication")

            self._connected = True
            _LOGGER.warning("[CONNECT] Connection successful, marked as connected")
            return True
        except Exception as e:
            _LOGGER.error(f"[CONNECT] Failed to connect to VESCHub: {e}", exc_info=True)
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
        # Determine if we need short or long format
        if len(payload) <= 256:
            # Short format: [2][len][payload][crc][3]
            packet = bytes([VESC_PACKET_START_BYTE, len(payload)])
        else:
            # Long format: [2][len_high][len_low][payload][crc][3]
            packet = bytes([VESC_PACKET_START_BYTE,
                          (len(payload) >> 8) & 0xFF,
                          len(payload) & 0xFF])

        packet += payload

        # Calculate CRC on payload only
        crc = self._calculate_crc16(payload)
        packet += struct.pack('>H', crc)
        packet += bytes([VESC_PACKET_STOP_BYTE])

        return packet

    async def _send_command(self, command: int, data: bytes = b'') -> Optional[bytes]:
        """Send a command to VESC and wait for response."""
        if not self._connected or not self.writer or not self.reader:
            _LOGGER.error("[CMD] Not connected to VESCHub")
            return None

        try:
            # Build payload: [command][data]
            payload = bytes([command]) + data
            packet = self._pack_payload(payload)

            _LOGGER.warning(f"[CMD] Sending command {command} (0x{command:02x}), packet: {packet.hex()}")
            self.writer.write(packet)
            await self.writer.drain()
            _LOGGER.warning("[CMD] Packet sent, waiting for response...")

            # Read response with timeout
            response = await asyncio.wait_for(
                self._read_packet(),
                timeout=5.0
            )

            _LOGGER.warning(f"[CMD] Response received: {len(response) if response else 0} bytes")
            return response

        except asyncio.TimeoutError:
            _LOGGER.error("[CMD] Timeout waiting for response after 5 seconds")
            return None
        except Exception as e:
            _LOGGER.error(f"[CMD] Error sending command: {e}", exc_info=True)
            return None

    async def _read_packet(self) -> Optional[bytes]:
        """Read a VESC protocol packet from the stream."""
        try:
            # Wait for start byte
            while True:
                byte = await self.reader.readexactly(1)
                if byte[0] == VESC_PACKET_START_BYTE:
                    break

            # Read length
            len_byte = await self.reader.readexactly(1)

            if len_byte[0] < 128:
                # Short format
                payload_len = len_byte[0]
            else:
                # Long format
                len_low = await self.reader.readexactly(1)
                payload_len = ((len_byte[0] & 0x7F) << 8) | len_low[0]

            # Read payload
            payload = await self.reader.readexactly(payload_len)

            # Read CRC
            crc_bytes = await self.reader.readexactly(2)
            received_crc = struct.unpack('>H', crc_bytes)[0]

            # Read stop byte
            stop_byte = await self.reader.readexactly(1)
            if stop_byte[0] != VESC_PACKET_STOP_BYTE:
                _LOGGER.error("Invalid stop byte")
                return None

            # Verify CRC
            calculated_crc = self._calculate_crc16(payload)
            if calculated_crc != received_crc:
                _LOGGER.error(f"CRC mismatch: {calculated_crc:04x} != {received_crc:04x}")
                return None

            _LOGGER.debug(f"Received payload: {payload.hex()}")
            return payload

        except asyncio.IncompleteReadError:
            _LOGGER.error("Incomplete packet received")
            return None
        except Exception as e:
            _LOGGER.error(f"Error reading packet: {e}")
            return None

    async def get_bms_values(self) -> Optional[dict]:
        """Get BMS values from VESC."""
        response = await self._send_command(COMM_BMS_GET_VALUES)

        if not response or len(response) < 2:
            return None

        try:
            # Parse BMS data based on VESC BMS protocol
            # Response format: [command_id][data...]
            if response[0] != COMM_BMS_GET_VALUES:
                _LOGGER.error(f"Unexpected response command: {response[0]}")
                return None

            data = response[1:]  # Skip command byte

            # Parse based on VESC BMS firmware structure
            # This is a simplified parser - adjust based on actual VESC BMS firmware version
            index = 0

            def read_float32(offset):
                return struct.unpack('>f', data[offset:offset+4])[0]

            def read_uint16(offset):
                return struct.unpack('>H', data[offset:offset+2])[0]

            def read_uint8(offset):
                return data[offset]

            # Parse BMS values (structure based on VESC BMS firmware)
            bms_data = {
                "v_tot": read_float32(index),           # Total voltage
                "v_charge": read_float32(index + 4),    # Charge voltage
                "i_in": read_float32(index + 8),        # Input current
                "i_in_ic": read_float32(index + 12),    # Input current IC
                "ah_cnt": read_float32(index + 16),     # Amp-hour counter
                "wh_cnt": read_float32(index + 20),     # Watt-hour counter
            }

            index += 24

            # Cell voltages
            if len(data) > index + 1:
                cell_num = read_uint8(index)
                index += 1

                cells = []
                for i in range(min(cell_num, 32)):  # Max 32 cells
                    if len(data) >= index + 2:
                        cell_v = read_uint16(index) / 1000.0  # Convert mV to V
                        cells.append(cell_v)
                        index += 2

                bms_data["cell_voltages"] = cells
                bms_data["cell_num"] = cell_num

            # Balance state
            if len(data) > index + 4:
                bms_data["bal_state"] = struct.unpack('>I', data[index:index+4])[0]
                index += 4

            # Temperatures
            if len(data) > index + 1:
                temp_adc_num = read_uint8(index)
                index += 1

                temps = []
                for i in range(min(temp_adc_num, 10)):  # Max 10 temp sensors
                    if len(data) >= index + 2:
                        temp = read_uint16(index) / 10.0  # Convert to °C
                        temps.append(temp)
                        index += 2

                bms_data["temperatures"] = temps
                bms_data["temp_adc_num"] = temp_adc_num

            # State of charge
            if len(data) >= index + 4:
                bms_data["soc"] = read_float32(index)
                index += 4

            # State of health
            if len(data) >= index + 4:
                bms_data["soh"] = read_float32(index)
                index += 4

            # Capacity Ah
            if len(data) >= index + 4:
                bms_data["capacity_ah"] = read_float32(index)

            _LOGGER.debug(f"Parsed BMS data: {bms_data}")
            return bms_data

        except Exception as e:
            _LOGGER.error(f"Error parsing BMS values: {e}")
            return None

    async def get_values(self) -> Optional[dict]:
        """Get general VESC values (motor controller data)."""
        response = await self._send_command(COMM_GET_VALUES)

        if not response or len(response) < 2:
            return None

        try:
            if response[0] != COMM_GET_VALUES:
                return None

            # Parse VESC values - simplified version
            # Add more fields as needed
            data = response[1:]

            return {
                "packet_id": response[0],
                "raw_data": data.hex()
            }

        except Exception as e:
            _LOGGER.error(f"Error parsing VESC values: {e}")
            return None
