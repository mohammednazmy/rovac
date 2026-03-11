#!/usr/bin/env python3
"""
Motor Characterization Tool for ROVAC — Direct Serial Access.

Bypasses the ROS2 PID controller entirely. Opens /dev/esp32_motor directly,
sends raw M <left> <right> commands at each duty level, reads encoder ticks,
and computes actual per-wheel velocity. This gives the TRUE motor response
curve, unfiltered by PID.

IMPORTANT: Stop the motor driver service before running:
  sudo systemctl stop rovac-edge-esp32.service

Usage:
  python3 motor_characterization.py
  python3 motor_characterization.py --min-duty 80 --max-duty 255 --step 5
  python3 motor_characterization.py --reverse   # test reverse direction too
"""

import argparse
import math
import sys
import time

import serial

# Must match driver/firmware constants
TICKS_PER_REV = 2640        # 11 PPR × 4 × 60:1
WHEEL_RADIUS = 0.032        # meters
WHEEL_CIRCUMFERENCE = 2.0 * math.pi * WHEEL_RADIUS
SERIAL_PORT = "/dev/esp32_motor"
BAUD = 115200


def ticks_to_mps(ticks, dt):
    """Convert encoder tick delta over dt seconds to m/s."""
    if dt <= 0:
        return 0.0
    revs = ticks / TICKS_PER_REV
    return revs * WHEEL_CIRCUMFERENCE / dt


