#!/usr/bin/env python3
"""Stream BMS data from LOCAL VESCHub (192.168.1.195:65102)."""
import asyncio
import logging
import struct
import sys
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)

VESC_PACKET_START_BYTE = 0x02
VESC_PACKET_STOP_BYTE = 0x03
COMM_BMS_GET_VALUES = 96  # 0x60

# LOCAL VESCHub (from your screenshot!)
DEFAULT_HOST = "192.168.1.195"
DEFAULT_PORT = 65102

BMS_POLL_RATE_HZ = 10
BMS_POLL_INTERVAL = 1.0 / BMS_POLL_RATE_HZ


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

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        auth_string = f"VESCTOOL:{self.vesc_id}:{self.password}\n"
        self.writer.write(auth_string.encode('utf-8'))
        await self.writer.drain()
        await asyncio.sleep(1.0)
        _LOGGER.info(f"✓ Connected to LOCAL VESCHub at {self.host}:{self.port}")

    async def disconnect(self):
        self.running = False
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
            packet = bytes([VESC_PACKET_START_BYTE,
                          (len(payload) >> 8) & 0xFF,
                          len(payload) & 0xFF])
        packet += payload
        crc = self._calculate_crc16(payload)
        packet += struct.pack('>H', crc)
        packet += bytes([VESC_PACKET_STOP_BYTE])
        return packet

    async def _send_bms_request(self):
        try:
            payload = bytes([COMM_BMS_GET_VALUES])
            packet = self._pack_payload(payload)
            self.writer.write(packet)
            await self.writer.drain()
            return True
        except Exception as e:
            _LOGGER.error(f"Error sending: {e}")
            return False

    async def _read_packet(self, timeout: float = 0.5) -> bytes:
        try:
            while True:
                byte = await asyncio.wait_for(
                    self.reader.readexactly(1),
                    timeout=timeout
                )
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

        except asyncio.TimeoutError:
            return None
        except Exception as e:
            return None

    def _parse_bms_data(self, data: bytes) -> dict:
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

            if len(payload) > idx + 4:
                bms_data['bal_state'] = struct.unpack('>I', payload[idx:idx+4])[0]
                idx += 4

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
            _LOGGER.error(f"Parse error: {e}")
            return None

    def _display_bms_data(self, bms_data: dict):
        print(f"\n{'='*60}")
        print(f"🔋 BMS Data #{self.bms_data_count} - {datetime.now().strftime('%H:%M:%S')}")
        print('='*60)

        print(f"\n⚡ Battery:")
        print(f"  Total Voltage:   {bms_data.get('v_tot', 0):6.2f} V")
        print(f"  Charge Voltage:  {bms_data.get('v_charge', 0):6.2f} V")
        print(f"  Current In:      {bms_data.get('i_in', 0):6.3f} A")
        print(f"  Current IC:      {bms_data.get('i_in_ic', 0):6.3f} A")

        soc = bms_data.get('soc', 0)
        soh = bms_data.get('soh', 0)
        print(f"  State of Charge: {soc:6.1f} %")
        print(f"  State of Health: {soh:6.1f} %")
        print(f"  Capacity:        {bms_data.get('capacity_ah', 0):6.2f} Ah")

        print(f"\n📈 Counters:")
        print(f"  Amp Hours:       {bms_data.get('ah_cnt', 0):6.3f} Ah")
        print(f"  Watt Hours:      {bms_data.get('wh_cnt', 0):6.3f} Wh")

        if 'cells' in bms_data and bms_data['cells']:
            cells = bms_data['cells']
            print(f"\n🔋 Cells ({len(cells)}):")

            # Print in rows of 5
            for i in range(0, len(cells), 5):
                row = cells[i:i+5]
                cell_strs = [f"C{i+j+1:2d}:{v:.3f}V" for j, v in enumerate(row)]
                print(f"  {' '.join(cell_strs)}")

            avg_v = sum(cells) / len(cells)
            min_v = min(cells)
            max_v = max(cells)
            delta_v = max_v - min_v

            print(f"\n  Stats: Avg={avg_v:.3f}V Min={min_v:.3f}V Max={max_v:.3f}V Delta={delta_v*1000:.1f}mV")

        if 'temps' in bms_data and bms_data['temps']:
            print(f"\n🌡️  Temps: {', '.join([f'{t:.1f}°C' for t in bms_data['temps']])}")

    async def polling_task(self):
        _LOGGER.info(f"Polling BMS at {BMS_POLL_RATE_HZ} Hz...")

        while self.running:
            if await self._send_bms_request():
                response = await self._read_packet(timeout=BMS_POLL_INTERVAL * 0.8)

                if response and response[0] == COMM_BMS_GET_VALUES:
                    self.bms_data_count += 1
                    bms_data = self._parse_bms_data(response)
                    if bms_data:
                        self._display_bms_data(bms_data)

            await asyncio.sleep(BMS_POLL_INTERVAL)

    async def stream(self, duration: float = 60.0):
        self.running = True

        print(f"\n{'='*60}")
        print(f"🔄 BMS Streaming: {self.host}:{self.port}")
        print('='*60)
        print(f"Poll Rate: {BMS_POLL_RATE_HZ} Hz")
        print(f"Duration: {duration}s (Ctrl+C to stop)")

        try:
            await asyncio.wait_for(self.polling_task(), timeout=duration)
        except asyncio.TimeoutError:
            print(f"\n⏱️  {duration}s completed")
        except KeyboardInterrupt:
            print("\n🛑 Stopped")
        finally:
            self.running = False
            print(f"\n📊 Total: {self.bms_data_count} BMS packets received")


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

    # Allow host/port override
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT

    print("="*60)
    print("BMS Data Streaming - LOCAL VESCHub")
    print("="*60)
    print(f"Host: {host}:{port}")
    print(f"VESC ID: {vesc_id}\n")

    streamer = BMSStreamer(host, port, vesc_id, password)

    try:
        await streamer.connect()
        await streamer.stream(duration=30.0)
    finally:
        await streamer.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n")
