#!/usr/bin/env python3
"""
Motor Characterization Tool — ROVAC COBS binary protocol.

Drives raw PWM values directly to the ESP32 (bypassing PID) and records the
measured per-wheel steady-state velocity. Output is a CSV of the *true* motor
response curve — the input to Phase 3 PID/FF retuning.

REQUIREMENTS:
  1. Stop the motor driver service so this tool can own the serial port:
         sudo systemctl stop rovac-edge-motor-driver
  2. Robot should be on BLOCKS with wheels free to spin (wheels-free sweep)
     OR on the floor in an open area (on-ground sweep). This tool will
     drive both wheels at the commanded PWM — don't let the robot drive
     into anything.

USAGE (on the Pi):
  python3 motor_characterization.py --out sweep.csv
  python3 motor_characterization.py --min 0 --max 255 --step 5 --direction fwd
  python3 motor_characterization.py --direction both --settle 1.0 --sample 1.0

AFTER:
  sudo systemctl start rovac-edge-motor-driver

OUTPUT CSV columns:
  pwm            signed PWM value sent (-255..+255)
  direction      'fwd' or 'rev'
  v_left_mps     mean measured left wheel velocity (m/s, firmware native frame)
  v_right_mps    mean measured right wheel velocity (m/s, firmware native frame)
  v_left_std     stddev of left wheel samples (m/s)
  v_right_std    stddev of right wheel samples (m/s)
  n_samples      number of velocity samples averaged
  dt_elapsed_s   seconds over which samples were collected
"""

import argparse
import csv
import queue
import statistics
import struct
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

try:
    import serial
except ImportError:
    sys.exit("ERROR: pyserial not installed. Run: pip3 install pyserial")


# ────────────────────────────────────────────────────────────────────────
# Protocol constants — keep in sync with common/serial_protocol.h
# ────────────────────────────────────────────────────────────────────────

SERIAL_BAUD           = 460800

MSG_CMD_VEL           = 0x01
MSG_CMD_ESTOP         = 0x02
MSG_CMD_RESET_ODOM    = 0x03
MSG_CMD_PWM_RAW       = 0x04
MSG_CMD_SET_PARAM     = 0x05
MSG_CMD_SAVE_NVS      = 0x06
MSG_CMD_LOAD_NVS      = 0x07
MSG_CMD_RESET_PARAMS  = 0x08
MSG_CMD_GET_PARAM     = 0x09

MSG_ODOM              = 0x10
MSG_IMU               = 0x11
MSG_DIAG              = 0x12
MSG_PARAM_VALUE       = 0x13

MSG_LOG               = 0xF0

# Wheel geometry — used to decompose /odom linear+angular → per-wheel velocity.
# Must match odometry.h WHEEL_SEPARATION. Physically measured 2026-04-22.
WHEEL_SEPARATION      = 0.2005   # meters (track centerline to centerline)


# ────────────────────────────────────────────────────────────────────────
# CRC-16/CCITT — exact port of serial_protocol.h version
# ────────────────────────────────────────────────────────────────────────

def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


# ────────────────────────────────────────────────────────────────────────
# COBS encode / decode
# ────────────────────────────────────────────────────────────────────────

def cobs_encode(data: bytes) -> bytes:
    """Encode a byte string into COBS. Returns the encoded block (no trailing 0x00)."""
    out = bytearray()
    code_idx = 0
    out.append(0)   # placeholder for first code byte
    code = 1
    for byte in data:
        if byte == 0:
            out[code_idx] = code
            code_idx = len(out)
            out.append(0)
            code = 1
        else:
            out.append(byte)
            code += 1
            if code == 0xFF:
                out[code_idx] = code
                code_idx = len(out)
                out.append(0)
                code = 1
    out[code_idx] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    """Decode a COBS-encoded block (without trailing 0x00). Returns raw bytes."""
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        if code == 0:
            raise ValueError("Zero byte in COBS input")
        i += 1
        for _ in range(code - 1):
            if i >= len(data):
                break
            out.append(data[i])
            i += 1
        if code < 0xFF and i < len(data):
            out.append(0)
    return bytes(out)


