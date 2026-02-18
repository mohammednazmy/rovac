#!/bin/bash
#
# Mac Dual Controller Script (Tank + Arm on Mac, Edge on Pi)
#
# Usage:
#   ./dual_control_mac.sh start         # Start basic control
#   ./dual_control_mac.sh map           # Start mapping mode (SLAM + Foxglove)
#   ./dual_control_mac.sh stop          # Stop all
#   ./dual_control_mac.sh status        # Check status
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# User indicated arm is currently offline/not used, but we keep the var for future.
export ENABLE_ARM=1

case "${1:-}" in
    map)
        # "Map mode" delegates to the mapping script
        echo "[DUAL] Switching to MAP mode..."
        exec "$SCRIPT_DIR/map_house.sh" start
        ;;
    *)
        # Default/other commands delegate to standalone control
        exec "$SCRIPT_DIR/standalone_control.sh" "$@"
        ;;
esac
