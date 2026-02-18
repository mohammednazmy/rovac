# USB-Lidar Module (Neato XV-11)

A USB-connected LiDAR module using the Neato XV-11 sensor with Arduino Nano bridge for robotics applications.

## Features

- Neato XV-11 LiDAR sensor (360° scanning)
- Arduino Nano USB-to-serial bridge
- Motor speed control via resistor network
- ROS2 integration for ROVAC robot
- Web-based visualization interface

## Quick Start (ROVAC)

The USB-Lidar is pre-configured as a systemd service on the ROVAC Raspberry Pi:

```bash
# Check service status
sudo systemctl status rovac-edge-lidar.service

# View logs
sudo journalctl -u rovac-edge-lidar.service -f

# Restart if needed
sudo systemctl restart rovac-edge-lidar.service
```

**Device symlink:** `/dev/usb_lidar` → USB hub port 4-1.3

## Hardware Setup

### Components

| Component | Description |
|-----------|-------------|
| Neato XV-11 LiDAR | 360° laser scanner from Neato vacuum |
| Arduino Nano | CH340 USB-to-serial bridge |
| 29.5Ω Resistor | Motor speed control (22Ω + 7.5Ω in series) |

### Wiring

```
XV-11 LiDAR               Arduino Nano
┌─────────────┐          ┌─────────────┐
│ Red (Motor+)├────┬─────┤ 5V          │
│             │    │     │             │
│ Black (GND) ├────┼─────┤ GND         │
│             │    │     │             │
│ Brown (TX)  ├────┼─────┤ RX (D0)     │
│             │   [R]    │             │
│ Orange (M-) ├────┘     │             │
└─────────────┘  29.5Ω   └─────────────┘

[R] = 22Ω + 7.5Ω in series for motor speed control
```

### XV-11 Connector Pinout

| Pin | Color | Function |
|-----|-------|----------|
| 1 | Red | Motor + (5V) |
| 2 | Brown | Serial TX (3.3V TTL) |
| 3 | Orange | Motor - (via resistor to GND) |
| 4 | Black | Ground |

## ROS2 Integration

### Systemd Service (ROVAC)

The USB-Lidar runs as a systemd service on the ROVAC robot:

```bash
# Service file: /etc/systemd/system/rovac-edge-lidar.service
# Part of: rovac-edge.target

sudo systemctl status rovac-edge-lidar.service
sudo systemctl restart rovac-edge-lidar.service
sudo journalctl -u rovac-edge-lidar.service -f
```

### Manual Launch

```bash
source /opt/ros/jazzy/setup.bash
source ~/yahboom_tank_ws/install/setup.bash
ros2 run xv11_lidar_python xv11_lidar --ros-args \
  -p port:=/dev/usb_lidar
```

### Published Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/scan` | sensor_msgs/LaserScan | 360° laser scan data |

### LaserScan Message Details

```yaml
header:
  frame_id: "laser_frame"
angle_min: 0.0
angle_max: 6.283185  # 2π radians (360°)
angle_increment: 0.017453  # ~1° per reading
range_min: 0.06  # 6 cm minimum
range_max: 5.0   # 5 m maximum
ranges: [...]    # 360 distance values in meters
intensities: [...] # Signal strength values
```

### ROS2 Usage Examples

```bash
# List topics
ros2 topic list | grep scan

# Check publishing rate
ros2 topic hz /scan

# Echo scan data
ros2 topic echo /scan

# View scan info
ros2 topic info /scan
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `port` | string | `/dev/usb_lidar` | Serial port path |
| `frame_id` | string | `laser_frame` | TF frame ID |
| `baudrate` | int | 115200 | Serial baud rate |

## udev Rules

The device is assigned a stable symlink via udev rules:

```bash
# /etc/udev/rules.d/99-rovac-usb.rules
SUBSYSTEM=="tty", KERNELS=="4-1.3", MODE="0666", GROUP="dialout", SYMLINK+="usb_lidar"
```

This ensures `/dev/usb_lidar` always points to the correct USB port regardless of enumeration order.

## XV-11 Data Protocol

### Serial Settings

- Baud rate: 115200
- Data bits: 8
- Stop bits: 1
- Parity: None

### Packet Format

Each packet is 22 bytes:

```
Byte 0:    0xFA (start byte)
Byte 1:    Index (0xA0 to 0xF9, 90 packets per revolution)
Bytes 2-3: Speed (RPM × 64, little-endian)
Bytes 4-21: 4 readings × 4 bytes each:
  - Bytes 0-1: Distance (mm, little-endian)
  - Bytes 2-3: Signal strength (little-endian)
  - Bit 15 of distance: Invalid flag
  - Bit 14 of distance: Strength warning
