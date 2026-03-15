# ESP32-S3 Sensor Hub — Wiring Guide

## Overview

New wireless micro-ROS sensor node for ROVAC. Connects MPU-6050 IMU, 2x Sharp IR cliff sensors, Yahboom IR tracking module, and 2x HC-SR04 ultrasonics to an ESP32-S3 (Lonely Binary) board. Communicates via WiFi UDP to the micro-ROS Agent on the Pi (same architecture as motor and LIDAR ESP32s).

## Board

ESP32-S3 WROOM (Lonely Binary 2518V5), 16MB flash, 8MB OPI PSRAM.
See `hardware/ESP32-S3–WROOM/CLAUDE.md` for full pin reference.

**Key constraint**: OPI PSRAM steals GPIO26-37. ADC2 (GPIO11-20) unavailable for analog reads while WiFi is active.

## Power Architecture

```
Robot 12V Battery
    │
    ├──► 5V Buck Converter (e.g., LM2596 module) ──► 5V Rail
    │        │
    │        ├── GP2Y0A51SK0F #1 VCC (12mA)
    │        ├── GP2Y0A51SK0F #2 VCC (12mA)
    │        ├── HC-SR04 #1 VCC (15mA)
    │        ├── HC-SR04 #2 VCC (15mA)
    │        └── Yahboom IR Tracker VCC (≈60mA)
    │
    └──► ESP32-S3 USB power (from Pi USB or separate USB cable)
             │
             └── 3.3V Pin ──► MPU-6050 VCC (3.9mA)
```

**IMPORTANT**: The ESP32-S3 Lonely Binary board's 5V pin does NOT output VBUS.
You MUST provide 5V from an external source for the 5V sensors.

## Pin Assignment Table

| GPIO | Sensor | Function | Signal Type | Voltage |
|------|--------|----------|-------------|---------|
| **1** | GP2Y0A51SK0F #1 | Left cliff analog in | ADC1_CH0 | 0-2.3V |
| **2** | GP2Y0A51SK0F #2 | Right cliff analog in | ADC1_CH1 | 0-2.3V |
| **4** | Yahboom IR X1 | Cliff/track channel 1 | Digital IN | 3.3V |
| **5** | Yahboom IR X2 | Cliff/track channel 2 | Digital IN | 3.3V |
| **6** | Yahboom IR X3 | Cliff/track channel 3 | Digital IN | 3.3V |
| **7** | Yahboom IR X4 | Cliff/track channel 4 | Digital IN | 3.3V |
| **8** | MPU-6050 SDA | I2C data | I2C | 3.3V |
| **9** | MPU-6050 SCL | I2C clock | I2C | 3.3V |
| **10** | MPU-6050 INT | Data-ready interrupt | Digital IN | 3.3V |
| **11** | HC-SR04 #1 TRIG | Ultrasonic trigger | Digital OUT | 3.3V |
| **12** | HC-SR04 #1 ECHO | Ultrasonic echo (via divider) | Digital IN | 3.3V* |
| **13** | HC-SR04 #2 TRIG | Ultrasonic trigger | Digital OUT | 3.3V |
| **14** | HC-SR04 #2 ECHO | Ultrasonic echo (via divider) | Digital IN | 3.3V* |
| **48** | Onboard WS2812 | Status LED | RMT TX | 3.3V |

*HC-SR04 ECHO outputs 5V — MUST use voltage divider (see below).

**Pins used**: 13 of ~21 available. **Pins remaining**: GPIO15, 16, 17, 18, 21, 47 (6 spare for future sensors).

## Wiring Diagram

