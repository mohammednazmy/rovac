# ESP32 XV11 LIDAR USB Bridge

A reliable USB-to-UART bridge for the XV11 Neato LIDAR using an ESP32 microcontroller. This project enables seamless integration of salvaged XV11 LIDAR modules with ROS2 robotics systems via USB.

## Overview

The ESP32 XV11 Bridge provides:
- **Rock-solid 115200 baud communication** using hardware UART
- **Full 360° scan coverage** with all 90 angle indices
- **~20 Hz scan rate** for responsive navigation
- **Single-board power solution** - ESP32 powers both LIDAR electronics and motor
- **Plug-and-play USB interface** - appears as standard serial port on host

## Features

| Feature | Description |
|---------|-------------|
| Hardware UART | Uses ESP32's dedicated UART2 for reliable high-speed serial |
| USB Power | Powers entire LIDAR system from single USB connection |
| Status LED | Visual feedback - fast blink when data flowing |
| Debug Commands | Built-in diagnostics via `!id`, `!version`, `!status` |
| ROS2 Compatible | Works with standard `xv11_lidar_python` ROS2 package |

## Hardware Requirements

- **ESP32-WROOM-32 DevKit** (or compatible ESP32 development board)
- **XV11 Neato LIDAR module** (salvaged from Neato robot vacuum)
- **USB cable** (USB-A to Micro-USB for most ESP32 boards)

## Quick Start

### 1. Wire the LIDAR to ESP32

```
LIDAR Main Connector:
  Red (5V)     → ESP32 5V
  Black (GND)  → ESP32 GND
  Orange (RX)  → ESP32 GPIO16
  Brown (TX)   → ESP32 GPIO17

LIDAR Motor Connector:
  Red (Motor)  → ESP32 5V
  Black (GND)  → ESP32 GND
```

### 2. Upload Firmware

```bash
# Using Arduino CLI
arduino-cli compile --fqbn esp32:esp32:esp32 .
arduino-cli upload -p /dev/ttyUSB2 --fqbn esp32:esp32:esp32 .
```

### 3. Connect to Host

Connect ESP32 USB to your Raspberry Pi or computer. The device appears as `/dev/ttyUSB*` (Linux) or `COM*` (Windows).

### 4. Verify Operation

```bash
# Check for XV11 data packets
stty -F /dev/ttyUSB2 115200 raw -echo
timeout 2 cat /dev/ttyUSB2 | xxd | head -10
# Should see 0xFA bytes (XV11 packet markers)
```

## ROS2 Integration

### Using with xv11_lidar_python

```bash
ros2 run xv11_lidar_python xv11_lidar --ros-args \
  -p port:=/dev/ttyUSB2 \
  -p frame_id:=laser_frame
```

### Systemd Service (Raspberry Pi)

```ini
[Service]
ExecStart=/bin/bash -lc 'source /opt/ros/jazzy/setup.bash && \
  ros2 run xv11_lidar_python xv11_lidar --ros-args \
  -p port:=/dev/ttyUSB2 -p frame_id:=laser_frame'
```

## Specifications

| Parameter | Value |
|-----------|-------|
| Baud Rate | 115200 |
| Protocol | XV11 Neato LIDAR (0xFA packets) |
| Scan Rate | ~20 Hz |
| Angular Resolution | 4° (90 readings per rotation) |
| Range | 0.06m - 5.0m |
| Field of View | 360° |
| Power Draw | ~500-600mA @ 5V (from USB) |

## Project Structure

```
esp32_xv11_bridge/
├── esp32_xv11_bridge.ino    # Main firmware
├── README.md                 # This file
├── WIRING_GUIDE.md          # Detailed wiring instructions
├── FIRMWARE.md              # Firmware documentation
└── TROUBLESHOOTING.md       # Common issues and solutions
```

## Debug Commands

Send commands via serial terminal (prefix with `!`):

| Command | Response | Description |
|---------|----------|-------------|
| `!id` | `!DEVICE:ESP32_XV11_BRIDGE` | Device identification |
| `!version` | `!VERSION:1.0.0` | Firmware version |
| `!status` | Statistics | Uptime, bytes forwarded, packet count |
| `!reset` | `!STATS_RESET` | Reset statistics counters |
| `!help` | Command list | Show available commands |

## License

This project is part of the ROVAC robotics platform.

## See Also

- [WIRING_GUIDE.md](WIRING_GUIDE.md) - Detailed wiring diagrams
- [FIRMWARE.md](FIRMWARE.md) - Firmware architecture and customization
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues and solutions
