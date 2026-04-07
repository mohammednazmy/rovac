# ESP32 Sensor Hub — Wiring Guide

**Board**: ESP32-DevKitV1 (WROOM-32, 38-pin, CH340 USB)

## Sensors Connected

| Sensor | Qty | VCC | Purpose |
|--------|-----|-----|---------|
| HC-SR04 Ultrasonic | 4 | 5V | Obstacle detection (front, rear, left, right) |
| Sharp GP2Y0A51SK0F IR | 2 | 5V | Cliff/edge detection (front, rear) |
| Yahboom 4-CH IR Tracker | 1 | 3.3V | Surface/line tracking + cliff detection |
| LED Flashlight Breakout | 1 | 3.3V | RGB status light (PWM controlled) |

---

## Complete Pin Assignment

```
ESP32-DevKitV1 (38-pin) — Top View (USB port at bottom)
┌─────────────────────────────────┐
│          [USB / CH340]          │
│                                 │
│  3V3  ●──[3.3V POWER BUS]──●  VIN
│  GND  ●──[GROUND BUS]──────●  GND
│  GPIO15                    GPIO13 ── Yahboom X2
│  GPIO2                     GPIO12
│  GPIO4 ── Yahboom X1       GPIO14 ── Yahboom X3
│  GPIO16 ── US Front TRIG   GPIO27 ── Yahboom X4
│  GPIO17 ── US Rear TRIG    GPIO26 ── LED Green (PWM)
│  GPIO5                     GPIO25 ── LED Red (PWM)
│  GPIO18 ── US Left TRIG    GPIO33 ── Sharp IR Rear (ADC)
│  GPIO19 ── US Right TRIG   GPIO32 ── Sharp IR Front (ADC)
│  GPIO21 ── (reserved I2C)  GPIO35 ── US Rear ECHO ⚡
│  GPIO3  ── UART0 RX        GPIO34 ── US Front ECHO ⚡
│  GPIO1  ── UART0 TX        GPIO39 ── US Right ECHO ⚡
│  GPIO22 ── (reserved I2C)  GPIO36 ── US Left ECHO ⚡
│  GPIO23 ── LED Blue (PWM)   EN
│                                 │
│  5V  ●──[5V POWER BUS]─────●  GND
└─────────────────────────────────┘
⚡ = Needs 5V→3.3V voltage divider (1kΩ + 2.2kΩ)
```

### Pin Table

| GPIO | Direction | Sensor | Function | Voltage | Notes |
|------|-----------|--------|----------|---------|-------|
| **HC-SR04 Ultrasonic (4x)** |
| 16 | OUTPUT | HC-SR04 Front | TRIG | 3.3V | 10μs pulse to trigger |
| 34 | INPUT | HC-SR04 Front | ECHO | 3.3V* | Input-only pin. Voltage divider required. |
| 17 | OUTPUT | HC-SR04 Rear | TRIG | 3.3V | |
| 35 | INPUT | HC-SR04 Rear | ECHO | 3.3V* | Input-only pin. Voltage divider required. |
| 18 | OUTPUT | HC-SR04 Left | TRIG | 3.3V | |
| 36 | INPUT | HC-SR04 Left | ECHO | 3.3V* | Input-only pin (VP). Voltage divider required. |
| 19 | OUTPUT | HC-SR04 Right | TRIG | 3.3V | |
| 39 | INPUT | HC-SR04 Right | ECHO | 3.3V* | Input-only pin (VN). Voltage divider required. |
| **Sharp GP2Y0A51SK0F IR Cliff (2x)** |
| 32 | ADC IN | Sharp IR Front | Analog out | 0–2.4V | ADC1_CH4. No divider needed. |
| 33 | ADC IN | Sharp IR Rear | Analog out | 0–2.4V | ADC1_CH5. No divider needed. |
| **Yahboom 4-CH IR Tracker** |
| 4 | INPUT | Yahboom | X1 (leftmost) | 3.3V | Powered at 3.3V — no level shift needed |
| 13 | INPUT | Yahboom | X2 (inner left) | 3.3V | |
| 14 | INPUT | Yahboom | X3 (inner right) | 3.3V | |
| 27 | INPUT | Yahboom | X4 (rightmost) | 3.3V | |
| **LED Flashlight Breakout** |
| 25 | PWM OUT | LED | Red | 3.3V | LEDC PWM channel |
| 26 | PWM OUT | LED | Green | 3.3V | LEDC PWM channel |
| 23 | PWM OUT | LED | Blue | 3.3V | LEDC PWM channel |
| **Reserved** |
| 1 | TX | — | UART0 TX | — | USB serial (COBS protocol to Pi) |
| 3 | RX | — | UART0 RX | — | USB serial (COBS protocol to Pi) |
| 21 | — | — | Reserved | — | Future I2C SDA |
| 22 | — | — | Reserved | — | Future I2C SCL |
| 5 | — | — | Available | — | Strapping pin (unused) |

