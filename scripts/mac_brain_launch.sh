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

PI_HOST="${ROVAC_EDGE_IP:-192.168.1.200}"
PI_USER="pi"
STOPPED_MAP_TF=false

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

# Stop the static map→odom TF on Pi (conflicts with SLAM's dynamic map→odom)
stop_pi_map_tf() {
    if ssh -o ConnectTimeout=3 "$PI_USER@$PI_HOST" \
        'sudo systemctl is-active --quiet rovac-edge-map-tf 2>/dev/null'; then
        log_info "Stopping Pi static map->odom TF (SLAM will provide it dynamically)..."
        ssh "$PI_USER@$PI_HOST" 'sudo systemctl stop rovac-edge-map-tf'
        STOPPED_MAP_TF=true
    fi
}

# Re-enable static map→odom TF on Pi when SLAM exits
start_pi_map_tf() {
    if [ "$STOPPED_MAP_TF" = true ]; then
        log_info "Re-enabling Pi static map->odom TF..."
        ssh -o ConnectTimeout=3 "$PI_USER@$PI_HOST" \
            'sudo systemctl start rovac-edge-map-tf' 2>/dev/null || true
    fi
}

cleanup() {
    log_warn "Shutting down Mac brain nodes..."
    pkill -f "foxglove_bridge" 2>/dev/null || true
    pkill -f "phone_sensor_relay" 2>/dev/null || true
    pkill -f "slam_toolbox" 2>/dev/null || true
    pkill -f "nav2" 2>/dev/null || true
    start_pi_map_tf
    exit 0
}

# Start the phone sensor relay (bridges XRCE-DDS phone topics for Foxglove)
start_phone_relay() {
    if ! pgrep -f "phone_sensor_relay" > /dev/null 2>&1; then
        log_info "Starting phone sensor relay..."
        python3 "$HOME/robots/rovac/scripts/phone_sensor_relay.py" &
        PHONE_RELAY_PID=$!
        log_info "Phone relay PID: $PHONE_RELAY_PID"
    else
        log_info "Phone sensor relay already running"
    fi
}
trap cleanup SIGINT SIGTERM

# ── Pre-flight checks ──────────────────────────────────────────────
log_info "Running pre-flight checks..."

# 1) Pi connectivity via SSH
if ssh -o ConnectTimeout=3 "$PI_USER@$PI_HOST" 'true' 2>/dev/null; then
    log_info "Pi SSH: OK"
else
    log_warn "Pi SSH unreachable at $PI_HOST — edge services can't be managed"
fi

# 2) ROS2 topics visible (CycloneDDS unicast can take 5-8s for discovery)
log_info "Waiting for DDS discovery (up to 15s)..."
TOPICS_FOUND=false
for i in $(seq 1 3); do
    TOPIC_LIST=$(ros2 topic list --no-daemon 2>/dev/null || true)
    if echo "$TOPIC_LIST" | grep -q "/scan"; then
        TOPICS_FOUND=true
        break
    fi
    sleep 5
done

if [ "$TOPICS_FOUND" = true ]; then
    log_info "/scan topic: OK"
    # Quick sanity: also check for odom and tf
    if echo "$TOPIC_LIST" | grep -q "/odom"; then
        log_info "/odom topic: OK"
    else
        log_warn "/odom not found — ESP32 motor may not be connected"
    fi
    if echo "$TOPIC_LIST" | grep -q "/tf"; then
        log_info "/tf topic: OK"
    else
        log_warn "/tf not found — odom->base_link transform missing"
    fi
else
    log_error "/scan topic NOT found after 15s!"
    log_error "Check: Pi edge services running? ESP32 LIDAR powered? micro-ROS Agent up?"
    log_error "  ssh pi@$PI_HOST 'sudo systemctl status rovac-edge-uros-agent'"
    exit 1
fi

# ── Launch modes ───────────────────────────────────────────────────
case "$MODE" in
    slam)
        stop_pi_map_tf

        log_info "Starting SLAM Toolbox (Online Async mode)..."
        ros2 launch slam_toolbox online_async_launch.py \
            slam_params_file:=$HOME/robots/rovac/config/slam_params.yaml \
            use_sim_time:=false &
        SLAM_PID=$!

        log_info "Starting Foxglove Bridge on port 8765..."
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
        start_phone_relay
        FOX_PID=$!
        ;;

    nav)
        if [ -z "$MAP_FILE" ]; then
            log_error "Navigation mode requires a map file"
            usage
            exit 1
        fi

        stop_pi_map_tf

        log_info "Starting Nav2 with map: $MAP_FILE"
        ros2 launch nav2_bringup bringup_launch.py \
            map:="$MAP_FILE" \
            use_sim_time:=false \
            params_file:=$HOME/robots/rovac/config/nav2_params.yaml &
        NAV_PID=$!

        log_info "Starting Foxglove Bridge..."
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
        start_phone_relay
        FOX_PID=$!
        ;;

    foxglove)
        # Foxglove-only: ensure the static map→odom TF is running for visualization
        if ssh -o ConnectTimeout=3 "$PI_USER@$PI_HOST" \
            '! sudo systemctl is-active --quiet rovac-edge-map-tf 2>/dev/null'; then
            log_info "Starting Pi static map->odom TF for Foxglove visualization..."
            ssh "$PI_USER@$PI_HOST" 'sudo systemctl start rovac-edge-map-tf' 2>/dev/null || true
        fi

        log_info "Starting Foxglove Bridge only on port 8765..."
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
        start_phone_relay
        FOX_PID=$!
        ;;

    all)
        stop_pi_map_tf

        log_info "Starting full stack: SLAM + Nav2 + Foxglove..."

        # Start SLAM first
        ros2 launch slam_toolbox online_async_launch.py \
            slam_params_file:=$HOME/robots/rovac/config/slam_params.yaml \
            use_sim_time:=false &
        SLAM_PID=$!
        sleep 3

        # Start Nav2
        ros2 launch nav2_bringup navigation_launch.py \
            use_sim_time:=false \
            params_file:=$HOME/robots/rovac/config/nav2_params.yaml &
        NAV_PID=$!

        # Start Foxglove
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
        start_phone_relay
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
echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}  Mode: $MODE"
echo -e "${CYAN}║${NC}  Foxglove: ws://localhost:8765"
echo -e "${CYAN}║${NC}  Open Foxglove Studio and connect to above URL"
if [ "$MODE" = "slam" ] || [ "$MODE" = "all" ]; then
echo -e "${CYAN}║${NC}"
echo -e "${CYAN}║${NC}  SLAM Tips:"
echo -e "${CYAN}║${NC}    - /map topic appears after first scan match (~5s)"
echo -e "${CYAN}║${NC}    - Set Foxglove 3D panel display frame to 'map'"
echo -e "${CYAN}║${NC}    - Add Map display for /map topic"
echo -e "${CYAN}║${NC}    - Drive slowly with: python3 scripts/keyboard_teleop.py"
fi
echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
log_info "Press Ctrl+C to stop all nodes"

wait
