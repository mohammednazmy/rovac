#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import serial
from serial.tools import list_ports


CH340_VID_PID_CANDIDATES = {
    (0x1A86, 0x7523),
    (0x1A86, 0x5523),
}

LINUX_STABLE_SYMLINK = "/dev/rovac_lidar"

XV11_PACKET_LEN = 22
XV11_HEADER_BYTES = (0xFA, 0xFC)  # 0xFC shows up as a common corrupted 0xFA in some setups
XV11_INDEX_MIN = 0xA0
XV11_INDEX_MAX = 0xF9
XV11_INDEX_COUNT = XV11_INDEX_MAX - XV11_INDEX_MIN + 1  # 90
XV11_BYTES_PER_REV = XV11_PACKET_LEN * XV11_INDEX_COUNT  # 1980


@dataclass(frozen=True)
class DiagnosticsResult:
    found: bool
    device: str | None = None
    resolved_device: str | None = None
    busy: bool | None = None
    busy_pids: list[int] | None = None
    baud: int | None = None
    duration_s: float | None = None
    bytes_received: int | None = None
    bytes_per_s: float | None = None
    rpm_est_bytes: float | None = None
    rpm_est_speed: float | None = None
    rpm_est_speed_samples: int | None = None
    rpm_est_speed_stdev: float | None = None
    rpm_est: float | None = None
    rpm_est_method: str | None = None
    packets_total: int | None = None
    packets_per_s: float | None = None
    sync_dropped_bytes: int | None = None
    unique_indexes: int | None = None
    missing_indexes: int | None = None
    wraps: int | None = None
    rpm_est_packets: float | None = None
    rpm_est_wraps: float | None = None
    speed_raw_mean: float | None = None
    speed_raw_min: int | None = None
    speed_raw_max: int | None = None
    speed_rpm_mean: float | None = None
    speed_rpm_note: str | None = None
    header_fa_count: int | None = None
    header_fc_count: int | None = None
    header_index_candidates: int | None = None
    header_index_candidates_per_s: float | None = None
    header_recognition_ratio: float | None = None
    ascii_printable_ratio: float | None = None
    ascii_bang_lines: list[str] | None = None
    quality_score: int | None = None
    quality_grade: str | None = None
    measurements_total: int | None = None
    measurements_valid: int | None = None
    measurements_invalid: int | None = None
    measurements_warning: int | None = None
    distance_mm_min: int | None = None
    distance_mm_p50: float | None = None
    distance_mm_p90: float | None = None
    distance_mm_max: int | None = None
    signal_min: int | None = None
    signal_p50: float | None = None
    signal_p90: float | None = None
    signal_max: int | None = None
    max_packet_gap_s: float | None = None
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