**Total GPIOs used**: 17 of 20 available (3 remaining for future expansion)

---

## Power Wiring

```
Pi USB Port ──USB Cable──→ ESP32 DevKitV1 Micro-USB
                                │
                                ├── 5V pin ──→ 5V Power Bus (red rail)
                                │               ├── HC-SR04 Front VCC
                                │               ├── HC-SR04 Rear VCC
                                │               ├── HC-SR04 Left VCC
                                │               ├── HC-SR04 Right VCC
                                │               ├── Sharp IR Front VCC (red wire)
                                │               └── Sharp IR Rear VCC (red wire)
                                │
                                ├── 3V3 pin ──→ 3.3V Power Bus
                                │               ├── Yahboom Tracker VCC
                                │               └── LED Flashlight (if 3.3V module)
                                │
                                └── GND pin ──→ Ground Bus (blue rail)
                                                ├── All HC-SR04 GND
                                                ├── Sharp IR Front GND (black wire)
                                                ├── Sharp IR Rear GND (black wire)
                                                ├── Yahboom Tracker GND
                                                └── LED Flashlight GND
```

### Power Budget

| Component | Voltage | Current (max) |
|-----------|---------|---------------|
| ESP32 (no WiFi) | 3.3V | 50 mA |
| 4x HC-SR04 | 5V | 60 mA (4 × 15 mA) |
| 2x Sharp IR | 5V | 44 mA (2 × 22 mA) |
| 1x Yahboom Tracker | 3.3V | 60 mA |
| 1x LED Flashlight | 3.3V | ~60 mA (est.) |
| **Total 5V** | | **~104 mA** (USB can supply 500+ mA) |
| **Total 3.3V** | | **~170 mA** (AMS1117 can supply 800 mA) |

---

## Detailed Wiring Instructions

### 1. HC-SR04 Ultrasonic Sensors (×4)

