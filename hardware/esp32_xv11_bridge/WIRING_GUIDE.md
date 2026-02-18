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
| TIP120 Darlington Transistor | Motor switching |
| 1KΩ Resistor | Base current limiting |
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
│    ┌─────────────────┐      ┌─────────┐        │              │            │
│    │ MOTOR CONNECTOR │      │ TIP120  │        │              │            │
│    │    (2 wires)    │      │  (front │        │              │            │
│    │                 │      │   view) │        │              │            │
│    │  Red  (Motor+) ●┼──┬───┤         │        │              │            │
│    │                 │  │   │  B C E  │        │              │            │
│    │                 │  │   └──┬─┬─┬──┘        │              │            │
│    │                 │  │      │ │ │           │              │            │
│    │  Black(Motor-) ●┼──┼──────┼─┘ │           │              │            │
│    │                 │  │      │   └───────────┼─● GND        │            │
│    └─────────────────┘  │      │               │              │            │
│                         │    [1KΩ]             │              │            │
│                         │      │               │              │            │
│      ┌────────┐         │      └───────────────┼─● GPIO25     │            │
│      │ 1N4004 │         │                      │    (PWM)     │            │
│      │ DIODE  │         │                      │              │            │
│      │  ┬──┬  │         │                      └──────────────┘            │
│      │  │K │A │◄────────┘                                                  │
│      │  │  │  │         (Cathode to Motor+, Anode to Motor-)               │
│      │  │  └──┼─────────── to Motor Black (via TIP120 Collector)           │
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

### Motor Connector (via TIP120)

| Connection | From | To |
|------------|------|-----|
| Motor Power | Motor Red (+) | ESP32 5V |
| Motor Control | Motor Black (-) | TIP120 Collector |
| Transistor Base | 1KΩ Resistor | ESP32 GPIO25 |
| Transistor Ground | TIP120 Emitter | ESP32 GND |
| **Flyback Diode** | 1N4004 Cathode (stripe) | Motor Red (+) |
| **Flyback Diode** | 1N4004 Anode | Motor Black (-) |

## TIP120 Pinout

```
      TIP120 (TO-220 package)
      Front view (flat side facing you)
      Metal heatsink tab on back

            ┌───────────┐
            │           │
            │  TIP120   │
            │           │
            └─────┬─────┘
                 │││
                 ││└── EMITTER (E) - Right  → GND
                 │└─── COLLECTOR (C) - Middle → Motor Black (-)
                 └──── BASE (B) - Left → 1KΩ → GPIO25
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
    Motor Black (-) ─┴──── TIP120 Collector
```

The diode conducts when the motor is switched off, safely dissipating the back-EMF.

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

### Step 2: TIP120 Motor Driver

1. Place TIP120 with flat side facing you
2. Connect **TIP120 Emitter (right)** → ESP32 **GND**
3. Connect **TIP120 Collector (middle)** → Motor **Black (-)**
4. Connect **TIP120 Base (left)** → **1KΩ resistor** → ESP32 **GPIO25**

### Step 3: Motor Power

1. Connect Motor **Red (+)** → ESP32 **5V**

### Step 4: Flyback Diode (IMPORTANT!)

1. Connect **1N4004 Cathode** (stripe end) → Motor **Red (+)** / 5V rail
2. Connect **1N4004 Anode** → Motor **Black (-)** / TIP120 Collector

### Step 5: Verify Before Power

- [ ] All 4 main connector wires connected
- [ ] TIP120 orientation correct (E-C-B from right to left)
- [ ] 1KΩ resistor between Base and GPIO25
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
| Motor doesn't spin | TIP120 wiring wrong | Check E-C-B pins |
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
