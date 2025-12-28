#!/usr/bin/env python3
"""Analyze the packet capture to find the secret."""

# Key packets from capture
packets = {
    4: "56455343544f4f4c3a726b2d616476323a747261696c73666f72627265616b666173740a",  # Auth
    6: "020100000003",  # Request
    10: "02025d0078e303",  # ??? Command before BMS
    11: "02013ed79d03",  # ??? Another command
    25: "0201606ca603",  # BMS request
    27: "02a66004fe4a300501bd00000000000002366800000000000000001410561058105a10601060105e105e105d105e105c105c105e105c105e105e105c105e105b105e105e0101010101010101010101010101010101010101180af00a9e0a8c26ac00000000000000000000000000000000000000000000000000000000000000000000000000000000115000000000000000000000ff0000000000000000000000000000000000002eb903",  # BMS response!
}

print("="*70)
print("PACKET CAPTURE ANALYSIS")
print("="*70)

# Frame 4: Authentication
print("\n📍 Frame 4: Authentication")
auth_hex = packets[4]
auth_str = bytes.fromhex(auth_hex).decode('utf-8')
print(f"  Hex: {auth_hex}")
print(f"  Text: {auth_str.strip()}")
print(f"  ✓ Standard VESCTOOL auth")

# Frame 6: FW_VERSION
print("\n📍 Frame 6: First Command")
pkt = bytes.fromhex(packets[6])
print(f"  Hex: {packets[6]}")
print(f"  Structure: [{pkt[0]:02x}][{pkt[1]:02x}][{pkt[2]:02x}][crc][{pkt[-1]:02x}]")
print(f"  Command: 0x{pkt[2]:02x} = COMM_FW_VERSION")
print(f"  ✓ Normal FW query")

# Frame 10: MYSTERY COMMAND 1
print("\n📍 Frame 10: ⭐ MYSTERY COMMAND BEFORE BMS ⭐")
pkt = bytes.fromhex(packets[10])
print(f"  Hex: {packets[10]}")
print(f"  Structure: [{pkt[0]:02x}][{pkt[1]:02x}][{pkt[2]:02x} {pkt[3]:02x}][crc][{pkt[-1]:02x}]")
print(f"  Command: 0x{pkt[2]:02x}")
print(f"  Data: 0x{pkt[3]:02x}")
print(f"  → Command 0x5d with data 0x00")

# Frame 11: MYSTERY COMMAND 2
print("\n📍 Frame 11: ⭐ MYSTERY COMMAND 2 ⭐")
pkt = bytes.fromhex(packets[11])
print(f"  Hex: {packets[11]}")
print(f"  Structure: [{pkt[0]:02x}][{pkt[1]:02x}][{pkt[2]:02x}][crc][{pkt[-1]:02x}]")
print(f"  Command: 0x{pkt[2]:02x}")
print(f"  → Command 0x3e")

# Frame 25: BMS REQUEST
print("\n📍 Frame 25: BMS Request")
pkt = bytes.fromhex(packets[25])
print(f"  Hex: {packets[25]}")
print(f"  Structure: [{pkt[0]:02x}][{pkt[1]:02x}][{pkt[2]:02x}][crc][{pkt[-1]:02x}]")
print(f"  Command: 0x{pkt[2]:02x} = COMM_BMS_GET_VALUES")
print(f"  ✓ Same as what we send!")

# Frame 27: BMS RESPONSE
print("\n📍 Frame 27: ✓✓✓ BMS RESPONSE! ✓✓✓")
pkt = bytes.fromhex(packets[27])
print(f"  Length: {len(pkt)} bytes")
print(f"  Structure: [{pkt[0]:02x}][{pkt[1]:02x}][{pkt[2]:02x}][...data...]")
print(f"  Response cmd: 0x{pkt[2]:02x} = COMM_BMS_GET_VALUES")
print(f"  Payload: {len(pkt) - 5} bytes of BMS data")

print("\n" + "="*70)
print("CRITICAL DISCOVERY")
print("="*70)
print("""
VESCTool sends these commands IN ORDER:

1. COMM_FW_VERSION (0x00) ← We do this
2. ⭐ Command 0x5d with data 0x00 ← WE DON'T DO THIS!
3. ⭐ Command 0x3e ← WE DON'T DO THIS!
4. COMM_BMS_GET_VALUES (0x60) ← We do this
5. Gets BMS response ← We don't get this

Commands 0x5d and 0x3e are sent BEFORE BMS request.
These might be "enable BMS" or "select device" commands!

Let me look up what these commands are...
""")

# Command lookup
print("\n📚 Command Lookup:")
print("  0x5d = 93 decimal")
print("  0x3e = 62 decimal")
print("")
print("From VESC protocol, checking common commands...")
print("  COMM_GET_MCCONF = 0x0e (14)")
print("  COMM_GET_APPCONF = 0x15 (21)")
print("  COMM_GET_VALUES_SETUP = 0x24 (36)")
print("  COMM_GET_VALUES_SELECTIVE = 0x23 (35)")
print("  COMM_DETECT_MOTOR_PARAM = 0x2f (47)")
print("  COMM_BMS_GET_VALUES = 0x60 (96)")
print("")
print("  ❓ 0x5d (93) = Unknown command!")
print("  ❓ 0x3e (62) = COMM_GET_DECODED_BALANCE or similar?")
print("")
print("NEXT STEP: Try sending these commands before BMS request!")

