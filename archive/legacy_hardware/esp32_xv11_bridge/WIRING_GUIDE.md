# ESP32 XV11 LIDAR Bridge - Wiring Guide

Complete wiring instructions for connecting an XV11 Neato LIDAR to an ESP32 with PWM motor control.

## Overview

The ESP32 provides:
- USB-to-UART bridge for LIDAR data
- PWM motor speed control for optimal RPM
- Single USB connection powers everything

## Components Required

| Component | Purpose |
|-----------|---------|
| ESP32-WROOM-32 DevKit | Main controller |
| XV11 Neato LIDAR | Laser scanner |
| IRLZ44N Logic-Level MOSFET | Motor switching |
| 1KΩ Resistor | Gate series resistor (dampens switching noise) |
| 10KΩ Resistor | Gate pull-down (prevents motor spin during boot) |
| **1N4004 Diode** | **Flyback protection (REQUIRED!)** |
| USB Cable | Power and data |

## Complete Wiring Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│    XV11 LIDAR                                    ESP32 DevKit               │
│    ==========                                    ===========                │
│                                                                             │
│    ┌─────────────────┐                          ┌──────────────┐            │
│    │  MAIN CONNECTOR │                          │              │            │
│    │    (4 wires)    │                          │     USB      │            │
│    │                 │                          │      ↓       │            │
│    │  Red    (5V)  ●─┼──────────────────────────┼─● 5V         │            │
│    │  Black (GND)  ●─┼──────────────────────────┼─● GND        │            │
│    │  Orange (RX)  ●─┼──────────────────────────┼─● GPIO17     │            │
│    │  Brown  (TX)  ●─┼──────────────────────────┼─● GPIO16 ←── │ DATA IN    │
│    │                 │                          │              │            │
│    └─────────────────┘                          │              │            │
│                                                 │              │            │
│    ┌─────────────────┐      ┌──────────┐       │              │            │
│    │ MOTOR CONNECTOR │      │ IRLZ44N  │       │              │            │
│    │    (2 wires)    │      │  (front  │       │              │            │
│    │                 │      │   view)  │       │              │            │
│    │  Red  (Motor+) ●┼──┬───┤          │       │              │            │
│    │                 │  │   │  G D S   │       │              │            │
│    │                 │  │   └──┬─┬─┬───┘       │              │            │
│    │                 │  │      │ │ │            │              │            │
│    │  Black(Motor-) ●┼──┼──────┼─┘ │            │              │            │
│    │                 │  │      │   └────────────┼─● GND        │            │
│    └─────────────────┘  │      │               │              │            │
│                         │    [1KΩ]             │              │            │
│                         │      │               │              │            │
│      ┌────────┐         │      ├───────────────┼─● GPIO25     │            │
│      │ 1N4004 │         │      │               │    (PWM)     │            │
│      │ DIODE  │         │    [10KΩ] (pull-down)│              │            │
│      │  ┬──┬  │         │      │               └──────────────┘            │
│      │  │K │A │◄────────┘      └──── to GND                               │
│      │  │  │  │         (Cathode to Motor+, Anode to Motor-)               │
│      │  │  └──┼─────────── to Motor Black (via IRLZ44N Drain)             │
│      └──┼─────┘                                                            │
│         │                                                                  │
│         └─── Flyback diode REQUIRED to prevent PWM noise!                  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

## Connection Table

### Main Connector (Data + Power)

| XV11 Wire | Color | ESP32 Pin | Function |
|-----------|-------|-----------|----------|
| 5V | Red | **5V** | Powers LIDAR electronics |
| GND | Black | **GND** | Ground |
| RX | Orange | **GPIO17** | Serial TO LIDAR (optional) |
| TX | Brown | **GPIO16** | Serial FROM LIDAR (data) |

### Motor Connector (via IRLZ44N)

| Connection | From | To |
|------------|------|-----|
| Motor Power | Motor Red (+) | ESP32 5V |
| Motor Control | Motor Black (-) | IRLZ44N Drain |
| MOSFET Gate | 1KΩ Resistor | ESP32 GPIO25 |
| MOSFET Source | IRLZ44N Source | ESP32 GND |
| Gate Pull-down | 10KΩ Resistor | IRLZ44N Gate to Source |
| **Flyback Diode** | 1N4004 Cathode (stripe) | Motor Red (+) |
| **Flyback Diode** | 1N4004 Anode | Motor Black (-) |

## IRLZ44N Pinout

```
      IRLZ44N (TO-220 package)
      Front view (flat side facing you)
      Metal heatsink tab on back (connected to Drain)

            ┌───────────┐
            │           │
            │  IRLZ44N  │
            │           │
            └─────┬─────┘
                 │││
                 ││└── SOURCE (S) - Right  → GND
                 │└─── DRAIN (D) - Middle → Motor Black (-)
                 └──── GATE (G) - Left → 1KΩ → GPIO25
                                    └── 10KΩ → GND (pull-down)
```

## Flyback Diode - CRITICAL!

**The 1N4004 diode is essential!** Without it:
- Motor back-EMF creates voltage spikes during PWM switching
- These spikes corrupt the LIDAR serial data
- You'll see intermittent data loss or garbage data

