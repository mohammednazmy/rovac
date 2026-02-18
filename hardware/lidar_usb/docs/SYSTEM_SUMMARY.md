# USB-Lidar System Summary

## Overview

The USB-Lidar module provides 360° laser scanning capability for the ROVAC robot using a repurposed Neato XV-11 LiDAR sensor connected via Arduino Nano USB bridge.

## System Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   XV-11 LiDAR   │────▶│  Arduino Nano   │────▶│  Raspberry Pi 5  │
│   (Sensor)      │ TX  │  (USB Bridge)   │ USB │  (ROS2 Node)     │
└─────────────────┘     └─────────────────┘     └──────────────────┘
                                                         │
                                                         ▼
                                                ┌──────────────────┐
                                                │   /scan Topic    │
                                                │ (LaserScan msg)  │
                                                └──────────────────┘
```

## Current Configuration

| Setting | Value |
|---------|-------|
| Device | `/dev/usb_lidar` |
| USB Port | 4-1.3 (via udev symlink) |
| Baud Rate | 115200 |
| ROS2 Topic | `/scan` |
| Frame ID | `laser_frame` |
| Service | `rovac-edge-lidar.service` |

## Performance Metrics

| Metric | Measured Value |
|--------|----------------|
| Scan Rate | ~5-16 Hz |
| Motor Speed | ~300 RPM |
| Valid Points | 5-50 per scan (varies by environment) |
| Range | 0.06m - 5.0m |

## Integration with ROVAC

The USB-Lidar is part of the ROVAC edge stack:

```bash
# Part of rovac-edge.target
sudo systemctl status rovac-edge.target

# Individual service
sudo systemctl status rovac-edge-lidar.service
```

## Data Flow

1. XV-11 sensor generates distance measurements
2. Arduino Nano relays serial data over USB
3. `xv11_lidar_publisher.py` parses XV-11 protocol
4. LaserScan messages published to `/scan`
5. SLAM/Nav2 consumes scan data for mapping/navigation

## Related Components

| Component | Service | Topic |
|-----------|---------|-------|
| USB-Lidar | `rovac-edge-lidar` | `/scan` |
| Super Sensor | `rovac-edge-supersensor` | `/super_sensor/*` |
| Motor Driver | `rovac-edge-motors` | `/cmd_vel` |
| IMU | `rovac-edge-imu` | `/imu` |

## Calibration History

- Motor speed optimized with 29.5Ω resistor (22Ω + 7.5Ω)
- Target RPM: 300
- Achieved: ~300-370 RPM (within acceptable range)