def percentile(sorted_values: list[int], p: float) -> float | None:
    if not sorted_values:
        return None
    if p <= 0:
        return float(sorted_values[0])
    if p >= 1:
        return float(sorted_values[-1])
    k = (len(sorted_values) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return float(sorted_values[f])
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return float(d0 + d1)


def speed_cluster_estimate(
    speed_rpm_values: list[float],
    *,
    anchor_rpm: float | None,
    bin_rpm: float = 5.0,
) -> tuple[float | None, int, float | None]:
    if not speed_rpm_values:
        return None, 0, None

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
    return est, len(values), stdev


def parse_packet_measurements(packet: bytes):
    # Packet format (XV11, 22 bytes):
    # [0]=0xFA, [1]=index, [2..3]=speed (raw), [4..19]=4 measurements, [20..21]=checksum
    measurements = []
    for i in range(4):
        base = 4 + i * 4
        dist_l = packet[base]
        dist_h = packet[base + 1]
        sig_l = packet[base + 2]
        sig_h = packet[base + 3]

        invalid = bool(dist_h & 0x80)
        warning = bool(dist_h & 0x40)
        distance_mm = ((dist_h & 0x3F) << 8) | dist_l
        signal = (sig_h << 8) | sig_l

        measurements.append((distance_mm, signal, invalid, warning))
    return measurements


def main() -> int:
    parser = argparse.ArgumentParser(
        description="XV11 LIDAR diagnostics (bounded read): estimates RPM + basic packet/measurement quality."
    )
    parser.add_argument("--port", help="Explicit serial port path (skips auto-detect).")
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Serial baud rate (default: 115200).",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=10.0,
        help="Sample duration in seconds (default: 10.0).",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=2_000_000,
        help="Hard cap for bytes read (default: 2000000).",
    )
    parser.add_argument(
        "--write-raw",
        type=Path,
        help="Write captured raw serial bytes to this file.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()

    notes: list[str] = []
    duration_s = max(0.2, args.seconds)

    ports = list(list_ports.comports())
    selected = None

    if args.port:
        selected = next((p for p in ports if p.device == args.port), None)
        if selected is None:
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
        result = DiagnosticsResult(found=False, notes=["No matching serial port detected by pyserial."])
        if args.json:
            print(json.dumps(asdict(result), separators=(",", ":")))
        else:
            print("No matching serial port detected.")
        return 1

    device = selected.device
    resolved_device = os.path.realpath(device) if os.path.exists(device) else None

    busy_pids = lsof_pids(device)
    busy = bool(busy_pids)
    if busy:
        notes.append(f"Port is in use (pids: {', '.join(map(str, busy_pids))}).")
        notes.append("Close the process holding it (or run ./preflight_check.sh) before reading.")

    try:
        ser = serial.Serial(
            device,
            args.baud,
            timeout=0.2,
            write_timeout=0.2,
        )
    except Exception as exc:
        notes.append(f"Failed to open serial port: {exc}")
        result = DiagnosticsResult(
            found=True,
            device=device,
            resolved_device=resolved_device if resolved_device != device else None,
            busy=busy,
            busy_pids=busy_pids or None,
            baud=args.baud,
            duration_s=duration_s,
            notes=notes or None,
        )
        if args.json:
            print(json.dumps(asdict(result), separators=(",", ":")))
        else:
            print(f"Detected: {device}")
            print(f"Open failed: {exc}")
        return 2

    bytes_received = 0
    packets_total = 0
    dropped_bytes_total = 0
    wraps = 0
    prev_index: int | None = None
    indexes_seen: set[int] = set()

    speed_raw_values: list[int] = []
    packet_times: list[float] = []
    distance_values: list[int] = []
    signal_values: list[int] = []
    measurements_total = 0
    measurements_valid = 0
    measurements_invalid = 0
    measurements_warning = 0

    buffer = bytearray()
    raw_out = None
    if args.write_raw:
        raw_out = args.write_raw.expanduser().resolve()
        try:
            raw_out.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    raw_file = None
    if raw_out:
        try:
            raw_file = raw_out.open("wb")
        except Exception as exc:
            notes.append(f"Failed to open raw output file: {exc}")
            raw_file = None

    raw_capture = bytearray()
    try:
        ser.reset_input_buffer()
        deadline = time.time() + duration_s
        max_bytes = max(1_000, args.max_bytes)

        while time.time() < deadline and len(raw_capture) < max_bytes:
            want = min(4096, max_bytes - len(raw_capture))
            chunk = ser.read(want)
            if chunk:
                if raw_file:
                    try:
                        raw_file.write(chunk)
                    except Exception:
                        raw_file = None
                raw_capture.extend(chunk)
            else:
                time.sleep(0.01)
    finally:
        try:
            ser.close()
        except Exception:
            pass
        if raw_file:
            try:
                raw_file.close()
            except Exception:
                pass

    bytes_received = len(raw_capture)
    bytes_per_s = bytes_received / duration_s if duration_s > 0 else None
    rpm_est_bytes = None
    if bytes_per_s is not None:
        rpm_est_bytes = bytes_per_s * 60.0 / XV11_BYTES_PER_REV

    header_fa_count = raw_capture.count(0xFA)
    header_fc_count = raw_capture.count(0xFC)
    ascii_ratio = ascii_printable_ratio(raw_capture)
    bang_lines = extract_bang_lines(raw_capture, max_lines=12)

    candidates: list[tuple[int, int, float]] = []
    speed_rpms_all: list[float] = []
    for pos in range(0, max(0, bytes_received - XV11_PACKET_LEN)):
        header = raw_capture[pos]
        if header not in XV11_HEADER_BYTES:
            continue
        idx_raw = raw_capture[pos + 1]
        if not (XV11_INDEX_MIN <= idx_raw <= XV11_INDEX_MAX):
            continue
        speed_raw = raw_capture[pos + 2] | (raw_capture[pos + 3] << 8)
        rpm = speed_raw / 64.0
        if 50.0 <= rpm <= 1000.0:
            index = idx_raw - XV11_INDEX_MIN
            candidates.append((pos, index, rpm))
            speed_rpms_all.append(rpm)

    header_index_candidates = len(candidates)
    header_index_candidates_per_s = (
        (header_index_candidates / duration_s) if duration_s > 0 else None
    )

    expected_packets = (bytes_received / XV11_PACKET_LEN) if bytes_received else None
    header_recognition_ratio = (
        (header_index_candidates / expected_packets)
        if expected_packets and expected_packets > 0
        else None
    )

    rpm_est_speed, rpm_est_speed_samples, rpm_est_speed_stdev = speed_cluster_estimate(
        speed_rpms_all, anchor_rpm=rpm_est_bytes
    )

    selected: list[tuple[int, int, float]] = []
    if rpm_est_speed is not None and rpm_est_speed_samples:
        tol = max(20.0, rpm_est_speed * 0.08)
        selected = [c for c in candidates if abs(c[2] - rpm_est_speed) <= tol]

    packets_total = len(selected)
    packets_per_s = packets_total / duration_s if duration_s > 0 else None

    indexes_seen = set()
    wraps = 0
    prev_index = None
    for _pos, index, _rpm in selected:
        indexes_seen.add(index)
        if prev_index is not None and index < prev_index:
            wraps += 1
        prev_index = index

    unique_indexes = len(indexes_seen)
    missing_indexes = max(0, XV11_INDEX_COUNT - unique_indexes) if unique_indexes else None

    rpm_est_packets = None
    if duration_s > 0 and packets_total > 0 and header_recognition_ratio is not None and header_recognition_ratio > 0.8:
        rpm_est_packets = (packets_total / duration_s) * (60.0 / XV11_INDEX_COUNT)

    rpm_est_wraps = None
    if duration_s > 0 and wraps > 0:
        rpm_est_wraps = (wraps / duration_s) * 60.0

    rpm_est = None
    rpm_est_method = None
    if rpm_est_speed is not None and rpm_est_speed_samples and rpm_est_speed_samples >= 50:
        rpm_est = rpm_est_speed
        rpm_est_method = "speed_cluster"
    elif rpm_est_bytes is not None:
        rpm_est = rpm_est_bytes
        rpm_est_method = "bytes_per_s"

    speed_raw_values = [int(round(rpm * 64.0)) for _pos, _idx, rpm in selected]
    speed_raw_mean = statistics.fmean(speed_raw_values) if speed_raw_values else None
    speed_raw_min = min(speed_raw_values) if speed_raw_values else None
    speed_raw_max = max(speed_raw_values) if speed_raw_values else None

    speed_rpm_mean = rpm_est_speed if rpm_est_speed is not None else None
    speed_rpm_note = (
        "Median of dominant speed cluster (speed_raw / 64.0), anchored to byte-rate RPM."
        if speed_rpm_mean is not None
        else None
    )

    for pos, _index, _rpm in selected:
        packet = bytes(raw_capture[pos : pos + XV11_PACKET_LEN])
        for distance_mm, signal, invalid, warning in parse_packet_measurements(packet):
            measurements_total += 1
            if invalid:
                measurements_invalid += 1
            else:
                measurements_valid += 1
                distance_values.append(distance_mm)
                signal_values.append(signal)
            if warning:
                measurements_warning += 1

    max_packet_gap_s = None
    if bytes_per_s and len(selected) >= 2:
        positions = [p for p, _idx, _rpm in selected]
        gaps = [(b - a) / bytes_per_s for a, b in zip(positions, positions[1:]) if b > a]
        max_packet_gap_s = max(gaps) if gaps else None

    distance_values.sort()
    signal_values.sort()

    quality_score = 100
    if bytes_received == 0:
        quality_score = 0
    if header_recognition_ratio is not None:
        if header_recognition_ratio < 0.3:
            quality_score -= 50
            notes.append("Heavy framing corruption: only a small fraction of packets have recognizable header/index.")
        elif header_recognition_ratio < 0.6:
            quality_score -= 25
            notes.append("Moderate framing corruption: many packets lack recognizable header/index.")
        elif header_recognition_ratio < 0.8:
            quality_score -= 10
    if packets_total < 20:
        quality_score -= 15
        notes.append("Low confidence: few usable packet candidates detected in the sample window.")
    if measurements_total:
        invalid_rate = measurements_invalid / measurements_total
        if invalid_rate > 0.30:
            quality_score -= 25
        elif invalid_rate > 0.15:
            quality_score -= 10
    if rpm_est_speed_stdev is not None and rpm_est_speed_stdev > 15:
        quality_score -= 10
    quality_score = max(0, min(100, int(round(quality_score))))
    if quality_score >= 80:
        quality_grade = "GOOD"
    elif quality_score >= 50:
        quality_grade = "WARN"
    else:
        quality_grade = "BAD"

    result = DiagnosticsResult(
        found=True,
        device=device,
        resolved_device=resolved_device if resolved_device and resolved_device != device else None,
        busy=busy,
        busy_pids=busy_pids or None,
        baud=args.baud,
        duration_s=duration_s,
        bytes_received=bytes_received,
        bytes_per_s=bytes_per_s,
        rpm_est_bytes=rpm_est_bytes,
        rpm_est_speed=rpm_est_speed,
        rpm_est_speed_samples=rpm_est_speed_samples,
        rpm_est_speed_stdev=rpm_est_speed_stdev,
        rpm_est=rpm_est,
        rpm_est_method=rpm_est_method,
        packets_total=packets_total,
        packets_per_s=packets_per_s,
        sync_dropped_bytes=None,
        unique_indexes=unique_indexes,
        missing_indexes=missing_indexes,
        wraps=wraps,
        rpm_est_packets=rpm_est_packets,
        rpm_est_wraps=rpm_est_wraps,
        speed_raw_mean=speed_raw_mean,
        speed_raw_min=speed_raw_min,
        speed_raw_max=speed_raw_max,
        speed_rpm_mean=speed_rpm_mean,
        speed_rpm_note=speed_rpm_note,
        header_fa_count=header_fa_count,
        header_fc_count=header_fc_count,
        header_index_candidates=header_index_candidates,
        header_index_candidates_per_s=header_index_candidates_per_s,
        header_recognition_ratio=header_recognition_ratio,
        ascii_printable_ratio=ascii_ratio,
        ascii_bang_lines=bang_lines or None,
        quality_score=quality_score,
        quality_grade=quality_grade,
        measurements_total=measurements_total,
        measurements_valid=measurements_valid,
        measurements_invalid=measurements_invalid,
        measurements_warning=measurements_warning,
        distance_mm_min=distance_values[0] if distance_values else None,
        distance_mm_p50=percentile(distance_values, 0.50),
        distance_mm_p90=percentile(distance_values, 0.90),
        distance_mm_max=distance_values[-1] if distance_values else None,
        signal_min=signal_values[0] if signal_values else None,
        signal_p50=percentile(signal_values, 0.50),
        signal_p90=percentile(signal_values, 0.90),
        signal_max=signal_values[-1] if signal_values else None,
        max_packet_gap_s=max_packet_gap_s,
        notes=notes or None,
    )

    if args.json:
        print(json.dumps(asdict(result), separators=(",", ":")))
        return 0 if packets_total > 0 else 4

    print("=== XV11 Diagnostics ===")
    print(f"Device: {device}")
    if resolved_device and resolved_device != device:
        print(f"Resolved: {resolved_device}")
    print(f"Baud: {args.baud}")
    print(f"Duration: {duration_s:.1f}s")
    if busy:
        print(f"Port busy: yes (pids: {', '.join(map(str, busy_pids))})")
    else:
        print("Port busy: no")
    print(f"Bytes received: {bytes_received} ({bytes_per_s:.0f}/s)")
    print(f"Packets: {packets_total} ({packets_per_s:.1f}/s)")
    if rpm_est is not None:
        print(f"RPM (best): {rpm_est:.1f} ({rpm_est_method})")
    if rpm_est_bytes is not None:
        print(f"RPM (byte-rate): {rpm_est_bytes:.1f}")
    if rpm_est_speed is not None:
        print(
            f"RPM (speed cluster): {rpm_est_speed:.1f} "
            f"(n={rpm_est_speed_samples}, stdev={rpm_est_speed_stdev:.1f})"
        )
    if rpm_est_wraps is not None:
        print(f"RPM (wrap-count): {rpm_est_wraps:.1f}")
    if speed_rpm_mean is not None:
        print(f"Speed field RPM (avg): {speed_rpm_mean:.1f}")
    print(f"Index coverage: {unique_indexes}/{XV11_INDEX_COUNT} (missing: {missing_indexes})")
    if header_recognition_ratio is not None:
        print(f"Header/index recognition: {header_recognition_ratio*100:.1f}%")
    if quality_grade is not None:
        print(f"Quality: {quality_grade} ({quality_score}/100)")
    if measurements_total:
        print(
            "Measurements: "
            f"{measurements_total} total, {measurements_valid} valid, {measurements_invalid} invalid, "
            f"{measurements_warning} warning"
        )
    if distance_values:
        print(
            "Distance mm (valid): "
            f"min={distance_values[0]} p50={percentile(distance_values,0.50):.0f} "
            f"p90={percentile(distance_values,0.90):.0f} max={distance_values[-1]}"
        )
    if signal_values:
        print(
            "Signal (valid): "
            f"min={signal_values[0]} p50={percentile(signal_values,0.50):.0f} "
            f"p90={percentile(signal_values,0.90):.0f} max={signal_values[-1]}"
        )
    if max_packet_gap_s is not None:
        print(f"Max packet gap: {max_packet_gap_s:.3f}s")
    if raw_out and raw_file is not None:
        print(f"Raw capture: {raw_out}")
    if ascii_ratio is not None:
        print(f"ASCII printable ratio: {ascii_ratio:.2f}")
    if bang_lines:
        print("ASCII lines:")
        for line in bang_lines[:6]:
            print(f"- {line}")
    if notes:
        print("Notes:")
        for note in notes:
            print(f"- {note}")

    return 0 if packets_total > 0 else 4


if __name__ == "__main__":
    raise SystemExit(main())
