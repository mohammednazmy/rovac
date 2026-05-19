# ROVAC — Official TODO / Backlog

**Single source of truth for outstanding ROVAC work.** This file is tracked in git and
lives at the repo root so every machine and every future Claude Code session can find it.

_Last consolidated: 2026-05-18 (full sweep of code + docs for forgotten TODOs)._

### How to use this file
- This is the **top-level backlog**. Large multi-phase projects (v2 / v3 chassis,
  super-vacuum) keep their detailed step checklists in their own `docs/` folders —
  this file links to them rather than duplicating them.
- When something is finished, delete it or move it to **Done** with a date.
- Asked "what's on the TODO list?" — a session should read this file.

---

## Near-term — active robot (ROVAC v1 tank)

- [ ] **Front ultrasonic `min_valid` retune.** The front HC-SR04 was remounted at 76 mm
  (was ~40 mm); geometric floor-bounce shifts from ~14 cm out to ~27 cm, so
  `MIN_VALID["front"] = 0.13` in `scripts/obstacle_avoidance_node.py` is stale. Needs an
  empirical measurement over clear floor on the real robot. _Planned with stereo calibration._

- [ ] **Stereo camera Phase 3 — calibration.** `rovac_stereo_camera` `camera_info`
  (`config/stereo_left.yaml`, `stereo_right.yaml`) is placeholder — guessed focal length,
  zero distortion, assumed 60 mm baseline. Run intrinsic + extrinsic calibration.
  Phases 1–2 (mount, 30 fps, lag/quality) are done.

- [ ] **B3 — quadratic / piecewise motor feed-forward.** Linear FF undershoots ~15% at
  0.30 m/s. Deferred — needs a 6–8 m clear corridor for an extended on-ground PWM sweep.
  Full detail in **B3 detail** below.

- [ ] **Phase-3 motor-control feature tuning.** Kickstart, gyro-yaw outer loop, turn
  kp-boost, stall FF boost, and yaw-rate FF are all coded in
  `hardware/esp32_motor_wireless/main/motor_control.c` but sit at no-op defaults in
  `motor_params.h`. Tune once the chassis/battery config is final.

- [ ] **Raise `yaw_rate_ff` after the final battery is installed.** Capped at 10 due to
  5 A adapter OCP risk; can likely reach 20–25 with the surge-rated battery
  (`docs/guides/motor_tuning.md`).

## Cleanup / housekeeping

- [ ] **`tank_description` package metadata.** `package.xml` / `setup.py` still have
  `license = TODO` and a placeholder maintainer. Set real values.

- [ ] **Delete `hardware/esp32_gateway/`.** Gitignored micro-ROS-era code; left in place
  during the 2026-05-18 archival because relocating it would un-ignore its build
  artifacts. It is not in the repo — `rm -rf` it locally when convenient.

## Major projects (detailed checklists in their own docs)

- [ ] **v2 Chassis Migration** — Neato D5 donor. Planned, not started, and **needs
  re-scoping**: v2 was premised on a vacuum subsystem (8× Delta blower motors), which
  was retired 2026-05-17. Sections of `docs/v2_chassis_migration/` now carry a
  `> NOTE: v2 scope under revision` marker — decide v2's purpose before proceeding.

- [ ] **v3 Custom 3D-Printed Chassis** — round 250 mm platform. CAD in progress;
  Iter-4 print-prep (split STLs + Bambu project) and first-print fitment validation
  pending. See `rovac_v3/`.

## Needs a decision

- [ ] **`robot_mcp_server/` direction.** Large sub-project that is mostly stubbed /
  emulated — thermal camera, RL/DL path planning, object recognition, and system-health
  monitoring all return simulated or placeholder data. Decide: finish it, scope it down
  to what is real, or shelve it. Not worth piecemeal stub-filling without that call.

## Hardware measurement tasks

- [ ] Salvaged-battery robot integration after first charge —
  `hardware/hiyiton-b6-v2-charger/BATTERY_INVENTORY.md`.

---

## B3 detail — quadratic / piecewise feed-forward

**Status:** deferred 2026-04-22 — requires an extended-range on-ground sweep.

**Why:** the current linear FF (`ff_offset=163, ff_scale=140`) is calibrated against an
on-ground sweep of PWM 0–180 (0–0.14 m/s). It matches well at 0.15 m/s but *undershoots
by ~15%* at 0.30 m/s — the real loaded PWM→velocity curve is mildly nonlinear (slope
flattens at higher PWM).

**What's needed:**
1. An on-ground PWM sweep covering PWM 180–255 (~0.14 up to ~0.30 m/s). Requires at least
   **6–8 m of clear corridor**. Current test area is too small.
2. Fit a quadratic `pwm = ff_offset + v·ff_scale + v²·ff_quad`, or a two-slope piecewise
   linear. Add protocol param `PARAM_FF_QUAD` (0x12), default 0 to preserve linear behavior.
3. Re-run `tools/step_response.py --target 0.30` — the ±15% steady-state error should
   drop below 5%.

**When to revisit:** before the first Nav2 deployment commanding sustained 0.25+ m/s; or
when the final secondary battery is installed; or if SLAM/path-following shows
speed-dependent tracking error.

**Files involved:** `common/serial_protocol.h` (add `PARAM_FF_QUAD`, bump `PARAM_ID_MAX`),
`hardware/esp32_motor_wireless/main/motor_params.{h,c}` (add `ff_quad`),
`pid_controller.c` (extend `ff_term`), `tools/motor_params_cli.py`, `pid_tune_live.py`,
`tools/analyze_sweep.py`, `docs/guides/motor_tuning.md`.

**Reference bench data already in repo:** `bench_data/sweep_free_phase3_1.csv`
(wheels-free, full PWM range — already shows the nonlinearity),
`bench_data/sweep_onground_phase3_2.csv` (on-ground PWM 0–180 — insufficient range).

---

## Done

- 2026-05-18 — Documentation realignment: ROVAC re-described as a general-purpose
  autonomous robot (vacuum framing retired); core, architecture, guide, hardware, and
  sub-project docs swept to current reality; retired hardware archived to
  `archive/legacy_hardware/`; super-vacuum experiments archived.
- 2026-05-18 — Established this TODO.md as the tracked single source of truth.
- 2026-05-18 — URDF front/rear fix: `laser_joint` rotated 180° (the RPLIDAR was mounted
  facing the rear after the front/rear redefinition, so `/scan` rendered flipped).
- 2026-05-18 — Sensor-hub frames (`us_*`, `cliff_*`) added to the URDF from measured
  mount positions; `obstacle_avoidance_node.py` now reads sensor poses from TF.
- 2026-05-18 — Robot dimensions, IMU, rear-stack, and stereo-camera offsets updated in
  the URDF from physical measurements.