```

### Checksum

Last 2 bytes of each packet contain CRC checksum (little-endian).

## Motor Speed Calibration

The XV-11 motor speed is controlled by the resistor value:

| Resistor | Approx RPM | Notes |
|----------|------------|-------|
| 22Ω | ~250 | Too slow, some invalid readings |
| 29.5Ω | ~300 | Optimal (target) |
| 33Ω | ~350 | Acceptable |
| 47Ω | ~400+ | Too fast, may reduce accuracy |

**Current Configuration:** 22Ω + 7.5Ω in series = 29.5Ω

### Checking Motor Speed

The motor speed is reported in the ROS2 logs:

```bash
sudo journalctl -u rovac-edge-lidar.service | grep "Scan rate"
```

Target: 250-350 RPM (4-6 Hz scan rate)

## Web Visualization (Standalone)

For standalone testing without ROS2:

```bash
cd ~/hardware/lidar_usb
python3 src/lidar_web_service.py
```

Access at: `http://<PI_IP>:8080`

## Troubleshooting

### No /scan Data Published

1. Check device exists: `ls -la /dev/usb_lidar`
2. Check service status: `sudo systemctl status rovac-edge-lidar`
3. View logs: `sudo journalctl -u rovac-edge-lidar -n 50`
4. Verify motor is spinning (visible/audible rotation)

### Low Valid Point Count

The XV-11 may report few valid points if:
- Motor speed is incorrect (check resistor values)
- Sensor window is dirty (clean with microfiber cloth)
- No objects in range (empty room)

Check logs for valid point count:
```bash
sudo journalctl -u rovac-edge-lidar | grep "valid points"
```

### Motor Not Spinning

1. Check 5V power connection
2. Verify resistor wiring (Motor- through resistor to GND)
3. Try different resistor values
4. Test motor directly with 5V (briefly)

### Serial Port Issues

1. Check USB connection: `lsusb | grep CH340`
2. Verify permissions: user must be in `dialout` group
3. Check for port conflicts: `sudo lsof /dev/usb_lidar`

### Scan Rate Too Low/High

Adjust resistor value:
- Too slow (<200 RPM): Decrease resistance
- Too fast (>400 RPM): Increase resistance
- Optimal: 250-350 RPM

## Files

```
lidar_usb/
├── src/
│   ├── lidar_driver.py              # Core XV-11 driver
│   ├── lidar_visualizer.py          # Pygame visualization
│   ├── lidar_web_service.py         # Web visualization
│   └── enhanced_lidar_web_service.py
├── docs/
│   ├── README.md                    # This file
│   ├── SYSTEM_SUMMARY.md
│   └── FINAL_DEPLOYMENT_REPORT.md
├── tools/                           # Calibration utilities
├── tests/                           # Test scripts
├── logs/                            # Data logs
└── examples/                        # Usage examples
```

## ROS2 Package Location

The ROS2 node is part of the ROVAC workspace:

```
~/yahboom_tank_ws/src/xv11_lidar_python/
└── xv11_lidar_python/
    └── xv11_lidar_publisher.py
```

## Performance Specifications

| Metric | Value |
|--------|-------|
| Range | 0.06m - 5.0m |
| Angular Resolution | ~1° (360 points/scan) |
| Scan Rate | ~5-10 Hz (at optimal motor speed) |
| Accuracy | ±30mm |
| Field of View | 360° |
