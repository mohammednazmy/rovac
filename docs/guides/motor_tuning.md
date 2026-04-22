# Motor Tuning Guide

How to characterize and retune the ESP32 motor controller when the
chassis changes (weight, surface, battery, worn treads). Everything here
assumes the Phase 0-4 tooling in the repo.

## What this guide covers

- What's tuned (the 15 parameters in `motor_params`)
- When to retune
- Step-by-step retune procedure using the bench tools
- Regression baselines to detect drift
- Troubleshooting common failures

---

## Quick reference — canonical NVS calibration (as of 2026-04-22)

Robot configuration at calibration time:
- **Weight**: 5.2 kg (chassis + vacuum; no secondary battery mounted)
- **Wheel separation**: 0.2005 m (track centerline to centerline, physically measured)
- **Wheel radius**: 0.032 m (rolling radius, matches JGB37-520R60 spec)
- **Power**: 12 V DC 5 A switching adapter (wall, not final battery)

Tuned values stored in NVS:

| Param                   | Value  | Role                                            |
|-------------------------|--------|-------------------------------------------------|
| `kp`                    | 25     | PID proportional gain                           |
| `ki`                    | 200    | PID integral gain                               |
| `kd`                    | 6      | PID derivative gain                             |
| `ff_scale`              | 140    | Feed-forward PWM per (m/s) — loaded mid-range   |
| `ff_offset_left_fwd`    | 163    | Stiction PWM, left motor forward                |
| `ff_offset_left_rev`    | 163    | Stiction PWM, left motor reverse                |
| `ff_offset_right_fwd`   | 163    | Stiction PWM, right motor forward               |
| `ff_offset_right_rev`   | 163    | Stiction PWM, right motor reverse               |
| `max_integral_pwm`      | 150    | Cap on I-term PWM contribution                  |
| `max_output`            | 255    | Max PID output magnitude                        |
| `stall_ff_boost`        | 0      | Disabled — new FF is correct enough             |
| `kickstart_pwm` / `_ms` | 0 / 0  | Disabled — not needed                           |
| `turn_kp_boost`         | 1.0    | Disabled — no turn-specific kp boost            |
| `gyro_yaw_kp`           | 0      | Disabled — requires IMU-aware tuning tool       |
| `yaw_rate_ff`           | 10     | Extra FF PWM per rad/s during turn-in-place — tuned with `step_response.py` IMU-aware (B2) |
| `brake_on_stop`         | 0      | 0 = coast (default), 1 = active brake on stop   |

Read the current NVS state on the robot:
```bash
ssh pi@192.168.1.200
sudo systemctl stop rovac-edge-motor-driver
cd ~/robots/rovac && python3 tools/motor_params_cli.py dump
sudo systemctl start rovac-edge-motor-driver
```

---

## When to retune

| Event                                            | Full retune | Step-response check only |
|--------------------------------------------------|-------------|--------------------------|
| Weight changed by >10% (new mount, new battery)  | ✅ yes      |                          |
| Track surface changed (hardwood↔carpet)          | ✅ yes      |                          |
| Wall adapter swapped for a different power spec  | ✅ yes      |                          |
| Motor replacement or brush wear suspected        | ✅ yes      |                          |
| Weeks passed, regression metrics drifted         |             | ✅ yes                   |
| Chassis tweaked (treads re-tensioned, bearings)  |             | ✅ yes                   |

If a step-response check shows >2× drift from regression baseline (below),
escalate to a full retune.

---

## Tools

All under `tools/` in the repo.

| Tool                            | Purpose                                         | Bench need    |
|---------------------------------|-------------------------------------------------|---------------|
| `motor_params_cli.py`           | get/set/save/load/reset motor params            | driver stopped|
| `motor_characterization.py`     | Raw-PWM sweep → CSV of PWM vs velocity          | driver stopped|
| `analyze_sweep.py`              | Fit stiction + ff_scale from a sweep CSV        | host only     |
| `step_response.py`              | Send velocity step, measure rise/overshoot/ss   | driver stopped|
| `pid_tune_live.py`              | Interactive curses TUI for live param editing   | driver stopped|

