#!/bin/bash
# Launch ROVAC Command Center
# Sources ROS2 environment and runs the TUI

set -e

# Activate conda
eval "$(/opt/homebrew/bin/conda shell.bash hook)"
conda activate ros_jazzy

# Source ROS2 environment
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

ROS_ENV="$ROVAC_DIR/config/ros2_env.sh"
if [ -f "$ROS_ENV" ]; then
    source "$ROS_ENV"
fi

# Run the command center
export PYTHONPATH="$ROVAC_DIR/scripts:$PYTHONPATH"
exec python3 -m command_center "$@"
