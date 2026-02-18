#!/bin/bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=42
cd ~/rovac/hardware/stereo_cameras

echo "=== Starting stereo depth node ==="
python3 ros2_stereo_depth_node.py 2>/dev/null &
NODE_PID=$!
echo "Node PID: $NODE_PID"
sleep 10

echo ""
echo "=== ROS2 Topics ==="
ros2 topic list | grep stereo

echo ""
echo "=== Checking depth publish rate (10 seconds) ==="
timeout 10 ros2 topic hz /stereo/depth/image_raw 2>&1 | tail -5

echo ""
echo "=== Cleanup ==="
kill $NODE_PID 2>/dev/null
wait $NODE_PID 2>/dev/null
echo "Test complete"
