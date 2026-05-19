# ROVAC v2 — Conversion Checklist

Step-by-step from "donor chassis arrives" to "v2 robot is navigating." Phased to de-risk the integration.

> NOTE: v2 scope under revision — the vacuum subsystem is retired; vacuum/brushroll/side-brush steps throughout this checklist need re-scoping by the maintainer.

## Phase 0 — Pre-arrival prep

While waiting for hardware (~1 week), do these:

- [ ] Read [neato_d5_internals.md](neato_d5_internals.md) and [decisions.md](decisions.md) to internalize the plan
- [ ] Inventory check (see [shopping_list.md](shopping_list.md) inventory check tasks)
- [ ] Order any low-cost prep parts (M3 hardware, gaskets, wire, JST pins) — long lead time items
- [ ] Verify USB-to-UART cable for connecting Mac to Neato Mini-B port for diagnostics
- [ ] Print the existing OpenSCAD model `rovac_layout_b1_pancake.scad` to PDF or screenshot for reference
- [ ] Set up a clean workspace: bench with anti-static mat, good lighting, multimeter, calipers, masking tape, marker

## Phase 1 — First 30-min inspection (when donor arrives)

**DO NOT disassemble until you've completed every step.** Document everything before changing anything.

### Visual inspection (5 min)
- [ ] Photograph the chassis from all 6 sides
- [ ] Note any obvious shipping damage or missing parts
- [ ] Check that dust cup is included
- [ ] Check that LIDAR turret rotates freely by hand

### Mechanical check (5 min)
- [ ] Both drive wheels rotate freely (no binding)
- [ ] Bumper springs back when pressed
- [ ] Side brush is present (or at least the mount)
- [ ] Brushroll is present and rotates
- [ ] No cracks in chassis at wheel wells

### Power-on test (5 min)
- [ ] Apply 14.4 V from bench supply directly to battery terminals
  - Red wire = positive, black = ground
  - Polarity verified BEFORE applying
- [ ] Press power button — does it boot?
- [ ] Watch for LED activity, listen for LDS spinning up
- [ ] If it boots: great, the seller's "probably the battery" diagnosis is confirmed

### USB diagnostic (10 min)
- [ ] Locate Mini-USB port on side of robot
- [ ] Connect to Mac, find serial device:
  ```bash
  ls /dev/tty.usb*
  ```
- [ ] Connect at 115200 baud:
  ```bash
  screen /dev/tty.usbXXX 115200
  ```
- [ ] Type `Help` to see command list
- [ ] Type `TestMode On` to enter diagnostic mode
- [ ] Run baseline commands and **save output to file**:
  ```
  GetVersion              → record firmware version
  GetCharger              → battery voltage, charge state
  GetAnalogSensors        → all analog readings
  GetDigitalSensors       → bumper, dust-bin, wheel-extended states
  GetMotors LeftWheel RightWheel    → encoder positions (zero baseline)
  ```
- [ ] **Encoder calibration**: rotate one wheel exactly 1 full turn by hand (mark with tape), run `GetMotors` again, record delta. **This is your PPR-per-wheel-revolution measurement.** Repeat for other wheel.
- [ ] Wheel test: `SetMotor lwheeldist 200 rwheeldist 200 speed 100` — confirm wheels move and direction
- [ ] LDS test: `GetLDSScan` — confirm OEM LIDAR alive (one full scan)

### Multimeter probes (5 min — battery disconnected)
- [ ] Continuity-test each bumper microswitch (4 switches)
- [ ] Resistance-check each wheel motor (should read few ohms; identifies dead motors)
- [ ] Resistance-check brushroll motor
- [ ] Resistance-check side brush motor
- [ ] Identify VL6180X breakouts visually (small boards near front bottom edge)
- [ ] Multimeter dock contact bars to identify polarity

**Document everything photographically before removing any cable.**

## Phase 2 — Disassembly

