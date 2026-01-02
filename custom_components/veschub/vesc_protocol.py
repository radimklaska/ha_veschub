"""VESC protocol implementation over TCP for VESCHub communication."""
import asyncio
import logging
import struct
from typing import Optional

from .const import (
    COMM_BMS_GET_VALUES,
    COMM_FW_VERSION,
    COMM_GET_CUSTOM_CONFIG,
    COMM_GET_VALUES,
    COMM_PING_CAN,
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

    async def _send_command(self, command: int, data: bytes = b'', timeout: float = 5.0) -> Optional[bytes]:
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
                timeout=timeout
            )

            _LOGGER.warning(f"[CMD] Response received: {len(response) if response else 0} bytes")
            return response

        except (ConnectionError, BrokenPipeError, OSError) as e:
            _LOGGER.error(f"[CMD] Connection error ({type(e).__name__}): {e} - marking as disconnected")
            self._connected = False
            await self.disconnect()
            return None
        except asyncio.TimeoutError:
            _LOGGER.error("[CMD] Timeout waiting for response after 5 seconds")
            self._connected = False
            await self.disconnect()
            return None
        except asyncio.IncompleteReadError as e:
            _LOGGER.error(f"[CMD] Connection closed by server (got {len(e.partial)} bytes, expected more)")
            _LOGGER.error(f"[CMD] Partial data: {e.partial.hex() if e.partial else 'none'}")
            self._connected = False
            await self.disconnect()
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

    async def get_bms_values_rapid(self) -> Optional[dict]:
        """Get BMS values using rapid-fire command sequence.

        This is the WORKING method discovered through packet capture analysis.
        Must send commands in rapid succession without waiting for individual responses.
        """
        # CRITICAL: Test script creates FRESH connection each time
        # Reconnect to avoid stale connection state
        _LOGGER.warning("[BMS] Creating fresh connection for BMS request...")
        await self.disconnect()
        if not await self.connect():
            _LOGGER.error("[BMS] Failed to reconnect for BMS request")
            return None

        try:
            _LOGGER.warning("[BMS] Sending rapid-fire command sequence for BMS access...")

            # CRITICAL: Wait after connection/auth before sending commands (like test script!)
            await asyncio.sleep(1.0)
            _LOGGER.warning("[BMS] Auth settled, sending commands...")

            # Send ALL commands rapidly (VESCTool's secret sauce!)
            # HARDCODED values matching proof_of_concept.py exactly!
            # 1. FW_VERSION - keep-alive
            packet1 = self._pack_payload(bytes([0x00]))
            _LOGGER.warning(f"[BMS] Packet 1 (FW_VERSION 0x00): {packet1.hex(' ')}")
            self.writer.write(packet1)

            # 2. GET_CUSTOM_CONFIG - initialize device context for BMS
            packet2 = self._pack_payload(bytes([0x5d, 0x00]))
            _LOGGER.warning(f"[BMS] Packet 2 (GET_CUSTOM_CONFIG 0x5d): {packet2.hex(' ')}")
            self.writer.write(packet2)

            # 3. PING_CAN - wake/discover CAN devices
            packet3 = self._pack_payload(bytes([0x3e]))
            _LOGGER.warning(f"[BMS] Packet 3 (PING_CAN 0x3e): {packet3.hex(' ')}")
            self.writer.write(packet3)

            # 4. BMS_GET_VALUES - request BMS data
            packet4 = self._pack_payload(bytes([0x60]))
            _LOGGER.warning(f"[BMS] Packet 4 (BMS_GET_VALUES 0x60): {packet4.hex(' ')}")
            self.writer.write(packet4)

            # Flush all at once
            await self.writer.drain()
            _LOGGER.info("[BMS] All commands sent, collecting responses...")

            # Collect ALL responses (up to 5 seconds total)
            import time
            all_data = b''
            start_time = time.time()

            while time.time() - start_time < 3.0:
                try:
                    chunk = await asyncio.wait_for(
                        self.reader.read(1024),
                        timeout=0.5
                    )
                    if chunk:
                        all_data += chunk
                        _LOGGER.warning(f"[BMS] Received {len(chunk)} bytes (total: {len(all_data)})")
                    # DON'T break on empty chunk - keep reading!
                except asyncio.TimeoutError:
                    # Timeout is normal - keep reading until 3 seconds elapsed
                    if all_data:
                        continue  # Got some data, keep trying
                    else:
                        break  # No data at all, give up

            if not all_data:
                _LOGGER.warning("[BMS] No response data received")
                return None

            _LOGGER.info(f"[BMS] Total received: {len(all_data)} bytes, searching for BMS packet...")

            # DEBUG: Log raw data as hex
            hex_dump = all_data.hex(' ')
            _LOGGER.warning(f"[BMS] Raw response data ({len(all_data)} bytes):")
            # Log in chunks for readability
            for i in range(0, len(hex_dump), 150):
                _LOGGER.warning(f"  {hex_dump[i:i+150]}")

            # Find BMS packet in response stream (starts with 02 [len] 60...)
            bms_data = self._extract_bms_from_stream(all_data)

            if bms_data:
                _LOGGER.info("[BMS] Successfully extracted and parsed BMS data!")
                return bms_data
            else:
                _LOGGER.warning("[BMS] BMS packet not found in response stream")
                # DEBUG: Log packet start bytes to see what commands we're receiving
                packets_found = []
                idx = 0
                while idx < len(all_data) - 3:
                    if all_data[idx] == VESC_PACKET_START_BYTE:
                        len_byte = all_data[idx + 1]
                        if len_byte < 128:
                            cmd_offset = idx + 2
                        else:
                            cmd_offset = idx + 3
                        if cmd_offset < len(all_data):
                            packets_found.append(f"0x{all_data[cmd_offset]:02x}")
                    idx += 1
                _LOGGER.warning(f"[BMS] Command bytes found in response: {', '.join(packets_found)}")
                return None

        except Exception as e:
            _LOGGER.error(f"[BMS] Error in rapid-fire BMS retrieval: {e}", exc_info=True)
            return None

    def _extract_bms_from_stream(self, data: bytes) -> Optional[dict]:
        """Extract and parse BMS packet from response stream."""
        idx = 0

        while idx < len(data) - 10:
            if data[idx] == VESC_PACKET_START_BYTE:
                # Found potential packet start
                len_byte = data[idx + 1]

                # VESC packet length encoding:
                # For our BMS packets (< 256 bytes), length is always single byte
                # Just use the byte value as-is
                payload_len = len_byte
                payload_start = idx + 2

                # Check if this is BMS packet (command byte 0x60)
                if payload_start < len(data) and data[payload_start] == COMM_BMS_GET_VALUES:
                    _LOGGER.debug(f"[BMS] Found BMS packet at offset {idx}, payload length {payload_len}")

                    # Extract payload
                    if payload_start + payload_len <= len(data):
                        payload = data[payload_start:payload_start + payload_len]

                        # Parse BMS data
                        return self._parse_bms_payload(payload)

            idx += 1

        return None

    def _parse_bms_payload(self, payload: bytes) -> Optional[dict]:
        """Parse BMS payload data.

        Based on packet capture analysis (2026-01-02):
        - Byte 0: 0x60 (command ID, stripped from payload)
        - Bytes 0-23: Status/metadata (format TBD)
        - Byte 24: Cell count (0x14 = 20 decimal)
        - Bytes 25+: Cell voltages (uint16, big-endian, millivolts)
        - Bytes 65+: Balance flags (uint8 per cell)
        - Bytes 85+: Additional data (temperatures, etc.)
        """
        try:
            # Skip command byte (0x60)
            data = payload[1:]

            def read_uint16(offset):
                return struct.unpack('>H', data[offset:offset+2])[0]

            def read_uint8(offset):
                return data[offset]

            bms_data = {}

            # Cell count at offset 24 (verified via packet capture)
            if len(data) > 24:
                cell_num = read_uint8(24)
                bms_data["cell_num"] = cell_num

                _LOGGER.debug(f"[BMS] Detected {cell_num} cells")

                # Cell voltages start at offset 25
                cells = []
                for i in range(min(cell_num, 32)):  # Max 32 cells safety limit
                    offset = 25 + (i * 2)
                    if offset + 2 <= len(data):
                        cell_mv = read_uint16(offset)
                        cell_v = cell_mv / 1000.0  # Convert mV to V
                        cells.append(cell_v)
                    else:
                        _LOGGER.warning(f"[BMS] Not enough data for cell {i+1}")
                        break

                bms_data["cell_voltages"] = cells

                # Calculate cell statistics
                if cells:
                    bms_data["cell_min"] = min(cells)
                    bms_data["cell_max"] = max(cells)
                    bms_data["cell_avg"] = sum(cells) / len(cells)
                    bms_data["cell_delta"] = max(cells) - min(cells)

                    # Calculate total pack voltage from cells
                    bms_data["v_tot"] = sum(cells)

                    _LOGGER.debug(
                        f"[BMS] Cell stats: min={bms_data['cell_min']:.3f}V, "
                        f"max={bms_data['cell_max']:.3f}V, "
                        f"avg={bms_data['cell_avg']:.3f}V, "
                        f"delta={bms_data['cell_delta']*1000:.1f}mV"
                    )

                # Balance flags at offset 65 (after 20 cells × 2 bytes = 40 bytes)
                balance_offset = 25 + (cell_num * 2)
                if len(data) > balance_offset + cell_num:
                    balance_flags = []
                    for i in range(cell_num):
                        flag = read_uint8(balance_offset + i)
                        balance_flags.append(bool(flag))
                    bms_data["balance_flags"] = balance_flags

                # Temperatures - read count byte first, then temperature values
                temp_offset = balance_offset + cell_num
                _LOGGER.warning(f"[BMS] Temperature offset: {temp_offset}, data length: {len(data)}")
                if len(data) > temp_offset + 1:
                    # Read temperature count byte
                    temp_adc_num = read_uint8(temp_offset)
                    _LOGGER.warning(f"[BMS] Temperature count byte: {temp_adc_num}")

                    # Dump the temperature region for analysis
                    temp_region = data[temp_offset:min(temp_offset+20, len(data))]
                    _LOGGER.warning(f"[BMS] Temp region hex (first 20 bytes): {temp_region.hex(' ')}")

                    # Skip the count byte and read temperature values
                    temps = []
                    for i in range(min(temp_adc_num, 10)):  # Max 10 temp sensors
                        offset = temp_offset + 1 + (i * 2)  # +1 to skip count byte
                        if offset + 2 <= len(data):
                            temp_raw = read_uint16(offset)
                            _LOGGER.warning(f"[BMS] Temp {i}: offset={offset}, raw=0x{temp_raw:04x} ({temp_raw} dec), div100={temp_raw/100.0:.2f}")
                            if temp_raw > 0 and temp_raw < 10000:  # Sanity check: 0-100°C (raw: 0-10000)
                                temp = temp_raw / 100.0  # Convert centidegrees to °C (0.01°C resolution)
                                temps.append(temp)
                                _LOGGER.warning(f"[BMS] Temp {i} ACCEPTED: {temp:.2f}°C")

                    if temps:
                        bms_data["temperatures"] = temps
                        bms_data["temp_adc_num"] = temp_adc_num
                        _LOGGER.warning(f"[BMS] Found {len(temps)} valid temperatures: {temps}")
                    else:
                        _LOGGER.warning(f"[BMS] No valid temperatures found (count={temp_adc_num})")

            return bms_data if bms_data else None

        except Exception as e:
            _LOGGER.error(f"[BMS] Error parsing BMS payload: {e}", exc_info=True)
            _LOGGER.error(f"[BMS] Payload hex dump: {payload[:100].hex()}")
            return None