"driver stopped" = `sudo systemctl stop rovac-edge-motor-driver` (the Pi
motor driver node owns the serial port normally; these tools take direct
control).

---

## Full retune procedure

### Setup

Pre-flight check:
- Verify chassis geometry (wheel separation, wheel radius) hasn't drifted
  from `hardware/esp32_motor_wireless/main/odometry.h`. If it has,
  update the constant and reflash firmware before tuning (the whole
  kinematic chain depends on this).
- Measure and note total robot weight. Record it in the retune notes.
- Back up current NVS:
  ```bash
  ssh pi@192.168.1.200 'cd ~/robots/rovac && python3 tools/motor_params_cli.py dump > /tmp/nvs_pre_retune.txt'
  ```

### Phase A — Wheels-free sweep (motor physics baseline)

Place the robot on **blocks** so both treads spin without touching ground.
Purpose: confirm the motors themselves are symmetric and measure the
linear-region slope (`ff_scale`).

```bash
ssh pi@192.168.1.200
sudo systemctl stop rovac-edge-motor-driver
cd ~/robots/rovac
python3 tools/motor_characterization.py \
    --direction both --min 0 --max 255 --step 5 \
    --out ~/bench/sweep_free.csv

# Copy to Mac and analyze
scp pi@192.168.1.200:~/bench/sweep_free.csv bench_data/
python3 tools/analyze_sweep.py bench_data/sweep_free.csv
```

Expected output: per-wheel stiction in the 120-145 PWM range, max velocity
~0.58 m/s at PWM 255, linear fits with R² > 0.98. If left and right are
wildly asymmetric (>20 PWM stiction difference) — investigate: motor
wiring, bearing drag, gearbox.

Apply the measured `ff_scale` only if the fits are confident:
```bash
python3 tools/motor_params_cli.py set ff_scale <measured>  # e.g. 208
```

### Phase B — On-ground sweep (loaded stiction)

Place the robot **on the floor** with the path clear of at least 3 m
ahead (robot will drive forward then reverse during the sweep).

```bash
python3 tools/motor_characterization.py \
    --direction both --min 0 --max 180 --step 10 \
    --settle 0.4 --sample 0.4 --rest 0.2 \
    --out ~/bench/sweep_onground.csv
```

Cap is 180 PWM (not 255) to keep the robot in the test area. Full sweep
takes ~80 seconds. Analyze:
```bash
scp pi@192.168.1.200:~/bench/sweep_onground.csv bench_data/
python3 tools/analyze_sweep.py bench_data/sweep_onground.csv
```

Find the measured stiction PWM — typically 20-40 PWM higher than
wheels-free. Set `ff_offset_*_*` to `(measured_stiction) + 3` for a
small safety margin.

```bash
# Example — on-ground sweep found stiction at 160 PWM, so:
python3 tools/motor_params_cli.py set ff_offset_left_fwd   163
python3 tools/motor_params_cli.py set ff_offset_left_rev   163
python3 tools/motor_params_cli.py set ff_offset_right_fwd  163
python3 tools/motor_params_cli.py set ff_offset_right_rev  163
```

### Phase C — Closed-loop PID dial-in

Use `step_response.py` iteratively. The tool sends a single velocity
step and reports rise/overshoot/settling/ss_error/smoothness metrics.

Start with the canonical 0.15 m/s linear step:

```bash
python3 tools/step_response.py --target 0.15 --duration 3.0 --tag baseline
```

Adjust ONE parameter at a time, re-test, compare. Typical dials in order
of preference:

1. **`ff_scale`** — if steady-state error is persistently large (>10%),
   the FF slope is wrong for the operating range. Lower `ff_scale` if
   overshooting steady-state; raise if undershooting. Start with the
   measured slope and walk 10-20% at a time.
