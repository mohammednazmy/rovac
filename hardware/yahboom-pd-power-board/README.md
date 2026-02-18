# Yahboom PD Power Expansion Board for Raspberry Pi 5

## Overview

This is a power regulation/distribution board designed specifically for the Raspberry Pi 5. It converts a wide range of input voltages (6-24V) to a stable 5V/5A output with PD (Power Delivery) protocol support, ensuring the Pi 5 operates at full performance without low-voltage warnings.

**Purchase Link:** [Amazon - B0D3XMLMGW](https://www.amazon.com/dp/B0D3XMLMGW)

## Key Specifications

| Specification | Value |
|---------------|-------|
| Input Voltage | 6-24V DC |
| Output Voltage | 5V (regulated) |
| Output Current | 5A max |
| Output Power | 25W |
| Protocol | PD (Power Delivery) for Pi 5 |
| Weight | ~50g |

## Why This Board?

### Raspberry Pi 5 Power Requirements

The Pi 5 requires:
- **5V at 5A (25W)** for full performance
- **PD protocol** handshake for optimal operation
- Without proper power, you'll see:
  - Low voltage warnings
  - USB port current limiting
  - Throttling and potential freezing
  - Peripheral power restrictions

This board ensures the Pi 5 receives proper power from battery sources commonly used in robotics.

## Protection Features

| Protection | Description |
|------------|-------------|
| Input Reverse Polarity | Prevents damage from wrong battery connection |
| Output Over-current | Protects against shorts and overloads |
| Current Limiting | Prevents excessive draw |
| Over-voltage | Protects against input voltage spikes |
| Over-temperature | Thermal shutdown if overheating |

## Input Interfaces (3 types)

| Connector | Pitch/Size | Use Case |
|-----------|------------|----------|
| KF301-2P | 5.08mm | Screw terminal for battery wires |
| XH2.54-2Pin | 2.54mm | JST-style battery connector |
| DC5.5×2.5 | 5.5mm/2.5mm | Barrel jack for DC adapters |

## Output Interfaces (4 types)

| Connector | Use Case |
|-----------|----------|
| Type-C | Direct to Pi 5 USB-C power input |
| PH2.0-2P | JST-PH style for other boards |
| DC5.5×2.1 | Barrel jack output |
| 6-Pin | Multi-purpose power distribution |

## Wiring for ROVAC

### Battery to Board

```
LiPo Battery (11.1V 3S or 12V)
    │
    └──► KF301-2P Terminal
         ├─ + (Red) ──► V+
         └─ - (Black) ──► GND
```

**Supported Battery Types:**
- 2S LiPo (7.4V nominal) ✓
- 3S LiPo (11.1V nominal) ✓ **Recommended**
- 4S LiPo (14.8V nominal) ✓
- 6S LiPo (22.2V nominal) ✓ (within 24V limit)
- 12V Lead-acid ✓
- 18650 packs (6-24V range) ✓

### Board to Raspberry Pi 5

```
Type-C Output ──► Pi 5 USB-C Power Port
```

Use the included Type-C cable or a quality USB-C cable rated for 5A.

### Additional Power Distribution

The board can simultaneously power other devices:

```
Input (Battery)
    │
    ├──► Type-C ──► Raspberry Pi 5 (5V/5A)
    ├──► PH2.0-2P ──► Small peripherals
    ├──► DC5.5×2.1 ──► External devices
    └──► 6-Pin ──► Custom connections
```

## Stacking with Raspberry Pi 5

The board is designed to stack directly on the Pi 5:

1. Use the included M2.5 copper standoffs
2. Align the mounting holes
3. Secure with screws
4. Connect Type-C cable from board output to Pi 5 power

**Clearance:** Designed to fit within mobile robot chassis height constraints.

## Integration with Other ROVAC Hardware

### With Yahboom ROS Expansion Board V3.0

**Option A: Power Board provides Pi 5 power**
```
Battery ──► PD Power Board ──► Pi 5 (Type-C)
        └──► ROS Expansion Board (direct from battery)
```

**Option B: ROS Expansion Board provides all power**
The Yahboom ROS Expansion Board V3.0 already supports Pi 5 power protocol. If using both boards:
- Use ROS board to power Pi 5 (simpler)
- Use PD Power Board for additional regulated 5V distribution to peripherals

### Recommended Configuration

For ROVAC, the simplest approach:
```
12V Battery
    │
    ├──► Yahboom ROS Expansion Board
    │         ├──► Motors
    │         ├──► Pi 5 (via onboard power)
    │         └──► Servos
    │
    └──► PD Power Board (if needed for extra 5V peripherals)
              └──► Additional 5V devices
```

## Comparison with Current Setup

| Aspect | Current ROVAC | With PD Power Board |
|--------|--------------|---------------------|
| Pi 5 Power | Separate 5V supply | Clean 5V/5A from battery |
| Voltage Warnings | Possible | Eliminated |
| USB Current | May be limited | Full 5A available |
| Battery Types | Limited | 6-24V flexibility |
| Protection | Basic | Full protection suite |

## Compatibility

The board works with:
- **Raspberry Pi 5** (primary target)
- Jetson Nano/Orin
- RDK X3/X5
- K210 boards
- STM32 development boards
- Any 5V device up to 5A

## LED Indicators

| LED | Status | Meaning |
|-----|--------|---------|
| Power | On | Input power present |
| Output | On | 5V output active |
| Fault | On | Protection triggered |

## Resources

- **Product Page:** https://category.yahboom.net/products/power-board-pi5
- **Support Email:** support@yahboom.com

## Notes for ROVAC Integration

1. **Primary Use:** Convert 12V battery to clean 5V/5A for Pi 5
2. **May be redundant if:** Using Yahboom ROS Expansion Board (which has Pi 5 power output)
3. **Useful for:** Additional 5V power distribution, using non-12V batteries
4. **Mounting:** Can stack on Pi 5 or mount separately in chassis

## Important Considerations

- **Not a UPS:** This is a power regulator, not a battery backup. It requires continuous input power.
- **No battery management:** Doesn't charge batteries or monitor battery level
- **Input protection:** While it has reverse polarity protection, always double-check connections
- **Heat dissipation:** May get warm under heavy load; ensure adequate airflow
