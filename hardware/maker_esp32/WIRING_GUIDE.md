# ROVAC Maker-ESP32 Wiring Guide

## Board: NULLLAB Maker-ESP32 (ESP32-WROOM-32E, Rev V3.1)

- **Motor Driver**: 4x Toshiba TB67H450FNG (3.5A each, 2-pin control)
- **USB Chip**: CH340 (vendor `1a86:7523`)
- **MAC**: `80:f3:da:8e:dc:1c`
- **Power Input**: 6–16V DC (5.5mm × 2.1mm barrel jack, center positive)
- **OLED**: 128×32 SSD1306 I2C at address 0x3C
- **RGB LEDs**: 4x WS2812 on GPIO16

## Board Orientation

Hold the board with the **Micro USB** and **DC Jack at the top edge**:

```
                        TOP EDGE
    ┌──────────────────────────────────────────────┐
    │  [FW HDR]    [PWR SW]   [Micro USB]  [DC JACK]│
    │                                                │
    │ IO34─┐                              ┌─UART TX │
    │ IO35─┤                              ├─UART RX │
    │ 3.3V─┤                              │         │
    │  GND─┤      ┌──────────────┐    ┌───┤ I2C x5  │
    │ Servo─┤     │   ESP32      │    │SCL├─GPIO22  │
    │  25  ─┤     │  WROOM-32E   │    │SDA├─GPIO21  │
    │  26  ─┤     │              │    │   │         │
    │  32  ─┤     └──────────────┘    │   ├─[OLED]  │
    │  33  ─┤                         │   │ G V SCL SDA
    │ 3.3V─┤     [4 x RGB LEDs]      │   │         │
    │  GND─┤      (GPIO16)           │   │ SPI HDR │
    │ IO36─┤                         │3.3├─GPIO5   │
    │ IO39─┤                         │GND│         │
    │      │                         │3.3├─GPIO18  │
    │      │                         │GND│         │
    │      │                         │3.3├─GPIO19  │
    │      │                         │GND│         │
    │      │                         │3.3├─GPIO23  │
    │      │                         │GND│         │
    │      │                              │         │
    │  ┌───┴──── MOTOR AREA (bottom) ─────┴───┐     │
    │  │ M4  M3  [SCREW TERMS ×5]  M2  M1    │     │
    │  │ PH  PH   ▫▫ ▫▫ ▫▫ ▫▫ ▫▫  PH  PH    │     │
    │  │         [DIP SWITCH]                  │     │
    │  └──────────────────────────────────────┘     │
    └──────────────────────────────────────────────┘
                       BOTTOM EDGE
```

## Pin Assignment Summary

| Signal | GPIO | Board Location | Notes |
|--------|------|----------------|-------|
| Left Motor IN1 | 27 | M1 screw terminal (via TB67H450FNG) | Auto-routed by driver chip |
| Left Motor IN2 | 13 | M1 screw terminal (via TB67H450FNG) | Auto-routed by driver chip |
| Right Motor IN1 | 4 | M2 screw terminal (via TB67H450FNG) | Auto-routed by driver chip |
| Right Motor IN2 | 2 | M2 screw terminal (via TB67H450FNG) | Auto-routed by driver chip |
| Left Encoder A (H1) | **5** | SPI header, 1st group | PCNT hardware decoder |
| Left Encoder B (H2) | **18** | SPI header, 2nd group | PCNT hardware decoder |
| Right Encoder A (H1) | **19** | SPI header, 3rd group | PCNT hardware decoder |
| Right Encoder B (H2) | **23** | SPI header, 4th group | PCNT hardware decoder |
| OLED SDA | 21 | OLED header (4-pin: G V SCL SDA) | I2C, 128×32 SSD1306 |
| OLED SCL | 22 | OLED header | I2C |
| RGB LEDs | 16 | Onboard (no wiring) | 4x WS2812, RMT driver |
| DIP Switch | 12, 14, 15, 17 | Bottom center | All set to IO position |

### Unused Motor Pins (M3/M4, disabled by DIP switch)

