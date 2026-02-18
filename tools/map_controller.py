#!/usr/bin/env python3
"""Quick controller mapping tool. Press each input one at a time.

Reads raw joystick events from /dev/input/js0 and prints what fired.
Run on the Pi: python3 tools/map_controller.py
Press Ctrl+C to stop.
"""
import struct
import time
import sys

AXIS_NAMES = {
    0: "X (LStick X)",
    1: "Y (LStick Y)",
    2: "Z (RStick X)",
    3: "Rz (RStick Y)",
    4: "Hat0X (DPad X)",
    5: "Hat0Y (DPad Y)",
}

BTN_NAMES = {
    0: "BtnA/South",
    1: "BtnB/East",
    2: "BtnC",
    3: "BtnX/North",
    4: "BtnY/West",
    5: "BtnZ",
    6: "BtnTL (L1)",
    7: "BtnTR (R1)",
    8: "BtnTL2 (L2)",
    9: "BtnTR2 (R2)",
    10: "BtnSelect",
    11: "BtnStart",
    12: "BtnMode",
}

dev = "/dev/input/js0"


def main():
    print("=" * 60)
    print(f"Controller Mapping Tool — reading {dev}")
    print("Press each button/stick ONE AT A TIME")
    print("Press Ctrl+C when done")
    print("=" * 60)
    header = "{:>6}  {:>8}  {:>5}  {:<20}  {:>8}".format(
        "Time", "Type", "Index", "Name", "Value"
    )
    print(header)
    print("-" * 60)

    with open(dev, "rb") as f:
        start = time.time()
        while True:
            data = f.read(8)
            if len(data) < 8:
                break

            ts, value, typ, number = struct.unpack("IhBB", data)

            # Filter out init events (type & 0x80)
            if typ & 0x80:
                continue

            elapsed = time.time() - start

            if typ == 1:  # Button
                name = BTN_NAMES.get(number, "Btn{}".format(number))
                state = "PRESSED" if value else "released"
                line = "{:6.1f}  {:>8}  {:>5}  {:<20}  {:>8}".format(
                    elapsed, "BUTTON", number, name, state
                )
                print(line)
            elif typ == 2:  # Axis
                name = AXIS_NAMES.get(number, "Axis{}".format(number))
                # js0 reports -32767..32767
                pct = value / 32767.0
                if abs(pct) > 0.15:  # deadzone filter for display
                    line = "{:6.1f}  {:>8}  {:>5}  {:<20}  {:>+8.2f}".format(
                        elapsed, "AXIS", number, name, pct
                    )
                    print(line)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDone.")
    except FileNotFoundError:
        print("ERROR: {} not found — is the controller connected?".format(dev))
        sys.exit(1)
    except PermissionError:
        print("ERROR: Permission denied on {} — try: sudo python3 {}".format(dev, __file__))
        sys.exit(1)