2. **`kd`** — raise if overshoot is high and smoothness is good. Typical
   range 3-10.
3. **`ki`** — raise if steady-state error converges slowly. Typical
   range 100-300. Very high `ki` can cause wind-up → overshoot.
4. **`kp`** — lower if rise is too aggressive and overshoots. Typical
   range 15-35. Most chassis don't need `kp` above 30.

After each change, re-run the step test and record the metrics in a
changelog. Once the 0.15 m/s response is clean, validate at 0.05 and
0.30 m/s:
```bash
python3 tools/step_response.py --target 0.05 --duration 3.0 --tag check_low
python3 tools/step_response.py --target 0.30 --duration 3.0 --tag check_high
```

Then angular:
```bash
python3 tools/step_response.py --angular 2.0 --duration 3.0 --tag ang_canonical
python3 tools/step_response.py --angular -2.0 --duration 3.0 --tag ang_rev
```

Note: angular step-response *via /odom* may show apparent overshoot that
isn't real body rotation (tread scrub — see the IMU-aware tool for
proper angular calibration).

### Phase D — Save to NVS

Once metrics are within regression targets (next section):
```bash
python3 tools/motor_params_cli.py save
```

Restart the motor driver and re-verify:
```bash
sudo systemctl start rovac-edge-motor-driver
python3 tools/step_response.py --target 0.15 --duration 3.0 --tag post_save
# Should match the last pre-save test
```

Commit the change:
```bash
# On Mac
cd ~/robots/rovac
git add bench_data/sweep_*.csv bench_data/step_*.csv
# update docs/guides/motor_tuning.md if baseline changed
git commit -m "Motor retune $(date +%Y-%m-%d) — <reason>"
git push
```

---

## Regression baseline (canonical metrics)

Measured on 2026-04-22 against the robot configuration listed at top.
Re-measure periodically; if current metrics deviate by > ±50%, do a full
retune.

| Test            | Target    | Rise 90%  | Overshoot | SS error   | Smoothness |
|-----------------|-----------|-----------|-----------|------------|------------|
| Linear 0.15 m/s | 0.15 m/s  | 0.40 s    | 13.7 %    | -2.2 %     | 0.002 m/s  |
| Linear 0.30 m/s | 0.30 m/s  | 0.50 s    | 0.3 %     | +15 %*     | 0.02 m/s   |
| Linear 0.05 m/s | 0.05 m/s  | 0.25 s    | 87 %*     | -26 %      | 0.0035 m/s |
| Angular 2.0 rad/s | 2.0 rad/s | 0.30 s | 75 %**    | -55 %**    | 0.05 rad/s |

\* Known limitation: linear FF (`ff_scale=140`) is matched to the
0.15 m/s operating point; 0.30 m/s undershoots and 0.05 m/s overshoots
because the true motor curve is mildly nonlinear. Fix with a piecewise
FF (B3 in the improvement plan) when needed.

\** Angular metrics are encoder-derived and subject to tread-scrub
artifact during turn-in-place. The IMU-aware step_response.py (B2 —
2026-04-22) now reports both encoder-derived AND gyro-based metrics.
At 2.0 rad/s commanded with the current NVS tuning, true body rotation
peaks at ~1.83 rad/s (91% of commanded) and settles at ~1.16 rad/s
(58% of commanded). Encoder-derived figures overstate body rotation
by +90-140% due to track scrub.

---

## Troubleshooting

### "Robot won't move at all under load"

Likely causes:
- `ff_offset` is below actual loaded stiction. Re-run Phase B.
- Stall watchdog firing pegs output at 255 then back — check with
  `sudo journalctl -u rovac-edge-motor-driver -n 50` for `STL-L` /
  `STL-R` markers in the PID debug log.
- Power supply sagging under load. Verify 12V ± 5% at full drive with
  a multimeter.

### "Steady-state velocity drifts higher than commanded"

