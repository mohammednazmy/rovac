#!/usr/bin/env python3
"""Direct I2C control of the Sense HAT v2 LED matrix.

Bypasses the broken kernel rpisense_fb driver on Pi 5 / Bookworm,
where framebuffer writes (via mmap or write()) succeed at the kernel
level but never reach the ATTiny88 LED driver chip.

The chip itself responds correctly to I2C register reads/writes
(verified by writing pixel bytes and reading them back). The kernel
driver's framebuffer→I2C update path is what's broken — likely the
deferred-IO/dirty-page mechanism for fb dirty tracking on Pi 5.

Protocol (from the upstream rpi-sense kernel module + Pi-Sense-HAT-AVR
firmware):
    I2C address: 0x46 (ATTiny88)
    Register 0x00..0xBF (192 bytes): pixel data, RGB triples per pixel,
        row-major. Each byte is interpreted as a 5-bit (0..31) value
        for R/B and 6-bit (0..63) for G — but in practice the chip only
        looks at lower 5 bits for all channels so 0..31 works for all.
    Register 0xF0: WAI ('s' = 0x73, identifies the chip)
    Register 0xF2: joystick state (read-only, single byte)

Usage:
    led = SenseHatDirect()
    led.set_pixels([(255, 0, 0)] * 64)   # all bright red
    led.clear()
"""
from __future__ import annotations

from typing import List, Tuple

from smbus2 import SMBus, i2c_msg

RGB = Tuple[int, int, int]

I2C_BUS = 1
I2C_ADDR = 0x46
REG_DISPLAY = 0x00
REG_WAI = 0xF0
REG_JOYSTICK = 0xF2
WAI_VALUE = 0x73   # ASCII 's' — chip identifier


class SenseHatDirect:
    """Drives the Sense HAT LED matrix by writing the chip's LED
    data registers directly via I2C — sidestepping the broken kernel
    framebuffer path on Pi 5 / current Bookworm kernel."""

    def __init__(self, bus_num: int = I2C_BUS):
        self._bus = SMBus(bus_num)
        # Sanity check the chip is reachable.
        wai = self._read_reg(REG_WAI)
        if wai != WAI_VALUE:
            raise RuntimeError(
                f"Sense HAT chip not detected at I2C 0x{I2C_ADDR:02X}: "
                f"expected WAI 0x{WAI_VALUE:02X}, got 0x{wai:02X}")

    def set_pixels(self, pixels: List[RGB]) -> None:
        """Write all 64 pixels in one I2C transaction.

        Input: list of 64 (r, g, b) tuples, each channel 0..255.
        We map 0..255 → 0..31 (5-bit) since that's what the chip uses
        for all channels in practice.
        """
        if len(pixels) != 64:
            raise ValueError(f"need exactly 64 pixels, got {len(pixels)}")
        data: List[int] = []
        for r, g, b in pixels:
            data.append((r >> 3) & 0x1F)
            data.append((g >> 3) & 0x1F)
            data.append((b >> 3) & 0x1F)
        # Single 193-byte write: [register] + [192 bytes of pixel data].
        # Same transaction shape the kernel driver uses internally.
        msg = i2c_msg.write(I2C_ADDR, [REG_DISPLAY] + data)
        self._bus.i2c_rdwr(msg)

    def clear(self) -> None:
        self.set_pixels([(0, 0, 0)] * 64)

    def read_joystick_byte(self) -> int:
        """Read joystick state register. Bitfield (per AVR firmware):
            bit 0: down, 1: right, 2: up, 3: held, 4: left
        Not currently used by the panel (we use the kernel input device
        for joystick events), but exposed here for completeness."""
        return self._read_reg(REG_JOYSTICK)

    def close(self) -> None:
        try:
            self._bus.close()
        except Exception:
            pass

    # ── internal ─────────────────────────────────────────────────────

    def _read_reg(self, reg: int) -> int:
        """Read a single register via combined write-then-read."""
        read = i2c_msg.read(I2C_ADDR, 1)
        self._bus.i2c_rdwr(i2c_msg.write(I2C_ADDR, [reg]), read)
        return list(read)[0]
