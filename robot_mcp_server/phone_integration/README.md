# Phone Integration for Yahboom G1 Robot Tank

This module integrates a Samsung Galaxy A16 5G (SM-A166M) Android phone as a sensor pack,
vision module, and control center for the robot tank.

## Overview

### What's Included

| Component | File | Description |
|-----------|------|-------------|
| **Sensor Bridge** | `phone_sensors_node.py` | Streams phone IMU, magnetometer, light, proximity to ROS2 |
| **Camera Node** | `phone_camera_simple.py` | Streams phone camera to ROS2 via scrcpy |
| **LIDAR-Camera Fusion** | `lidar_camera_fusion_node.py` | Projects LIDAR depth onto camera image |
| **Depth Estimation** | `depth_estimation_node.py` | Monocular depth (MiDaS) - optional |
| **Startup Script** | `start_phone_integration.sh` | One-command startup |
| **Sensor Test** | `test_sensors.py` | Quick sensor connection test |

### Phone Capabilities Used

- ✅ **Accelerometer** → `/phone/imu`
- ✅ **Gyroscope** → `/phone/imu`
- ✅ **Magnetometer/Compass** → `/phone/magnetic_field`
- ✅ **Ambient Light Sensor** → `/phone/illuminance`
- ✅ **Proximity Sensor** → `/phone/proximity`
- ✅ **GPS** → `/phone/gps` (if outdoors)
- ✅ **Cameras** → `/phone/image_raw`, `/phone/image_raw/compressed`
- ✅ **Screen** → Foxglove dashboard via Chrome browser

### Depth Perception Approach

The Samsung A16's rear cameras (50MP main, 5MP ultrawide, 2MP macro) have **different focal lengths**
and cannot be used for true stereo depth. Instead, we use:

**LIDAR + Camera Fusion** - Projects existing LIDAR scan points onto the camera image to create:
- Depth-colored overlay visualization
- Sparse depth map from LIDAR data
- Colored point cloud combining LIDAR depth + camera color

## Quick Start

### 1. Start SensorServer on Phone

The SensorServer app has been installed on your phone. To start it:

```bash
# Launch the app
adb shell am start -n github.umer0586.sensorserver/.MainActivity
```

**On your phone:**
1. The SensorServer app should open
2. Tap **START** to begin the WebSocket server
3. Note the port (default: 8080)

### 2. Set Up ADB Port Forwarding

```bash
adb forward tcp:8080 tcp:8080
```

### 3. Test Sensor Connection

```bash
source ~/robot_mcp_server/phone_integration/venv/bin/activate
python3 ~/robot_mcp_server/phone_integration/test_sensors.py
```

### 4. Start Full Integration

```bash
~/robot_mcp_server/phone_integration/start_phone_integration.sh start
```

### 5. View on Foxglove

On your phone's Chrome browser, navigate to:
```
http://192.168.1.211:8765
```

Or use Foxglove Studio and connect to `ws://192.168.1.211:8765`.

## ROS2 Topics Published

### Phone Sensors
| Topic | Type | Description |
|-------|------|-------------|
| `/phone/imu` | `sensor_msgs/Imu` | Accelerometer + gyroscope combined |
| `/phone/magnetic_field` | `sensor_msgs/MagneticField` | Magnetometer (compass) |
| `/phone/illuminance` | `sensor_msgs/Illuminance` | Ambient light (lux) |
| `/phone/proximity` | `sensor_msgs/Range` | Proximity sensor |
| `/phone/gps` | `sensor_msgs/NavSatFix` | GPS location |
| `/phone/sensors_connected` | `std_msgs/Bool` | Sensor connection status |

### Phone Camera
| Topic | Type | Description |
|-------|------|-------------|
| `/phone/image_raw` | `sensor_msgs/Image` | Raw camera feed (BGR8) |
| `/phone/image_raw/compressed` | `sensor_msgs/CompressedImage` | JPEG compressed |
| `/phone/camera_info` | `sensor_msgs/CameraInfo` | Camera calibration |
| `/phone/camera_connected` | `std_msgs/Bool` | Camera connection status |

