#!/usr/bin/env python3
"""
ESP32 Rescue Tool
=================
Monitors the serial port, detects download mode, syncs with the
bootloader, reads chip info, and erases flash using the raw ESP32
ROM bootloader SLIP protocol (no esptool dependency for operations).

Usage:
    python3 tools/esp32_rescue.py [--port /dev/cu.usbserial-0001] [--erase]
"""

import argparse
import sys
import time
import struct

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Run: pip3 install pyserial")
    sys.exit(1)

# ESP32 ROM bootloader commands
CMD_FLASH_BEGIN = 0x02
CMD_FLASH_DATA = 0x03
CMD_FLASH_END = 0x04
CMD_SYNC = 0x08
CMD_WRITE_REG = 0x09
CMD_READ_REG = 0x0A
CMD_SPI_SET_PARAMS = 0x0B
CMD_SPI_ATTACH = 0x0D
CMD_CHANGE_BAUDRATE = 0x0F
CMD_FLASH_DEFL_BEGIN = 0x10
CMD_FLASH_MD5 = 0x13

# ESP32 registers
CHIP_DETECT_MAGIC_REG = 0x40001000
EFUSE_BASE = 0x3FF5A000
GPIO_STRAP_REG = 0x3FF44038
UART_CLKDIV_REG = 0x3FF40014
UART_DATE_REG = 0x3FF40078


def slip_encode(data: bytes) -> bytes:
    out = b'\xc0'
    for b in data:
        if b == 0xc0:
            out += b'\xdb\xdc'
        elif b == 0xdb:
            out += b'\xdb\xdd'
        else:
            out += bytes([b])
    out += b'\xc0'
    return out


def slip_read_packet(ser: serial.Serial, timeout: float = 3.0) -> bytes | None:
    """Read one complete SLIP frame."""
    deadline = time.time() + timeout
    in_frame = False
    buf = b''
    escaped = False

    while time.time() < deadline:
        raw = ser.read(1)
        if not raw:
            continue
        b = raw[0]

        if b == 0xc0:
            if in_frame and buf:
                return buf  # complete frame
            in_frame = True
            buf = b''
            escaped = False
            continue

        if not in_frame:
            continue

        if escaped:
            if b == 0xdc:
                buf += b'\xc0'
            elif b == 0xdd:
                buf += b'\xdb'
            else:
                buf += bytes([0xdb, b])
            escaped = False
        elif b == 0xdb:
            escaped = True
        else:
            buf += bytes([b])

    return None


def send_command(ser: serial.Serial, cmd: int, data: bytes = b'',
                 checksum: int = 0, timeout: float = 5.0) -> tuple[int, bytes] | None:
    """Send a bootloader command and read response."""
    header = struct.pack('<BBHI', 0x00, cmd, len(data), checksum)
    packet = slip_encode(header + data)
    ser.reset_input_buffer()
    ser.write(packet)

    deadline = time.time() + timeout
    while time.time() < deadline:
        frame = slip_read_packet(ser, timeout=deadline - time.time())
        if frame and len(frame) >= 8:
            direction, resp_cmd = frame[0], frame[1]
            if direction == 1 and resp_cmd == cmd:
                value = struct.unpack('<I', frame[4:8])[0]
                body = frame[8:]
                return value, body
    return None


def read_reg(ser: serial.Serial, addr: int) -> int | None:
    data = struct.pack('<I', addr)
    result = send_command(ser, CMD_READ_REG, data, timeout=3)
    if result:
        return result[0]
    return None


def write_reg(ser: serial.Serial, addr: int, value: int,
              mask: int = 0xFFFFFFFF, delay_us: int = 0) -> bool:
    data = struct.pack('<IIII', addr, value, mask, delay_us)
    result = send_command(ser, CMD_WRITE_REG, data, timeout=3)
    return result is not None


def do_sync(ser: serial.Serial) -> bool:
    """Sync with the bootloader."""
    sync_data = b'\x07\x07\x12\x20' + (b'\x55' * 32)
    header = struct.pack('<BBHI', 0x00, CMD_SYNC, len(sync_data), 0)
    packet = slip_encode(header + sync_data)

    for _ in range(15):
        ser.reset_input_buffer()
        ser.write(packet)
        time.sleep(0.05)
        response = ser.read(256)
        if response and b'\xc0' in response:
            # Drain remaining sync responses
            time.sleep(0.3)
            ser.read(4096)
            ser.reset_input_buffer()
            return True
    return False