```
                        ┌─────────────────────────────────────────────┐
                        │          ESP32-S3 (Lonely Binary)           │
                        │                                             │
                        │  [USB-C]                        [USB-C]     │
                        │   Main                           UART       │
                        │                                             │
     ┌──────────────────┤ 3.3V                                        │
     │                  │ GND ────────────────────── GND bus ──────┐  │
     │                  │                                          │  │
     │  ┌───────────────┤ GPIO1  (ADC1_CH0) ◄── Vo ──┐            │  │
     │  │               │                             │            │  │
     │  │  ┌────────────┤ GPIO2  (ADC1_CH1) ◄── Vo ──┼──┐         │  │
     │  │  │            │                             │  │         │  │
     │  │  │  ┌─────────┤ GPIO4  ◄── X1 ──┐          │  │         │  │
     │  │  │  │  ┌──────┤ GPIO5  ◄── X2 ──┤          │  │         │  │
     │  │  │  │  │  ┌───┤ GPIO6  ◄── X3 ──┤          │  │         │  │
     │  │  │  │  │  │ ┌─┤ GPIO7  ◄── X4 ──┤          │  │         │  │
     │  │  │  │  │  │ │ │                  │          │  │         │  │
     │  │  │  │  │  │ │ ├ GPIO8  (SDA) ◄───┼──┐      │  │         │  │
     │  │  │  │  │  │ │ ├ GPIO9  (SCL) ◄───┼──┼──┐   │  │         │  │
     │  │  │  │  │  │ │ ├ GPIO10 (INT) ◄───┼──┼──┼─┐ │  │         │  │
     │  │  │  │  │  │ │ │                  │  │  │ │ │  │         │  │
     │  │  │  │  │  │ │ ├ GPIO11 ──► TRIG ─┼──┼──┼─┼─┼──┼──┐      │  │
     │  │  │  │  │  │ │ ├ GPIO12 ◄── ECHO*─┼──┼──┼─┼─┼──┼──┼──┐   │  │
     │  │  │  │  │  │ │ ├ GPIO13 ──► TRIG ─┼──┼──┼─┼─┼──┼──┼──┼─┐ │  │
     │  │  │  │  │  │ │ ├ GPIO14 ◄── ECHO*─┼──┼──┼─┼─┼──┼──┼──┼─┼─┤  │
     │  │  │  │  │  │ │ │                  │  │  │ │ │  │  │  │ │ │  │
     │  │  │  │  │  │ │ └──────────────────┼──┼──┼─┼─┼──┼──┼──┼─┼─┘  │
     │  │  │  │  │  │ │                    │  │  │ │ │  │  │  │ │    │
     └──┼──┼──┼──┼──┼─┼────────────────────┼──┼──┼─┘ │  │  │  │ │    │
        │  │  │  │  │ │                    │  │  │   │  │  │  │ │    │
        │  │  │  │  │ │                    │  │  │   │  │  │  │ │    │
        ▼  ▼  ▼  ▼  ▼ ▼                    ▼  ▼  ▼   ▼  ▼  ▼  ▼ ▼    │
                                                                      │
5V Rail ──────────────────────────────────────────────────────────────┘
(from buck converter)

 * ECHO lines require voltage divider (see below)
```

### Individual Sensor Wiring Details

#### MPU-6050 (GY-521) — I2C

```
  GY-521 Module              ESP32-S3
  ┌───────────┐
  │ VCC ──────────────────── 3.3V        (NOT 5V — avoids level shift issues)
  │ GND ──────────────────── GND
  │ SDA ──────────────────── GPIO8       (4.7kΩ pull-up to 3.3V)
  │ SCL ──────────────────── GPIO9       (4.7kΩ pull-up to 3.3V)
  │ INT ──────────────────── GPIO10      (optional — data-ready interrupt)
  │ AD0 ──────────────────── GND         (I2C address = 0x68)
  │ XDA ─── NC
  │ XCL ─── NC
  └───────────┘

  Notes:
  - Power at 3.3V directly (the GY-521 LDO passes through at 3.3V input)
  - 4.7kΩ pull-ups on SDA/SCL to 3.3V (some GY-521 boards have onboard pull-ups —
    check if yours do before adding external ones. If I2C works without, skip them.)
  - AD0 tied to GND sets address 0x68
```

