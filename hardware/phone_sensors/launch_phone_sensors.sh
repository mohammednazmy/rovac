#!/bin/bash
# Launch Phone Sensors ROS2 Node
# Streams sensor data from Android phone via SensorServer WebSocket

set -e

# Source ROS2 environment
source /opt/ros/jazzy/setup.bash
if [ -f /home/pi/ros2_env.sh ]; then
    source /home/pi/ros2_env.sh
fi

# Ensure ADB port forwarding is set up
echo "Setting up ADB port forwarding..."
adb forward tcp:8080 tcp:8080 2>/dev/null || echo "ADB forward may already be set"

# Check if phone is connected
if ! adb devices | grep -q "device$"; then
    echo "ERROR: No phone connected via ADB"
    exit 1
fi

echo "Phone connected, starting sensors node..."

# Launch the node
exec python3 /home/pi/hardware/phone_sensors/phone_sensors_ros2_node.py --ros-args \
    -p websocket_host:=localhost \
    -p websocket_port:=8080 \
    -p gps_poll_rate:=1.0 \
    -p imu_frame_id:=phone_imu_link \
    -p gps_frame_id:=phone_gps_link
