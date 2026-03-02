#!/bin/bash
# Static transform from odom to base_link
# This allows SLAM to work with pure scan matching
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

source /opt/ros/jazzy/setup.bash
source "$ROVAC_DIR/config/ros2_env.sh"

exec ros2 run tf2_ros static_transform_publisher \
    --x 0 --y 0 --z 0 \
    --roll 0 --pitch 0 --yaw 0 \
    --frame-id odom --child-frame-id base_link