#### GP2Y0A51SK0F x2 — Analog Cliff Sensors

```
  Sharp IR Sensor             ESP32-S3 / Power
  ┌──────────────┐
  │ Pin 1 (Vcc) ─────────── 5V Rail     (4.5-5.5V required)
  │ Pin 2 (GND) ─────────── GND
  │ Pin 3 (Vo)  ─────────── GPIO1       (Left cliff — ADC1_CH0)
  └──────────────┘           or GPIO2    (Right cliff — ADC1_CH1)

       ┌──────┐
  5V ──┤ 10µF ├── GND       (bypass cap, close to each sensor — REQUIRED)
       └──────┘              (sensor draws current in bursts, destabilizes supply)

  Notes:
  - Output voltage: 0.25V (15cm) to 2.3V (2cm) — within ADC1 range at 11dB atten.
  - Connector: 1.5mm JST ZH (3-pin). Solder wires if you don't have the cable.
  - Pinout from front: Vcc | GND | Vo (left to right)
  - Add 10µF electrolytic cap across Vcc-GND close to EACH sensor
```

#### Yahboom IR Tracking Module — 4-Channel Digital

```
  Yahboom Module (XH2.54-6Pin)    ESP32-S3
  ┌─────────────────┐
  │ VCC ───────────────────── 5V Rail    (5V power supply)
  │ GND ───────────────────── GND
  │ X1  ───────────────────── GPIO4      (Channel 1 — leftmost sensor)
  │ X2  ───────────────────── GPIO5      (Channel 2 — inner left)
  │ X3  ───────────────────── GPIO6      (Channel 3 — inner right)
  │ X4  ───────────────────── GPIO7      (Channel 4 — rightmost sensor)
  └─────────────────┘

  Notes:
  - Uses LM324 comparator: outputs are open-collector, pulled up to VCC via 10kΩ
  - Output logic (from Yahboom docs):
      LOW  = reflective surface detected (floor present — SAFE)
      HIGH = dark/no reflection (void/cliff — DANGER)
  - For cliff detection: ANY channel going HIGH = emergency stop
  - 4x adjustable potentiometers (SW1-SW4) tune sensitivity per channel
  - IMPORTANT: The LM324 outputs swing to VCC (5V). But the 10kΩ pull-up
    limits current. The ESP32-S3 GPIO input threshold is ~2.0V for HIGH.
    At 5V VCC, the HIGH output will be ~5V.

  ** 5V TOLERANCE WARNING **
  ESP32-S3 GPIOs are rated for 3.3V. The Yahboom outputs are 5V logic.
  Options (pick one):
    a) Power the Yahboom module at 3.3V instead of 5V (simpler — try this first,
       the LM324 works down to 3V but IR LED brightness may decrease slightly)
    b) Add 1kΩ series resistors on X1-X4 lines (limits current through ESD diodes)
    c) Use a 4-channel level shifter (safest but most complex)

  RECOMMENDATION: Power at 3.3V. The IR LEDs get their current through the
  100Ω series resistors (R1,R3,R5,R7), so at 3.3V they'll draw ~10mA each —
  still enough for short-range floor detection (1-3cm).
```

#### HC-SR04 x2 — Ultrasonic Distance Sensors

```
  HC-SR04                    ESP32-S3 / Power
  ┌──────────┐
  │ VCC ──────────────────── 5V Rail
  │ TRIG ─────────────────── GPIO11 (or GPIO13)   (3.3V output is fine for 5V TRIG)
  │ ECHO ─────┐
  │ GND ──────┼───────────── GND
  └──────────┘│
              │    VOLTAGE DIVIDER (required!)
              │
              ├──── 1kΩ ────┬──── GPIO12 (or GPIO14)
              │              │
              │           2kΩ (or 2.2kΩ)
              │              │
              └──────────── GND

  Echo voltage division: 5V × 2kΩ/(1kΩ+2kΩ) = 3.33V  ✓ safe for ESP32-S3

  Notes:
  - TRIG: ESP32 sends 10µs HIGH pulse (3.3V is above HC-SR04's 2.0V threshold)
  - ECHO: HC-SR04 outputs 5V pulse — MUST use voltage divider
  - Each sensor needs its own divider (2 resistors per sensor, 4 total)
  - Use 1kΩ + 2.2kΩ for slightly under 3.3V (more conservative)
```

