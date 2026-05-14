#!/bin/bash
# Launch stereo depth system with ROS2

# Source ROS2
source /opt/ros/jazzy/setup.bash

# Set ROS domain
export ROS_DOMAIN_ID=42

# Source CycloneDDS config if available
if [ -f ~/rovac/config/cyclonedds_pi.xml ]; then
    export CYCLONEDDS_URI=file://$HOME/rovac/config/cyclonedds_pi.xml
fi

cd ~/rovac/hardware/stereo_cameras

echo "Starting stereo depth ROS2 system..."
echo "ROS_DOMAIN_ID: $ROS_DOMAIN_ID"

# Check if --obstacle flag is passed
if [[ "$1" == "--obstacles" ]]; then
    echo "Starting with obstacle detection..."
    python3 ros2_stereo_depth_node.py &
    DEPTH_PID=$!
    sleep 2
    python3 obstacle_detector.py &
    OBSTACLE_PID=$!
    
    trap "kill $DEPTH_PID $OBSTACLE_PID 2>/dev/null" EXIT
    wait
else
    echo "Starting depth node only (use --obstacles for obstacle detection)"
    python3 ros2_stereo_depth_node.py
fi
