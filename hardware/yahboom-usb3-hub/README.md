# Yahboom 4-Port USB 3.0 Hub for Raspberry Pi

## Overview

This is a powered USB 3.0 hub designed specifically for robotics and single-board computer applications. It provides 4 USB 3.0 ports with external power input options, allowing high-power USB devices to operate reliably without drawing from the Pi's limited USB power budget.

**Purchase Link:** [Amazon - B09Y5S19LY](https://www.amazon.com/dp/B09Y5S19LY)

## Key Specifications

| Specification | Value |
|---------------|-------|
| USB Standard | USB 3.0 (backward compatible 2.0/1.1) |
| Output Ports | 4x USB 3.0 Type-A |
| Input Port | 1x USB 3.0 Type-A (to host) |
| Data Speed | Up to 5 Gbps (500 MB/s) |
| Max Total Current | 5A |
| Controller Chip | VL817 |

## Power Input Options

The hub supports three power input methods:

| Connector | Voltage | Use Case |
|-----------|---------|----------|
| USB-A (data cable) | 5V | Low-power devices only |
| Micro-USB | 5V | Moderate power needs |
| DC5.5×2.5 / XH2.54 | 9-24V | High-power devices, robotics |

**Note:** For robotics use with multiple USB devices, use the 9-24V DC input to ensure adequate power.

## Protection Features

| Protection | Description |
|------------|-------------|
| Overcurrent | Protects against excessive draw |
| Short Circuit | Prevents damage from shorts |
| Reverse Polarity | Protects against wrong power connection |
| Per-Port Protection | Each port independently protected |

## Features

- **Power Switch:** Physical switch to power cycle USB devices without unplugging
- **Per-Port LED:** Individual status indicator for each USB port
- **Driver-Free:** Plug-and-play on all major OS (Win7/8/10/11, Linux, Ubuntu, macOS)
- **Mounting Holes:** Compatible with Pi 4B/3B+/3B and Jetson Nano standoffs

## VL817 Controller Chip

The VL817 is a USB 3.0 hub controller from VIA Labs:
- USB 3.0 SuperSpeed (5 Gbps)
- 4 downstream ports
- USB Battery Charging 1.2 support
- Low power consumption
- Stable, reliable data transmission

## Wiring for ROVAC

### Power Connection (Recommended)

For robotics use, power the hub from your robot's battery:

```
12V Battery
    │
    └──► DC5.5×2.5 or XH2.54 connector ──► USB Hub
                                              │
              Pi 5 USB 3.0 Port ◄─────────────┘ (data cable)
```

### USB Data Connection

Connect the hub to the Raspberry Pi 5:

```
USB Hub (Type-A out) ──► Pi 5 USB 3.0 Port (blue port)
```

Use a short, high-quality USB 3.0 cable for best performance.

### Complete Setup

```
12V Robot Battery
    │
    ├──► Yahboom ROS Expansion Board (motors, power to Pi)
    │
    └──► USB Hub DC Input (9-24V)
              │
              ├──► USB Port 1: XV11 LIDAR (if USB adapter)
              ├──► USB Port 2: Camera
              ├──► USB Port 3: Additional sensors
              └──► USB Port 4: Spare
              │
              └──► Data cable to Pi 5 USB 3.0 port
```

## Use Cases for ROVAC

### 1. Camera Connection
USB cameras often draw significant power. The powered hub ensures stable video streaming.

### 2. USB-to-Serial Adapters
Connect multiple serial devices (LIDAR, motor controllers) via USB-serial adapters.

### 3. External Storage
For logging sensor data or storing maps, connect USB drives.

### 4. Wireless Adapters
WiFi or Bluetooth dongles for extended range.

### 5. Development/Debug
Connect keyboard, mouse, or other peripherals during development.

## Comparison with Pi 5 Native USB

| Aspect | Pi 5 Native USB | With Yahboom Hub |
|--------|----------------|------------------|
| Total Ports | 4 (2x USB 2.0, 2x USB 3.0) | 4 additional USB 3.0 |
| Power Budget | Shared with Pi | Independent external power |
| High-Power Devices | May cause issues | Fully supported (5A total) |
| Hot-Swap | Always on | Switch for power cycling |
| Protection | Basic | Full protection suite |

## Mounting

The hub includes mounting hardware compatible with:
- Raspberry Pi 4B/3B+/3B mounting holes
- Jetson Nano mounting pattern
- Custom chassis mounting

**Tip:** Mount the hub close to the Pi to keep USB cables short for best signal integrity.

## LED Indicators

| LED | Status | Meaning |
|-----|--------|---------|
| Power | On | Hub powered |
| Port 1-4 | On | Device connected and active |
| Port 1-4 | Blinking | Data transfer in progress |

## OS Compatibility

- **Linux/Ubuntu:** Native support, no drivers needed
- **Raspberry Pi OS:** Fully compatible
- **Windows 7/8/10/11:** Automatic driver installation
- **macOS:** Native support

## Troubleshooting

### Devices not recognized
1. Check power connection (use external 9-24V for high-power devices)
2. Try different USB port on the hub
3. Use power switch to reset

### Slow transfer speeds
1. Ensure USB 3.0 cable is used (not USB 2.0)
2. Connect to Pi's USB 3.0 port (blue)
3. Check for interference from nearby electronics

### Power issues
1. Use external power input for multiple devices
2. Don't exceed 5A total draw
3. Check protection LED indicators

## Resources

- **Product Page:** [Yahboom USB Hub](https://category.yahboom.net/products/usb-hub)
- **Support:** support@yahboom.com

## Notes for ROVAC Integration

1. **Primary Use:** Expand USB capacity for sensors and peripherals
2. **Power:** Use 12V from robot battery via DC input
3. **Mounting:** Position near Pi 5 for short cable runs
4. **Benefits:**
   - Eliminates USB power issues
   - Clean cable management
   - Easy device hot-swap with power switch
   - Per-port status monitoring
