# GeeekPi GPIO Screw Terminal Block Breakout Board HAT

## Overview

This is a GPIO breakout board that converts the Raspberry Pi's 40-pin header into easy-to-use screw terminals. It simplifies wiring for robotics projects by eliminating the need for soldering or crimping Dupont connectors, and includes LED indicators to show GPIO status.

**Purchase Link:** [Amazon - B08GKQMC72](https://www.amazon.com/dp/B08GKQMC72)

## Key Specifications

| Specification | Value |
|---------------|-------|
| Terminal Block Pitch | 3.5mm |
| Wire Gauge | 16-26 AWG |
| Stripping Length | 5mm |
| GPIO Pins | All 40 pins broken out |
| LED Indicators | Yes, color-coded |
| Pass-through Header | Yes (upper male GPIO) |

## Compatibility

- Raspberry Pi 5 ✓
- Raspberry Pi 4B ✓
- Raspberry Pi 3B+ ✓
- Raspberry Pi 3B ✓
- Raspberry Pi 2B ✓
- Raspberry Pi B+ ✓
- Pi Zero W ✓
- Pi Zero 2 W ✓

**Note:** Compatible with all 40-pin Raspberry Pi models.

## LED Status Indicators

The board has LED indicators for each GPIO pin. LED colors indicate pin function:

| LED Color | Pin Type | Pins |
|-----------|----------|------|
| Red | 5V Power | Pins 2, 4 |
| Pink | 3.3V Power | Pins 1, 17 |
| Dark Blue | Special Function | I2C, SPI, UART |
| Light Blue | Regular GPIO | General purpose pins |

The LED positions correspond to the 2×20 pin layout of the GPIO header.

## GPIO Pinout Reference

```
                    3.3V (1)  (2)  5V
             SDA1 / GPIO2 (3)  (4)  5V
             SCL1 / GPIO3 (5)  (6)  GND
                   GPIO4 (7)  (8)  GPIO14 / TXD
                     GND (9)  (10) GPIO15 / RXD
                  GPIO17 (11) (12) GPIO18 / PCM_CLK
                  GPIO27 (13) (14) GND
                  GPIO22 (15) (16) GPIO23
                    3.3V (17) (18) GPIO24
        MOSI / GPIO10 (19) (20) GND
        MISO / GPIO9  (21) (22) GPIO25
        SCLK / GPIO11 (23) (24) GPIO8 / CE0
                  GND (25) (26) GPIO7 / CE1
        ID_SD / GPIO0 (27) (28) GPIO1 / ID_SC
                GPIO5  (29) (30) GND
                GPIO6  (31) (32) GPIO12
               GPIO13  (33) (34) GND
      PWM1 / GPIO19    (35) (36) GPIO16
               GPIO26  (37) (38) GPIO20
                  GND  (39) (40) GPIO21
```

## Wiring Guide

### Connecting Wires to Screw Terminals

1. **Strip wire:** Remove 5mm of insulation
2. **Insert wire:** Place bare wire into terminal hole
3. **Tighten screw:** Secure with provided screwdriver
4. **Verify:** Gentle tug to confirm secure connection

### Wire Gauge Recommendations

| Application | Recommended Gauge |
|-------------|-------------------|
| Signal wires | 22-26 AWG |
| Power (moderate) | 20-22 AWG |
| Power (high current) | 16-18 AWG |

**Note:** For high current applications (5V power distribution), use heavier gauge wire.

## Use Cases for ROVAC

### 1. Sensor Connections

```
HC-SR04 Ultrasonic (example):
├── VCC ──► Terminal 2 or 4 (5V)
├── GND ──► Terminal 6, 9, 14, 20, 25, 30, 34, or 39
├── TRIG ──► Any GPIO terminal (e.g., GPIO17 - Terminal 11)
└── ECHO ──► Any GPIO terminal (e.g., GPIO27 - Terminal 13)
```

### 2. I2C Devices

```
I2C Device:
├── VCC ──► Terminal 1 (3.3V) or 2 (5V)
├── GND ──► Any GND terminal
├── SDA ──► Terminal 3 (GPIO2)
└── SCL ──► Terminal 5 (GPIO3)
```

### 3. UART Devices (when not using XV11 LIDAR)

```
Serial Device:
├── VCC ──► Appropriate voltage terminal
├── GND ──► Any GND terminal
├── TXD ──► Terminal 10 (GPIO15 / RXD)
└── RXD ──► Terminal 8 (GPIO14 / TXD)
```

### 4. PWM Outputs (Servos, LEDs)

```
PWM-capable pins:
├── GPIO12 (Terminal 32) - PWM0
├── GPIO13 (Terminal 33) - PWM1
├── GPIO18 (Terminal 12) - PWM0
└── GPIO19 (Terminal 35) - PWM1
```

## Package Contents

- 1× GPIO Screw Terminal HAT
- 4× M2.5 Copper standoffs
- 4× M2.5 Screws
- 4× M2.5 Nuts
- 1× Screwdriver
- 1× GPIO pinout adhesive label

## Installation

### Mounting on Raspberry Pi

1. Attach M2.5 standoffs to Pi's mounting holes
2. Align the 40-pin header with the Pi's GPIO
3. Press down firmly to seat the connector
4. Secure with screws from above

### Pass-through Capability

The board includes a male GPIO header on top, allowing:
- Jumper wire connections
- Additional HATs (may need GPIO riser for clearance)
- Mixed connection methods

## Integration with Other ROVAC Hardware

### With Yahboom ROS Expansion Board V3.0

The ROS Expansion Board communicates via UART. You can use this terminal HAT to:
- Easily connect UART pins (GPIO14/15) to the expansion board
- Add additional sensors without complex wiring
- Debug with multimeter probes on screw terminals

### Suggested Configuration

```
Pi 5 GPIO Header
    │
    └──► GeeekPi Terminal HAT
              │
              ├──► UART (terminals 8, 10) ──► Yahboom ROS Board
              ├──► I2C (terminals 3, 5) ──► Additional sensors
              ├──► GPIO ──► Buttons, switches, indicators
              └──► Power distribution ──► External devices
```

### Consideration: HAT Stacking

If using multiple HATs:
1. This terminal HAT should be on top (for wire access)
2. Other HATs below (connected via pass-through)
3. May need GPIO riser/extender for clearance

## LED Debugging

The onboard LEDs are useful for:
- Verifying pin states without multimeter
- Debugging GPIO control code
- Confirming power rail activity
- Visual feedback during development

**Example:** When you toggle GPIO17 HIGH, the corresponding light blue LED at terminal 11 will illuminate.

## Resources

- **Wiki:** https://wiki.52pi.com/index.php/GPIO_Screw_Terminal_Hat_SKU:_EP-0129
- **Similar Product (52Pi):** https://52pi.com/products/52pi-gpio-screw-terminal-hat-for-raspberry-pi

## Notes for ROVAC Integration

1. **Primary Use:** Simplify sensor and peripheral wiring
2. **Benefits:**
   - No soldering required
   - Easy to add/remove components
   - Visual LED feedback for debugging
   - Secure screw connections for mobile robots
3. **Position:** Mount on top of any HAT stack for wire access
4. **Wire management:** Use appropriate gauge wires and route cleanly

## Comparison with Dupont Connectors

| Aspect | Dupont Connectors | Screw Terminal HAT |
|--------|-------------------|-------------------|
| Connection Time | Fast | Moderate |
| Security | Can vibrate loose | Very secure |
| Wire Types | Crimped only | Any stripped wire |
| Modification | Easy swap | Screwdriver needed |
| Mobile Robot Use | May disconnect | Reliable |
| Debugging | Difficult | Easy (LED + terminals) |

## Important Considerations

- **Current Limits:** GPIO pins are rated for ~16mA each. Don't exceed this.
- **5V Caution:** GPIO pins are 3.3V logic. Never connect 5V to GPIO inputs directly.
- **Power Distribution:** The 5V and 3.3V terminals share Pi's power rails. High current draw should use external regulation.
- **Static Sensitivity:** Handle the board properly to avoid ESD damage.