| Signal | GPIO | Notes |
|--------|------|-------|
| M3 IN1 | 17 | DIP switch → IO position |
| M3 IN2 | 12 | DIP switch → IO position |
| M4 IN1 | 14 | DIP switch → IO position |
| M4 IN2 | 15 | DIP switch → IO position |

### Other Available Pins

| GPIO | Location | Capability |
|------|----------|------------|
| 25, 26, 32, 33 | Servo headers (left side) | PWM output (also usable as GPIO) |
| 34, 35, 36, 39 | IO headers (left side) | **Input only**, no pull-up/pull-down |
| TX (1), RX (3) | UART header (right side) | Default Serial UART |

## Connection Details

### 1. Power — DC Jack

| Wire | Destination |
|------|-------------|
| Battery 12V+ | DC jack **center pin** |
| Battery GND | DC jack **outer barrel** |

- Accepted range: **6–16V DC** (5.5mm × 2.1mm barrel plug)
- Powers ESP32 (via onboard DC-DC → 5V → 3.3V) AND motor drivers (VIN direct)
- Power switch on top edge must be **ON**

### 2. Left Motor → M1 Screw Terminal

Location: **Bottom-right** of motor area, next to M1 PH2.0 connector.

| Wire | Destination |
|------|-------------|
| Motor wire A | M1 screw terminal pin 1 |
| Motor wire B | M1 screw terminal pin 2 |

- Driven by TB67H450FNG via GPIO27 (IN1) + GPIO13 (IN2)
- If motor spins backward → swap direction in firmware (no rewiring needed)

### 3. Right Motor → M2 Screw Terminal

Location: Just to the **left of M1**, also bottom-right area.

| Wire | Destination |
|------|-------------|
| Motor wire A | M2 screw terminal pin 1 |
| Motor wire B | M2 screw terminal pin 2 |

- Driven by TB67H450FNG via GPIO4 (IN1) + GPIO2 (IN2)

### 4. Left Encoder → SPI Header (right side of board)

Each SPI header group is a 3-pin column: **3.3V (top) — Signal (middle) — GND (bottom)**.

| Encoder Wire | Destination | Header Group |
|-------------|-------------|--------------|
| Encoder VCC | **3.3V** pin | GPIO5 group (top pin) |
| Encoder GND | **GND** pin | GPIO5 group (bottom pin) |
| Encoder H1 (Channel A) | **GPIO5** | GPIO5 group (middle pin) |
| Encoder H2 (Channel B) | **GPIO18** | GPIO18 group (middle pin) |

### 5. Right Encoder → SPI Header

| Encoder Wire | Destination | Header Group |
|-------------|-------------|--------------|
| Encoder VCC | **3.3V** pin | GPIO19 group (top pin) |
| Encoder GND | **GND** pin | GPIO19 group (bottom pin) |
| Encoder H1 (Channel A) | **GPIO19** | GPIO19 group (middle pin) |
| Encoder H2 (Channel B) | **GPIO23** | GPIO23 group (middle pin) |

### 6. OLED Display (128×32 SSD1306)

Plugged into the dedicated 4-pin OLED header on the right side of the board.

| OLED Pin | Board Pin |
|----------|-----------|
| G (GND) | GND |
| V (VCC) | 3.3V |
| SCL | GPIO22 |
| SDA | GPIO21 |

### 7. USB to Raspberry Pi

- **Micro USB** on Maker-ESP32 → Pi USB port
- Device path: `/dev/ttyUSB0` (CH340, vendor `1a86:7523`)
- Baud rate: 115200

### 8. DIP Switch

All 4 positions set to **IO** (away from Motor side). This disables M3/M4 motor drivers and frees GPIO 12, 14, 15, 17 as general-purpose IO.

## Motor Wire Identification (JGB37-520R60-12)

The Hiwonder JGB37-520R60-12 motors have a **PH2.0 6-pin connector** with 6 wires:
- 2 wires: Motor power (to screw terminals)
- 2 wires: Encoder power — VCC and GND (to 3.3V and GND on SPI header)
- 2 wires: Encoder signals — H1 and H2 (to GPIO pins on SPI header)

