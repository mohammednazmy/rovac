# Phone Sensors Module

Stream Android phone sensors to ROS2 via SensorServer WebSocket app.

## Overview

This module integrates your Android phone's sensors into the ROVAC robot's ROS2 system, providing GPS for outdoor navigation, a high-quality backup IMU, and compass heading.

### Published Topics

| Sensor | Source | ROS2 Topic | Message Type | Rate |
|--------|--------|------------|--------------|------|
| Accelerometer | SensorServer | `/phone/imu` | sensor_msgs/Imu | ~45 Hz |
| Gyroscope | SensorServer | `/phone/imu` | sensor_msgs/Imu | ~45 Hz |
| Magnetometer | SensorServer | `/phone/magnetic_field` | sensor_msgs/MagneticField | ~6 Hz |
| Orientation | SensorServer | `/phone/orientation` | geometry_msgs/Vector3Stamped | ~45 Hz |
| GPS | ADB (Location Manager) | `/phone/gps/fix` | sensor_msgs/NavSatFix | 1 Hz |

### Phone Hardware

| Attribute | Value |
|-----------|-------|
| **Model** | Samsung Galaxy A16 (SM-A166M) |
| **OS** | Android 15 |
| **IMU** | LSM6DSOTR (500 Hz capable) |
| **Magnetometer** | MXG4300S |
| **GPS** | S.LSI SPOTNAV (GNSS) |

## Prerequisites

### On Android Phone

1. **Install SensorServer app**:
   - F-Droid: https://f-droid.org/packages/github.umer0586.sensorserver/
   - GitHub: https://github.com/umer0586/SensorServer/releases

2. **Configure SensorServer** (IMPORTANT):
   - Open the app → Settings (gear icon)
   - **Bind Address: `0.0.0.0`** (critical - allows connections from all interfaces)
   - **Port: `8080`** (default)
   - Back to main screen → Enable sensors:
     - ✅ Accelerometer
     - ✅ Gyroscope
     - ✅ Magnetometer (Uncalibrated)
     - ✅ Rotation Vector
   - Tap "Start" to begin streaming

3. **Enable USB Debugging**:
   - Settings → About Phone → Tap "Build Number" 7 times to enable Developer Options
   - Settings → Developer Options → USB Debugging: ON
   - Connect phone to Pi via USB
   - Accept the ADB authorization prompt on phone

4. **Grant Location Permission** (for GPS):
   - Settings → Location → ON
   - Open Google Maps once to establish a GPS fix
   - GPS data is polled via ADB, not SensorServer

### On Raspberry Pi

1. **ADB installed**: `sudo apt install adb`
2. **Phone authorized**: `adb devices` should show your phone as "device"
3. **websocket-client**: `pip3 install websocket-client`

## Quick Start

```bash
# SSH to Pi
ssh pi

# Start SensorServer app on phone first!

# Then run the node manually:
source /home/pi/ros2_env.sh
python3 /home/pi/hardware/phone_sensors/phone_sensors_ros2_node.py

# Or use the service:
sudo systemctl start rovac-edge-phone-sensors.service
```

## Published Topics

### /phone/imu (sensor_msgs/Imu)
Combined accelerometer and gyroscope data at ~50 Hz.

```bash
ros2 topic echo /phone/imu
```

**Fields:**
- `linear_acceleration`: [x, y, z] in m/s²
- `angular_velocity`: [x, y, z] in rad/s
- `orientation`: Not populated (use /phone/orientation instead)

### /phone/magnetic_field (sensor_msgs/MagneticField)
Magnetometer data for compass heading.

```bash
ros2 topic echo /phone/magnetic_field
```

**Fields:**
- `magnetic_field`: [x, y, z] in Tesla

### /phone/gps/fix (sensor_msgs/NavSatFix)
GPS location polled via ADB at 1 Hz.

```bash
ros2 topic echo /phone/gps/fix
```