Each HC-SR04 needs:
- VCC → 5V bus
- GND → Ground bus
- TRIG → ESP32 GPIO directly (3.3V trigger is fine — exceeds HC-SR04's ~2.0V HIGH threshold)
- ECHO → ESP32 GPIO **through voltage divider** (5V output → 3.3V safe)

**Voltage Divider Circuit (build one per HC-SR04):**

```
HC-SR04 ECHO ──── 1kΩ ──┬── ESP32 GPIO (34/35/36/39)
                         │
                        2.2kΩ
                         │
                        GND

Output voltage: 5V × 2.2k / (1k + 2.2k) = 3.44V (safe for ESP32)
```

**Wiring table:**

| HC-SR04 | VCC | TRIG | ECHO (through divider) | GND |
|---------|-----|------|----------------------|-----|
| Front | 5V bus | GPIO16 | 1kΩ+2.2kΩ → GPIO34 | GND bus |
| Rear | 5V bus | GPIO17 | 1kΩ+2.2kΩ → GPIO35 | GND bus |
| Left | 5V bus | GPIO18 | 1kΩ+2.2kΩ → GPIO36 | GND bus |
| Right | 5V bus | GPIO19 | 1kΩ+2.2kΩ → GPIO39 | GND bus |

### 2. Sharp GP2Y0A51SK0F IR Cliff Sensors (×2)

Each Sharp IR sensor has a 3-pin JST ZH (1.5mm pitch) connector:

| Wire Color | Pin | Connect To |
|------------|-----|------------|
| Red | VCC | 5V bus |
| Black | GND | GND bus |
| Yellow/White | Vo (analog output) | ESP32 ADC pin directly |

**IMPORTANT: Add a 10μF electrolytic capacitor between VCC and GND, as close to each sensor as possible.**
The sensor draws pulsed current that destabilizes the power rail without it.

```
5V bus ──┬── Red wire (VCC)
         │
       10μF (+)  ← Place close to sensor
         │
GND bus ──┬── Black wire (GND)
         │    └── 10μF (-)
         │
ESP32 ────── Yellow wire (Vo) → GPIO32 (front) or GPIO33 (rear)
```

**Connector note:** The JST ZH is 1.5mm pitch — NOT the common 2.0mm JST PH.
You may need specific JST ZH cables, or solder wires directly to the sensor board.

**ADC configuration (firmware side):**
- ADC1 channel, 11dB attenuation (0–3.3V range on ESP32-WROOM-32)
- Sensor output: ~0.25V at 15cm, ~2.4V at 2cm
- Output is non-linear (proportional to 1/distance)
- Objects closer than 2cm give DECREASING voltage (blind spot)

### 3. Yahboom 4-Channel IR Tracking Sensor (×1)

**Power at 3.3V** (not 5V) to get 3.3V-level outputs without needing level shifters.

| Yahboom Pin | Connect To |
|-------------|------------|
| VCC | 3.3V bus |
| GND | GND bus |
| X1 | GPIO4 |
| X2 | GPIO13 |
| X3 | GPIO14 |
| X4 | GPIO27 |

No pull-ups needed (10kΩ pull-ups to VCC are already onboard).

**Output logic:**
- LOW = reflective surface detected (floor present, LED ON on module)
- HIGH = dark surface or void/cliff (no floor, LED OFF on module)

**Calibration:**
After mounting, use the 4 onboard potentiometers (SW1–SW4) to adjust
sensitivity per channel. Turn each pot until the indicator LED just turns ON
when the sensor faces the floor at the mounted height.

### 4. LED Flashlight Breakout (×1)

| LED Pin | Connect To |
|---------|------------|
| R | GPIO25 |
| G | GPIO26 |
| B | GPIO23 |
| GND | GND bus |

If the breakout board does NOT have onboard current-limiting resistors,
add a 100–220Ω resistor in series with each R/G/B line.

The firmware will use LEDC PWM (8-bit, 5kHz) for smooth dimming control.

---

## Bill of Materials (Additional Parts Needed)

| Part | Qty | Purpose |
|------|-----|---------|
| 1kΩ resistor | 4 | HC-SR04 ECHO voltage dividers |
| 2.2kΩ resistor | 4 | HC-SR04 ECHO voltage dividers |
| 10μF electrolytic capacitor | 2 | Sharp IR sensor bypass (MANDATORY) |
| JST ZH 1.5mm 3-pin cable | 2 | Sharp IR connectors (or solder directly) |
| Micro-USB cable | 1 | ESP32 to Pi (data cable, not power-only) |
| Breadboard or proto board | 1 | Mounting and connections |
| Jumper wires (M-F, M-M) | ~30 | Sensor connections |

**You should already have:** ESP32-DevKitV1, 4× HC-SR04, 2× Sharp GP2Y0A51SK0F,
1× Yahboom IR tracker, 1× LED flashlight breakout.

---

## USB Device Setup (Pi Side)

The ESP32-DevKitV1 uses a CH340 USB-UART chip (same as the motor ESP32).
To distinguish them, add a udev rule on the Pi:

```bash
# /etc/udev/rules.d/99-rovac-esp32.rules
# Motor ESP32 (existing)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", \
  ATTRS{serial}=="<MOTOR_SERIAL>", SYMLINK+="esp32_motor", MODE="0666"

# Sensor Hub ESP32 (new — fill in serial after first plug-in)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", \
  ATTRS{serial}=="<SENSOR_HUB_SERIAL>", SYMLINK+="sensor_hub", MODE="0666"
```

To find the serial number after plugging in:
```bash
udevadm info -a /dev/ttyUSBx | grep serial
```

---

## Physical Mounting Recommendations

```
            FRONT
    ┌─────────────────────┐
    │   [HC-SR04 Front]   │  ← Center of front edge, facing forward
    │   [Sharp IR Front]  │  ← Below front HC-SR04, angled down 45° toward floor
    │                     │
    │ [HC-SR04    HC-SR04]│  ← Left/right centered on side edges
    │  Left]      Right]  │
    │                     │
    │ [Yahboom Tracker]   │  ← Underneath, facing down, ~10mm from floor
    │                     │
    │   [Sharp IR Rear]   │  ← Below rear HC-SR04, angled down 45° toward floor
    │   [HC-SR04 Rear]    │  ← Center of rear edge, facing backward
    └─────────────────────┘
            REAR

    ESP32 DevKitV1: Mount on top deck, accessible USB port toward rear
    LED Flashlight: Mount on top, visible from all sides
```

**HC-SR04 mounting**: Sensors should be mounted with both transducers
(the two "eyes") horizontal and facing outward. The beam is ~30° cone.

**Sharp IR cliff sensors**: Angle downward 30–45° so they see the floor
~5–10cm ahead of the robot. At 10mm mounting height, they detect drops
within their 2–15cm range.

**Yahboom tracker**: Mount flat on the underside, ~5–15mm above the floor.
Closer = stronger signal but may scrape on bumps.
