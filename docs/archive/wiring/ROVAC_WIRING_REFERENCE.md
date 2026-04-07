# ROVAC WIRING REFERENCE — PRINT THIS SHEET

## COMPONENT SPECIFICATIONS

| Component | Model | Key Specs |
|-----------|-------|-----------|
| **Computer** | Raspberry Pi 5 (8GB) | Ubuntu 24.04, hostname `rovac-pi`, IP `192.168.1.200` |
| **Motor Driver** | Yahboom BST-4WD V4.5 | TB6612FNG dual H-bridge, 1.2A cont / 3.2A peak per ch |
| **Motors (x2)** | JGB37-520R60-12 | 12V DC, 60:1 gear, 170 RPM, 6mm D-shaft, 33mm dia |
| **Encoders** | Hall effect (built-in) | 11 PPR, 4x quad = 2640 ticks/rev, 3.3-5V, square wave |
| **Battery** | 3S LiPo (11.1V nom) | Connects to BST-4WD power input (6-12V) |

---

## MOTOR 6-PIN CONNECTOR (JGB37-520R60-12)

Looking at the back of the motor (encoder side), connector pins left-to-right:

```
    ┌─────────────────────────────────────────────────┐
    │  MOTOR BODY (gearbox side →)     ┌──encoder──┐  │
    │                                  │  ○ ○ ○ ○  │  │
    │                                  │  ○ ○ ○ ○  │  │
    │                                  └───────────┘  │
    │         6-PIN CONNECTOR (flat ribbon cable)      │
    └──────────────┬──────────────────────────────────┘
                   │
     Pin 1  Pin 2  Pin 3  Pin 4  Pin 5  Pin 6
      RED   BLACK  GREEN  YELLOW  BLUE  WHITE
      M+    ENC-   Ch B    Ch A   ENC+   M-
     (Motor (Encdr (Signal (Signal (Encdr (Motor
      pwr+)  GND)    B)      A)    VCC)   pwr-)

    NOTE: Your motors may have uniform wire color.
    Use the PIN POSITION (1-6) as the primary reference.
```

| Pin | Std Color | Function | Connects To |
|-----|-----------|----------|-------------|
| 1 | **Red** | Motor power + (M+) | BST-4WD motor terminal (+ or either) |
| 2 | **Black** | Encoder GND | Nano GND |
| 3 | **Green** | Encoder Ch B | Nano digital pin (see encoder table below) |
| 4 | **Yellow** | Encoder Ch A | Nano digital pin (see encoder table below) |
| 5 | **Blue** | Encoder VCC (3.3-5V) | Nano 5V |
| 6 | **White** | Motor power - (M-) | BST-4WD motor terminal (- or either) |

---

## WIRING OVERVIEW

```
                                 ┌───────────────────────┐
  ┌──────────┐    Motor wires    │   BST-4WD V4.5        │
  │          ├── Red (M+) ──────►│ L-MOA terminal        │   ┌─────────┐
  │  LEFT    ├── White (M-) ────►│ L-MOA terminal        │   │         │
  │  MOTOR   │                   │                       │◄──┤ BATTERY │
  │          ├── Yellow (A) ─┐   │ R-MOA terminal  ◄─────┤   │ 6-12V   │
  │          ├── Green (B) ──┤   │ R-MOA terminal  ◄─────┤   └─────────┘
  │          ├── Blue (VCC)──┤   │                       │
  │          ├── Black (GND)─┤   │  40-pin female hdr    │
  └──────────┘               │   │  (NOT seated on Pi)   │
                             │   │                       │
  ┌──────────┐               │   │  8 JUMPER WIRES from  │
  │          ├── Red (M+) ──►│   │  Pi header to BST-4WD │
  │  RIGHT   ├── White (M-) ►│   └────────┬──────────────┘
  │  MOTOR   │               │            │ 8 jumper wires
  │          ├── Yellow (A) ─┤            │
  │          ├── Green (B) ──┤    ┌───────┴───────────────┐
  │          ├── Blue (VCC)──┤    │  RASPBERRY PI 5       │
  │          ├── Black (GND)─┤    │  40-pin male header   │
  └──────────┘               │    │                       │
                             │    └───────────────────────┘
  Encoder wires (6 total) ───┘
         │                    ┌───────────────────────────┐
         └──────────────────► │  Arduino Nano (ATmega328P)│
           (to Nano pins)     │  USB serial to Pi         │
                              └───────────────────────────┘
```

