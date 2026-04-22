#!/usr/bin/env python3
"""
analyze_sweep — Derive per-wheel per-direction ff_offset and ff_scale from
a motor_characterization.py CSV sweep.

The firmware's feed-forward model is:
    FF_pwm = sign(v_target) * (ff_offset + |v_target| * ff_scale)

So for the motor to achieve a given target velocity, it needs PWM roughly
equal to that formula. Inverted for characterization:

    Given (pwm, measured_velocity) samples, find:
      - Stiction break-out pwm:  smallest |pwm| where |velocity| > epsilon
      - ff_scale:                slope of pwm-vs-|v| in the linear region
      - ff_offset:               pwm-intercept when extrapolating the
                                 linear fit back to v=0 (captures the
                                 "dead zone" above which the motor starts
                                 accepting proportional control)

Usage:
    python3 tools/analyze_sweep.py bench_data/sweep_free_phase3_1.csv
"""

import csv
import statistics
import sys
from dataclasses import dataclass


MOVE_EPSILON_MPS = 0.010  # anything below this we call "not moving"
# When deriving ff_offset we skip the lowest N points above break-out because
# the low end of the curve is nonlinear (motor starting to move but not yet
# on the clean linear portion). The last ~60% of samples gives the cleanest
# linear fit.
LINEAR_REGION_START_FRAC = 0.40   # start fit at this fraction of range above break-out


@dataclass
class WheelFit:
    wheel: str            # "left" or "right"
    direction: str        # "fwd" or "rev"
    n_points: int
    stiction_pwm: int     # first |pwm| at which wheel started moving
    ff_scale: float       # slope (PWM per m/s)
    ff_offset: float      # extrapolated PWM-intercept (the dead-zone height)
    max_velocity: float   # achieved at |pwm|=255
    r_squared: float      # linear fit quality


def load_rows(path):
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            r["pwm"] = int(r["pwm"])
            r["v_left"] = float(r["v_left_mps"])
            r["v_right"] = float(r["v_right_mps"])
            rows.append(r)
    return rows


def linfit(xs, ys):
    """Least-squares fit y = m*x + b. Returns (m, b, r_squared)."""
    n = len(xs)
    if n < 2:
        return 0.0, 0.0, 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0, 0.0, 0.0
    m = num / den
    b = my - m * mx
    ss_res = sum((y - (m * x + b)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return m, b, r2


def fit_wheel_direction(rows, wheel: str, direction: str) -> WheelFit:
    """Extract samples for (wheel, direction), find stiction, fit linear region."""
    v_key = "v_left" if wheel == "left" else "v_right"
    samples = []  # list of (|pwm|, |v|)
    for r in rows:
        if r["direction"] != direction:
            continue
        p = abs(r["pwm"])
        v = abs(r[v_key])
        samples.append((p, v))
    samples.sort()

    # Find stiction break-out: first point where v > epsilon
    stiction = None
    for p, v in samples:
        if v > MOVE_EPSILON_MPS:
            stiction = p
            break
    if stiction is None:
        # Never moved — abort
        return WheelFit(wheel, direction, len(samples), stiction_pwm=255,
                        ff_scale=0.0, ff_offset=255.0, max_velocity=0.0, r_squared=0.0)

    # Linear region: take samples from LINEAR_REGION_START_FRAC of way up to max
    max_pwm = samples[-1][0]
    linear_start = stiction + int((max_pwm - stiction) * LINEAR_REGION_START_FRAC)
    linear_samples = [(p, v) for p, v in samples if p >= linear_start]

    # Fit pwm = ff_scale * v + ff_offset  (i.e. invert: x=v, y=pwm)
    xs = [v for _, v in linear_samples]
    ys = [float(p) for p, _ in linear_samples]
    m, b, r2 = linfit(xs, ys)

    # Max velocity at pwm=255
    max_v_samples = [v for p, v in samples if p >= 250]
    max_v = statistics.fmean(max_v_samples) if max_v_samples else samples[-1][1]

    return WheelFit(
        wheel=wheel, direction=direction,
        n_points=len(samples),
        stiction_pwm=stiction,
        ff_scale=m, ff_offset=b,
        max_velocity=max_v, r_squared=r2,
    )


def print_fit(f: WheelFit):
    print(f"  {f.wheel:5} {f.direction:3}: "
          f"stiction @ pwm={f.stiction_pwm:3d}  "
          f"fit ff_offset={f.ff_offset:6.1f}  ff_scale={f.ff_scale:6.1f}  "
          f"R²={f.r_squared:.3f}  max_v={f.max_velocity:.3f} m/s")


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: analyze_sweep.py <sweep.csv>")

    rows = load_rows(sys.argv[1])
    print(f"Loaded {len(rows)} samples from {sys.argv[1]}\n")

    fits = []
    for wheel in ("left", "right"):
        for direction in ("fwd", "rev"):
            fits.append(fit_wheel_direction(rows, wheel, direction))

    print("Per-wheel per-direction linear fits:")
    print("  wheel dir:   stiction   ff_offset   ff_scale   R²    max_v")
    print("  " + "─" * 66)
    for f in fits:
        print_fit(f)

    print("\nInterpretation:")
    # Characterize asymmetry
    stictions = {(f.wheel, f.direction): f.stiction_pwm for f in fits}
    l_avg = (stictions[("left","fwd")] + stictions[("left","rev")]) / 2
    r_avg = (stictions[("right","fwd")] + stictions[("right","rev")]) / 2
    print(f"  Mean stiction pwm:  left={l_avg:.0f}   right={r_avg:.0f}   delta={l_avg-r_avg:+.0f}")

    max_vs = {(f.wheel, f.direction): f.max_velocity for f in fits}
    l_max = (max_vs[("left","fwd")] + max_vs[("left","rev")]) / 2
    r_max = (max_vs[("right","fwd")] + max_vs[("right","rev")]) / 2
    print(f"  Mean max velocity:  left={l_max:.3f} m/s   right={r_max:.3f} m/s   delta={r_max-l_max:+.3f}")

    print("\nRecommended motor_params values (wheels-free baseline):")
    print("  ── For each wheel/direction we write the empirical ff_offset,")
    print("     rounded up slightly so the FF reliably exceeds actual stiction ──")
    for f in fits:
        name = f"ff_offset_{f.wheel}_{f.direction}"
        # Round up to nearest integer, bias slightly above the fit
        # to reliably exceed the measured stiction break-out point.
        recommended = max(int(round(f.ff_offset)) + 3, f.stiction_pwm + 3)
        print(f"    {name:<28} = {recommended}   (fit says {f.ff_offset:.1f}, stiction break {f.stiction_pwm})")

    # ff_scale: take the median across all four fits; slopes should agree up
    # to small motor-to-motor variation.
    scales = [f.ff_scale for f in fits]
    median_scale = statistics.median(scales)
    print(f"    ff_scale                     = {median_scale:.0f}   (median of 4 fits: "
          f"{[round(s) for s in scales]})")


if __name__ == "__main__":
    main()
