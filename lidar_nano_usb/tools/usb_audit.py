#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
from dataclasses import dataclass

from serial.tools import list_ports


CH340_VID_PID_CANDIDATES = {
    (0x1A86, 0x7523),
    (0x1A86, 0x5523),
}


@dataclass(frozen=True)
class MacSystemExtension:
    bundle_id: str
    state: str


def _run(cmd: list[str], timeout_s: float = 10.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired:
        return 124, "", "Timed out"


def macos_ch34x_driver_status() -> MacSystemExtension | None:
    if platform.system() != "Darwin":
        return None

    code, output, err = _run(["systemextensionsctl", "list"], timeout_s=15.0)
    if code != 0 and not output:
        return MacSystemExtension(bundle_id="cn.wch.CH34xVCPDriver", state=f"unavailable ({err.strip()})")
    for line in output.splitlines():
        if "cn.wch.CH34xVCPDriver" not in line:
            continue
        state = "activated enabled" if "activated enabled" in line else line.strip()
        return MacSystemExtension(bundle_id="cn.wch.CH34xVCPDriver", state=state)

    return MacSystemExtension(bundle_id="cn.wch.CH34xVCPDriver", state="not present")


def macos_usb_summary_for_vid_pid(vid: int, pid: int) -> dict[str, str] | None:
    if platform.system() != "Darwin":
        return None

    code, output, _err = _run(
        ["ioreg", "-p", "IOUSB", "-l", "-w", "0", "-r", "-c", "IOUSBHostDevice"],
        timeout_s=10.0,
    )
    if code != 0 or not output:
        return None

    current_device: str | None = None
    current: dict[str, str] = {}
    matches: list[dict[str, str]] = []

    device_header = re.compile(r"^\s*(\|\s*)*\+\-o\s+(?P<name>.+?)@")
    kv = re.compile(r'^\s*(?:\|\s*)*"(?P<key>[^"]+)"\s+=\s+(?P<value>.+)$')

    def flush():
        nonlocal current_device, current
        if not current:
            current_device = None
            return
        try:
            id_vendor = int(current.get("idVendor", ""), 10)
            id_product = int(current.get("idProduct", ""), 10)
        except ValueError:
            current_device = None
            current = {}
            return
        if id_vendor == vid and id_product == pid:
            current["__device"] = current_device or "Unknown"
            matches.append(dict(current))
        current_device = None
        current = {}

    for line in output.splitlines():
        header_match = device_header.match(line)
        if header_match:
            flush()
            current_device = header_match.group("name").strip()
            continue
        kv_match = kv.match(line)
        if not kv_match:
            continue
        key = kv_match.group("key")
        value = kv_match.group("value").strip()
        value = value.strip('"')
        current[key] = value

    flush()

    if not matches:
        return None

    # If multiple matches exist, return the first; most setups have just one.
    candidate = matches[0]
    return {
        "device": candidate.get("__device", "Unknown"),
        "idVendor": candidate.get("idVendor", ""),
        "idProduct": candidate.get("idProduct", ""),
        "USB Product Name": candidate.get("USB Product Name", ""),
        "USB Vendor Name": candidate.get("USB Vendor Name", ""),
        "bDeviceClass": candidate.get("bDeviceClass", ""),
        "iSerialNumber": candidate.get("iSerialNumber", ""),
        "USB Serial Number": candidate.get("USB Serial Number", ""),
    }


def port_to_dict(port) -> dict[str, object]:
    return {
        "device": port.device,
        "description": getattr(port, "description", None),
        "hwid": getattr(port, "hwid", None),
        "vid": f"0x{port.vid:04x}" if getattr(port, "vid", None) is not None else None,
        "pid": f"0x{port.pid:04x}" if getattr(port, "pid", None) is not None else None,
        "serial_number": getattr(port, "serial_number", None),
        "manufacturer": getattr(port, "manufacturer", None),
        "product": getattr(port, "product", None),
        "location": getattr(port, "location", None),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="USB audit for the CH340-based LIDAR Nano USB bridge.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()

    ports = list(list_ports.comports())

    candidates = [
        p
        for p in ports
        if (p.vid, p.pid) in CH340_VID_PID_CANDIDATES
        or (p.device and "wchusbserial" in p.device.lower())
    ]

    ext = None
    usb_summaries: list[dict[str, str]] = []
    if platform.system() == "Darwin":
        ext = macos_ch34x_driver_status()
        for vid, pid in sorted(CH340_VID_PID_CANDIDATES):
            summary = macos_usb_summary_for_vid_pid(vid, pid)
            if summary:
                usb_summaries.append(summary)

    if args.json:
        payload: dict[str, object] = {
            "platform": platform.system(),
            "release": platform.release(),
            "python": sys.executable,
            "ports": [port_to_dict(p) for p in ports],
            "candidates": [port_to_dict(p) for p in candidates],
        }
        if ext is not None:
            payload["macos_driver"] = {"bundle_id": ext.bundle_id, "state": ext.state}
        if usb_summaries:
            payload["macos_usb_summaries"] = usb_summaries

        if candidates and platform.system() == "Darwin":
            assessment = (
                "CH340 detected; macOS typically requires the WCH CH34x DriverKit extension on clean machines."
            )
        elif candidates:
            assessment = "CH340-style USB-serial device detected; plug-and-play depends on OS driver availability."
        else:
            assessment = "No CH340-style candidate detected."
        payload["assessment"] = assessment

        print(json.dumps(payload, separators=(",", ":")))
        return 0

    print("=== USB LIDAR Plug-and-Play Audit ===")
    print(f"Platform: {platform.system()} {platform.release()}")
    print()

    if not ports:
        print("No serial ports detected by pyserial.")
    else:
        print("Serial ports (pyserial):")
        for port in ports:
            vid_pid = ""
            if port.vid is not None and port.pid is not None:
                vid_pid = f"{port.vid:04X}:{port.pid:04X}"
            print(f"- {port.device}  ({port.description})  {vid_pid}".rstrip())
        print()

    if not candidates:
        print("No CH340-style device detected (VID:PID 1A86:7523 or 1A86:5523).")
    else:
        print("Detected USB LIDAR candidate port(s):")
        for p in candidates:
            print(f"- device: {p.device}")
            print(f"  description: {p.description}")
            print(f"  hwid: {p.hwid}")
            print(f"  serial: {p.serial_number}")
            print(f"  manufacturer: {p.manufacturer}")
            print(f"  product: {p.product}")
            print(f"  location: {p.location}")
        print()

    if platform.system() == "Darwin" and ext is not None:
        print("macOS driver status:")
        print(f"- {ext.bundle_id}: {ext.state}")
        print()

        for summary in usb_summaries:
            vid = summary.get("idVendor")
            pid = summary.get("idProduct")
            print(f"macOS IOUSB summary (VID:PID {vid}:{pid}):")
            for key, value in summary.items():
                if value:
                    print(f"- {key}: {value}")
            print()

    print("Assessment:")
    if candidates and platform.system() == "Darwin":
        print(
            "- This device enumerates as WCH CH340 (1A86:7523). On macOS it commonly depends on the "
            "WCH CH34x DriverKit extension, so it is not driverless plug-and-play on a clean Mac."
        )
        print("- For truly driverless behavior, prefer a native-USB MCU presenting USB CDC-ACM (or HID).")
    elif candidates:
        print("- A CH340-style USB-serial bridge is present. Plug-and-play depends on OS driver availability.")
    else:
        print("- No candidate device detected; check USB connection and driver availability.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