# ────────────────────────────────────────────────────────────────────────
# Frame encoding / parsing
# ────────────────────────────────────────────────────────────────────────

def build_frame(msg_type: int, payload: bytes = b"") -> bytes:
    """Build [msg_type][payload][crc16] and COBS-encode it with 0x00 delimiter."""
    raw = bytes([msg_type]) + payload
    crc = crc16_ccitt(raw)
    raw = raw + struct.pack("<H", crc)
    return cobs_encode(raw) + b"\x00"


def parse_frame(decoded: bytes) -> Optional[tuple[int, bytes]]:
    """Parse decoded [msg_type][payload][crc16_lo][crc16_hi]. Returns (type, payload) or None."""
    if len(decoded) < 3:
        return None
    data_len = len(decoded) - 2
    expected = crc16_ccitt(decoded[:data_len])
    received = struct.unpack("<H", decoded[data_len:])[0]
    if expected != received:
        return None
    return decoded[0], decoded[1:data_len]


# Odom payload layout: see serial_protocol.h odom_payload_t
# uint64_t timestamp_us + 7x float
_ODOM_STRUCT = struct.Struct("<Q7f")


def parse_odom(payload: bytes) -> Optional[tuple[float, float, float]]:
    """Return (firmware_v_linear, firmware_v_angular, timestamp_s) or None.
    Un-negates the ROS frame correction applied in serial_transport.c."""
    if len(payload) != _ODOM_STRUCT.size:
        return None
    ts_us, _x, _y, _yaw, v_linear, v_angular, _cov_x, _cov_yaw = _ODOM_STRUCT.unpack(payload)
    # Firmware applies:  ODOM.v_linear = -firmware.v_linear (ROS frame correction)
    # Undo it for characterization so positive PWM → positive velocity.
    return -v_linear, -v_angular, ts_us / 1e6


# ────────────────────────────────────────────────────────────────────────
# Serial reader thread — parses frames as they arrive
# ────────────────────────────────────────────────────────────────────────

@dataclass
class OdomSample:
    t_mono: float       # monotonic receive time (seconds)
    v_linear: float     # firmware native frame, m/s
    v_angular: float    # firmware native frame, rad/s


class SerialReader(threading.Thread):
    """Reads from the serial port in a background thread.
    Dispatches ODOM samples to a thread-safe queue.
    Surfaces MSG_LOG lines to a configurable callback (default: print)."""

    def __init__(self, ser: serial.Serial,
                 log_cb: Callable[[str], None] = lambda s: print(f"[esp32] {s}")):
        super().__init__(daemon=True)
        self._ser = ser
        self._log_cb = log_cb
        self._running = True
        self.odom_q: queue.Queue[OdomSample] = queue.Queue(maxsize=1024)

    def stop(self):
        self._running = False

    def run(self):
        buf = bytearray()
        while self._running:
            try:
                chunk = self._ser.read(256)
            except serial.SerialException:
                break
            if not chunk:
                continue
            for byte in chunk:
                if byte == 0:
                    if buf:
                        try:
                            decoded = cobs_decode(bytes(buf))
                        except ValueError:
                            buf.clear()
                            continue
                        buf.clear()
                        parsed = parse_frame(decoded)
                        if parsed is None:
                            continue
                        msg_type, payload = parsed
                        self._dispatch(msg_type, payload)
                else:
                    buf.append(byte)

    def _dispatch(self, msg_type: int, payload: bytes):
        if msg_type == MSG_ODOM:
            r = parse_odom(payload)
            if r is not None:
                v_lin, v_ang, _ = r
                try:
                    self.odom_q.put_nowait(
                        OdomSample(t_mono=time.monotonic(),
                                   v_linear=v_lin, v_angular=v_ang))
                except queue.Full:
                    # drop oldest to keep up
                    try:
                        self.odom_q.get_nowait()
                    except queue.Empty:
                        pass
        elif msg_type == MSG_LOG:
            # Null-terminated ASCII
            text = payload.rstrip(b"\x00").decode("utf-8", errors="replace")
            if text:
                self._log_cb(text)