def detect_state(ser: serial.Serial) -> str:
    ser.reset_input_buffer()
    time.sleep(0.1)
    data = ser.read(512)
    if not data:
        return "silent"
    if len(data) > 50:
        return "streaming"
    return "burst"


def read_chip_info(ser: serial.Serial) -> bool:
    print("-" * 60)
    print("  CHIP INFO")
    print("-" * 60)

    magic = read_reg(ser, CHIP_DETECT_MAGIC_REG)
    if magic is None:
        print("  ERROR: Cannot read chip — no response from bootloader")
        return False

    chip_names = {
        0x00F01D83: "ESP32",
        0x000007C6: "ESP32-S2",
        0x9: "ESP32-S3",
        0x6F51306F: "ESP32-C2",
        0x1B31506F: "ESP32-C3",
        0x2CE0806F: "ESP32-C6",
    }
    print(f"  Chip:        {chip_names.get(magic, 'Unknown')}")
    print(f"  Magic:       0x{magic:08X}")

    # MAC from EFUSE
    mac0 = read_reg(ser, EFUSE_BASE + 0x044)
    mac1 = read_reg(ser, EFUSE_BASE + 0x048)
    if mac0 is not None and mac1 is not None:
        mac_bytes = [
            (mac1 >> 8) & 0xFF, mac1 & 0xFF,
            (mac0 >> 24) & 0xFF, (mac0 >> 16) & 0xFF,
            (mac0 >> 8) & 0xFF, mac0 & 0xFF,
        ]
        mac_str = ":".join(f"{b:02x}" for b in mac_bytes)
        print(f"  MAC:         {mac_str}")

    # Package version
    efuse3 = read_reg(ser, EFUSE_BASE + 0x050)
    if efuse3 is not None:
        pkg = (efuse3 >> 9) & 0x07
        pkg_names = {0: "ESP32D0WDQ6", 1: "ESP32D0WDQ5", 2: "ESP32D2WDQ5",
                     3: "ESP32-PICO-V3", 5: "ESP32-PICO-V3-02"}
        print(f"  Package:     {pkg_names.get(pkg, f'Type {pkg}')}")

    # Crystal frequency
    uart_div = read_reg(ser, UART_CLKDIV_REG)
    if uart_div is not None:
        clkdiv = uart_div & 0xFFFFF
        if clkdiv > 0:
            xtal = round((115200 * clkdiv) / 1e6)
            print(f"  Crystal:     {xtal} MHz")

    # Boot strapping
    strap = read_reg(ser, GPIO_STRAP_REG)
    if strap is not None:
        mode = "DOWNLOAD" if (strap & 1) == 0 else "NORMAL"
        print(f"  Boot mode:   {mode} (strap=0x{strap:04X})")

    return True


def erase_flash(ser: serial.Serial) -> bool:
    """Erase entire flash using ROM bootloader FLASH_BEGIN."""
    print()
    print("-" * 60)
    print("  ERASING FLASH")
    print("-" * 60)

    # Step 1: SPI attach
    print("  Attaching SPI flash...")
    spi_data = struct.pack('<I', 0)
    result = send_command(ser, CMD_SPI_ATTACH, spi_data, timeout=10)
    if result is None:
        print("  WARNING: SPI attach no response (continuing anyway)")

    # Step 2: Set flash parameters
    print("  Setting flash parameters...")
    params = struct.pack('<IIIIII',
                         0,                 # fl_id
                         4 * 1024 * 1024,   # 4MB total
                         64 * 1024,          # block size
                         4 * 1024,           # sector size
                         256,                # page size
                         0xFFFF)             # status mask
    result = send_command(ser, CMD_SPI_SET_PARAMS, params, timeout=5)
    if result is None:
        print("  WARNING: SPI params no response (continuing anyway)")

    # Step 3: FLASH_BEGIN — triggers erase of specified region
    # The ROM bootloader erases sectors before allowing writes.
    # By requesting to write to 4MB starting at offset 0, it erases everything.
    erase_size = 4 * 1024 * 1024
    block_size = 64 * 1024  # 64KB blocks
    num_blocks = erase_size // block_size

    flash_begin = struct.pack('<IIII', erase_size, num_blocks, block_size, 0)

    print(f"  Erasing {erase_size // (1024*1024)}MB flash (this takes 30-90 seconds)...")
    sys.stdout.flush()

    result = send_command(ser, CMD_FLASH_BEGIN, flash_begin, timeout=120)
    if result is None:
        print("  ERROR: Flash erase timed out or failed")
        return False

    value, body = result
    # Check status
    if body and len(body) >= 4:
        status = struct.unpack('<I', body[:4])[0]
        if status != 0:
            print(f"  ERROR: Flash erase error status: {status}")
            return False

    # Step 4: End flash operation (don't reboot)
    end_data = struct.pack('<I', 1)  # 1 = stay in bootloader
    send_command(ser, CMD_FLASH_END, end_data, timeout=5)

    print()
    print("  *** FLASH ERASED SUCCESSFULLY! ***")
    print("  The ESP32 is now clean — ready for new firmware.")
    return True


