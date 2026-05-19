# Phone Cameras Module

Stream Android phone cameras to ROS2 via scrcpy and v4l2loopback.

## Overview

This module uses the phone's cameras as visual sensors for the robot. The phone is connected via USB to the Raspberry Pi, and scrcpy streams the camera feed to a v4l2loopback virtual device, which is then published to ROS2.

**Important:** Only one camera can stream at a time due to Android limitations. Use `switch_camera.sh` to easily switch between cameras.

## Available Cameras (Samsung SM-A166M)

| Camera | ID | Position | Max Resolution | Use Case |
|--------|----|---------:|----------------|----------|
| `back` | 0 | Back Main | 4080x3060 | Forward vision (default) |
| `front` | 1 | Front | 4128x3096 | Operator view |
| `wide` | 2 | Back Wide | 2576x1932 | Wide-angle navigation |
| `front2` | 3 | Front Secondary | 3712x2556 | Alternate front view |

## ROS2 Topics

The active camera publishes to:

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/phone/camera/{name}/image_raw` | sensor_msgs/Image | ~12 Hz | Raw BGR8 image |
| `/phone/camera/{name}/image_raw/compressed` | sensor_msgs/CompressedImage | ~12 Hz | JPEG compressed |
| `/phone/camera/{name}/camera_info` | sensor_msgs/CameraInfo | ~12 Hz | Camera parameters |

Where `{name}` is `back`, `front`, `wide`, or `front2`.

## Quick Start

### Start Camera Service

```bash
# SSH to Pi
ssh pi

# Start the service (default: back camera)
sudo systemctl start rovac-phone-cameras.service

# Check it's running
sudo systemctl status rovac-phone-cameras.service
```

### Verify Camera is Working

```bash
# On Mac or Pi
ros2 topic hz /phone/camera/back/image_raw
# Should show ~12 Hz

# View in Foxglove
# Add Image panel → /phone/camera/back/image_raw/compressed
```

### Switch Cameras

```bash
# Switch to different camera (on Pi)
~/robots/rovac/hardware/phone_cameras/switch_camera.sh front   # Front camera
~/robots/rovac/hardware/phone_cameras/switch_camera.sh wide    # Back wide-angle
~/robots/rovac/hardware/phone_cameras/switch_camera.sh front2  # Secondary front
~/robots/rovac/hardware/phone_cameras/switch_camera.sh back    # Back to default
```

## Prerequisites

### Hardware
- Android phone with USB debugging enabled
- USB cable connected to Raspberry Pi
- Phone screen unlocked (required for camera access)

### Software (on Pi)

```bash
# Required packages
sudo apt install scrcpy v4l2loopback-dkms adb

# Python packages
pip3 install opencv-python

# ROS2 packages
sudo apt install ros-jazzy-cv-bridge
```

### Phone Setup

1. **Enable Developer Options**:
   - Settings → About Phone → Tap "Build Number" 7 times

2. **Enable USB Debugging**:
   - Settings → Developer Options → USB Debugging: ON

3. **Connect phone via USB** and authorize when prompted

4. **Unlock phone screen** (camera won't work with screen locked)

5. **Close any camera apps** on the phone

## Systemd Service

```bash
# Start service
sudo systemctl start rovac-phone-cameras.service

# Stop service
sudo systemctl stop rovac-phone-cameras.service

# Check status
sudo systemctl status rovac-phone-cameras.service

# View logs
sudo journalctl -u rovac-phone-cameras -f

# Enable at boot
sudo systemctl enable rovac-phone-cameras.service
```

## Configuration

### Resolution and Frame Rate

Default: 640x480 at 15 FPS (good balance of quality and bandwidth)

Edit `launch_multi_cameras.sh` to change:

```bash
RESOLUTION="640x480"  # Options: "640x480", "1280x720", "1920x1080"
FPS="15"              # Options: "10", "15", "30"
```

### Selecting Default Camera

To change which camera starts by default:

```bash
# Edit the service
sudo systemctl edit rovac-phone-cameras.service

