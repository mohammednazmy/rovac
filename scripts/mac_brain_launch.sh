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
DISABLED_MOTOR_TF=false

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
    echo "  slam-ekf  - Run SLAM + EKF (best map quality — gyro-fused odometry)"
    echo "  nav       - Run navigation with existing map"
    echo "  foxglove  - Run only Foxglove bridge for visualization"
    echo "  ekf       - Run EKF sensor fusion (wheel odom + BNO055 IMU)"
    echo "  all       - Run SLAM + Nav2 + Foxglove"
    echo ""
    echo "Examples:"
    echo "  $0 slam-ekf                 # Best quality SLAM mapping"
    echo "  $0 slam                     # SLAM without EKF (faster startup)"
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

# Disable motor driver's odom→base_link TF (EKF will publish its own)
disable_motor_tf() {
    log_info "Disabling motor driver TF (EKF will publish odom->base_link)..."
    ssh -o ConnectTimeout=3 "$PI_USER@$PI_HOST" \
        "source /opt/ros/jazzy/setup.bash && export ROS_DOMAIN_ID=42 && \
         export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp && \
         export CYCLONEDDS_URI=file:///home/pi/robots/rovac/config/cyclonedds_pi.xml && \
         ros2 param set /motor_driver_node publish_tf false" 2>/dev/null && \
        DISABLED_MOTOR_TF=true || \
        log_warn "Could not set publish_tf — motor driver may not be running"
}

# Re-enable motor driver's TF on exit
restore_motor_tf() {
    if [ "$DISABLED_MOTOR_TF" = true ]; then
        log_info "Re-enabling motor driver TF publishing..."
        ssh -o ConnectTimeout=3 "$PI_USER@$PI_HOST" \
            "source /opt/ros/jazzy/setup.bash && export ROS_DOMAIN_ID=42 && \
             export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp && \
             export CYCLONEDDS_URI=file:///home/pi/robots/rovac/config/cyclonedds_pi.xml && \
             ros2 param set /motor_driver_node publish_tf true" 2>/dev/null || true
    fi
}

CLEANUP_DONE=false
cleanup() {
    if [ "$CLEANUP_DONE" = true ]; then return; fi
    CLEANUP_DONE=true
    trap '' SIGINT SIGTERM
    log_warn "Shutting down Mac brain nodes..."
    pkill -f "foxglove_bridge" 2>/dev/null || true
    pkill -f "slam_toolbox" 2>/dev/null || true
    pkill -f "nav2" 2>/dev/null || true
    pkill -f "ekf_node" 2>/dev/null || true
    start_pi_map_tf
    restore_motor_tf
}
trap cleanup EXIT SIGINT SIGTERM

# Kill leftover Mac-side brain processes from a prior crashed/hard-killed run.
# Orphans re-parent to PID 1 and keep holding port 8765, blocking the new
# foxglove_bridge with a silent "Bind Error". Auto-kill is the right default
# for a single-operator setup; swap to a detect-and-refuse check if you run
# multiple Foxglove bridges on purpose.
kill_stale_instances() {
    local pids_8765
    pids_8765=$(lsof -ti :8765 2>/dev/null || true)
    if [ -n "$pids_8765" ]; then
        log_warn "Port 8765 held by PID(s) $pids_8765 — killing stale foxglove"
    fi
    # Include every Nav2 lifecycle component — leaving a stale planner_server
    # or bt_navigator behind is what causes "lifecycle stuck inactive" on
    # the next boot, because the new instance can't bind the same node name
    # while the zombie is still up.
    local pattern="foxglove_bridge|ekf_node|slam_toolbox|nav2_bringup"
    pattern="$pattern|nav2_amcl|amcl"
    pattern="$pattern|controller_server|planner_server|bt_navigator"
    pattern="$pattern|behavior_server|smoother_server|velocity_smoother"
    pattern="$pattern|waypoint_follower|lifecycle_manager|nav2_map_server|map_server"
    pattern="$pattern|coverage_node|coverage_tracker"
    if pgrep -f "$pattern" >/dev/null 2>&1; then
        pkill -TERM -f "$pattern" 2>/dev/null || true
        sleep 1
        pkill -KILL -f "$pattern" 2>/dev/null || true
    fi
}