```
Diode Orientation:

    Motor Red (+) ←──┬──── ESP32 5V
                     │
                   ──┴── Cathode (stripe/band side)
                     │
                   ──┬── Anode
                     │
    Motor Black (-) ─┴──── IRLZ44N Drain
```

The diode conducts when the motor is switched off, safely dissipating the back-EMF.

## Why IRLZ44N over TIP120?

The IRLZ44N is a logic-level MOSFET that is a direct upgrade from the TIP120 Darlington transistor:

- **3.3V compatible**: The IRLZ44N is fully driven by ESP32's 3.3V GPIO (Vgs(th) ~1-2V). No level shifting needed.
- **Near-zero voltage drop**: ~0.025V vs the TIP120's ~2V Vce(sat). The motor gets nearly the full 5V supply, improving RPM stability.
- **More efficient, less heat**: Virtually no power wasted in the switching element.
- **10KΩ pull-down required**: Unlike the TIP120 (which has an internal base-emitter resistor), a MOSFET gate floats when the ESP32 GPIO is high-impedance during boot. The 10KΩ pull-down resistor holds the gate low, preventing the motor from spinning uncontrolled during startup.

## ESP32 Pin Reference

```
        ESP32-WROOM-32 DevKit (Top View)

                     USB Port
                ┌──────────────┐
                │   [     ]    │
                │              │
          EN    │ o          o │  D23
          VP    │ o          o │  D22
          VN    │ o          o │  TX0
          D34   │ o          o │  RX0
          D35   │ o          o │  D21
          D32   │ o          o │  GND  ◄── Common Ground
          D33   │ o          o │  D19
          D25 ◄─│ o  (PWM)   o │  D18
          D26   │ o          o │  D5
          D27   │ o          o │  D17  ◄── LIDAR Orange (RX)
          D14   │ o          o │  D16  ◄── LIDAR Brown (TX) - DATA!
          D12   │ o          o │  D4
          GND   │ o          o │  D0
          D13   │ o          o │  D2 (LED)
          SD2   │ o          o │  D15
          SD3   │ o          o │  SD1
          CMD   │ o          o │  SD0
          5V  ◄─│ o          o │  CLK
                │      ◄── LIDAR Power (Red wires)
                └──────────────┘
```

## Step-by-Step Wiring

### Step 1: Main Connector (Data)

1. Connect **Red (5V)** → ESP32 **5V**
2. Connect **Black (GND)** → ESP32 **GND**
3. Connect **Orange (RX)** → ESP32 **GPIO17**
4. Connect **Brown (TX)** → ESP32 **GPIO16**

### Step 2: IRLZ44N Motor Driver

1. Place IRLZ44N with flat side facing you
2. Connect **IRLZ44N Source (right)** → ESP32 **GND**
3. Connect **IRLZ44N Drain (middle)** → Motor **Black (-)**
4. Connect **IRLZ44N Gate (left)** → **1KΩ resistor** → ESP32 **GPIO25**
5. Connect **10KΩ resistor** between **Gate (left)** and **Source (right)** — pull-down

### Step 3: Motor Power

1. Connect Motor **Red (+)** → ESP32 **5V**

### Step 4: Flyback Diode (IMPORTANT!)

1. Connect **1N4004 Cathode** (stripe end) → Motor **Red (+)** / 5V rail
2. Connect **1N4004 Anode** → Motor **Black (-)** / IRLZ44N Drain

### Step 5: Verify Before Power

- [ ] All 4 main connector wires connected
- [ ] IRLZ44N orientation correct (S-D-G from right to left)
- [ ] 1KΩ resistor between Gate and GPIO25
- [ ] 10KΩ pull-down resistor between Gate and Source
- [ ] Flyback diode installed with correct polarity
- [ ] No shorts between 5V and GND

## Testing

### Power On

1. Connect ESP32 USB to Pi
2. Motor should spin up automatically
3. LED blinks fast when data flowing

### Verify RPM

```bash
stty -F /dev/ttyUSB2 115200 raw -echo
echo '!rpm' > /dev/ttyUSB2
cat /dev/ttyUSB2

# Expected: !RPM: Current=~300, Target=300, PWM=xxx, Mode=AUTO
```

### Check Data Flow

```bash
echo '!status' > /dev/ttyUSB2
cat /dev/ttyUSB2

# Expected: Bytes and Packets should be increasing
```

## Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| Motor doesn't spin | IRLZ44N wiring wrong | Check G-D-S pins |
| Motor spins during boot | Missing 10KΩ pull-down | Add 10KΩ Gate-to-Source |
| Data corrupted/intermittent | Missing flyback diode | Add 1N4004 diode |
| No data at all | TX/RX swapped | Brown→GPIO16, Orange→GPIO17 |
| RPM too high/low | Auto mode off | Send `!auto` command |
| ESP32 not detected | USB cable | Try different cable |

## Power Budget

| Component | Current |
|-----------|---------|
| LIDAR Electronics | ~150-200mA |
| LIDAR Motor | ~300-400mA |
| ESP32 | ~50-80mA |
| **Total** | **~500-680mA** |

Use USB 3.0 port or powered hub for reliable operation.