### Identifying Wires with a Multimeter

1. **Motor pair**: Set to resistance (Ω). Test all wire pairs — the two with **low resistance (2–10Ω)** are motor power.
2. **Encoder power**: Of the remaining 4, connect 3.3V + GND to a candidate pair. Spin the motor shaft by hand while measuring the other 2 wires. If voltage toggles (0V ↔ 3.3V), you found the correct power pair.
3. **Signal A vs B**: Both toggle when spinning, with a phase offset. If encoder counts backward in testing, swap A/B in firmware.

### Common Wire Colors (verify with multimeter — colors vary by batch!)

| Wire Color | Function | Connect To |
|------------|----------|------------|
| Red | Motor + | M1 or M2 screw terminal |
| White | Motor − | M1 or M2 screw terminal |
| Green | Encoder VCC | 3.3V on SPI header |
| Black | Encoder GND | GND on SPI header |
| Yellow | Encoder A (H1) | GPIO5 (left) or GPIO19 (right) |
| Blue | Encoder B (H2) | GPIO18 (left) or GPIO23 (right) |

## TB67H450FNG Motor Driver Notes

Unlike the L298N (3-pin: ENA + IN1 + IN2), the TB67H450FNG uses **2-pin control**:

| Action | IN1 (GPIO) | IN2 (GPIO) |
|--------|-----------|-----------|
| Forward | PWM | LOW |
| Reverse | LOW | PWM |
| Brake | HIGH | HIGH |
| Coast (stop) | LOW | LOW |

- Max current: **3.5A per channel** (vs L298N's 2A)
- Low voltage drop: ~0.5V (vs L298N's ~2V)
- No separate enable pin needed — PWM duty cycle controls speed directly

## Schematic Reference

- Full KiCad schematic: `maker-esp32/maker-esp32.pdf` (4 pages: Index, Power, ESP32 MainBoard, Motor)
- Board diagram: `maker-esp32/picture/esp32_pic.png`
- 3D model: `maker-esp32/maker-esp32.step`

### Motor Driver Circuit (from schematic page 4)

```
M1: U10 (TB67H450FNG) — GPIO27 → IN1, GPIO13 → IN2 → OUT1/OUT2 → M1 terminals
M2: U9  (TB67H450FNG) — GPIO4  → IN1, GPIO2  → IN2 → OUT1/OUT2 → M2 terminals
M3: U8  (TB67H450FNG) — GPIO17 → IN1, GPIO12 → IN2 → OUT1/OUT2 → M3 terminals
M4: U7  (TB67H450FNG) — GPIO14 → IN1, GPIO15 → IN2 → OUT1/OUT2 → M4 terminals
```

## Troubleshooting

### Motor doesn't spin
1. Check power switch is ON (top edge of board)
2. Check DC jack has 6–16V (measure with multimeter)
3. Verify motor wires are in the correct screw terminal (M1 or M2, not M3/M4)
4. Confirm DIP switch doesn't affect M1/M2 (it only controls M3/M4)
5. Test motor directly: touch motor wires to battery — does it spin?

### Encoder reads zero
1. Check encoder VCC is on 3.3V (not 5V — Hall sensors work at 3.3V)
2. Check encoder GND is connected
3. Spin motor by hand — encoder count should change
4. Verify signal wires are on the correct GPIO (5/18 for left, 19/23 for right)
5. Check for loose jumper wire connections on SPI header

### OLED blank
1. Confirm 4-pin header orientation: G V SCL SDA (left to right)
2. I2C address: 0x3C (128×32 SSD1306)
3. Run I2C scan in firmware to detect device

### USB not detected on Pi
1. CH340 driver should be built into Linux kernel
2. Check: `ls /dev/ttyUSB*` on Pi
3. Vendor:Product = `1a86:7523`
4. Try different USB cable (some are charge-only, no data)

## Version History

| Date | Change |
|------|--------|
| 2026-03-10 | Initial wiring for ROVAC on Maker-ESP32 (replacing ESP32 DevKitV1 + L298N) |