- `ff_scale` too high. Lower in 10-20% increments, re-test.
- Or the integral is being clamped by `max_integral_pwm`. Check the PID
  debug log; raise `max_integral_pwm` if I-term is pegged.

### "Robot stutters / oscillates at low speed"

- This was the Phase 3.3 bug: stall watchdog firing on small target
  velocities. Already fixed in firmware (`STALL_TGT_MIN=0.08`,
  `STALL_MEAS_EPS=0.015`). If it recurs, verify firmware is current
  (`git log -1 --oneline` on Pi).
- Could also be `kd` too high — try reducing.

### "Angular reported by /odom doesn't match the body I see rotating"

This is expected on tread drives — encoder-derived angular overestimates
actual body rotation because the treads scrub (slip sideways) during
turn-in-place. Use `/imu/data` (gyro z-axis) for true body rotation, or
the forthcoming IMU-aware step response tool.

### "Motors suddenly stopped responding after aggressive tuning"

Symptom: firmware logs show PID commanding growing PWM (e.g., `pwm=-230/-230 STL-L STL-R`), encoders read 0, robot doesn't move. `/odom` and IMU data still stream normally.

Root cause: the Maker ESP32 has two power rails — **USB from the Pi powers the ESP32 logic + sensors, but the 12V barrel jack powers the TB67H450FNG motor drivers**. If the 12V rail dies, the chip stays alive and keeps trying to drive motors, but the H-bridges have no supply.

The 12V 5A adapter can latch into over-current protection (OCP) if both motors are driven to PWM 255 simultaneously for an extended period — e.g., during turn-in-place at high `yaw_rate_ff` combined with high angular targets.

Fix: unplug the 12V adapter from the wall for 10 seconds, then reconnect. OCP self-resets. Motors return immediately.

Prevention: keep `yaw_rate_ff × max_angular_target` below ~75 PWM of FF bias. With current tuning, `yaw_rate_ff = 15` paired with max teleop angular 6.5 rad/s gives 97 PWM — still risky. `yaw_rate_ff = 10` is the safer ceiling while using the 5A adapter. When the final secondary battery is installed (rated for 15-30A surge), this limit relaxes significantly.

### Yaw-rate FF + IMU-aware tuning observations (2026-04-22 bench)

Initial encoder-based measurements were misleading. After `step_response.py`
was extended to also read `/imu/data` (gyro z-axis), the TRUE body rotation
rate became visible, revealing a ~142% scrub artifact in encoder-derived
angular velocity during turn-in-place.

Commanded 2.0 rad/s angular, compared by measurement source:

| `yaw_rate_ff` | ENC peak   | GYRO peak (truth) | GYRO SS err | Scrub |
|---------------|-----------:|------------------:|------------:|------:|
| 0             | 3.23 rad/s | **1.33 rad/s** (67% of cmd) | +84 % | +142 % |
| 10            | 3.63 rad/s | **1.83 rad/s** (91% of cmd) | +42 % |  +98 % |
| 15            | 3.82 rad/s | **2.01 rad/s** (100% of cmd peak!) | +42 % |  +90 % |
| 20            | 3.51 rad/s | — (tested pre-IMU)           | — | — |
| 30            | *OCP latch — motor rail lost* | | | |

Key insights:
- **Real body rotation caps near 1.5–2.0 rad/s** under load. Commanding
  above that with the default tuning just wastes motor power as tread scrub
  without producing faster rotation.
- **Peak vs steady-state diverge**: `yaw_rate_ff=15` briefly hits commanded
  at peak, but body settles ~58% of commanded during sustained turn. This
  is physical — tread scrub reaches equilibrium.
- **Encoder-derived "overshoot" is mostly scrub**, not real overshoot. A
  60-80% encoder overshoot usually means the body is actually undershooting.

**Current NVS**: `yaw_rate_ff = 10` — 91% of commanded at peak, no OCP risk.
Pushing to 15 gives peak-hits-target but requires caution at high teleop
rates (97 PWM of bias at 6.5 rad/s cmd → near saturation).

