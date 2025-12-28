#!/usr/bin/env python3
"""Stream BMS data like VESCTool does.

This script mimics VESCTool's "Stream BMS realtime data" button:
- Polls COMM_BMS_GET_VALUES at 10 Hz (every 100ms)
- Continuously displays received BMS data
- Uses timeout mechanism to prevent request spam
"""
import asyncio
import logging
import struct
import time
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)

VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03
COMM_BMS_GET_VALUES = 96  # 0x60 - from VESC Tool datatypes.h

# BMS polling configuration (from VESCTool)
BMS_POLL_RATE_HZ = 10  # 10 Hz default
BMS_POLL_INTERVAL = 1.0 / BMS_POLL_RATE_HZ  # 100ms


class BMSStreamer:
    def __init__(self, host: str, port: int, vesc_id: str, password: str):
        self.host = host
        self.port = port
        self.vesc_id = vesc_id
        self.password = password
        self.reader = None
        self.writer = None
        self.running = False
        self.bms_data_count = 0
        self.last_bms_data = None

    async def connect(self):
        """Connect to VESCHub."""
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        auth_string = f"VESCTOOL:{self.vesc_id}:{self.password}\n"
        self.writer.write(auth_string.encode('utf-8'))
        await self.writer.drain()
        await asyncio.sleep(1.0)
        _LOGGER.info("✓ Connected to VESCHub")

    async def disconnect(self):
        """Disconnect from VESCHub."""
        self.running = False
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()

    @staticmethod
    def _calculate_crc16(data: bytes) -> int:
        """Calculate CRC16 for VESC protocol."""
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
        """Pack payload with VESC framing."""
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

    async def _send_bms_request(self):
        """Send COMM_BMS_GET_VALUES request (mimics VESCTool's bmsGetValues())."""
        try:
            payload = bytes([COMM_BMS_GET_VALUES])
            packet = self._pack_payload(payload)
            self.writer.write(packet)
            await self.writer.drain()
            return True
        except Exception as e:
            _LOGGER.error(f"Error sending BMS request: {e}")
            return False

    async def _read_packet(self, timeout: float = 0.5) -> bytes:
        """Read VESC packet with timeout."""
        try:
            # Wait for start byte
            while True:
                byte = await asyncio.wait_for(
                    self.reader.readexactly(1),
                    timeout=timeout
                )
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
                return None

            if calculated_crc != received_crc:
                return None

            return payload

        except asyncio.TimeoutError:
            return None
        except Exception as e:
            _LOGGER.error(f"Error reading packet: {e}")
            return None

    def _parse_bms_data(self, data: bytes) -> dict:
        """Parse BMS_GET_VALUES response."""
        if data[0] != COMM_BMS_GET_VALUES:
            return None

        payload = data[1:]
        idx = 0

        def read_float32(offset):
            return struct.unpack('>f', payload[offset:offset+4])[0]

        def read_uint16(offset):
            return struct.unpack('>H', payload[offset:offset+2])[0]

        def read_uint8(offset):
            return payload[offset]

        try:
            bms_data = {
                'v_tot': read_float32(0),
                'v_charge': read_float32(4),
                'i_in': read_float32(8),
                'i_in_ic': read_float32(12),
                'ah_cnt': read_float32(16),
                'wh_cnt': read_float32(20),
            }

            idx = 24

            # Cell voltages
            if len(payload) > idx:
                cell_num = read_uint8(idx)
                idx += 1
                cells = []

                for i in range(min(cell_num, 32)):
                    if len(payload) >= idx + 2:
                        cell_v = read_uint16(idx) / 1000.0
                        cells.append(cell_v)
                        idx += 2

                bms_data['cell_num'] = cell_num
                bms_data['cells'] = cells

            # Balance state
            if len(payload) > idx + 4:
                bms_data['bal_state'] = struct.unpack('>I', payload[idx:idx+4])[0]
                idx += 4

            # Temperatures
            if len(payload) > idx:
                temp_num = read_uint8(idx)
                idx += 1
                temps = []

                for i in range(min(temp_num, 10)):
                    if len(payload) >= idx + 2:
                        temp = read_uint16(idx) / 10.0
                        temps.append(temp)
                        idx += 2

                bms_data['temp_num'] = temp_num
                bms_data['temps'] = temps

            # SOC/SOH/Capacity
            if len(payload) >= idx + 4:
                bms_data['soc'] = read_float32(idx)
                idx += 4

            if len(payload) >= idx + 4:
                bms_data['soh'] = read_float32(idx)
                idx += 4

            if len(payload) >= idx + 4:
                bms_data['capacity_ah'] = read_float32(idx)

            return bms_data

        except Exception as e:
            _LOGGER.error(f"Error parsing BMS data: {e}")
            return None

    def _display_bms_data(self, bms_data: dict):
        """Display BMS data in a readable format."""
        print("\n" + "="*60)
        print(f"📊 BMS Data Update #{self.bms_data_count}")
        print("="*60)

        print(f"\n⚡ Battery Status:")
        print(f"  Total Voltage:   {bms_data.get('v_tot', 0):.2f} V")
        print(f"  Charge Voltage:  {bms_data.get('v_charge', 0):.2f} V")
        print(f"  Current In:      {bms_data.get('i_in', 0):.3f} A")
        print(f"  Current IC:      {bms_data.get('i_in_ic', 0):.3f} A")
        print(f"  State of Charge: {bms_data.get('soc', 0):.1f} %")
        print(f"  State of Health: {bms_data.get('soh', 0):.1f} %")
        print(f"  Capacity:        {bms_data.get('capacity_ah', 0):.2f} Ah")

        print(f"\n📈 Counters:")
        print(f"  Amp Hours:       {bms_data.get('ah_cnt', 0):.3f} Ah")
        print(f"  Watt Hours:      {bms_data.get('wh_cnt', 0):.3f} Wh")

        if 'cells' in bms_data and bms_data['cells']:
            print(f"\n🔋 Cell Voltages ({bms_data.get('cell_num', 0)} cells):")
            cells = bms_data['cells']
            for i, cell_v in enumerate(cells):
                print(f"  Cell {i+1:2d}: {cell_v:.3f} V")

            # Calculate statistics
            if cells:
                avg_v = sum(cells) / len(cells)
                min_v = min(cells)
                max_v = max(cells)
                delta_v = max_v - min_v
                print(f"\n  Average: {avg_v:.3f} V")
                print(f"  Min:     {min_v:.3f} V")
                print(f"  Max:     {max_v:.3f} V")
                print(f"  Delta:   {delta_v*1000:.1f} mV")

        if 'temps' in bms_data and bms_data['temps']:
            print(f"\n🌡️  Temperatures ({bms_data.get('temp_num', 0)} sensors):")
            for i, temp in enumerate(bms_data['temps']):
                print(f"  Sensor {i+1}: {temp:.1f} °C")

        if 'bal_state' in bms_data:
            print(f"\n⚖️  Balance State: 0x{bms_data['bal_state']:08x}")

    async def polling_task(self):
        """Background task that polls for BMS data at regular intervals."""
        _LOGGER.info(f"Starting BMS polling at {BMS_POLL_RATE_HZ} Hz")

        while self.running:
            # Send BMS request
            if await self._send_bms_request():
                # Try to read response (with short timeout)
                response = await self._read_packet(timeout=BMS_POLL_INTERVAL * 0.8)

                if response and response[0] == COMM_BMS_GET_VALUES:
                    self.bms_data_count += 1
                    bms_data = self._parse_bms_data(response)

                    if bms_data:
                        self.last_bms_data = bms_data
                        self._display_bms_data(bms_data)

            # Wait for next poll interval
            await asyncio.sleep(BMS_POLL_INTERVAL)

    async def receive_task(self):
        """Background task that continuously reads incoming packets."""
        while self.running:
            try:
                response = await self._read_packet(timeout=1.0)

                if response and response[0] == COMM_BMS_GET_VALUES:
                    self.bms_data_count += 1
                    bms_data = self._parse_bms_data(response)

                    if bms_data:
                        self.last_bms_data = bms_data
                        self._display_bms_data(bms_data)

            except Exception as e:
                if self.running:
                    _LOGGER.error(f"Error in receive task: {e}")

    async def stream(self, duration: float = 60.0):
        """Stream BMS data for specified duration."""
        self.running = True

        print("\n" + "="*60)
        print("🔄 BMS Data Streaming Active")
        print("="*60)
        print(f"Polling Rate: {BMS_POLL_RATE_HZ} Hz ({BMS_POLL_INTERVAL*1000:.0f}ms)")
        print(f"Duration: {duration}s")
        print(f"Command: COMM_BMS_GET_VALUES (0x{COMM_BMS_GET_VALUES:02x})")
        print("\nPress Ctrl+C to stop...")

        try:
            # Run polling task
            await asyncio.wait_for(
                self.polling_task(),
                timeout=duration
            )

        except asyncio.TimeoutError:
            print(f"\n⏱️  Streaming duration completed ({duration}s)")

        except KeyboardInterrupt:
            print("\n\n🛑 Stopped by user")

        finally:
            self.running = False
            print("\n" + "="*60)
            print(f"📊 Summary: Received {self.bms_data_count} BMS data packets")
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
    print("BMS Data Streaming (VESCTool Mode)")
    print("="*60)
    print(f"Mimicking VESCTool's 'Stream BMS realtime data' button")
    print(f"VESC ID: {vesc_id}\n")

    streamer = BMSStreamer("veschub.vedder.se", 65101, vesc_id, password)

    try:
        await streamer.connect()

        # Stream for 60 seconds (or until Ctrl+C)
        await streamer.stream(duration=60.0)

    finally:
        await streamer.disconnect()
        print("\n✓ Disconnected")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nExiting...")
