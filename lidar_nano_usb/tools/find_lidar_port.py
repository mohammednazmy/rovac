#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

from serial.tools import list_ports


CH340_VID_PID_CANDIDATES = {
    (0x1A86, 0x7523),  # WCH CH340 (common)
    (0x1A86, 0x5523),  # Some WCH variants reported in older notes
}

LINUX_STABLE_SYMLINK = "/dev/rovac_lidar"


def choose_port(ports):
    for port in ports:
        vid_pid = (port.vid, port.pid)
        if vid_pid in CH340_VID_PID_CANDIDATES:
            return port
        if port.device and "wchusbserial" in port.device.lower():
            return port
        if port.description and "USB Serial" in port.description:
            return port
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print the most likely serial port for the USB LIDAR module."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a minimal JSON object instead of a raw device path.",
    )
    args = parser.parse_args()

    if os.path.exists(LINUX_STABLE_SYMLINK):
        if args.json:
            resolved = os.path.realpath(LINUX_STABLE_SYMLINK)
            payload = {
                "found": True,
                "device": LINUX_STABLE_SYMLINK,
                "resolved_device": resolved if resolved != LINUX_STABLE_SYMLINK else None,
                "vid": None,
                "pid": None,
                "serial": None,
                "description": "Stable symlink (udev)",
            }
            ports = list(list_ports.comports())
            port = next(
                (p for p in ports if p.device in {LINUX_STABLE_SYMLINK, resolved}), None
            )
            if port is not None:
                payload["vid"] = f"0x{port.vid:04x}" if port.vid is not None else None
                payload["pid"] = f"0x{port.pid:04x}" if port.pid is not None else None
                payload["serial"] = getattr(port, "serial_number", None) or None
                payload["description"] = getattr(port, "description", None) or payload[
                    "description"
                ]
            print(json.dumps(payload, separators=(",", ":")))
            return 0

        print(LINUX_STABLE_SYMLINK)
        return 0

    ports = list(list_ports.comports())
    port = choose_port(ports)
    if port is None:
        if args.json:
            print('{"found":false}')
        return 1

    if args.json:
        payload = {
            "found": True,
            "device": port.device,
            "vid": f"0x{port.vid:04x}" if port.vid is not None else None,
            "pid": f"0x{port.pid:04x}" if port.pid is not None else None,
            "serial": getattr(port, "serial_number", None) or None,
            "description": getattr(port, "description", None) or None,
        }
        print(json.dumps(payload, separators=(",", ":")))
        return 0

    print(port.device)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