### Photograph and label all cables (15 min)
- [ ] Open bottom panel (4–6 screws, see iFixit guide)
- [ ] Photograph the mainboard with all chip labels visible
- [ ] Photograph every connector going to the mainboard (color, pin count, location)
- [ ] **Label every cable with masking tape:**
  - LEFT_WHEEL, RIGHT_WHEEL
  - BRUSHROLL, SIDE_BRUSH
  - LDS_DATA, LDS_MOTOR
  - BUMPER, CLIFF_LEFT, CLIFF_RIGHT
  - WHEEL_DROP_LEFT, WHEEL_DROP_RIGHT
  - DUST_BIN, BATTERY, DOCK_CONTACTS, POWER_BUTTON

### Disconnect and remove mainboard (10 min)
- [ ] Disconnect every cable from the mainboard (don't pull on wires; release latches)
- [ ] Unscrew the mainboard
- [ ] Set aside in an ESD-safe bag (we discard but don't damage; useful if we ever need to verify connector pinouts)

### Remove and discard subsystems we don't keep (10 min)
- [ ] OEM Neato battery (set aside; properly dispose if dead)
- [ ] LDS spinning module (full assembly: laser, motor, belt, encoder)
- [ ] OEM suction fan motor (replaced with Delta)

### Mechanical cleaning (10 min)
- [ ] Vacuum out interior of dust cup, cyclone, HEPA chamber
- [ ] Wipe down chassis interior
- [ ] Lightly lubricate LIDAR turret bearing (very small drop of light oil)
- [ ] Inspect wheel hubs and bearings; lubricate if needed

## Phase 3 — Pi 5 + ESP32 brain installation

### Plan mounting positions (10 min)
- [ ] Decide where Pi 5 mounts (above battery? above dust cup? above motor manifold area?)
- [ ] Decide where ESP32 motor controller mounts
- [ ] Decide where ESP32 sensor hub mounts
- [ ] Decide where BNO055 mounts (must be rigidly coupled to chassis, away from motors)
- [ ] Sketch wire routing paths

### CAD + print mounting plates (varies)
- [ ] Print Pi 5 mount plate
- [ ] Print ESP32 mount plate
- [ ] Print AS5600 motor shaft adapter (after measuring motor shaft on arrival)
- [ ] Print RPLIDAR C1 turret adapter ring

### Install electronics (30 min)
- [ ] Mount Pi 5 in chassis
- [ ] Mount ESP32 motor controller
- [ ] Mount ESP32 sensor hub
- [ ] Mount BNO055
- [ ] Mount RPLIDAR C1 in turret bay (replaces OEM LDS)
- [ ] Install power distribution board (battery → buck converters)

## Phase 4 — Wiring

### Power bus (15 min)
- [ ] Wire fresh aftermarket battery to power distribution
- [ ] Install 20 A blade fuse on V+ within 100 mm of battery
- [ ] Wire 14.4 V → buck → 5 V (Pi 5) and → 5 V (ESP32s)
- [ ] Wire 14.4 V direct rail for motor drivers
- [ ] Wire 4S CC/CV charger module to dock contact bars
- [ ] Verify all voltages with multimeter BEFORE connecting any logic boards

### Sensor wiring (30 min)
- [ ] Connect 4 bumper microswitches → ESP32 sensor hub GPIO
- [ ] Connect 2 wheel-drop microswitches → ESP32 sensor hub GPIO
- [ ] Connect VL6180X cliff sensors (×2) → ESP32 I²C bus (with XSHUT pin sequencing for address conflict)
- [ ] Connect dust bin sensor → ESP32 sensor hub GPIO
- [ ] (Optional) Connect side wall IR → ESP32 ADC

### Motor wiring (30 min)
- [ ] Connect AS5600 encoders to motor shafts (mechanical mount + I²C wiring)
- [ ] Connect drive motors → TB67H450FNG H-bridges → ESP32 motor controller PWM
- [ ] Connect AS5600 → ESP32 motor controller I²C bus

> NOTE: v2 scope under revision — the vacuum subsystem is retired; this section needs re-scoping by the maintainer.

- [ ] Connect brushroll motor → TB67H450FNG → ESP32 sensor hub PWM
- [ ] Connect side brush motor → TB67H450FNG → ESP32 sensor hub PWM
- [ ] Connect Delta blower motor → ESP32 sensor hub PWM (4-wire: V+, GND, PWM, FG)

## Phase 5 — Software bring-up

### Per-component validation (varies)
- [ ] ESP32 firmware — adapt motor controller firmware for new motors
  - [ ] Tune PID for AS5600 + Neato motor combination
  - [ ] Verify quadrature decoding from AS5600 angle delta
  - [ ] Test forward/reverse motion
  - [ ] Calibrate ticks-per-meter using known-distance test
- [ ] ESP32 firmware — adapt sensor hub for new sensors
  - [ ] VL6180X driver (replaces Sharp GP2Y0A51 driver)
  - [ ] Bumper switch debouncing
  - [ ] Wheel-drop emergency stop logic
- [ ] RPLIDAR C1 — verify scan publication via existing `rplidar_ros` node
- [ ] BNO055 — verify IMU data via existing motor controller firmware

> NOTE: v2 scope under revision — the vacuum subsystem is retired; this section needs re-scoping by the maintainer.

- [ ] ~~Vacuum control node — new ROS2 node for `/vacuum/cmd` topic~~ (retired)

### System integration (varies)
- [ ] EKF tuning for new chassis kinematics
- [ ] Nav2 parameter tuning (new wheel diameter, new max speeds)
- [ ] Costmap configuration for new sensor layout
- [ ] Teleop verification (smooth motion, no oscillation)
- [ ] SLAM mapping test (drive a small map, verify quality)
- [ ] Auto-docking test (drive to dock, charge contacts engage)

## Phase 6 — Final integration

### Mechanical finalization
- [ ] Cable management (route wires neatly, secure with zip ties)

> NOTE: v2 scope under revision — the vacuum subsystem is retired; the vacuum-manifold / dust-cup / HEPA steps below need re-scoping by the maintainer.

- [ ] Vibration isolation (Sorbothane pads under vacuum manifold)
- [ ] Verify dust cup latches and unlatches cleanly
- [ ] Verify HEPA filter is properly seated

### Functional testing

> NOTE: v2 scope under revision — the vacuum subsystem is retired; the cleaning-cycle step needs re-scoping by the maintainer.

- [ ] Full cleaning cycle on hard floor
- [ ] Cliff detection at room edge / stairs
- [ ] Bump recovery (drive into wall, verify backup behavior)
- [ ] Dock and charge cycle
- [ ] Long-duration test (30+ minutes runtime, watch battery curve)

### Documentation update
- [ ] Update CLAUDE.md to reflect v2 architecture
- [ ] Update topology diagrams in `~/robots/rovac/docs/architecture/`
- [ ] Update topic reference in main project docs
- [ ] Photograph completed v2 build for project history

## Estimated total time

| Phase | Estimated hours |
|---|---|
| Phase 0 (pre-arrival prep) | 2–3 |
| Phase 1 (inspection) | 0.5 |
| Phase 2 (disassembly) | 1 |
| Phase 3 (brain installation) | 2–3 |
| Phase 4 (wiring) | 2–3 |
| Phase 5 (software bring-up) | 8–12 |
| Phase 6 (integration) | 4–6 |
| **Total** | **20–30 hours** over ~2–3 weeks |

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Donor chassis arrives mechanically damaged | Low | Buyer has limited recourse (no returns); inspect on arrival, escalate to eBay if egregious |
| Drive motors are dead (not just battery) | Medium | Phase 1 multimeter test catches this; fall back to JGB37 motors with adapter |
| Cliff sensors are NOT VL6180X (D5 differs from D7) | Low–Medium | If they're some other ToF, still upgrade vs current Sharp IR; if they're analog IR, keep ROVAC's current Sharp setup |
| Aftermarket battery doesn't fit Neato bay | Low | Verify dimensions BEFORE ordering battery (after donor arrives) |
| AS5600 mount adapter design takes longer than expected | Medium | Iterate after measuring motor shaft; first version may need 2–3 print revisions |
| 4S charger module too low current to charge during use | Medium | Acceptable trade-off; charge while idle, not during operation |
| Vacuum motor noise excessive | Medium | Sorbothane vibration mounts; foam-lined enclosure if needed |
| Neato motor + AS5600 PID tuning takes longer than expected | High | Plan 4–8 hours of tuning work; have JGB37s as backup if Neato motors don't behave well |
