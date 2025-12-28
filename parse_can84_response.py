#!/usr/bin/env python3
"""Parse the CAN ID 84 responses."""
import struct

# FW_VERSION response (35 bytes)
fw_response = bytes.fromhex("00 06 05 41 44 56 35 30 30 00 35 00 21 00 13 47 32 33 33 36 32 33 00 00 00 01 00 00 01 00 00 e0 8a cd 97")

print("="*60)
print("FW_VERSION Response from CAN ID 84")
print("="*60)
print(f"Raw: {fw_response.hex(' ')}")
print(f"\nCommand: 0x{fw_response[0]:02x} (COMM_FW_VERSION)")
print(f"FW Major: {fw_response[1]}")
print(f"FW Minor: {fw_response[2]}")

# Extract firmware name (null-terminated string)
fw_name_bytes = fw_response[3:]
fw_name = fw_name_bytes.decode('utf-8', errors='ignore').split('\x00')[0]
print(f"FW Name: {fw_name}")

print(f"\nFull firmware: v{fw_response[1]}.{fw_response[2]} - {fw_name}")

# GET_VALUES response (74 bytes)
print("\n" + "="*60)
print("GET_VALUES Response from CAN ID 84")
print("="*60)

values_response = bytes.fromhex("04 01 02 00 f9 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 03 43 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 03 00 00 00 05 00 00 00 07 00 09 c3 63 c0 54 00 00 00 00 00 00 ff ff ff ee ff ff ff e2 00")

print(f"Raw: {values_response.hex(' ')}")
print(f"\nCommand: 0x{values_response[0]:02x} (COMM_GET_VALUES)")
print(f"Length: {len(values_response)} bytes")

# Parse COMM_GET_VALUES structure
# Based on VESC protocol documentation
data = values_response[1:]  # Skip command byte

def read_float32(offset):
    return struct.unpack('>f', data[offset:offset+4])[0]

def read_uint16(offset):
    return struct.unpack('>H', data[offset:offset+2])[0]

def read_int32(offset):
    return struct.unpack('>i', data[offset:offset+4])[0]

try:
    print("\nParsed Values:")
    print(f"  Temperature FET: {read_float32(0):.2f}°C")
    print(f"  Temperature Motor: {read_float32(4):.2f}°C")
    print(f"  Current Motor: {read_float32(8):.2f}A")
    print(f"  Current In: {read_float32(12):.2f}A")
    print(f"  Current In Filter: {read_float32(16):.2f}A")
    print(f"  Duty Cycle: {read_float32(20):.4f}")
    print(f"  RPM: {read_float32(24):.0f}")
    print(f"  Input Voltage: {read_float32(28):.2f}V")
    print(f"  Amp Hours: {read_float32(32):.3f}Ah")
    print(f"  Amp Hours Charged: {read_float32(36):.3f}Ah")
    print(f"  Watt Hours: {read_float32(40):.3f}Wh")
    print(f"  Watt Hours Charged: {read_float32(44):.3f}Wh")
    print(f"  Tachometer: {read_int32(48)}")
    print(f"  Tachometer Abs: {read_int32(52)}")
    print(f"  Fault Code: {data[56] if len(data) > 56 else 0}")
except Exception as e:
    print(f"Error parsing: {e}")

print("\n" + "="*60)
print("CONCLUSION")
print("="*60)
print("✓ CAN ID 84 is a VESC motor controller (ADV500)")
print("✓ It responds to FW_VERSION and GET_VALUES")
print("✗ It does NOT respond to BMS_GET_VALUES (not a BMS)")
print("\nThe BMS might be on a different CAN ID!")