## Complete Wiring Diagram (All Sensors)

```
                                    5V Rail (from buck converter)
                                         │
              ┌──────────────────────────┼─────────────────────────────────┐
              │                          │                                 │
         ┌────┴────┐              ┌──────┴──────┐                   ┌──────┴──────┐
         │ 10µF cap│              │  10µF cap   │                   │ HC-SR04 #1  │
         └────┬────┘              └──────┬──────┘                   │             │
              │                          │                          │ VCC ─── 5V  │
     ┌────────┴────────┐      ┌──────────┴────────┐                │ GND ─── GND │
     │  SHARP IR #1    │      │  SHARP IR #2      │                │ TRIG ── G11 │
     │  (Left Cliff)   │      │  (Right Cliff)    │                │ ECHO──┐     │
     │                 │      │                   │                └───────┼─────┘
     │ Vo ──── GPIO1   │      │ Vo ──── GPIO2    │                       │
     │ VCC ─── 5V      │      │ VCC ─── 5V       │           1kΩ ──┤     │
     │ GND ─── GND     │      │ GND ─── GND      │   GPIO12 ──────┤     │
     └─────────────────┘      └───────────────────┘           2kΩ ──┤─ GND
                                                                         │
    ┌─────────────────────────┐                                   ┌──────┴──────┐
    │  YAHBOOM IR TRACKER     │                                   │ HC-SR04 #2  │
    │  (powered at 3.3V)      │                                   │             │
    │                         │                                   │ VCC ─── 5V  │
    │ VCC ─── 3.3V            │                                   │ GND ─── GND │
    │ GND ─── GND             │                                   │ TRIG ── G13 │
    │ X1  ─── GPIO4           │                                   │ ECHO──┐     │
    │ X2  ─── GPIO5           │                                   └───────┼─────┘
    │ X3  ─── GPIO6           │                                          │
    │ X4  ─── GPIO7           │                              1kΩ ──┤     │
    └─────────────────────────┘                      GPIO14 ──────┤     │
                                                              2kΩ ──┤─ GND
    ┌─────────────────────────┐
    │  MPU-6050 (GY-521)      │       ┌─── 4.7kΩ ─── 3.3V    (optional pull-ups)
    │                         │       │
    │ VCC ─── 3.3V            │       ├─── 4.7kΩ ─── 3.3V
    │ GND ─── GND             │       │
    │ SDA ─── GPIO8 ──────────┼───────┘
    │ SCL ─── GPIO9 ──────────┼───────┘
    │ INT ─── GPIO10          │
    │ AD0 ─── GND             │
    └─────────────────────────┘

    ┌─────────────────────────┐
    │  ESP32-S3 POWER         │
    │                         │
    │ USB-C ── Pi USB port    │    (or separate USB power)
    │          (powers ESP32) │
    │                         │
    │ 3.3V pin ── to MPU &   │
    │              IR tracker │
    │                         │
    │ GND ─── common GND bus  │    (ALL grounds connected together)
    └─────────────────────────┘
```

## Bill of Materials (Additional Parts Needed)