---

## BST-4WD JUMPER WIRES (8 wires: Pi header → BST-4WD header)

**The BST-4WD is NOT seated on the Pi header.** Connect these 8 wires only:

| # | Signal    | Pi Header Pin | BCM GPIO | BST-4WD Pin | TB6612 Function              |
|---|-----------|---------------|----------|-------------|------------------------------|
| 1 | Left Fwd  | **Pin 38**    | GPIO20   | Pin 38      | AIN2 — Left motor forward    |
| 2 | Left Rev  | **Pin 40**    | GPIO21   | Pin 40      | AIN1 — Left motor reverse    |
| 3 | Left PWM  | **Pin 36**    | GPIO16   | Pin 36      | PWMA — Left motor speed      |
| 4 | Right Fwd | **Pin 35**    | GPIO19   | Pin 35      | BIN2 — Right motor forward   |
| 5 | Right Rev | **Pin 37**    | GPIO26   | Pin 37      | BIN1 — Right motor reverse   |
| 6 | Right PWM | **Pin 33**    | GPIO13   | Pin 33      | PWMB — Right motor speed     |
| 7 | 5V Power  | **Pin 2**     | (5V)     | Pin 2       | TB6612 logic VCC             |
| 8 | Ground    | **Pin 6**     | (GND)    | Pin 6       | Common ground reference      |

---

## ENCODER WIRES (to Arduino Nano via USB serial to Pi)

Encoders connect to the Arduino Nano (NOT the Pi). The Nano uses hardware
interrupt pins (INT0/INT1) for reliable quadrature decoding, streaming
counts to the Pi over USB serial.

| Motor      | Encoder Wire     | Std Color      | Nano Pin          |
|------------|------------------|----------------|-------------------|
| **Left**   | Channel A (C1)   | Yellow (pin 4) | **D2** (INT0)     |
| **Left**   | Channel B (C2)   | Green (pin 3)  | **D4**            |
| **Right**  | Channel A (C1)   | Yellow (pin 4) | **D3** (INT1)     |
| **Right**  | Channel B (C2)   | Green (pin 3)  | **D5**            |
| **Both**   | Encoder VCC      | Blue (pin 5)   | **5V**            |
| **Both**   | Encoder GND      | Black (pin 2)  | **GND**           |

D2/D3 are hardware interrupt pins — best response time for Channel A.
**Left encoder is inverted in software** (motor physically mirrored).

---

## PI 5 GPIO HEADER — COMPLETE PIN MAP

Encoder wires now go to ESP32 (not Pi GPIO). Only motor control + power remain on Pi.

```
             Raspberry Pi 5 — 40-Pin GPIO Header
             (looking down at Pi, USB ports facing you)

          LEFT SIDE                         RIGHT SIDE
   ┌─────────────────────────────────────────────────────┐
   │                                                     │
   │           3.3V  (1)○  ●(2)  5V   [BST-4WD 5V]      │
   │          SDA/GPIO2  (3)○  ○(4)  5V                  │
   │          SCL/GPIO3  (5)○  ●(6)  GND  [BST-4WD GND]  │
   │              GPIO4  (7)○  ○(8)  GPIO14/TX           │
   │                GND  (9)○  ○(10) GPIO15/RX           │
   │             GPIO17 (11)○  ○(12) GPIO18              │
   │             GPIO27 (13)○  ○(14) GND                 │
   │             GPIO22 (15)○  ○(16) GPIO23              │
   │           3.3V (17)○  ○(18) GPIO24                  │
   │        MOSI/GPIO10 (19)○  ○(20) GND                 │
   │        MISO/GPIO9  (21)○  ○(22) GPIO25              │
   │        SCLK/GPIO11 (23)○  ○(24) GPIO8               │
   │                GND (25)○  ○(26) GPIO7               │
   │       ID_SD/GPIO0  (27)○  ○(28) GPIO1/ID_SC         │
   │              GPIO5 (29)○  ○(30) GND                 │
   │              GPIO6 (31)○  ○(32) GPIO12              │
   │  ►[R-PWM]  GPIO13 (33)■  ○(34) GND                 │
   │  ►[R-FWD]  GPIO19 (35)■  ■(36) GPIO16 [L-PWM]◄     │
   │  ►[R-REV]  GPIO26 (37)■  ■(38) GPIO20 [L-FWD]◄     │
   │                GND (39)○  ■(40) GPIO21 [L-REV]◄     │
   │                                                     │
   └─────────────────────────────────────────────────────┘
                        ▼ USB PORTS ▼

   LEGEND:  ■ = BST-4WD motor jumper    (6 wires)
            ● = BST-4WD power           (2 wires: 5V + GND)
            ○ = Unused / available
```