class MotorCharacterizer:

    def __init__(self, port, baud):
        self.ser = serial.Serial(port, baud, timeout=0.1, dsrdtr=False)
        time.sleep(0.5)  # Let ESP32 settle after DTR

        # Drain any startup data
        self.ser.reset_input_buffer()

        # Identify firmware
        self.ser.write(b"!id\n")
        time.sleep(0.3)
        while self.ser.in_waiting:
            line = self.ser.readline().decode('ascii', errors='replace').strip()
            if line:
                print(f"# Firmware: {line}", file=sys.stderr)

        # Disable firmware dead zone for raw proportional control
        self.ser.write(b"!minduty 0\n")
        time.sleep(0.2)

        # Start encoder streaming at 50 Hz
        self.ser.write(b"!stream 50\n")
        time.sleep(0.2)

        # Reset encoders
        self.ser.write(b"!enc reset\n")
        time.sleep(0.2)
        self.ser.reset_input_buffer()

        # State
        self._prev_left = None
        self._prev_right = None

    def stop(self):
        """Stop motors and close serial."""
        self.ser.write(b"S\n")
        time.sleep(0.1)
        self.ser.write(b"!stream 0\n")
        time.sleep(0.1)
        self.ser.close()

    def set_motors(self, left, right):
        """Send raw M command."""
        self.ser.write(f"M {left} {right}\n".encode())

    def read_encoder_deltas(self, duration, keep_alive_duty=None):
        """Read encoder data for `duration` seconds.

        If keep_alive_duty is set, re-sends M command every 500ms to
        prevent firmware watchdog from stopping motors (1s timeout).

        Returns list of (timestamp, left_delta, right_delta) samples.
        Each sample represents the ticks since the previous encoder report.
        """
        samples = []
        start = time.monotonic()
        last_keepalive = start
        self.ser.reset_input_buffer()

        while time.monotonic() - start < duration:
            # Re-send motor command every 500ms to prevent watchdog
            if keep_alive_duty is not None:
                now_ka = time.monotonic()
                if now_ka - last_keepalive >= 0.5:
                    self.set_motors(keep_alive_duty, keep_alive_duty)
                    last_keepalive = now_ka

            try:
                line = self.ser.readline().decode('ascii', errors='replace').strip()
            except Exception:
                continue

            if not line or not line.startswith('E '):
                continue

            parts = line.split()
            if len(parts) != 3:
                continue

            try:
                left_abs = int(parts[1])
                right_abs = int(parts[2])
            except ValueError:
                continue

            now = time.monotonic()

            if self._prev_left is not None:
                left_delta = left_abs - self._prev_left
                right_delta = right_abs - self._prev_right
                samples.append((now, left_delta, right_delta))

            self._prev_left = left_abs
            self._prev_right = right_abs

        return samples

    def characterize_duty(self, duty, hold_time, settle_time):
        """Run both wheels at `duty` and measure per-wheel velocity.

        Returns dict with velocities and stats.
        """
        # Send motor command
        self.set_motors(duty, duty)

        # Let motors settle (keep sending M to prevent watchdog)
        _ = self.read_encoder_deltas(settle_time, keep_alive_duty=duty)

        # Measure (keep sending M to prevent watchdog)
        samples = self.read_encoder_deltas(hold_time, keep_alive_duty=duty)

        # Stop motors
        self.set_motors(0, 0)

        if not samples:
            return {
                'duty': duty,
                'v_left': 0.0, 'v_right': 0.0,
                'std_left': 0.0, 'std_right': 0.0,
                'n_samples': 0,
            }

        # Compute per-sample velocities
        left_vels = []
        right_vels = []

        for i in range(1, len(samples)):
            dt = samples[i][0] - samples[i-1][0]
            if dt <= 0:
                continue
            left_vels.append(ticks_to_mps(samples[i][1], dt))
            right_vels.append(ticks_to_mps(samples[i][2], dt))

        if not left_vels:
            # Fallback: compute from total ticks over total time
            total_dt = samples[-1][0] - samples[0][0]
            total_left = sum(s[1] for s in samples)
            total_right = sum(s[2] for s in samples)
            return {
                'duty': duty,
                'v_left': ticks_to_mps(total_left, total_dt),
                'v_right': ticks_to_mps(total_right, total_dt),
                'std_left': 0.0, 'std_right': 0.0,
                'n_samples': len(samples),
            }

        avg_left = sum(left_vels) / len(left_vels)
        avg_right = sum(right_vels) / len(right_vels)

        var_left = sum((v - avg_left)**2 for v in left_vels) / max(len(left_vels)-1, 1)
        var_right = sum((v - avg_right)**2 for v in right_vels) / max(len(right_vels)-1, 1)

        return {
            'duty': duty,
            'v_left': avg_left,
            'v_right': avg_right,
            'std_left': math.sqrt(var_left),
            'std_right': math.sqrt(var_right),
            'v_linear': (avg_left + avg_right) / 2.0,
            'v_angular_est': (avg_right - avg_left) / 0.155,
            'asymmetry': avg_right - avg_left,
            'n_samples': len(left_vels),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Motor characterization via direct serial")
    parser.add_argument("--port", default=SERIAL_PORT)
    parser.add_argument("--baud", type=int, default=BAUD)
    parser.add_argument("--min-duty", type=int, default=80,
                        help="Minimum duty to test")
    parser.add_argument("--max-duty", type=int, default=255,
                        help="Maximum duty to test")
    parser.add_argument("--step", type=int, default=5,
                        help="Duty step size")
    parser.add_argument("--hold-time", type=float, default=3.0,
                        help="Measurement time at each duty (s)")
    parser.add_argument("--settle-time", type=float, default=1.0,
                        help="Settle time before measuring (s)")
    parser.add_argument("--reverse", action="store_true",
                        help="Also test reverse direction")
    parser.add_argument("--pause", type=float, default=1.0,
                        help="Pause between duty levels (s)")
    args = parser.parse_args()

    duties = list(range(args.min_duty, args.max_duty + 1, args.step))
    if args.max_duty not in duties:
        duties.append(args.max_duty)

    if args.reverse:
        duties = list(reversed([-d for d in duties])) + duties

    print(f"# Motor Characterization — Direct Serial", file=sys.stderr)
    print(f"# Port: {args.port}, {len(duties)} duty levels to test", file=sys.stderr)
    print(f"# Hold: {args.hold_time}s, Settle: {args.settle_time}s", file=sys.stderr)

    mc = MotorCharacterizer(args.port, args.baud)

    results = []
    try:
        for i, duty in enumerate(duties):
            print(f"  [{i+1}/{len(duties)}] Duty {duty:+4d}...",
                  end="", flush=True, file=sys.stderr)

            r = mc.characterize_duty(duty, args.hold_time, args.settle_time)
            results.append(r)

            print(f" L={r['v_left']:+.4f}±{r['std_left']:.4f}"
                  f" R={r['v_right']:+.4f}±{r['std_right']:.4f}"
                  f" asym={r['asymmetry']:+.4f}"
                  f" ({r['n_samples']} samples)", file=sys.stderr)

            # Pause between levels
            time.sleep(args.pause)

    except KeyboardInterrupt:
        print("\n# Interrupted!", file=sys.stderr)
    finally:
        mc.stop()

    # Output CSV
    print("\n# Motor Characterization Results")
    print(f"# hold={args.hold_time}s, settle={args.settle_time}s")
    print("# duty,v_left,v_right,std_left,std_right,v_linear,asymmetry,n_samples")
    for r in results:
        v_lin = r.get('v_linear', (r['v_left'] + r['v_right']) / 2.0)
        asym = r.get('asymmetry', r['v_right'] - r['v_left'])
        print(f"{r['duty']},{r['v_left']:.5f},{r['v_right']:.5f},"
              f"{r['std_left']:.5f},{r['std_right']:.5f},"
              f"{v_lin:.5f},{asym:.5f},{r['n_samples']}")

    # Analysis
    print("\n# --- Analysis ---")

    moving = [r for r in results if r['duty'] > 0
              and (abs(r['v_left']) > 0.005 or abs(r['v_right']) > 0.005)]

    # Stiction thresholds
    stiction_left = None
    stiction_right = None
    for r in results:
        if r['duty'] <= 0:
            continue
        if stiction_left is None and abs(r['v_left']) > 0.005:
            stiction_left = r['duty']
        if stiction_right is None and abs(r['v_right']) > 0.005:
            stiction_right = r['duty']

    print(f"# Left wheel stiction: duty={stiction_left}")
    print(f"# Right wheel stiction: duty={stiction_right}")

    # Max speed
    fwd_results = [r for r in results if r['duty'] > 0]
    if fwd_results:
        last = fwd_results[-1]
        print(f"# At duty {last['duty']}: "
              f"L={last['v_left']:.4f} R={last['v_right']:.4f} "
              f"linear={last.get('v_linear', 0):.4f} m/s")

    # Asymmetry
    if moving:
        avg_asym = sum(r['asymmetry'] for r in moving) / len(moving)
        max_asym = max(abs(r['asymmetry']) for r in moving)
        print(f"# Avg asymmetry (R-L): {avg_asym:+.4f} m/s")
        print(f"# Max asymmetry: {max_asym:.4f} m/s")

    # Average oscillation
    if moving:
        avg_std_l = sum(r['std_left'] for r in moving) / len(moving)
        avg_std_r = sum(r['std_right'] for r in moving) / len(moving)
        print(f"# Avg std dev: L={avg_std_l:.4f} R={avg_std_r:.4f} m/s")

    # Linear fit: duty = a * velocity + b (i.e., inverse of motor curve)
    if len(moving) >= 3:
        for side, key in [("Left", "v_left"), ("Right", "v_right"),
                          ("Combined", "v_linear")]:
            duties_m = [float(r['duty']) for r in moving]
            vels = [r.get(key, (r['v_left'] + r['v_right'])/2) for r in moving]
            n = len(duties_m)
            if n < 3:
                continue

            # Fit: duty = ff_scale * vel + ff_offset
            sum_x = sum(vels)
            sum_y = sum(duties_m)
            sum_xy = sum(v * d for v, d in zip(vels, duties_m))
            sum_x2 = sum(v * v for v in vels)
            sum_y2 = sum(d * d for d in duties_m)

            denom_x = n * sum_x2 - sum_x**2
            if denom_x > 0:
                ff_scale = (n * sum_xy - sum_x * sum_y) / denom_x
                ff_offset = (sum_y - ff_scale * sum_x) / n

                # R²
                denom_r = denom_x * (n * sum_y2 - sum_y**2)
                r_sq = ((n * sum_xy - sum_x * sum_y) ** 2 / denom_r
                        if denom_r > 0 else 0)

                max_speed = (255 - ff_offset) / ff_scale if ff_scale > 0 else 0
                print(f"# {side} fit: ff_offset={ff_offset:.1f}, "
                      f"ff_scale={ff_scale:.1f}, R²={r_sq:.4f}, "
                      f"max_speed@255={max_speed:.3f}")

    print(f"\n# {len(results)} duty levels tested")


if __name__ == "__main__":
    main()