# Wait until a topic is publishing at >= min_hz, with a timeout. Returns 0
# on success, 1 on timeout. Use this instead of fixed `sleep N` — it adapts
# to slow boot conditions (cold ROS daemon, DDS discovery delay).
wait_for_topic() {
    local topic="$1"
    local timeout_s="${2:-30}"
    local min_hz="${3:-1.0}"
    log_info "Waiting up to ${timeout_s}s for $topic (>= ${min_hz} Hz)..."
    local deadline=$((SECONDS + timeout_s))
    while [ $SECONDS -lt $deadline ]; do
        # `topic hz` measures over a 5s window, so cap our probe at 4s and
        # bail early if it returns rate. The grep handles "average rate: X.YZ".
        local rate
        rate=$(timeout 4 ros2 topic hz "$topic" 2>&1 \
                | grep -oE 'average rate: [0-9.]+' \
                | head -1 | awk '{print $3}')
        if [ -n "$rate" ] && \
           [ "$(awk -v r="$rate" -v m="$min_hz" 'BEGIN{print (r>=m)}')" = "1" ]; then
            log_info "  $topic publishing at ${rate} Hz — OK"
            return 0
        fi
        sleep 1
    done
    log_error "Timed out waiting for $topic"
    return 1
}

# After Nav2 launches, every lifecycle node must reach 'active' or no
# action server will accept goals. Poll until they all are, or recover
# automatically. The first cold-start often hits a race where one node
# misses the activation window — RESET+STARTUP fixes it deterministically.
verify_and_recover_nav2() {
    local timeout_s="${1:-25}"
    # Must match the lifecycle_nodes list in scripts/nav2_launch.py.
    # /smoother_server is NOT in the list — Nav2 has two distinct smoothers
    # and we use velocity_smoother (the cmd_vel limiter), not smoother_server
    # (the path smoother). Adding /smoother_server here makes verification
    # always fail because that node doesn't exist.
    local nav_nodes=(/map_server /amcl /controller_server /planner_server
                     /behavior_server /velocity_smoother /waypoint_follower
                     /bt_navigator)
    log_info "Verifying Nav2 lifecycle state (up to ${timeout_s}s)..."
    local deadline=$((SECONDS + timeout_s))
    local all_active=false
    while [ $SECONDS -lt $deadline ]; do
        all_active=true
        for n in "${nav_nodes[@]}"; do
            local state
            state=$(timeout 3 ros2 service call ${n}/get_state \
                      lifecycle_msgs/srv/GetState 2>&1 \
                      | grep -oE "label='[a-z]+'" | cut -d"'" -f2)
            if [ "$state" != "active" ]; then
                all_active=false
                break
            fi
        done
        if [ "$all_active" = "true" ]; then
            log_info "  All Nav2 nodes active — OK"
            return 0
        fi
        sleep 2
    done
    # We hit the timeout with at least one node not active. Try recovery.
    log_warn "Some Nav2 nodes did not reach 'active'. Attempting RESET+STARTUP recovery..."
    timeout 8 ros2 service call \
        /lifecycle_manager_navigation/manage_nodes \
        nav2_msgs/srv/ManageLifecycleNodes "{command: 3}" >/dev/null 2>&1 || true
    sleep 1
    if timeout 20 ros2 service call \
        /lifecycle_manager_navigation/manage_nodes \
        nav2_msgs/srv/ManageLifecycleNodes "{command: 0}" 2>&1 \
        | grep -q "success=True"; then
        log_info "  Recovery succeeded — Nav2 fully active"
        return 0
    fi
    log_error "Nav2 recovery failed. Try: tools/nav2_recover.py for diagnostics"
    return 1
}

# ── Pre-flight checks ──────────────────────────────────────────────
log_info "Running pre-flight checks..."