### LIDAR-Camera Fusion
| Topic | Type | Description |
|-------|------|-------------|
| `/phone/depth/overlay` | `sensor_msgs/Image` | Camera with LIDAR points overlay |
| `/phone/depth/lidar_projected` | `sensor_msgs/Image` | Sparse depth from LIDAR |
| `/phone/depth/fusion_active` | `std_msgs/Bool` | Fusion node status |

## TF Frames

```
map
 └── odom
      └── base_link
           ├── base_footprint
           ├── laser_frame
           └── phone_link
                └── phone_camera_link
```

## Manual Commands

### Start Individual Components

```bash
# Activate environment
source ~/robot_mcp_server/phone_integration/venv/bin/activate
source /opt/ros/jazzy/setup.bash

# Start sensors only
python3 ~/robot_mcp_server/phone_integration/phone_sensors_node.py \
    --ros-args -p host:=localhost -p port:=8080

# Start camera (requires scrcpy running)
python3 ~/robot_mcp_server/phone_integration/phone_camera_simple.py \
    --ros-args -p video_device:=/dev/video10

# Start LIDAR-camera fusion
python3 ~/robot_mcp_server/phone_integration/lidar_camera_fusion_node.py
```

### Camera Setup

```bash
# Load v4l2loopback
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="Phone_Camera" exclusive_caps=1
sudo chmod 666 /dev/video10

# Start scrcpy camera streaming
SNAP_LAUNCHER_NOTICE_ENABLED=false /snap/bin/scrcpy \
    --video-source=camera \
    --camera-id=0 \
    --camera-size=1280x720 \
    --no-playback \
    --v4l2-sink=/dev/video10 &
```

### Switch Cameras

```bash
# List available cameras
SNAP_LAUNCHER_NOTICE_ENABLED=false /snap/bin/scrcpy --list-cameras

# Camera IDs:
# 0 = Back main (50MP)
# 1 = Front (13MP)
# 2 = Back ultrawide (5MP)
```

## Robot Localization Integration

To fuse the phone IMU with wheel odometry using `robot_localization`:

```yaml
# ekf_config.yaml
ekf_filter_node:
  ros__parameters:
    # Wheel odometry
    odom0: /odom
    odom0_config: [true, true, false,   # x, y, z
                   false, false, true,   # roll, pitch, yaw
                   true, true, false,    # vx, vy, vz
                   false, false, true,   # vroll, vpitch, vyaw
                   false, false, false]  # ax, ay, az

    # Phone IMU
    imu0: /phone/imu
    imu0_config: [false, false, false,   # x, y, z
                  true, true, true,      # roll, pitch, yaw
                  false, false, false,   # vx, vy, vz
                  true, true, true,      # vroll, vpitch, vyaw
                  true, true, true]      # ax, ay, az
```

## Troubleshooting

### Sensor Connection Fails

1. Check SensorServer is running (START tapped in app)
2. Verify port forwarding: `adb forward --list`
3. Check USB connection: `adb devices`

### Camera Not Working

1. Check scrcpy is running: `pgrep -la scrcpy`
2. Check v4l2loopback: `v4l2-ctl -d /dev/video10 --info`
3. Reload module: `sudo rmmod v4l2loopback && sudo modprobe v4l2loopback ...`

### Phone Screen Off

Enable "Stay awake while charging" in Developer Options to keep sensors active.

## Dependencies

- scrcpy 3.x (snap)
- v4l2loopback-dkms
- websockets (Python)
- opencv-python-headless
- SensorServer app (F-Droid)

## Sources & References

- [SensorServer App](https://github.com/umer0586/SensorServer) - F-Droid
- [scrcpy](https://github.com/Genymobile/scrcpy) - Screen/camera mirroring
- [v4l2loopback](https://github.com/umlaeute/v4l2loopback) - Virtual video device
- [Depth Anything](https://github.com/LiheYoung/Depth-Anything) - Monocular depth (optional)
