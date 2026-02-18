# USB Webcam Module

Stream USB webcam video to ROS2 topics.

## Hardware

| Attribute | Value |
|-----------|-------|
| **Model** | NexiGo N930E FHD Webcam |
| **Max Resolution** | 1920x1080 @ 30fps (MJPG) |
| **Default** | 640x480 @ 30fps |
| **Device** | `/dev/webcam` or `/dev/video0` |
| **Interface** | USB (UVC) |

## ROS2 Topics

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/webcam/image_raw` | sensor_msgs/Image | ~16 Hz | Raw BGR8 image |
| `/webcam/image_raw/compressed` | sensor_msgs/CompressedImage | ~16 Hz | JPEG compressed |
| `/webcam/camera_info` | sensor_msgs/CameraInfo | ~16 Hz | Camera parameters |

## Quick Start

```bash
# Start the service
sudo systemctl start rovac-edge-webcam.service

# Check status
sudo systemctl status rovac-edge-webcam.service

# View logs
sudo journalctl -u rovac-edge-webcam -f
```

## Manual Launch

```bash
# Default (640x480 @ 30fps)
./launch_webcam.sh

# HD (1280x720 @ 30fps)
./launch_webcam.sh 1280 720 30

# Full HD (1920x1080 @ 30fps)
./launch_webcam.sh 1920 1080 30
```

## Systemd Service

```bash
# Start/stop
sudo systemctl start rovac-edge-webcam.service
sudo systemctl stop rovac-edge-webcam.service

# Enable at boot
sudo systemctl enable rovac-edge-webcam.service

# Check status
sudo systemctl status rovac-edge-webcam.service
```

## Configuration

### Resolution Options

| Resolution | Format | Max FPS | Use Case |
|------------|--------|---------|----------|
| 640x480 | MJPG | 30 | Low bandwidth, fast |
| 1280x720 | MJPG | 30 | HD quality |
| 1920x1080 | MJPG | 30 | Full HD (high bandwidth) |

To change resolution, edit the service:

```bash
sudo systemctl edit rovac-edge-webcam.service

# Add override:
[Service]
ExecStart=
ExecStart=/bin/bash -c 'source /opt/ros/jazzy/setup.bash && python3 /home/pi/hardware/webcam/webcam_publisher.py --device /dev/webcam --width 1280 --height 720 --fps 30'
```

## Troubleshooting

### Webcam not found

```bash
# Check device exists
ls -la /dev/webcam /dev/video0

# Check v4l2 devices
v4l2-ctl --list-devices

# Reload udev rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### Low frame rate

1. Use MJPG format (default) for better USB bandwidth
2. Reduce resolution if needed
3. Check USB port (prefer USB 3.0)

### Service fails to start

```bash
# Check logs
sudo journalctl -u rovac-edge-webcam -n 50

# Verify device
ls -la /dev/webcam

# Test manually
python3 /home/pi/hardware/webcam/webcam_publisher.py --device /dev/video0
```

## Integration with Robot

### View in Foxglove

```bash
# On Mac
./scripts/mac_brain_launch.sh foxglove

# Connect Foxglove Studio to ws://localhost:8765
# Add Image panel → /webcam/image_raw/compressed
```

### Save Frames

```bash
ros2 run image_view image_saver --ros-args \
    -r image:=/webcam/image_raw \
    -p filename_format:="webcam_%04d.jpg"
```

## Files

```
webcam/
├── README.md               # This file
├── webcam_publisher.py     # ROS2 camera publisher
└── launch_webcam.sh        # Launch script
```