---

## OTHER PI CONNECTIONS (USB)

| Device | Port | Dev Path | Notes |
|--------|------|----------|-------|
| Nano Encoder Bridge | USB | `/dev/encoder_bridge` | Quadrature decoder via interrupts (CH340 `1a86:7523`) |
| Super Sensor (Arduino Nano) | USB | `/dev/ttyUSB1` | 4x HC-SR04 ultrasonic |
| PS2 Controller Receiver | USB | `/dev/input/js0` | ShanWan ZD-V+ HID `2563:0575` |
| Stereo Cameras (x2) | USB | `/dev/video*` | 102.67mm baseline |
| Hiwonder Board | USB | `/dev/hiwonder_board` | CH9102 `1a86:55d4` — **currently unused** |

---

## BST-4WD POWER

```
  Battery (6-12V) ──► BST-4WD barrel jack / screw terminal
                         │
                         ├── LM2596S regulator → 5V (TB6612 logic VCC)
                         ├── TB6612FNG VM pins  → Motor drive voltage
                         └── AMS1117 regulator  → 3.3V

  BST-4WD power switch (S2) MUST be ON for motors to receive voltage.
  The battery provides BOTH motor power AND logic power to the BST-4WD.
  The Pi's 5V jumper wire (wire #7) provides backup logic power and
  ensures signal ground reference between Pi and BST-4WD.
```

---

## QUICK-CHECK SUMMARY

```
Pi header wires:
  ■ 6 jumper wires  →  BST-4WD (motor control GPIO)
  ● 2 power wires   →  BST-4WD (5V + GND)
  ─────────────────
  8 wires total (from Pi header)

Encoder wires (to ESP32, NOT Pi):
  ◆ 4 signal wires  →  Nano (Ch A/B for each motor)
  ● 2 power wires   →  Nano (5V + GND)
  ─────────────────
  6 wires total (from encoders to Nano)

Motor terminal wires:
  2 wires per motor  →  BST-4WD L-MOA / R-MOA screw terminals
  ─────────────────
  4 wires total (Red/M+ and White/M- from each motor)

Nano → Pi:
  1 USB cable (USB serial for encoder data)
```

---

## SOFTWARE REFERENCE

| Parameter | Value |
|-----------|-------|
| Driver | `hardware/yahboom-bst-4wd-expansion-board/bst4wd_driver.py` |
| GPIO chip | `/dev/gpiochip4` (RP1, Pi 5) — motor control only |
| Motor PWM method | gpiozero `PWMOutputDevice` + `LGPIOFactory(chip=4)` |
| Encoder method | Arduino Nano interrupt-driven via USB serial (`/dev/encoder_bridge`) |
| Encoder firmware | `hardware/nano_encoder_bridge/nano_encoder_bridge.ino` |
| Wheel separation | 0.155 m |
| Wheel radius | 0.032 m |
| Ticks per rev | 2640 (11 PPR x 4 edges x 60:1 gear) |
| Max PWM | 60% |
| PWM frequency | 1000 Hz |
| ROS2 topics | Sub: `/cmd_vel` — Pub: `/odom`, `/diagnostics` |
| Systemd service | `rovac-edge-bst4wd.service` |
