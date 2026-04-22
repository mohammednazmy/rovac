#!/usr/bin/env python3
"""
step_response — Single-shot velocity step-response characterization.

Sends a cmd_vel step for a fixed duration, records the odom response
at 20Hz, and computes the canonical PID tuning metrics:

  * rise_time_90      — seconds to reach 90% of target velocity
  * overshoot_pct     — peak excursion past target, as % of target
  * settling_time     — seconds to enter and stay within ±5% band
  * steady_state_err  — mean error over the last 25% of step
  * smoothness        — stddev of velocity in the settled region

Used to dial kp / ki / kd iteratively. Saves a CSV per run so we can
compare tunings side by side.

REQUIREMENTS:
  Stop motor driver so this tool can own the serial port:
      sudo systemctl stop rovac-edge-motor-driver

USAGE:
  step_response.py --target 0.15 --duration 2.0
  step_response.py --angular 2.0 --duration 2.0     # rotation step
  step_response.py --target 0.15 --tag before_kp50  # tag saved CSV
"""

import argparse
import queue
import struct
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import serial
except ImportError:
    sys.exit("ERROR: pyserial not installed. Run: pip3 install pyserial")


# ────────────────────────────────────────────────────────────────────────
# Protocol (mirrors serial_protocol.h)
# ────────────────────────────────────────────────────────────────────────

SERIAL_BAUD     = 460800
MSG_CMD_VEL     = 0x01
MSG_CMD_ESTOP   = 0x02
MSG_ODOM        = 0x10

WHEEL_SEPARATION = 0.2005   # meters


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    out = bytearray([0]); code_idx = 0; code = 1
    for byte in data:
        if byte == 0:
            out[code_idx] = code; code_idx = len(out); out.append(0); code = 1
        else:
            out.append(byte); code += 1
            if code == 0xFF:
                out[code_idx] = code; code_idx = len(out); out.append(0); code = 1
    out[code_idx] = code
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    out = bytearray(); i = 0
    while i < len(data):
        code = data[i]
        if code == 0: raise ValueError("zero in COBS input")
        i += 1
        for _ in range(code - 1):
            if i >= len(data): break
            out.append(data[i]); i += 1
        if code < 0xFF and i < len(data): out.append(0)
    return bytes(out)


def build_frame(msg_type: int, payload: bytes = b"") -> bytes:
    raw = bytes([msg_type]) + payload
    return cobs_encode(raw + struct.pack("<H", crc16_ccitt(raw))) + b"\x00"


def parse_frame(decoded: bytes):
    if len(decoded) < 3: return None
    dl = len(decoded) - 2
    if crc16_ccitt(decoded[:dl]) != struct.unpack("<H", decoded[dl:])[0]:
        return None
    return decoded[0], decoded[1:dl]


_ODOM_STRUCT = struct.Struct("<Q7f")


@dataclass
class Sample:
    t_mono: float
    v_linear: float
    v_angular: float