| Part | Qty | Purpose | Approx Cost |
|------|-----|---------|-------------|
| 5V Buck Converter (LM2596 module) | 1 | 12V→5V for sensors | $2-3 |
| 10µF electrolytic capacitor | 2 | Bypass caps for Sharp IR sensors | $0.10 |
| 1kΩ resistor | 2 | HC-SR04 ECHO voltage dividers | $0.02 |
| 2.2kΩ resistor | 2 | HC-SR04 ECHO voltage dividers | $0.02 |
| 4.7kΩ resistor | 2 | I2C pull-ups (if needed) | $0.02 |
| 3-pin JST ZH cable (1.5mm) | 2 | Sharp IR sensor cables | $1-2 |
| Dupont jumper wires | ~20 | General wiring | $2-3 |
| Small breadboard or perfboard | 1 | Mounting/connections | $2-3 |

## Sensor Mounting Guide

### Side View of Robot with Sensor Placement

```
                    LIDAR (existing)
                    ┌───┐
                    │ L │  12.5cm above base_link
    ────────────────┴───┴──────────────────
    │                                      │
    │         ┌───────────┐                │   ◄── MPU-6050 (center, flat)
    │         │  MPU-6050 │                │       on foam tape
    │         └───────────┘                │
    │                                      │
    │   CHASSIS (top view: 25cm x 20cm)    │   ◄── 10cm height
    │                                      │
    ├──────────────────────────────────────┤
    │    ▼ ▼          ▼ ▼            ▼ ▼   │   ◄── Bottom edge (2-3cm from floor)
    │   IR1 IR2     IR3 IR4        S1  S2  │
    │  (Yahboom)    (Yahboom)    (Sharp)   │
    │                                      │
    │  ┌──┐                          ┌──┐  │   ◄── Front face, bumper height (~5cm)
    │  │US│ (HC-SR04 #1)  (HC-SR04 #2)│US│  │
    │  └──┘     30° left    30° right └──┘  │
    └──────────────────────────────────────┘
         ◄─── FRONT (direction of travel) ──►

    Floor ═══════════════════════════════════
```

### MPU-6050 — Center of Chassis, Flat

```
    Mounting: Double-sided foam tape (vibration damping)
    Location: Center of robot, as close to center of rotation as possible
    Orientation: Chip label facing UP, long edge parallel to robot's forward axis

    ┌─────────────────────────┐
    │                         │
    │      ┌─────────┐       │     X-axis → forward
    │      │ MPU-6050│       │     Y-axis → left
    │      │  (flat) │       │     Z-axis → up
    │      └─────────┘       │
    │       ↑ CENTER         │
    │                         │
    └─────────────────────────┘

    WHY center: Minimizes centripetal acceleration artifacts during turns.
    WHY foam tape: The tank treads vibrate heavily. Hard-mounting the IMU
    couples motor vibration directly into the accelerometer, corrupting
    tilt measurements. 2-3mm foam tape acts as a low-pass mechanical filter.

    KEEP AWAY FROM: Motors (electromagnetic interference), magnets,
    speakers, and large current-carrying wires.
```

### GP2Y0A51SK0F — Front Edge, Pointing DOWN

```
    Mount 2 sensors at the front-left and front-right bottom edges,
    pointing straight down at the floor.

    Side view:
                    ┌── chassis bottom ──┐
                    │                     │
                    │  ┌────┐     ┌────┐  │
                    │  │ IR │     │ IR │  │    sensors face DOWN
                    │  │ ▼  │     │ ▼  │  │
                    │  └────┘     └────┘  │
                    │  LEFT       RIGHT   │
                    └─────────────────────┘
                                              3-5cm to floor
    ═══════════ FLOOR ════════════════════

    Normal reading (floor present): ~1.0-1.5V (3-5cm distance)
    Cliff detected (no floor):     <0.3V (>15cm or no return)

    Spacing: Mount ~15cm apart (near robot's front corners)
    Angle: Point straight down (perpendicular to floor)
    Height: 3-5cm above floor gives strongest, most reliable signal

    IMPORTANT: The IR beam has a narrow cone (~5°). If mounted at an angle,
    the reflection may miss the detector. Keep perpendicular to floor.

    GOTCHA: Dark carpet absorbs IR light and may read as "no floor."
    Calibrate the cliff threshold on your actual floor surfaces.
```

