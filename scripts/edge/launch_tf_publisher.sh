#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

source /opt/ros/jazzy/setup.bash
source "$ROVAC_DIR/config/ros2_env.sh"

URDF_FILE="$ROVAC_DIR/ros2_ws/src/tank_description/urdf/tank.urdf"

if [ ! -f "$URDF_FILE" ]; then
    echo "ERROR: URDF file not found: $URDF_FILE"
    exit 1
fi

# Read URDF content
URDF_CONTENT=$(cat "$URDF_FILE")

# Launch robot_state_publisher with URDF
exec ros2 run robot_state_publisher robot_state_publisher \
    --ros-args -p robot_description:="$URDF_CONTENT"
