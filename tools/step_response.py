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
MSG_IMU         = 0x11

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
# imu_payload_t from serial_protocol.h:
#   uint64_t timestamp_us + 4x float quat + 3x float gyro + 3x float accel = 48 bytes
_IMU_STRUCT = struct.Struct("<Q10f")


@dataclass
class Sample:
    t_mono: float
    v_linear: float     # from ODOM, encoder-derived
    v_angular: float    # from ODOM, encoder-derived
    gyro_z: float = 0.0  # from IMU, true body rotation rate (rad/s)
    gyro_fresh: bool = False  # True if gyro was updated in this cycle


class StepRunner:
    def __init__(self, port: str):
        self._ser = serial.Serial(port, SERIAL_BAUD, timeout=0.05)
        time.sleep(0.3)
        self._ser.reset_input_buffer()
        self._q: queue.Queue = queue.Queue()
        self._latest_gyro_z = 0.0   # updated asynchronously by IMU messages
        self._gyro_fresh = False    # set by IMU handler, cleared by ODOM handler
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
                        if p is None:
                            continue
                        msg_type, payload = p
                        if msg_type == MSG_ODOM and len(payload) == _ODOM_STRUCT.size:
                            _ts, _x, _y, _yaw, vl, va, _cx, _cy = _ODOM_STRUCT.unpack(payload)
                            # Pair the freshest IMU gyro_z with this odom sample.
                            gyro_z = self._latest_gyro_z
                            fresh  = self._gyro_fresh
                            self._gyro_fresh = False
                            self._q.put(Sample(time.monotonic(), vl, va,
                                               gyro_z=gyro_z, gyro_fresh=fresh))
                        elif msg_type == MSG_IMU and len(payload) == _IMU_STRUCT.size:
                            unpacked = _IMU_STRUCT.unpack(payload)
                            # layout: ts_us, qw, qx, qy, qz, gx, gy, gz, ax, ay, az
                            _ts = unpacked[0]
                            _gx = unpacked[5]
                            _gy = unpacked[6]
                            gz_raw = unpacked[7]
                            # BNO055 is mounted face-down (URDF: rpy 3.14159 0 0
                            # around X). In the IMU's native frame +Z is DOWN,
                            # so positive commanded angular (ROS +Z = up, CCW)
                            # shows up as NEGATIVE gyro_z. Negate to put it in
                            # base_link / commanded convention.
                            self._latest_gyro_z = -gz_raw
                            self._gyro_fresh = True
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
                    step_duration: float, use_gyro: bool = False) -> dict:
    # Pick the value of interest. For angular tests with use_gyro=True, we
    # measure against the BNO055 z-axis — the true body rotation rate, not
    # the encoder-derived (scrub-inflated) v_angular.
    if is_angular and use_gyro:
        def val(s): return s.gyro_z
    else:
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


def save_csv(samples: list[Sample], path: Path, target: float, is_angular: bool,
             step_duration: float):
    with open(path, "w") as f:
        f.write("t_s,v_linear_mps,v_angular_radps,gyro_z_radps,target\n")
        for s in samples:
            tgt = target if (0.0 <= s.t_mono <= step_duration) else 0.0
            f.write(f"{s.t_mono:.4f},{s.v_linear:.5f},{s.v_angular:.5f},"
                    f"{s.gyro_z:.5f},{tgt:.5f}\n")


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

    save_csv(samples, out_csv, target, is_angular, args.duration)

    def _print_metrics(tag: str, m: dict):
        print(f"Metrics ({tag}):")
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

    # Primary metric: encoder-derived velocity (linear and angular).
    m_enc = compute_metrics(samples, target, is_angular, args.duration)
    _print_metrics("encoder-derived" if is_angular else "linear", m_enc)

    # For angular tests, ALSO compute metrics against the gyro. This is the
    # truth: encoder-derived v_angular double-counts track scrub, gyro sees
    # actual body rotation.
    if is_angular:
        # Sanity — did we actually receive IMU samples?
        fresh_count = sum(1 for s in samples if s.gyro_fresh)
        if fresh_count == 0:
            print("\nWARNING: no IMU samples received — gyro metrics unavailable.")
        else:
            print()
            m_gyro = compute_metrics(samples, target, is_angular, args.duration,
                                     use_gyro=True)
            _print_metrics("GYRO (true body rotation)", m_gyro)
            # Summarize the encoder-vs-gyro delta — this is the scrub signature.
            if (m_enc.get("peak_value") is not None and
                m_gyro.get("peak_value") is not None and
                abs(m_gyro["peak_value"]) > 0.01):
                scrub_pct = (abs(m_enc["peak_value"]) -
                             abs(m_gyro["peak_value"])) / abs(m_gyro["peak_value"]) * 100.0
                print(f"\nScrub signature: encoder peak overstates gyro peak by "
                      f"{scrub_pct:+.1f}% — track slip during rotation.")


if __name__ == "__main__":
    main()