With the final secondary battery (larger current budget), yaw_rate_ff can
likely be raised to 20-25 safely.

### "NVS is corrupted / values loaded as default on every boot"

- Check `dmesg` on Pi for ESP32 NVS erase messages
- Try a factory reset: `python3 tools/motor_params_cli.py reset`, then
  re-apply your calibration and `save` again.
- Last resort: reflash firmware with a cleared NVS partition
  (`idf.py erase-flash && idf.py flash` — will lose all calibration).

### "Motor driver service flapping / won't stay up"

- USB serial cable may be intermittent — see CLAUDE.md
  "CH340 USB not detected on Pi" section.
- `BindsTo=rovac-edge-motor-driver` means the sensor-hub and mux
  services cycle with the motor driver. If just the motor driver fails,
  replacing the USB cable or the power barrel usually fixes it.

---

## Deferred / future work

### B3 — Piecewise or quadratic FF (⏸ TODO)

**Why deferred**: The current linear FF (`ff_offset + |v| × ff_scale`)
is calibrated against the on-ground sweep of PWM 0–180 (velocities
0–0.14 m/s). It matches well at 0.15 m/s but **undershoots by ~15% at
0.30 m/s** because the real loaded PWM→velocity curve is mildly
nonlinear — slope flattens at higher PWM. Calibrating the fix requires
an extended-range PWM 180–255 on-ground sweep (velocities 0.14–0.30
m/s), which needs **6–8 m of clear corridor**. Current test area is
too small.

**What's needed**:
1. On-ground PWM sweep covering PWM 180–255 in a space ≥6 m long.
   Use `motor_characterization.py --min 180 --max 255 --step 5`.
2. Fit either a piecewise-linear (two slopes) or quadratic (`pwm =
   ff_offset + v × ff_scale + v² × ff_quad`) to the combined low- and
   high-range data.
3. Add a new protocol parameter `PARAM_FF_QUAD` (0x12) with default 0
   so existing NVS behavior is preserved. Bump `PARAM_ID_MAX` to 0x12.
4. Update `pid_controller.c` `ff_term` formula: add `v² × ff_quad`.
5. Update tools: `motor_params_cli.py`, `pid_tune_live.py`,
   `analyze_sweep.py` (piecewise fit).
6. Re-run `tools/step_response.py --target 0.30` — SS error should drop
   from +15% to <5%.

**When to revisit**:
- Before first Nav2 deployment that commands sustained 0.25+ m/s, OR
- When the final secondary battery is installed (retune anyway), OR
- If SLAM/path-following shows speed-dependent tracking errors.

**Reference data already in repo**:
- `bench_data/sweep_free_phase3_1.csv` — wheels-free full range (PWM 0-255).
  Already shows nonlinearity: PWM 250 → 0.57 m/s, PWM 180 → 0.40 m/s
  (ratio 1.43 vs linear prediction 1.39). Under load the nonlinearity
  is stronger.
- `bench_data/sweep_onground_phase3_2.csv` — on-ground PWM 0-180 only.

### IMU-aware gyro outer loop retune

`gyro_yaw_kp` is wired up end-to-end (Phase 4 firmware + B2 tool) but
remains at 0 in NVS. Bench data showed body rotation saturates near
1.5-1.8 rad/s regardless of the gain under current load, so no value
improved beyond what `yaw_rate_ff` alone achieves. Revisit when chassis
mass changes (heavier → more scrub → loop may provide value).

---

## Related

- **Firmware defaults**: `hardware/esp32_motor_wireless/main/motor_params.c`
  (`s_defaults` struct) — these are the factory-reset values.
- **Protocol**: `common/serial_protocol.h` — `PARAM_*` IDs and payload
  layout. Don't change IDs across firmware versions (NVS storage is
  keyed on them).
- **Bench data**: `bench_data/` — historical sweep and step CSVs for
  reference.
- **Deferred work**: see "Deferred / future work" section above.
