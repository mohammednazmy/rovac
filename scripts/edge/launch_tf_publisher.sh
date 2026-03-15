#!/bin/bash
source /opt/ros/jazzy/setup.bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../config/ros2_env.sh"

URDF="$SCRIPT_DIR/../../ros2_ws/src/tank_description/urdf/tank.urdf"

# Strip XML comments and pass URDF safely via Python os.execvp
exec python3 -c "
import sys, os, re
with open('$URDF') as f:
    urdf = f.read()
# Remove XML comments (they contain = signs that break rcl argument parsing)
urdf = re.sub(r'<!--.*?-->', '', urdf, flags=re.DOTALL)
# Remove blank lines
urdf = '\n'.join(l for l in urdf.split('\n') if l.strip())
os.execvp('ros2', ['ros2', 'run', 'robot_state_publisher', 'robot_state_publisher',
    '--ros-args', '-p', 'robot_description:=' + urdf])
"
