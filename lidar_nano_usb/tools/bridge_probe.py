#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass

import serial
from serial.tools import list_ports


CH340_VID_PID_CANDIDATES = {
    (0x1A86, 0x7523),
    (0x1A86, 0x5523),
}

LINUX_STABLE_SYMLINK = "/dev/rovac_lidar"

XV11_INDEX_COUNT = 0xF9 - 0xA0 + 1  # 90
XV11_PACKET_LEN = 22
XV11_HEADER_BYTES = (0xFA, 0xFC)
XV11_BYTES_PER_REV = XV11_PACKET_LEN * XV11_INDEX_COUNT  # 1980

@dataclass(frozen=True)
class ProbeResult:
    found: bool
    device: str | None = None
    vid: str | None = None
    pid: str | None = None
    description: str | None = None
    serial_number: str | None = None
    busy: bool | None = None
    busy_pids: list[int] | None = None
    baud: int | None = None
    firmware_id: str | None = None
    firmware_version: str | None = None
    firmware_status: str | None = None
    firmware_baud: str | None = None
    bytes_received: int | None = None
    bytes_per_s: float | None = None
    xv11_headers_seen: int | None = None
    xv11_packets_seen: int | None = None
    rpm_est_packets: float | None = None
    rpm_est_bytes: float | None = None
    rpm_est_speed: float | None = None
    rpm_est_speed_samples: int | None = None
    rpm_est_speed_stdev: float | None = None
    rpm_est: float | None = None
    rpm_est_method: str | None = None
    unique_indexes: int | None = None
    missing_indexes: int | None = None
    speed_raw_mean: float | None = None
    speed_rpm_mean: float | None = None
    speed_rpm_note: str | None = None
    header_fa_count: int | None = None
    header_fc_count: int | None = None
    header_index_candidates: int | None = None
    header_index_candidates_per_s: float | None = None
    ascii_printable_ratio: float | None = None
    ascii_bang_lines: list[str] | None = None
    notes: list[str] | None = None


def choose_port(ports):
    for port in ports:
        if (port.vid, port.pid) in CH340_VID_PID_CANDIDATES:
            return port
        if port.device and "wchusbserial" in port.device.lower():
            return port
    for port in ports:
        if port.description and "USB Serial" in port.description:
            return port
    return None


