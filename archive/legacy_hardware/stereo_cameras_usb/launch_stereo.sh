#!/bin/bash
# Launch script for stereo depth and obstacle detection on Pi

source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=42
cd ~/rovac/hardware/stereo_cameras

NO_OBSTACLES=false
DISPLAY_MODE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-obstacles)
            NO_OBSTACLES=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

echo "=================================================="
echo "STEREO DEPTH SYSTEM - Raspberry Pi"
echo "=================================================="

# Start stereo depth node
echo "Starting stereo depth node..."
python3 ros2_stereo_depth_node.py 2>&1 &
DEPTH_PID=$!
echo "  PID: $DEPTH_PID"
sleep 3

# Start obstacle detector if not disabled
if [ "$NO_OBSTACLES" = false ]; then
    echo "Starting obstacle detector..."
    python3 obstacle_detector.py 2>&1 &
    OBSTACLE_PID=$!
    echo "  PID: $OBSTACLE_PID"
fi

echo "=================================================="
echo "System running. Press Ctrl+C to stop."
echo "=================================================="
echo ""
echo "Published topics:"
echo "  /stereo/depth/image_raw  - Depth image (32FC1)"
echo "  /stereo/left/image_rect  - Rectified left image"
echo "  /stereo/camera_info      - Camera parameters"
if [ "$NO_OBSTACLES" = false ]; then
    echo "  /obstacles               - Obstacle detection JSON"
    echo "  /obstacles/ranges        - Virtual laser scan"
    echo "  /cmd_vel_obstacle        - Emergency stop commands"
fi
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $DEPTH_PID 2>/dev/null
    [ "$NO_OBSTACLES" = false ] && kill $OBSTACLE_PID 2>/dev/null
    wait 2>/dev/null
    echo "Done"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait
wait
