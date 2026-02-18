#!/bin/bash
# Launch USB Webcam ROS2 Publisher
#
# Usage:
#   ./launch_webcam.sh              # Default 640x480 @ 30fps
#   ./launch_webcam.sh 1280 720 30  # HD @ 30fps
#   ./launch_webcam.sh 1920 1080 30 # Full HD @ 30fps

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default resolution
WIDTH=${1:-640}
HEIGHT=${2:-480}
FPS=${3:-30}
DEVICE=${4:-/dev/video0}

# Set environment
export HOME=/home/pi
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/pi/robots/rovac/config/cyclonedds_pi.xml

# Source ROS2
source /opt/ros/jazzy/setup.bash
if [ -f /home/pi/ros2_env.sh ]; then
    source /home/pi/ros2_env.sh
fi

echo "=== USB Webcam Publisher ==="
echo "Device: $DEVICE"
echo "Resolution: ${WIDTH}x${HEIGHT} @ ${FPS}fps"
echo "Publishing to: /webcam/image_raw"
echo ""

# Check device exists
if [ ! -e "$DEVICE" ]; then
    echo "ERROR: Device $DEVICE not found"
    echo "Available video devices:"
    ls -la /dev/video* 2>/dev/null || echo "  None found"
    exit 1
fi

# Run publisher
python3 "$SCRIPT_DIR/webcam_publisher.py" \
    --device "$DEVICE" \
    --width "$WIDTH" \
    --height "$HEIGHT" \
    --fps "$FPS"