# 0) Clear orphaned Mac-side processes from a previous crashed run
kill_stale_instances

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
    log_error "Check: Pi edge services running? RPLIDAR C1 USB connected?"
    log_error "  ssh pi@$PI_HOST 'sudo systemctl status rovac-edge-rplidar-c1'"
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

        log_info "Starting Foxglove Bridge on port 8765..."
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
        ;;

    nav)
        if [ -z "$MAP_FILE" ]; then
            log_error "Navigation mode requires a map file"
            usage
            exit 1
        fi

        stop_pi_map_tf
        disable_motor_tf

        # EKF must run for AMCL to get a scrub-free odom->base_link TF.
        # Without EKF, AMCL localizes against the motor driver's raw /odom
        # yaw (which tread-scrubs during turns) and drifts heavily.
        log_info "Starting EKF sensor fusion (wheel odom + BNO055 IMU)..."
        ros2 launch $HOME/robots/rovac/scripts/ekf_launch.py &
        EKF_PID=$!

        # Wait for EKF to actually be publishing — the old `sleep 2` was a
        # fixed guess that broke whenever DDS discovery or EKF init was slow,
        # which is what caused Nav2 lifecycle nodes to fail activation.
        if ! wait_for_topic /odometry/filtered 30 15.0; then
            log_error "EKF never started publishing /odometry/filtered."
            log_error "Nav2 will not function correctly. Aborting."
            exit 1
        fi

        # NOTE: RoboStack doesn't package nav2_bringup for macOS (osx-arm64),
        # so we use our own launch file that wires up the individual Nav2
        # nodes the same way bringup_launch.py would. See scripts/nav2_launch.py.
        log_info "Starting Nav2 with map: $MAP_FILE"
        ros2 launch $HOME/robots/rovac/scripts/nav2_launch.py \
            map:="$MAP_FILE" \
            params_file:=$HOME/robots/rovac/config/nav2_params.yaml \
            use_sim_time:=false &

        # Verify all Nav2 lifecycle nodes reach 'active'. This is the actual
        # readiness signal — without it, /navigate_to_pose silently rejects
        # goals because bt_navigator never came up. Auto-recovers via
        # RESET+STARTUP if the manager got wedged on the first activation.
        verify_and_recover_nav2 25 || \
            log_warn "Nav2 may not be fully ready — coverage runs may stall"

        log_info "Starting Foxglove Bridge..."
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
        FOX_PID=$!
        ;;

    ekf)
        disable_motor_tf

        log_info "Starting EKF sensor fusion (wheel odom + BNO055 IMU)..."
        log_info "BNO055 onboard IMU provides gyro-fused heading correction"
        ros2 launch $HOME/robots/rovac/scripts/ekf_launch.py &

        log_info "Starting Foxglove Bridge..."
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
        ;;

    slam-ekf)
        stop_pi_map_tf
        disable_motor_tf

        log_info "Starting EKF sensor fusion (wheel odom + BNO055 IMU)..."
        ros2 launch $HOME/robots/rovac/scripts/ekf_launch.py &
        sleep 2  # Let EKF start publishing TF before SLAM needs it

        log_info "Starting SLAM Toolbox (Online Async mode)..."
        ros2 launch slam_toolbox online_async_launch.py \
            slam_params_file:=$HOME/robots/rovac/config/slam_params.yaml \
            use_sim_time:=false &

        log_info "Starting Foxglove Bridge on port 8765..."
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
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
        ;;

    all)
        stop_pi_map_tf

        log_info "Starting full stack: SLAM + Nav2 + Foxglove..."

        # Start SLAM first
        ros2 launch slam_toolbox online_async_launch.py \
            slam_params_file:=$HOME/robots/rovac/config/slam_params.yaml \
            use_sim_time:=false &
        sleep 3

        # Start Nav2
        ros2 launch nav2_bringup navigation_launch.py \
            use_sim_time:=false \
            params_file:=$HOME/robots/rovac/config/nav2_params.yaml &

        # Start Foxglove
        ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 &
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
if [ "$MODE" = "slam" ] || [ "$MODE" = "slam-ekf" ] || [ "$MODE" = "all" ]; then
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

wait || true