# ────────────────────────────────────────────────────────────────────────
# Characterization driver
# ────────────────────────────────────────────────────────────────────────

class Characterizer:
    def __init__(self, port: str, settle_s: float, sample_s: float,
                 wheel_sep: float, verbose: bool = True):
        self.port = port
        self.settle_s = settle_s
        self.sample_s = sample_s
        self.wheel_sep = wheel_sep
        self.verbose = verbose

        self._ser: Optional[serial.Serial] = None
        self._reader: Optional[SerialReader] = None

    def __enter__(self):
        self._ser = serial.Serial(self.port, SERIAL_BAUD, timeout=0.05)
        # Drain boot noise
        time.sleep(0.3)
        self._ser.reset_input_buffer()
        self._reader = SerialReader(self._ser)
        self._reader.start()
        # Wait for the first ODOM sample to confirm ESP32 is alive
        if not self._wait_for_odom(timeout=3.0):
            raise RuntimeError(
                "No ODOM received from ESP32 in 3s. Is motor driver service still running? "
                "Run: sudo systemctl stop rovac-edge-motor-driver")
        if self.verbose:
            print(f"Connected to ESP32 on {self.port}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Always try to stop motors cleanly on exit
        try:
            self._send_raw_pwm(0, 0)
            time.sleep(0.1)
            self._send(MSG_CMD_ESTOP)
        except Exception:
            pass
        if self._reader is not None:
            self._reader.stop()
        if self._ser is not None:
            self._ser.close()

    # ── Low-level send/receive ─────────────────────────────────────────

    def _send(self, msg_type: int, payload: bytes = b""):
        assert self._ser is not None
        self._ser.write(build_frame(msg_type, payload))

    def _send_raw_pwm(self, left: int, right: int):
        payload = struct.pack("<hh", left, right)  # int16 int16
        self._send(MSG_CMD_PWM_RAW, payload)

    def _wait_for_odom(self, timeout: float) -> bool:
        assert self._reader is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                self._reader.odom_q.get(timeout=0.1)
                return True
            except queue.Empty:
                continue
        return False

    def _drain_odom(self):
        assert self._reader is not None
        try:
            while True:
                self._reader.odom_q.get_nowait()
        except queue.Empty:
            pass

    # ── PWM → velocity measurement ─────────────────────────────────────

    def measure_point(self, pwm: int) -> dict:
        """Drive both wheels at `pwm`, wait for settling, then average velocity.

        Returns a dict suitable for the CSV writer."""
        assert self._reader is not None
        # Start the drive
        self._send_raw_pwm(pwm, pwm)
        # Settle — discard any samples from the transient
        time.sleep(self.settle_s)
        self._drain_odom()

        # Collect samples over the sample window.
        samples: list[tuple[float, float]] = []  # (v_left, v_right)
        t_start = time.monotonic()
        while time.monotonic() - t_start < self.sample_s:
            # Refresh raw PWM command so the firmware watchdog doesn't time out
            self._send_raw_pwm(pwm, pwm)
            try:
                s = self._reader.odom_q.get(timeout=0.1)
            except queue.Empty:
                continue
            # Decompose linear + angular → per-wheel velocity (firmware frame).
            #   v_linear  = (v_left + v_right) / 2
            #   v_angular = (v_right - v_left) / wheel_sep
            # ⇒ v_left  = v_linear - v_angular * wheel_sep / 2
            #   v_right = v_linear + v_angular * wheel_sep / 2
            half_sep = self.wheel_sep / 2.0
            v_left = s.v_linear - s.v_angular * half_sep
            v_right = s.v_linear + s.v_angular * half_sep
            samples.append((v_left, v_right))
        t_elapsed = time.monotonic() - t_start

        # Release drive before returning
        self._send_raw_pwm(0, 0)

        if not samples:
            return dict(pwm=pwm, v_left_mps=float("nan"), v_right_mps=float("nan"),
                        v_left_std=float("nan"), v_right_std=float("nan"),
                        n_samples=0, dt_elapsed_s=t_elapsed)

        lefts = [s[0] for s in samples]
        rights = [s[1] for s in samples]
        return dict(
            pwm=pwm,
            v_left_mps=statistics.fmean(lefts),
            v_right_mps=statistics.fmean(rights),
            v_left_std=(statistics.pstdev(lefts) if len(lefts) > 1 else 0.0),
            v_right_std=(statistics.pstdev(rights) if len(rights) > 1 else 0.0),
            n_samples=len(samples),
            dt_elapsed_s=t_elapsed,
        )


# ────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Motor characterization via direct COBS binary serial.")
    ap.add_argument("--port", default="/dev/esp32_motor",
                    help="Serial port (default: /dev/esp32_motor)")
    ap.add_argument("--out", default="motor_sweep.csv",
                    help="Output CSV path (default: motor_sweep.csv)")
    ap.add_argument("--min", type=int, default=0,
                    help="Minimum PWM magnitude to sweep (default: 0)")
    ap.add_argument("--max", type=int, default=255,
                    help="Maximum PWM magnitude to sweep (default: 255)")
    ap.add_argument("--step", type=int, default=5,
                    help="PWM step size (default: 5)")
    ap.add_argument("--direction", choices=("fwd", "rev", "both"),
                    default="both", help="Direction(s) to sweep (default: both)")
    ap.add_argument("--settle", type=float, default=0.7,
                    help="Seconds to settle before averaging (default: 0.7)")
    ap.add_argument("--sample", type=float, default=0.8,
                    help="Seconds to average over (default: 0.8)")
    ap.add_argument("--rest", type=float, default=0.3,
                    help="Seconds of rest between points (default: 0.3)")
    ap.add_argument("--wheel-sep", type=float, default=WHEEL_SEPARATION,
                    help=f"Wheel separation m (default: {WHEEL_SEPARATION})")
    args = ap.parse_args()

    if args.min < 0 or args.max > 255 or args.min > args.max or args.step <= 0:
        sys.exit("ERROR: invalid sweep range")

    # Build the PWM schedule
    magnitudes = list(range(args.min, args.max + 1, args.step))
    if args.max not in magnitudes:
        magnitudes.append(args.max)
    schedule: list[tuple[int, str]] = []
    if args.direction in ("fwd", "both"):
        schedule += [(+m, "fwd") for m in magnitudes]
    if args.direction in ("rev", "both"):
        # Do reverse high→low so we finish near zero (graceful wind-down)
        schedule += [(-m, "rev") for m in magnitudes]

    print(f"Characterization plan: {len(schedule)} points "
          f"({args.min}..{args.max}, step {args.step}, dir={args.direction})")
    print(f"Per-point: {args.settle:.1f}s settle + {args.sample:.1f}s sample + "
          f"{args.rest:.1f}s rest")
    estimated_s = len(schedule) * (args.settle + args.sample + args.rest)
    print(f"Estimated total duration: {estimated_s:.0f}s "
          f"(~{estimated_s / 60:.1f} min)")

    results = []
    try:
        with Characterizer(args.port, args.settle, args.sample,
                           args.wheel_sep) as c:
            for i, (pwm, direction) in enumerate(schedule, 1):
                print(f"  [{i:3d}/{len(schedule)}] pwm={pwm:+4d} ({direction})…",
                      end="", flush=True)
                r = c.measure_point(pwm)
                r["direction"] = direction
                results.append(r)
                print(f" v_l={r['v_left_mps']:+.3f}  v_r={r['v_right_mps']:+.3f}  "
                      f"(n={r['n_samples']})")
                time.sleep(args.rest)
    except KeyboardInterrupt:
        print("\n[interrupted] Saving partial results…")

    # Write CSV
    cols = ["pwm", "direction", "v_left_mps", "v_right_mps",
            "v_left_std", "v_right_std", "n_samples", "dt_elapsed_s"]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in results:
            w.writerow({k: r.get(k, "") for k in cols})
    print(f"Wrote {len(results)} rows to {args.out}")


if __name__ == "__main__":
    main()