def lsof_pids(device: str) -> list[int]:
    try:
        proc = subprocess.run(
            ["lsof", device],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    pids: list[int] = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            pids.append(int(parts[1]))
        except ValueError:
            continue
    return sorted(set(pids))


def ascii_printable_ratio(data: bytes) -> float | None:
    if not data:
        return None
    printable = 0
    for b in data:
        if b in (9, 10, 13) or 32 <= b <= 126:
            printable += 1
    return printable / len(data)


def extract_bang_lines(data: bytes, max_lines: int = 20) -> list[str]:
    if not data:
        return []
    sanitized_chars: list[str] = []
    for b in data:
        if b in (10, 13):
            sanitized_chars.append("\n")
        elif b == 9 or 32 <= b <= 126:
            sanitized_chars.append(chr(b))
        else:
            sanitized_chars.append(" ")
    text = "".join(sanitized_chars)
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("!"):
            continue
        if len(line) < 3:
            continue
        if any(ord(c) < 32 or ord(c) > 126 for c in line):
            continue
        lines.append(line)
        if len(lines) >= max_lines:
            break
    return lines


def send_command_collect_lines(
    ser: serial.Serial,
    command_text: str,
    window_s: float = 0.6,
    max_bytes: int = 8192,
) -> list[str]:
    ser.reset_input_buffer()
    ser.write((command_text.rstrip() + "\n").encode("ascii", errors="ignore"))
    ser.flush()

    received = bytearray()
    deadline = time.time() + max(0.05, window_s)
    while time.time() < deadline and len(received) < max_bytes:
        chunk = ser.read(512)
        if chunk:
            received.extend(chunk)
        else:
            time.sleep(0.01)
    return extract_bang_lines(bytes(received), max_lines=20)


def count_xv11_headers(data: bytes) -> int:
    # XV11 packets typically begin with 0xFA followed by an index in [0xA0, 0xF9].
    headers = 0
    for i in range(len(data) - 1):
        if data[i] in XV11_HEADER_BYTES and 0xA0 <= data[i + 1] <= 0xF9:
            headers += 1
    return headers


def speed_cluster_estimate(
    speed_rpm_values: list[float],
    *,
    anchor_rpm: float | None,
    bin_rpm: float = 5.0,
) -> tuple[float | None, int, float | None, float | None]:
    if not speed_rpm_values:
        return None, 0, None, None

    bins: dict[float, list[float]] = {}
    for rpm in speed_rpm_values:
        key = round(rpm / bin_rpm) * bin_rpm
        bins.setdefault(key, []).append(rpm)

    best_key = None
    if anchor_rpm is not None and anchor_rpm > 0:
        tol = max(50.0, anchor_rpm * 0.30)
        close = {k: v for k, v in bins.items() if abs(k - anchor_rpm) <= tol}
        if close:
            best_key = max(close.keys(), key=lambda k: len(close[k]))
        else:
            best_key = max(bins.keys(), key=lambda k: len(bins[k]))
    else:
        best_key = max(bins.keys(), key=lambda k: len(bins[k]))

    values = bins[best_key]
    est = statistics.median(values)
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    return est, len(values), stdev, best_key


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safe probe for the USB LIDAR bridge (port detection + optional handshake + short data sample)."
    )
    parser.add_argument("--port", help="Explicit serial port path (skips auto-detect).")
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Serial baud rate (default: 115200).",
    )
    parser.add_argument(
        "--sample-seconds",
        type=float,
        default=1.0,
        help="How long to sample incoming bytes (default: 1.0s).",
    )
    parser.add_argument(
        "--handshake",
        action="store_true",
        help="Try firmware commands (!id, !version). Safe; does not read continuous data.",
    )
    parser.add_argument(
        "--force-open",
        action="store_true",
        help="Attempt to open the port even if another process is holding it.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()

    notes: list[str] = []

    ports = list(list_ports.comports())
    selected = None
    if args.port:
        selected = next((p for p in ports if p.device == args.port), None)
        if selected is None:
            # Still allow probing an explicit port even if pyserial doesn't list it.
            selected = type("Port", (), {})()
            selected.device = args.port
            selected.vid = None
            selected.pid = None
            selected.description = None
            selected.serial_number = None
    else:
        if os.path.exists(LINUX_STABLE_SYMLINK):
            resolved = os.path.realpath(LINUX_STABLE_SYMLINK)
            selected = next(
                (p for p in ports if p.device in {LINUX_STABLE_SYMLINK, resolved}), None
            )
            if selected is None:
                selected = type("Port", (), {})()
                selected.device = LINUX_STABLE_SYMLINK
                selected.vid = None
                selected.pid = None
                selected.description = "Stable symlink (udev)"
                selected.serial_number = None
        else:
            selected = choose_port(ports)

    if selected is None:
        result = ProbeResult(found=False, notes=["No matching serial port detected by pyserial."])
        if args.json:
            print(json.dumps(asdict(result), separators=(",", ":")))
        else:
            print("No matching serial port detected.")
        return 1

    device = selected.device
    vid = f"0x{selected.vid:04x}" if getattr(selected, "vid", None) is not None else None
    pid = f"0x{selected.pid:04x}" if getattr(selected, "pid", None) is not None else None
    description = getattr(selected, "description", None)
    serial_number = getattr(selected, "serial_number", None)

    busy_pids = lsof_pids(device)
    busy = bool(busy_pids)
    if busy:
        notes.append(f"Port is in use (pids: {', '.join(map(str, busy_pids))}).")
        notes.append("Close the process holding it (or run ./preflight_check.sh) before reading.")
        if not args.force_open:
            result = ProbeResult(
                found=True,
                device=device,
                vid=vid,
                pid=pid,
                description=description,
                serial_number=serial_number,
                busy=True,
                busy_pids=busy_pids or None,
                baud=args.baud,
                notes=notes or None,
            )
            if args.json:
                print(json.dumps(asdict(result), separators=(",", ":")))
            else:
                print("=== USB LIDAR Bridge Probe ===")
                print(f"Device: {device}")
                if vid and pid:
                    print(f"VID:PID: {vid}:{pid}")
                print(f"Port busy: yes (pids: {', '.join(map(str, busy_pids))})")
                for note in notes:
                    print(f"- {note}")
                print("Tip: re-run with --force-open to probe anyway.")
            return 3

    firmware_id = None
    firmware_version = None
    firmware_status = None
    firmware_baud = None
    bytes_received = None
    bytes_per_s = None
    xv11_headers_seen = None
    xv11_packets_seen = None
    rpm_est_packets = None
    rpm_est_bytes = None
    rpm_est_speed = None
    rpm_est_speed_samples = None
    rpm_est_speed_stdev = None
    rpm_est = None
    rpm_est_method = None
    unique_indexes = None
    missing_indexes = None
    speed_raw_mean = None
    speed_rpm_mean = None
    speed_rpm_note = None
    header_fa_count = None
    header_fc_count = None
    header_index_candidates = None
    header_index_candidates_per_s = None
    ascii_ratio = None
    ascii_lines = None

    # Open with short timeouts to avoid blocking/hanging.
    try:
        ser = serial.Serial(
            device,
            args.baud,
            timeout=0.2,
            write_timeout=0.2,
        )
    except Exception as exc:
        notes.append(f"Failed to open serial port: {exc}")
        result = ProbeResult(
            found=True,
            device=device,
            vid=vid,
            pid=pid,
            description=description,
            serial_number=serial_number,
            busy=busy,
            busy_pids=busy_pids or None,
            baud=args.baud,
            notes=notes or None,
        )
        if args.json:
            print(json.dumps(asdict(result), separators=(",", ":")))
        else:
            print(f"Detected: {device}")
            print(f"Open failed: {exc}")
        return 2

    try:
        if args.handshake:
            all_lines: list[str] = []
            for cmd in ("!id", "!version", "!status", "!baud"):
                all_lines.extend(send_command_collect_lines(ser, cmd, window_s=0.7))
            for line in all_lines:
                if firmware_id is None and line.startswith("!DEVICE_ID"):
                    firmware_id = line
                elif firmware_version is None and line.startswith("!VERSION"):
                    firmware_version = line
                elif firmware_status is None and line.startswith("!STATUS"):
                    firmware_status = line
                elif firmware_baud is None and line.startswith("!BAUD_RATE"):
                    firmware_baud = line
            if firmware_id is None:
                notes.append("No !id response detected (device may be basic bridge firmware).")
            if all_lines:
                notes.append(f"Handshake lines: {', '.join(all_lines[:4])}")

        # Sample incoming bytes briefly to confirm data flow.
        ser.reset_input_buffer()
        sample_s = max(0.1, args.sample_seconds)
        deadline = time.time() + sample_s
        buf = bytearray()
        while time.time() < deadline:
            chunk = ser.read(1024)
            if chunk:
                buf.extend(chunk)
        bytes_received = len(buf)
        bytes_per_s = bytes_received / sample_s if sample_s > 0 else None
        if bytes_per_s is not None:
            rpm_est_bytes = bytes_per_s * 60.0 / XV11_BYTES_PER_REV

        header_fa_count = buf.count(0xFA)
        header_fc_count = buf.count(0xFC)
        xv11_headers_seen = count_xv11_headers(buf)

        candidate_rpms: list[float] = []
        candidate_indexes: list[int] = []
        for i in range(len(buf) - 3):
            if buf[i] not in XV11_HEADER_BYTES:
                continue
            idx = buf[i + 1]
            if not (0xA0 <= idx <= 0xF9):
                continue
            speed_raw = buf[i + 2] | (buf[i + 3] << 8)
            rpm = speed_raw / 64.0
            if 50.0 <= rpm <= 1000.0:
                candidate_rpms.append(rpm)
                candidate_indexes.append(idx - 0xA0)

        header_index_candidates = len(candidate_rpms)
        header_index_candidates_per_s = (
            (header_index_candidates / sample_s) if sample_s > 0 else None
        )

        rpm_est_speed, rpm_est_speed_samples, rpm_est_speed_stdev, _bin = speed_cluster_estimate(
            candidate_rpms, anchor_rpm=rpm_est_bytes
        )

        if rpm_est_speed is not None and rpm_est_speed_samples:
            tol = max(20.0, rpm_est_speed * 0.08)
            chosen_indexes = [
                idx for idx, rpm in zip(candidate_indexes, candidate_rpms) if abs(rpm - rpm_est_speed) <= tol
            ]
            unique_indexes = len(set(chosen_indexes))
            missing_indexes = XV11_INDEX_COUNT - unique_indexes if unique_indexes else None
            xv11_packets_seen = len(chosen_indexes)
        else:
            xv11_packets_seen = 0

        rpm_est_packets = (
            (xv11_packets_seen / sample_s) * (60.0 / XV11_INDEX_COUNT)
            if xv11_packets_seen and sample_s > 0
            else None
        )

        rpm_est = None
        rpm_est_method = None
        if rpm_est_speed is not None and rpm_est_speed_samples and rpm_est_speed_samples >= 10:
            rpm_est = rpm_est_speed
            rpm_est_method = "speed_cluster"
        elif rpm_est_bytes is not None:
            rpm_est = rpm_est_bytes
            rpm_est_method = "bytes_per_s"

        speed_raw_mean = statistics.fmean([r * 64.0 for r in candidate_rpms]) if candidate_rpms else None
        if rpm_est_speed is not None:
            speed_rpm_mean = rpm_est_speed
            speed_rpm_note = "Median of dominant speed cluster (speed_raw / 64.0), anchored to byte-rate RPM."

        ascii_ratio = ascii_printable_ratio(buf)
        ascii_lines = extract_bang_lines(bytes(buf), max_lines=10)
        if bytes_received == 0:
            notes.append(
                "No bytes received during sample window. Motor may be stopped, baud mismatch, or wiring issue."
            )
        elif not header_index_candidates:
            notes.append("Bytes received but no XV11 header/index markers detected; check baud and wiring.")
    finally:
        try:
            ser.close()
        except Exception:
            pass

    result = ProbeResult(
        found=True,
        device=device,
        vid=vid,
        pid=pid,
        description=description,
        serial_number=serial_number,
        busy=busy,
        busy_pids=busy_pids or None,
        baud=args.baud,
        firmware_id=firmware_id,
        firmware_version=firmware_version,
        firmware_status=firmware_status,
        firmware_baud=firmware_baud,
        bytes_received=bytes_received,
        bytes_per_s=bytes_per_s,
        xv11_headers_seen=xv11_headers_seen,
        xv11_packets_seen=xv11_packets_seen,
        rpm_est_packets=rpm_est_packets,
        rpm_est_bytes=rpm_est_bytes,
        rpm_est_speed=rpm_est_speed,
        rpm_est_speed_samples=rpm_est_speed_samples,
        rpm_est_speed_stdev=rpm_est_speed_stdev,
        rpm_est=rpm_est,
        rpm_est_method=rpm_est_method,
        unique_indexes=unique_indexes,
        missing_indexes=missing_indexes,
        speed_raw_mean=speed_raw_mean,
        speed_rpm_mean=speed_rpm_mean,
        speed_rpm_note=speed_rpm_note,
        header_fa_count=header_fa_count,
        header_fc_count=header_fc_count,
        header_index_candidates=header_index_candidates,
        header_index_candidates_per_s=header_index_candidates_per_s,
        ascii_printable_ratio=ascii_ratio,
        ascii_bang_lines=ascii_lines or None,
        notes=notes or None,
    )

    if args.json:
        print(json.dumps(asdict(result), separators=(",", ":")))
        return 0

    print("=== USB LIDAR Bridge Probe ===")
    print(f"Device: {device}")
    if vid and pid:
        print(f"VID:PID: {vid}:{pid}")
    if description:
        print(f"Description: {description}")
    if serial_number:
        print(f"USB Serial: {serial_number}")
    if busy:
        print(f"Port busy: yes (pids: {', '.join(map(str, busy_pids))})")
    else:
        print("Port busy: no")
    if firmware_id:
        print(f"Firmware: {firmware_id}")
    if firmware_version:
        print(f"Version: {firmware_version}")
    print(f"Baud: {args.baud}")
    print(f"Sample bytes: {bytes_received}")
    if bytes_per_s is not None:
        print(f"Data rate: {bytes_per_s:.0f} B/s")
    print(f"XV11 headers seen: {xv11_headers_seen}")
    if xv11_packets_seen is not None:
        print(f"XV11 packets seen: {xv11_packets_seen}")
    if rpm_est_packets is not None:
        print(f"RPM (packet-rate): {rpm_est_packets:.1f}")
    if rpm_est_bytes is not None:
        print(f"RPM (byte-rate): {rpm_est_bytes:.1f}")
    if rpm_est_speed is not None:
        print(
            f"RPM (speed cluster): {rpm_est_speed:.1f} "
            f"(n={rpm_est_speed_samples}, stdev={rpm_est_speed_stdev:.1f})"
        )
    if rpm_est is not None:
        print(f"RPM (best): {rpm_est:.1f} ({rpm_est_method})")
    if unique_indexes is not None and missing_indexes is not None:
        print(f"Index coverage: {unique_indexes}/{XV11_INDEX_COUNT} (missing: {missing_indexes})")
    if speed_rpm_mean is not None:
        print(f"Speed field RPM (avg): {speed_rpm_mean:.1f}")
    if ascii_ratio is not None:
        print(f"ASCII printable ratio: {ascii_ratio:.2f}")
    if ascii_lines:
        print("ASCII lines:")
        for line in ascii_lines[:6]:
            print(f"- {line}")
    if notes:
        print("Notes:")
        for note in notes:
            print(f"- {note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