class StepRunner:
    def __init__(self, port: str):
        self._ser = serial.Serial(port, SERIAL_BAUD, timeout=0.05)
        time.sleep(0.3)
        self._ser.reset_input_buffer()
        self._q: queue.Queue = queue.Queue()
        self._running = True
        self._t = threading.Thread(target=self._reader, daemon=True)
        self._t.start()

    def close(self):
        self._running = False
        try:
            self._ser.write(build_frame(MSG_CMD_ESTOP))
        except Exception:
            pass
        self._ser.close()

    def _reader(self):
        buf = bytearray()
        while self._running:
            try:
                chunk = self._ser.read(256)
            except serial.SerialException:
                return
            if not chunk: continue
            for b in chunk:
                if b == 0:
                    if buf:
                        try:
                            decoded = cobs_decode(bytes(buf))
                        except ValueError:
                            buf.clear(); continue
                        buf.clear()
                        p = parse_frame(decoded)
                        if p and p[0] == MSG_ODOM and len(p[1]) == _ODOM_STRUCT.size:
                            _ts, _x, _y, _yaw, vl, va, _cx, _cy = _ODOM_STRUCT.unpack(p[1])
                            self._q.put(Sample(time.monotonic(), vl, va))
                else:
                    buf.append(b)

    def send_cmd_vel(self, lin: float, ang: float):
        self._ser.write(build_frame(MSG_CMD_VEL, struct.pack("<ff", lin, ang)))

    def run_step(self, linear: float, angular: float,
                 pre_s: float, step_s: float, post_s: float) -> list[Sample]:
        samples: list[Sample] = []
        t0 = time.monotonic()
        # Drain queue
        try:
            while True: self._q.get_nowait()
        except queue.Empty:
            pass
        # Phase 1: pre (quiet, robot at rest)
        self.send_cmd_vel(0.0, 0.0)
        while time.monotonic() - t0 < pre_s:
            try:
                samples.append(self._q.get(timeout=0.1))
            except queue.Empty:
                pass
            self.send_cmd_vel(0.0, 0.0)
        step_start = time.monotonic()
        # Phase 2: step command (re-issued continuously so watchdog doesn't fire)
        while time.monotonic() - step_start < step_s:
            try:
                samples.append(self._q.get(timeout=0.1))
            except queue.Empty:
                pass
            self.send_cmd_vel(linear, angular)
        step_end = time.monotonic()
        # Phase 3: post (return to zero, robot decelerates)
        while time.monotonic() - step_end < post_s:
            try:
                samples.append(self._q.get(timeout=0.1))
            except queue.Empty:
                pass
            self.send_cmd_vel(0.0, 0.0)
        # Make sample times relative to step start
        for s in samples:
            s.t_mono = s.t_mono - step_start
        return samples


# ────────────────────────────────────────────────────────────────────────
# Metrics
# ────────────────────────────────────────────────────────────────────────

def compute_metrics(samples: list[Sample], target: float, is_angular: bool,
                    step_duration: float) -> dict:
    # Pick the value of interest
    def val(s): return s.v_angular if is_angular else s.v_linear
    sign = 1.0 if target >= 0 else -1.0
    abs_tgt = abs(target)

    step_samples = [s for s in samples if 0.0 <= s.t_mono <= step_duration]
    if not step_samples:
        return {"error": "no step samples"}

    # Rise time: first time |val| reaches 90% of |target| (with correct sign)
    rise_time = None
    for s in step_samples:
        if sign * val(s) >= 0.90 * abs_tgt:
            rise_time = s.t_mono
            break

    # Peak and overshoot (only meaningful if we actually reached target)
    peak_val = max((sign * val(s) for s in step_samples), default=0.0)
    if rise_time is not None and abs_tgt > 0:
        overshoot_pct = max(0.0, (peak_val - abs_tgt) / abs_tgt) * 100.0
    else:
        overshoot_pct = float("nan")

    # Settling time: time after which |val - target| stays below 5% of target
    settling_time = None
    band = 0.05 * abs_tgt
    if abs_tgt > 0:
        # Walk backward: find the LAST time the signal was outside the band
        last_out = None
        for s in step_samples:
            if abs(sign * val(s) - abs_tgt) > band:
                last_out = s.t_mono
        settling_time = last_out if last_out is not None else 0.0

    # Steady-state error: mean over last 25% of step
    tail_start = 0.75 * step_duration
    tail = [sign * val(s) for s in step_samples if s.t_mono >= tail_start]
    if tail:
        mean_tail = sum(tail) / len(tail)
        ss_error = abs_tgt - mean_tail
        # Smoothness = stddev of tail
        if len(tail) > 1:
            m = mean_tail
            smoothness = (sum((x - m) ** 2 for x in tail) / (len(tail) - 1)) ** 0.5
        else:
            smoothness = 0.0
    else:
        ss_error = float("nan")
        smoothness = float("nan")

    return {
        "n_samples": len(step_samples),
        "target": abs_tgt,
        "rise_time_90": rise_time,
        "peak_value": peak_val,
        "overshoot_pct": overshoot_pct,
        "settling_time_5pct": settling_time,
        "steady_state_error": ss_error,
        "smoothness_stddev": smoothness,
    }