### Yahboom IR Tracker — Front Bottom Edge, Facing DOWN

```
    Mount the module at the front-center bottom of the chassis,
    IR probes pointing straight down, 1-2cm from the floor.

    Bottom view of front edge:
    ┌──────────────────────────────────────┐
    │                                      │
    │   ┌──────────────────────────────┐   │
    │   │  P1    P2    P3    P4        │   │   ◄── Yahboom module
    │   │  (X1)  (X2)  (X3)  (X4)     │   │       screwed to chassis
    │   └──────────────────────────────┘   │
    │          ▼    ▼    ▼    ▼            │   ◄── IR probes face floor
    └──────────────────────────────────────┘
    ═══════════ FLOOR ═════════════════════

    Detection distance: 1-3cm from floor surface

    Use as SECONDARY cliff detection + surface type detection:
    - All 4 channels LOW = floor present (safe)
    - Any channel HIGH = possible cliff/edge (trigger alert)
    - Adjust potentiometers SW1-SW4 so LEDs are OFF on your floor
      and ON when lifted away from floor (>3cm)

    CALIBRATION: Hold module 1-2cm above your floor surface, turn each
    potentiometer until the corresponding LED just turns OFF. Then verify
    the LED turns ON when you lift the module 3+ cm.
```

### HC-SR04 — Front Face, Angled Outward

```
    Mount 2 ultrasonics on the front face at bumper height (~5cm),
    angled 30° outward from center to cover the forward arc.

    Top view:
                         FRONT
                    ┌──────────────┐
                   ╱                ╲
            US #1 ╱   30°      30°   ╲ US #2
                 ╱                     ╲
                ╱         ◉             ╲     ◉ = robot center
               ╱      (forward)          ╲
              ╱                            ╲

    Height: ~5cm above floor (below LIDAR scan at 12.5cm)
    Purpose: Detect obstacles in LIDAR's blind zone
    Range: 2-400cm (but useful range is 2-50cm for obstacle avoidance)

    WHY angled: Two sensors at ±30° give ~120° forward coverage combined,
    catching obstacles approaching from either side.

    GOTCHA: Ultrasonics have a ~30° beam cone. Two sensors at ±30° may
    create crosstalk (one sensor's ping is received by the other).
    Mitigate by triggering them sequentially (not simultaneously) in firmware.
```

## micro-ROS Topics (Planned)

| Topic | Message Type | Rate | Description |
|-------|-------------|------|-------------|
| `/imu/data` | sensor_msgs/Imu | 100 Hz | Accel + gyro (fuse with odom) |
| `/cliff/left` | sensor_msgs/Range | 30 Hz | Sharp IR left distance |
| `/cliff/right` | sensor_msgs/Range | 30 Hz | Sharp IR right distance |
| `/cliff/detected` | std_msgs/Bool | on-event | ANY cliff sensor triggered |
| `/surface/ir_raw` | std_msgs/UInt8 | 20 Hz | 4-bit bitmask of IR tracker |
| `/ultrasonic/left` | sensor_msgs/Range | 10 Hz | HC-SR04 #1 distance |
| `/ultrasonic/right` | sensor_msgs/Range | 10 Hz | HC-SR04 #2 distance |
| `/diagnostics` | diagnostic_msgs/DiagnosticArray | 1 Hz | Sensor health |

## Safety Behavior (Firmware)

The sensor hub should implement LOCAL emergency stop logic:
1. If any cliff sensor detects a drop → publish `/cliff/detected` = true
2. The cmd_vel_mux obstacle channel or a dedicated cliff subscriber
   on the Pi should issue immediate stop + small reverse

This is a SAFETY-CRITICAL path. The cliff detection and stop must happen
with minimum latency — ideally within 100ms of detection.
