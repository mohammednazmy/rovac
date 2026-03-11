#!/bin/bash
#
# ROVAC Wireless Bringup Script (Mac)
#
# Starts all Mac-side processes for wireless ESP32 operation:
#   1. micro-ROS Agent (WiFi UDP bridge to Gateway ESP32)
#   2. robot_state_publisher (URDF → static TFs)
#   3. cmd_vel_mux (priority: joy > obstacle > nav)
#   4. joy_node + ps2_joy_mapper (PS2 controller on Mac USB)
#   5. static_transform_publisher (map→odom identity, fallback)
#
# Usage:
#   ./mac_wireless_bringup.sh start    # Start all processes
#   ./mac_wireless_bringup.sh stop     # Stop all processes
#   ./mac_wireless_bringup.sh status   # Show process status
#   ./mac_wireless_bringup.sh restart  # Restart all
#
# Environment:
#   AGENT_PORT  - micro-ROS Agent UDP port (default: 8888)
#   AGENT_MODE  - "source" or "docker" (default: source)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="/tmp/rovac_wireless"
PID_DIR="/tmp/rovac_wireless/pids"

AGENT_PORT="${AGENT_PORT:-8888}"
AGENT_MODE="${AGENT_MODE:-docker}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[ROVAC]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[ROVAC]${NC} $1"; }
log_error()   { echo -e "${RED}[ROVAC]${NC} $1"; }
log_section() { echo -e "\n${CYAN}=== $1 ===${NC}"; }

# Source ROS2 environment
source_ros() {
    eval "$(/opt/homebrew/Caskroom/miniforge/base/bin/conda shell.bash hook)"
    conda activate ros_jazzy
    source "$ROVAC_DIR/config/ros2_env.sh"
}

mkdir_logs() {
    mkdir -p "$LOG_DIR" "$PID_DIR"
}

# --- Process management ---

start_process() {
    local name="$1"
    shift
    local pid_file="$PID_DIR/${name}.pid"
    local log_file="$LOG_DIR/${name}.log"

    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        log_warn "$name already running (PID $(cat "$pid_file"))"
        return 0
    fi

    log_info "Starting $name..."
    "$@" > "$log_file" 2>&1 &
    local pid=$!
    echo "$pid" > "$pid_file"
    log_info "$name started (PID $pid, log: $log_file)"
}

stop_process() {
    local name="$1"
    local pid_file="$PID_DIR/${name}.pid"

    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log_info "Stopping $name (PID $pid)..."
            kill "$pid" 2>/dev/null || true
            # Wait up to 3s for graceful shutdown
            for i in 1 2 3; do
                if ! kill -0 "$pid" 2>/dev/null; then break; fi
                sleep 1
            done
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$pid_file"
    fi
}

check_process() {
    local name="$1"
    local pid_file="$PID_DIR/${name}.pid"

    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo -e "  ${GREEN}●${NC} $name (PID $(cat "$pid_file"))"
    else
        echo -e "  ${RED}○${NC} $name (not running)"
    fi
}

# --- Start all ---

do_start() {
    log_section "ROVAC Wireless Bringup"
    mkdir_logs
    source_ros

    # 1. micro-ROS Agent
    log_section "micro-ROS Agent (UDP port $AGENT_PORT)"
    if [ "$AGENT_MODE" = "docker" ]; then
        # Docker mode — use official micro-ROS agent image
        # --net=host doesn't work on macOS Docker, so we map the port
        start_process "uros_agent" \
            docker run --rm --name rovac_uros_agent \
            -p "${AGENT_PORT}:${AGENT_PORT}/udp" \
            microros/micro-ros-agent:jazzy \
            udp4 --port "$AGENT_PORT" -v4
    else
        # Source build mode — assumes ~/uros_ws is built
        start_process "uros_agent" \
            ros2 run micro_ros_agent micro_ros_agent udp4 --port "$AGENT_PORT" -v4
    fi

    # 2. robot_state_publisher (URDF → static TFs)
    local urdf_file="$ROVAC_DIR/ros2_ws/src/tank_description/urdf/tank.urdf"
    if [ -f "$urdf_file" ]; then
        log_section "Robot State Publisher"
        local robot_desc
        robot_desc=$(cat "$urdf_file")
        start_process "robot_state_publisher" \
            ros2 run robot_state_publisher robot_state_publisher \
            --ros-args -p robot_description:="$robot_desc"
    else
        log_warn "URDF not found at $urdf_file, skipping robot_state_publisher"
    fi

    # 3. cmd_vel_mux (priority multiplexer)
    local mux_script="$ROVAC_DIR/ros2_ws/src/tank_description/tank_description/cmd_vel_mux.py"
    if [ -f "$mux_script" ]; then
        log_section "cmd_vel_mux"
        start_process "cmd_vel_mux" python3 "$mux_script"
    else
        log_warn "cmd_vel_mux not found, skipping"
    fi

    # 4. PS2 controller (joy_node + mapper)
    log_section "PS2 Controller"
    # Check if a joystick is connected
    if ls /dev/input/js* 2>/dev/null | head -1 > /dev/null; then
        start_process "joy_node" \
            ros2 run joy joy_node --ros-args \
            -p device_id:=0 \
            -p deadzone:=0.1 \
            -p autorepeat_rate:=20.0
        sleep 1
        start_process "ps2_mapper" \
            python3 "$SCRIPT_DIR/ps2_joy_mapper_node.py"
    else
        log_warn "No joystick detected at /dev/input/js*"
        log_warn "PS2 controller will need to be started manually"
    fi

    # 5. Static transform: map → odom (identity, fallback when no SLAM)
    log_section "Static Transforms"
    start_process "map_odom_tf" \
        ros2 run tf2_ros static_transform_publisher \
        --x 0 --y 0 --z 0 --yaw 0 --pitch 0 --roll 0 \
        --frame-id map --child-frame-id odom

    log_section "Bringup Complete"
    log_info "Gateway ESP32 should connect automatically when powered on"
    log_info "Check: ros2 topic list --no-daemon"
    log_info "Expected topics: /odom, /scan, /cmd_vel, /tf, /diagnostics"
}

# --- Stop all ---

do_stop() {
    log_section "Stopping ROVAC Wireless Processes"

    stop_process "map_odom_tf"
    stop_process "ps2_mapper"
    stop_process "joy_node"
    stop_process "cmd_vel_mux"
    stop_process "robot_state_publisher"

    # Stop micro-ROS agent
    if [ "$AGENT_MODE" = "docker" ]; then
        docker stop rovac_uros_agent 2>/dev/null || true
    fi
    stop_process "uros_agent"

    log_info "All processes stopped"
}

# --- Status ---

do_status() {
    log_section "ROVAC Wireless Process Status"
    check_process "uros_agent"
    check_process "robot_state_publisher"
    check_process "cmd_vel_mux"
    check_process "joy_node"
    check_process "ps2_mapper"
    check_process "map_odom_tf"
}

# --- Main ---

case "${1:-}" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_stop; sleep 1; do_start ;;
    status)  do_status ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        echo ""
        echo "Starts Mac-side processes for wireless ESP32 operation."
        echo "The Gateway ESP32 connects to the micro-ROS Agent via WiFi UDP."
        echo ""
        echo "Environment variables:"
        echo "  AGENT_PORT=$AGENT_PORT  (micro-ROS Agent UDP port)"
        echo "  AGENT_MODE=$AGENT_MODE  ('source' or 'docker')"
        exit 1
        ;;
esac
