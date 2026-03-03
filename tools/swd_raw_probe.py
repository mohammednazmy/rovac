#!/usr/bin/env python3
"""
Raw SWD bit-bang probe — bypasses OpenOCD entirely.
Manually bit-bangs the SWD protocol via Pi 5 GPIO to read the STM32 DPIDR.

Usage: sudo python3 tools/swd_raw_probe.py
"""

import gpiod
import sys

CHIP = "/dev/gpiochip4"


class SWDBitBang:
    def __init__(self, swdio_pin, swclk_pin):
        self.swdio_pin = swdio_pin
        self.swclk_pin = swclk_pin
        self.out_req = self._make_output([swdio_pin, swclk_pin])
        self.in_req = None
        self.swdio_is_output = True

    def _make_output(self, pins):
        return gpiod.request_lines(
            CHIP, consumer="swd",
            config={p: gpiod.LineSettings(
                direction=gpiod.line.Direction.OUTPUT,
                output_value=gpiod.line.Value.INACTIVE,
            ) for p in pins},
        )

    def _make_input(self, pin):
        return gpiod.request_lines(
            CHIP, consumer="swd_in",
            config={pin: gpiod.LineSettings(
                direction=gpiod.line.Direction.INPUT,
                bias=gpiod.line.Bias.PULL_UP,
            )},
        )

    def close(self):
        if self.out_req:
            self.out_req.release()
            self.out_req = None
        if self.in_req:
            self.in_req.release()
            self.in_req = None

    def _swdio_out(self, val):
        if not self.swdio_is_output:
            if self.in_req:
                self.in_req.release()
                self.in_req = None
            if self.out_req:
                self.out_req.release()
                self.out_req = None
            self.out_req = self._make_output([self.swdio_pin, self.swclk_pin])
            self.swdio_is_output = True
        v = gpiod.line.Value.ACTIVE if val else gpiod.line.Value.INACTIVE
        self.out_req.set_value(self.swdio_pin, v)

    def _swdio_read(self):
        if self.swdio_is_output:
            self.out_req.release()
            self.out_req = self._make_output([self.swclk_pin])
            self.in_req = self._make_input(self.swdio_pin)
            self.swdio_is_output = False
        return 1 if self.in_req.get_value(self.swdio_pin) == gpiod.line.Value.ACTIVE else 0

    def _clk(self):
        self.out_req.set_value(self.swclk_pin, gpiod.line.Value.ACTIVE)
        self.out_req.set_value(self.swclk_pin, gpiod.line.Value.INACTIVE)

    def write_bits(self, data, nbits):
        for i in range(nbits):
            self._swdio_out((data >> i) & 1)
            self._clk()

    def read_bits(self, nbits):
        val = 0
        for i in range(nbits):
            val |= (self._swdio_read() << i)
            self._clk()
        return val

    def line_reset(self):
        self._swdio_out(1)
        for _ in range(56):
            self._clk()

    def jtag_to_swd(self):
        self.write_bits(0xE79E, 16)

    def idle(self, n=8):
        self._swdio_out(0)
        for _ in range(n):
            self._clk()

    def read_dpidr(self):
        """Read DPIDR: request=0xA5, turnaround, ACK(3), DATA(32), PARITY(1)."""
        self.write_bits(0xA5, 8)
        # Turnaround
        self._swdio_read()
        self._clk()
        # ACK
        ack = self.read_bits(3)
        if ack == 0x01:
            data = self.read_bits(32)
            parity = self.read_bits(1)
            self._swdio_out(0)
            self._clk()
            return ack, data, parity
        self._swdio_out(0)
        self._clk()
        return ack, None, None


def try_probe(swdio, swclk):
    """Try SWD probe with given pin assignment. Returns (success, ack, data)."""
    print(f"  SWDIO=GPIO{swdio}  SWCLK=GPIO{swclk}")
    swd = SWDBitBang(swdio, swclk)
    try:
        swd.line_reset()
        swd.jtag_to_swd()
        swd.line_reset()
        swd.idle(8)
        ack, data, parity = swd.read_dpidr()
        return ack, data, parity
    finally:
        swd.close()


def main():
    print("=" * 60)
    print("  SWD RAW BIT-BANG PROBE")
    print("=" * 60)
    print()

    ack_names = {0x01: "OK", 0x02: "WAIT", 0x04: "FAULT", 0x07: "NO RESPONSE"}

    for attempt, (dio, clk) in enumerate([(24, 25), (25, 24)], 1):
        print(f"  --- Attempt {attempt} ---")
        ack, data, parity = try_probe(dio, clk)
        ack_name = ack_names.get(ack, f"UNKNOWN(0x{ack:02X})")
        print(f"  ACK: {ack_name} (0b{ack:03b})")

        if data is not None:
            print(f"  DPIDR: 0x{data:08X}")
            print(f"  Parity: {parity}")
            designer = (data >> 1) & 0x7FF
            version = (data >> 28) & 0xF
            partno = (data >> 12) & 0xFF
            print(f"  Designer: 0x{designer:03X}  Part: 0x{partno:02X}  Ver: {version}")
            print()
            print("  *** STM32 SWD IS ALIVE! ***")
            return 0

        if ack == 0x02:
            print("  Target says WAIT — chip is alive but busy!")
        elif ack == 0x04:
            print("  Target says FAULT — chip is alive but protected!")
        else:
            print("  No valid response.")
        print()

    print("  Both pin assignments failed.")
    print()
    print("  Possible causes:")
    print("    1. Wiring: double-check GND is connected")
    print("    2. STM32 SWD permanently disabled (RDP Level 2)")
    print("    3. SWD pins physically damaged from overvoltage")
    print("    4. Board not powered (check LEDs)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