# Add override:
[Service]
ExecStart=
ExecStart=/home/pi/robots/rovac/hardware/phone_cameras/launch_multi_cameras.sh front
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       Samsung Galaxy A16                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │ Back    │  │ Front   │  │ Wide    │  │ Front2  │             │
│  │ Cam 0   │  │ Cam 1   │  │ Cam 2   │  │ Cam 3   │             │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘             │
│       │            │            │            │                   │
│       └────────────┴────────────┴────────────┘                   │
│                           │                                      │
│                    (only one at a time)                          │
└───────────────────────────┼──────────────────────────────────────┘
                            │ USB (scrcpy --video-source=camera)
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Raspberry Pi 5                               │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ scrcpy → v4l2loopback (/dev/video10)                       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                            │                                      │
│                            ▼                                      │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ multi_camera_publisher.py (ROS2 Node)                      │  │
│  │   • Reads from /dev/video10                                │  │
│  │   • Publishes /phone/camera/{name}/image_raw              │  │
│  │   • Publishes /phone/camera/{name}/image_raw/compressed   │  │
│  │   • Publishes /phone/camera/{name}/camera_info            │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### Camera not starting

```bash
# Check scrcpy log
cat /tmp/phone_cameras/scrcpy_back.log

# Common issues:
# - Phone screen locked → Unlock it
# - Camera app open on phone → Close it
# - USB debugging not authorized → Check phone for prompt
# - scrcpy not installed → sudo apt install scrcpy
```

### No video on ROS2 topic

```bash
# Check v4l2loopback device exists
ls -la /dev/video10

# Check scrcpy is running
ps aux | grep scrcpy

# Check ROS2 publisher
cat /tmp/phone_cameras/ros2_back.log

# Check if module is loaded
lsmod | grep v4l2loopback
```

### "Device busy" error

```bash
# Another process is using the camera
# Kill existing scrcpy processes
pkill -f "scrcpy.*video-source=camera"

# Wait and restart
sleep 2
sudo systemctl restart rovac-phone-cameras.service
```

### Low frame rate

1. Reduce resolution: Edit RESOLUTION in `launch_multi_cameras.sh`
2. Close other apps on phone
3. Use USB 3.0 port if available
4. Check Pi CPU usage: `htop`

### Phone battery drain

Camera streaming uses significant power:
- Keep phone plugged in (USB provides ~500mA)
- Reduce resolution/frame rate
- Stream only when needed

## Resource Usage

| Resolution | CPU (Pi 5) | RAM | Network to Mac |
|------------|------------|-----|----------------|
| 640x480 @ 15fps | ~15% | ~100MB | ~5 Mbps |
| 1280x720 @ 15fps | ~25% | ~150MB | ~12 Mbps |
| 1920x1080 @ 15fps | ~35% | ~200MB | ~25 Mbps |

## Files

```
phone_cameras/
├── README.md                    # This file
├── multi_camera_publisher.py    # ROS2 camera publisher node
├── launch_multi_cameras.sh      # Multi-camera launch script
└── switch_camera.sh             # Easy camera switching script
```

## Integration with Robot

### Use Cases

| Use Case | Camera | Topic |
|----------|--------|-------|
| Forward navigation | back | `/phone/camera/back/image_raw` |
| Obstacle detection | wide | `/phone/camera/wide/image_raw` |
| Teleoperation view | front | `/phone/camera/front/image_raw` |
| Visual SLAM | back | `/phone/camera/back/image_raw` |

### View in Foxglove

```bash
# On Mac - start Foxglove bridge
./scripts/mac_brain_launch.sh foxglove

# Open Foxglove Studio
# Connect to ws://localhost:8765
# Add Image panel → /phone/camera/back/image_raw/compressed
```

### Save Frames

```bash
# Save individual frames
ros2 run image_view image_saver --ros-args \
    -r image:=/phone/camera/back/image_raw \
    -p filename_format:="frame_%04d.jpg"

# Record video (rosbag)
ros2 bag record /phone/camera/back/image_raw/compressed
```

### Record Video

```bash
# Record compressed stream to bag file
ros2 bag record -o phone_camera_recording \
    /phone/camera/back/image_raw/compressed \
    /phone/camera/back/camera_info
```