**Fields:**
- `latitude`: Degrees
- `longitude`: Degrees
- `altitude`: Meters above sea level
- `position_covariance`: Based on accuracy

### /phone/orientation (geometry_msgs/Vector3Stamped)
Device orientation as Euler angles.

```bash
ros2 topic echo /phone/orientation
```

**Fields:**
- `vector.x`: Roll (radians)
- `vector.y`: Pitch (radians)
- `vector.z`: Yaw (radians)

## Systemd Service

```bash
# Check status
sudo systemctl status rovac-edge-phone-sensors.service

# Start/stop
sudo systemctl start rovac-edge-phone-sensors.service
sudo systemctl stop rovac-edge-phone-sensors.service

# View logs
sudo journalctl -u rovac-edge-phone-sensors -f

# Enable at boot
sudo systemctl enable rovac-edge-phone-sensors.service
```

## Troubleshooting

### "No phone connected via ADB"
```bash
# Check ADB connection
adb devices

# If empty, reconnect USB and authorize on phone
# May need to revoke and re-authorize USB debugging
```

### "Connection failed" for sensors
1. Ensure SensorServer app is running on phone
2. Ensure the sensor is enabled in SensorServer
3. Check ADB port forwarding:
   ```bash
   adb forward tcp:8080 tcp:8080
   adb forward --list
   ```

### GPS not updating
- GPS is polled via ADB, not WebSocket
- Ensure location services are enabled on phone
- Open Google Maps briefly to get a fresh GPS fix
- Check ADB works: `adb shell dumpsys location | head -50`

### WebSocket connection drops
- SensorServer may have timed out - restart it on phone
- Check if phone screen turned off (may pause app)
- Consider enabling "Keep screen on" in SensorServer settings

## Architecture

```
┌─────────────────────┐     USB      ┌─────────────────────┐
│   Android Phone     │◄────────────►│   Raspberry Pi 5    │
│                     │     ADB      │                     │
│ ┌─────────────────┐ │              │ ┌─────────────────┐ │
│ │  SensorServer   │ │  WebSocket   │ │  phone_sensors  │ │
│ │  App (port 8080)│◄──(forwarded)──┤ │  _ros2_node.py  │ │
│ └─────────────────┘ │              │ └────────┬────────┘ │
│                     │              │          │          │
│ ┌─────────────────┐ │   ADB shell  │          ▼          │
│ │ Location Manager│◄──(dumpsys)───┤    ROS2 Topics      │
│ │ (GPS/GNSS)      │ │              │   /phone/imu        │
│ └─────────────────┘ │              │   /phone/gps/fix    │
│                     │              │   /phone/magnetic   │
└─────────────────────┘              └─────────────────────┘
```

## Phone Sensors Available

Your Samsung SM-A166M (Android 15) has these sensors:

| Sensor | Chip | Max Rate |
|--------|------|----------|
| Accelerometer | LSM6DSOTR | 500 Hz |
| Gyroscope | LSM6DSOTR | 500 Hz |
| Magnetometer | MXG4300S | 125 Hz |
| Light | TCS3701 | - |
| Proximity | ProToS | - |
| Step Counter | - | - |
| GPS/GNSS | S.LSI SPOTNAV | 1 Hz |

## Integration with Robot

The phone sensors complement the Yahboom board sensors:

| Source | Sensors | Use Case |
|--------|---------|----------|
| Yahboom Board | IMU, Encoders, Odometry | Primary robot localization |
| Phone | GPS, Secondary IMU | Outdoor navigation, sensor fusion |

For outdoor navigation, you can fuse:
- `/phone/gps/fix` - Global position
- `/odom` - Local wheel odometry
- `/phone/imu` or `/imu/data` - Attitude

## Files

```
phone_sensors/
├── README.md                      # This file
├── phone_sensors_ros2_node.py     # Main ROS2 node
└── launch_phone_sensors.sh        # Launch script
```