def save_csv(samples: list[Sample], path: Path, target: float, is_angular: bool):
    with open(path, "w") as f:
        f.write("t_s,v_linear_mps,v_angular_radps,target\n")
        for s in samples:
            tgt = target if (0.0 <= s.t_mono <= 2.0) else 0.0
            f.write(f"{s.t_mono:.4f},{s.v_linear:.5f},{s.v_angular:.5f},{tgt:.5f}\n")


# ────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Step response characterization")
    ap.add_argument("--port", default="/dev/esp32_motor")
    ap.add_argument("--target", type=float, default=0.15,
                    help="linear velocity target (m/s, default 0.15)")
    ap.add_argument("--angular", type=float, default=0.0,
                    help="angular velocity target (rad/s, overrides linear if set)")
    ap.add_argument("--duration", type=float, default=2.0,
                    help="step duration (seconds, default 2.0)")
    ap.add_argument("--pre", type=float, default=0.5,
                    help="pre-step quiet time (seconds, default 0.5)")
    ap.add_argument("--post", type=float, default=1.0,
                    help="post-step return-to-zero time (seconds, default 1.0)")
    ap.add_argument("--tag", type=str, default="",
                    help="tag for CSV filename (e.g. 'kp25_ki120')")
    ap.add_argument("--outdir", default=None,
                    help="output directory (default: ~/bench)")
    args = ap.parse_args()

    is_angular = args.angular != 0.0
    linear = 0.0 if is_angular else args.target
    angular = args.angular
    target = angular if is_angular else linear
    units = "rad/s" if is_angular else "m/s"

    outdir = Path(args.outdir) if args.outdir else Path.home() / "bench"
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    tag = f"_{args.tag}" if args.tag else ""
    suffix = f"ang{target:+.2f}" if is_angular else f"lin{target:+.3f}"
    out_csv = outdir / f"step_{stamp}_{suffix}{tag}.csv"

    print(f"Step target: {target:+.3f} {units} for {args.duration:.1f}s")
    print(f"Saving CSV: {out_csv}")
    print()

    try:
        r = StepRunner(args.port)
    except serial.SerialException as e:
        sys.exit(f"ERROR: {e}\n"
                 "Stop the motor driver service first:\n"
                 "  sudo systemctl stop rovac-edge-motor-driver")

    try:
        samples = r.run_step(linear, angular, args.pre, args.duration, args.post)
    finally:
        r.close()

    if not samples:
        sys.exit("No odom samples — is the ESP32 responsive?")

    save_csv(samples, out_csv, target, is_angular)

    m = compute_metrics(samples, target, is_angular, args.duration)
    print("Metrics:")
    if "error" in m:
        print(f"  error: {m['error']}")
        return
    print(f"  n_samples               {m['n_samples']}")
    print(f"  target                  {m['target']:.4f} {units}")
    print(f"  peak value              {m['peak_value']:.4f} {units}")
    print(f"  rise_time_90            "
          + (f"{m['rise_time_90']:.3f} s" if m['rise_time_90'] is not None
             else "did not reach 90% of target"))
    print(f"  overshoot               {m['overshoot_pct']:.1f} %")
    print(f"  settling_time_5pct      "
          + (f"{m['settling_time_5pct']:.3f} s" if m['settling_time_5pct'] is not None
             else "never settled"))
    print(f"  steady_state_error      {m['steady_state_error']:.4f} {units}  "
          f"({100.0*m['steady_state_error']/m['target']:+.1f}% of target)")
    print(f"  smoothness (stddev)     {m['smoothness_stddev']:.4f} {units}")


if __name__ == "__main__":
    main()