def main():
    parser = argparse.ArgumentParser(description="ESP32 Rescue Tool")
    parser.add_argument("--port", default="/dev/cu.usbserial-0001",
                        help="Serial port (default: /dev/cu.usbserial-0001)")
    parser.add_argument("--erase", action="store_true",
                        help="Erase flash after reading chip info")
    args = parser.parse_args()

    print("=" * 60)
    print("  ESP32 RESCUE TOOL")
    print("=" * 60)
    print()
    print(f"  Port: {args.port}")
    print(f"  Mode: {'ERASE + CHIP INFO' if args.erase else 'CHIP INFO ONLY'}")
    print()
    print("  Keep trying the boot mode sequence until I detect it:")
    print("    1. Hold BOOT")
    print("    2. Tap EN (while holding BOOT)")
    print("    3. Keep holding BOOT for 2-3 sec, then release")
    print()
    print("  Or try power-on boot mode:")
    print("    1. Unplug USB")
    print("    2. Hold BOOT")
    print("    3. Plug USB back in")
    print("    4. Release BOOT after 2 seconds")
    print()
    print("  Press Ctrl+C to quit.")
    print("=" * 60)
    print()

    silence_count = 0
    streaming_notified = False
    cycle = 0

    while True:
        try:
            ser = serial.Serial(
                args.port, 115200, timeout=0.4,
                dsrdtr=False, rtscts=False
            )
            ser.dtr = False
            ser.rts = False
        except serial.SerialException:
            print(f"\r  Waiting for {args.port}...", end="", flush=True)
            time.sleep(1)
            continue

        try:
            while True:
                cycle += 1
                state = detect_state(ser)

                if state == "streaming":
                    silence_count = 0
                    if not streaming_notified:
                        print("  [FIRMWARE] Chip is running — waiting for boot mode...")
                        streaming_notified = True
                    elif cycle % 25 == 0:
                        print("  [FIRMWARE] Still running... try the button sequence")

                elif state == "burst":
                    silence_count += 1
                    if silence_count == 1:
                        print("  [BURST]    Data burst — possible boot message")

                elif state == "silent":
                    silence_count += 1
                    if silence_count == 1:
                        print("  [SILENT]   Silence detected...")
                    if silence_count >= 2:
                        # Drain residual, then sync
                        ser.reset_input_buffer()
                        time.sleep(0.3)
                        residual = ser.read(4096)
                        if residual:
                            print(f"             Drained {len(residual)} residual bytes")
                        ser.reset_input_buffer()

                        print("  [SYNC]     Attempting bootloader sync...")
                        if do_sync(ser):
                            print()
                            print("  *** SYNC SUCCESS — BOOTLOADER CONNECTED! ***")
                            print()

                            ok = read_chip_info(ser)

                            if ok and args.erase:
                                erase_flash(ser)

                            print()
                            print("-" * 60)
                            print("  Press EN/RST button to reboot the chip.")
                            print("-" * 60)
                            print()
                            print("=" * 60)
                            print("  RESCUE COMPLETE" if ok else
                                  "  RESCUE INCOMPLETE — see errors above")
                            print("=" * 60)

                            ser.close()
                            return 0 if ok else 1

                        else:
                            print("  [SYNC]     No response — false alarm")
                            silence_count = 0
                            streaming_notified = False

        except serial.SerialException:
            print("  [PORT]     Port disconnected — waiting for reconnect...")
            streaming_notified = False
            silence_count = 0
            time.sleep(1)
            continue
        except KeyboardInterrupt:
            print()
            print("  Interrupted by user. Goodbye!")
            return 1
        finally:
            try:
                ser.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
