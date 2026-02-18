# Stereo Depth Camera System - Raspberry Pi 5

## Overview

This stereo camera system provides real-time depth estimation for obstacle detection on the ROVAC robot. Optimized for Raspberry Pi 5 performance.

## Hardware Setup

| Component | Details |
|-----------|---------|
| Cameras | 2x Logitech Brio 100 |
| Resolution | 1280x720 (native), 640x360 (computation) |
| Frame Rate | ~2-3 Hz (depth), 10 Hz (target) |
| Left Camera | /dev/video3 |
| Right Camera | /dev/video1 |

## Quick Start

```bash
# Source ROS2
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=42

# Start stereo depth node
cd ~/rovac/hardware/stereo_cameras
python3 ros2_stereo_depth_node.py

# In another terminal, start obstacle detector (optional)
python3 obstacle_detector.py
```

## Published Topics

### Stereo Depth Node
| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/stereo/depth/image_raw` | sensor_msgs/Image | ~2 Hz | 32FC1 depth in meters |
| `/stereo/left/image_rect` | sensor_msgs/Image | ~2 Hz | Rectified left image |
| `/stereo/camera_info` | sensor_msgs/CameraInfo | ~2 Hz | Camera parameters |

### Obstacle Detector Node
| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/obstacles` | std_msgs/String | ~2 Hz | JSON obstacle status |
| `/obstacles/ranges` | sensor_msgs/LaserScan | ~2 Hz | Virtual laser scan |
| `/cmd_vel_obstacle` | geometry_msgs/Twist | On event | Emergency stop |

## Obstacle Detection Zones

```
+-------------------+
|     (unused)      |
|+---+   +---+   +---+
||   | C |   |   |   |
|| L | E | R |   |   |
||   | N |   |   |   |
|+---+ T +---+   +---+
|     E           |
|     R     +-----+
|         | GROUND |
+-------------------+
```

| Zone | Priority | Purpose |
|------|----------|---------|
| Center | High (1.0) | Main path obstacles |
| Left | Medium (0.7) | Left side clearance |
| Right | Medium (0.7) | Right side clearance |
| Ground | Medium (0.8) | Low obstacles, steps |

## Configuration

### config_pi.json
```json
{
  "left_device": 3,
  "right_device": 1,
  "width": 1280,
  "height": 720,
  "rotate_90_cw": true,
  "calibration_dir": "calibration_data",
  "target_fps": 10.0
}
```

### ROS2 Parameters

**Stereo Depth Node:**
- `publish_rate` (float): Target publish rate [default: 10.0]
- `publish_pointcloud` (bool): Enable point cloud [default: false]
- `use_correction` (bool): Apply depth correction [default: true]

**Obstacle Detector:**
- `danger_distance` (float): Emergency stop distance [default: 0.4m]
- `warning_distance` (float): Slow down distance [default: 0.8m]
- `emergency_stop_enabled` (bool): Enable /cmd_vel_obstacle [default: true]

## Performance Notes

- **Computation Time:** ~0.3s per frame (with 2x downsampling)
- **Actual Rate:** 2-3 Hz (limited by stereo matching)
- **Memory Usage:** ~200MB per node
- **CPU Usage:** ~100% of one core during depth computation

## Calibration

The calibration files in `calibration_data/` were created on Mac and should work on Pi:
- `stereo_calibration.json` - Camera matrices and baseline
- `stereo_maps.npz` - Rectification lookup tables
- `depth_correction.json` - Depth correction polynomial

**Note:** If cameras are swapped (left/right reversed), swap the device IDs in `config_pi.json`.

## Troubleshooting

### "No frames" warning at startup
Normal - takes ~1s for camera threads to start capturing.

### Low frame rate
- Expected: ~2-3 Hz with current configuration
- Depth computation is CPU-intensive
- 2x downsampling is applied to improve speed

### Camera device not found
```bash
# Check available devices
ls -la /dev/video*
v4l2-ctl -d /dev/video1 --info
v4l2-ctl -d /dev/video3 --info
```

### NumPy 2.x warning
A compatibility warning may appear but does not affect functionality:
```
A module that was compiled using NumPy 1.x cannot be run in NumPy 2.x
```
This is a cosmetic issue with cv_bridge - the nodes work correctly.

## Integration with ROVAC

The obstacle detector publishes to `/cmd_vel_obstacle` for emergency stops.
The navigation stack should monitor this topic and respond to zero-velocity commands.

Example integration:
```python
# In your navigation node
def obstacle_callback(msg):
    if msg.linear.x == 0 and msg.angular.z == 0:
        self.get_logger().warn("Emergency stop from obstacle detector!")
        # Stop the robot
```

## Files

| File | Description |
|------|-------------|
| `ros2_stereo_depth_node.py` | Main depth publisher node |
| `obstacle_detector.py` | Obstacle detection from depth |
| `config_pi.json` | Pi-specific camera configuration |
| `calibration_data/` | Calibration files from Mac |

## Authors

- ROVAC Project Team
- Pi Integration: January 2026
