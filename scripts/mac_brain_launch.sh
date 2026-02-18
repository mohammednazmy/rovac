#!/bin/bash
# Mac Brain Launch Script
# Runs on MacBook - Nav2, SLAM, Foxglove, path planning
# The Pi handles sensors and motor control

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[MAC-BRAIN]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[MAC-BRAIN]${NC} $1"; }
log_error() { echo -e "${RED}[MAC-BRAIN]${NC} $1"; }

# Activate conda ROS environment
eval "$(/opt/homebrew/bin/conda shell.bash hook)"
conda activate ros_jazzy

# Load shared ROS2 environment config if available
ROS_ENV="$HOME/robots/rovac/config/ros2_env.sh"
if [ -f "$ROS_ENV" ]; then
    # shellcheck disable=SC1090
    source "$ROS_ENV"
else
    export ROS_DOMAIN_ID=42
    export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
    export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
    export ROS_LOCALHOST_ONLY=0
    [ -f "$HOME/fastdds_peers.xml" ] && export FASTRTPS_DEFAULT_PROFILES_FILE="$HOME/fastdds_peers.xml"
    export RMW_FASTRTPS_USE_QOS_FROM_XML=0
fi

log_info "Starting Mac Brain Node Stack..."
log_info "ROS_DOMAIN_ID: $ROS_DOMAIN_ID"

# Parse arguments
MODE="${1:-slam}"  # Default to SLAM mode
MAP_FILE="${2:-}"

usage() {
    echo "Usage: $0 [mode] [map_file]"
    echo "Modes:"
    echo "  slam      - Run SLAM toolbox for mapping (default)"
    echo "  nav       - Run navigation with existing map"
    echo "  foxglove  - Run only Foxglove bridge for visualization"
    echo "  all       - Run SLAM + Nav2 + Foxglove"
    echo ""
    echo "Examples:"
    echo "  $0 slam                     # Start SLAM mapping"
    echo "  $0 nav ~/maps/house.yaml    # Navigate with saved map"
    echo "  $0 foxglove                 # Just visualization"
}

cleanup() {
    log_warn "Shutting down Mac brain nodes..."
    pkill -f "foxglove_bridge" 2>/dev/null || true
    pkill -f "slam_toolbox" 2>/dev/null || true
    pkill -f "nav2" 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# Check Pi connectivity
log_info "Checking Pi connectivity..."
if ros2 topic list --no-daemon 2>/dev/null | grep -q "/cmd_vel"; then
    log_info "Pi is connected - ROS2 topics visible"
else
    log_warn "Pi may not be running - /cmd_vel topic not found"
    log_warn "Start Pi edge stack first: ssh pi 'sudo systemctl start rovac-edge.target'"
fi

case "$MODE" in
    slam)
        log_info "Starting SLAM Toolbox (Online Async mode)..."
        ros2 launch slam_toolbox online_async_launch.py \
            slam_params_file:=~/robots/rovac/config/slam_params.yaml \
            use_sim_time:=false &
        SLAM_PID=$!

        log_info "Starting Foxglove Bridge on port 8765..."
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
        FOX_PID=$!
        ;;

    nav)
        if [ -z "$MAP_FILE" ]; then
            log_error "Navigation mode requires a map file"
            usage
            exit 1
        fi

        log_info "Starting Nav2 with map: $MAP_FILE"
        ros2 launch nav2_bringup bringup_launch.py \
            map:="$MAP_FILE" \
            use_sim_time:=false \
            params_file:=~/robots/rovac/config/nav2_params.yaml &
        NAV_PID=$!

        log_info "Starting Foxglove Bridge..."
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
        FOX_PID=$!
        ;;

    foxglove)
        log_info "Starting Foxglove Bridge only on port 8765..."
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
        FOX_PID=$!
        ;;

    all)
        log_info "Starting full stack: SLAM + Nav2 + Foxglove..."

        # Start SLAM first
        ros2 launch slam_toolbox online_async_launch.py \
            slam_params_file:=~/robots/rovac/config/slam_params.yaml \
            use_sim_time:=false &
        SLAM_PID=$!
        sleep 3

        # Start Nav2
        ros2 launch nav2_bringup navigation_launch.py \
            use_sim_time:=false \
            params_file:=~/robots/rovac/config/nav2_params.yaml &
        NAV_PID=$!

        # Start Foxglove
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
        FOX_PID=$!
        ;;

    *)
        log_error "Unknown mode: $MODE"
        usage
        exit 1
        ;;
esac

echo ""
log_info "Mac Brain Stack Running!"
echo -e "${CYAN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}  Mode: $MODE"
echo -e "${CYAN}║${NC}  Foxglove: ws://localhost:8765"
echo -e "${CYAN}║${NC}  Open Foxglove Studio and connect to above URL"
echo -e "${CYAN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
log_info "Press Ctrl+C to stop all nodes"

wait
