#!/bin/bash
#
# ROVAC Standalone Control Script
# Architecture: Mac (Brain + Controller) <-> Pi (Edge)
#
# This script:
#   1. Starts the Pi edge stack via SSH (motors, sensors, LIDAR, camera)
#   2. Starts controller nodes on Mac (joy_node, joy_mapper)
#   3. Optionally starts Foxglove bridge for visualization
#
# Usage:
#   ./standalone_control.sh start    # Start everything
#   ./standalone_control.sh stop     # Stop everything
#   ./standalone_control.sh restart  # Restart everything
#   ./standalone_control.sh status   # Show status
#
# Environment variables:
#   PI_HOST         - Pi SSH target (default: pi@192.168.1.200)
#   JOY_ID          - Joystick device ID (default: 0)
#   START_FOXGLOVE  - Start Foxglove bridge (default: 0)
#   FOXGLOVE_PORT   - Foxglove port (default: 8765)
#   STOP_PI_EDGE    - Also stop Pi edge on stop (default: 1)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Configuration
PI_HOST="${PI_HOST:-pi@192.168.1.200}"
JOY_ID="${JOY_ID:-0}"
START_FOXGLOVE="${START_FOXGLOVE:-0}"
FOXGLOVE_PORT="${FOXGLOVE_PORT:-8765}"
STOP_PI_EDGE="${STOP_PI_EDGE:-1}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[ROVAC]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[ROVAC]${NC} $1"; }
log_error() { echo -e "${RED}[ROVAC]${NC} $1"; }
log_section() { echo -e "\n${CYAN}=== $1 ===${NC}"; }

# Source ROS2 environment on Mac
source_ros() {
    eval "$(/opt/homebrew/bin/conda shell.bash hook)"
    conda activate ros_jazzy
    if [ -f "$ROVAC_DIR/config/ros2_env.sh" ]; then
        source "$ROVAC_DIR/config/ros2_env.sh"
    else
        log_error "ros2_env.sh not found!"
        exit 1
    fi

    # IMPORTANT (macOS): ensure we run rclpy with the conda env Python.
    # System python3 (often 3.13+) will fail to import rclpy built for this env.
    if [ -n "${CONDA_PREFIX:-}" ] && [ -x "$CONDA_PREFIX/bin/python3" ]; then
        export ROVAC_PYTHON="$CONDA_PREFIX/bin/python3"
    elif [ -n "${CONDA_PREFIX:-}" ] && [ -x "$CONDA_PREFIX/bin/python" ]; then
        export ROVAC_PYTHON="$CONDA_PREFIX/bin/python"
    else
        export ROVAC_PYTHON="$(command -v python3)"
    fi
}

# Check Pi connectivity
check_pi() {
    if ! ping -c 1 -W 2 192.168.1.200 >/dev/null 2>&1; then
        log_error "Cannot reach Pi at 192.168.1.200"
        log_error "Check network connection"
        return 1
    fi
    return 0
}

# Start Pi edge stack
start_pi_edge() {
    log_section "Pi Edge Stack"
    
    if ! check_pi; then
        return 1
    fi

    # Prefer systemd on the Pi if rovac-edge.target is installed.
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "systemctl cat rovac-edge.target >/dev/null 2>&1"; then
        log_info "Pi edge stack is managed by systemd (rovac-edge.target)"
        ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "sudo systemctl start rovac-edge.target"
        sleep 1
        if ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "systemctl is-active --quiet rovac-edge.target"; then
            log_info "Pi edge stack active (systemd)"
            ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "systemctl --no-pager -l status rovac-edge.target | sed -n '1,8p'" 2>/dev/null || true
            return 0
        fi
        log_error "Failed to start Pi edge stack via systemd"
        log_error "Check: ssh $PI_HOST 'systemctl --no-pager -l status rovac-edge.target rovac-edge-bst4wd.service rovac-edge-esp32.service rovac-edge-mux.service rovac-edge-tf.service'"
        return 1
    fi
    
    # Note: "motor driver running" does NOT imply the whole edge stack is healthy.
    # We need motor + mux + tf for full controller functionality (drive + transforms).
    local motor_running=0
    local mux_running=0
    local tf_running=0

    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "pgrep -f 'bst4wd_driver\\.py|esp32_at8236_driver\\.py' >/dev/null" 2>/dev/null; then
        motor_running=1
    fi
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "pgrep -f 'cmd_vel_mux' >/dev/null" 2>/dev/null; then
        mux_running=1
    fi
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "pgrep -f 'robot_state_publisher' >/dev/null" 2>/dev/null; then
        tf_running=1
    fi

    if [ "$motor_running" = "1" ] && [ "$mux_running" = "1" ] && [ "$tf_running" = "1" ]; then
        log_info "Pi edge stack already running (motor + mux + tf)"
        return 0
    fi

    log_warn "Pi edge stack partially running:"
    [ "$motor_running" = "1" ] && echo "  [+] motor driver (bst4wd/esp32)" || echo "  [-] motor driver (bst4wd/esp32)"
    [ "$mux_running" = "1" ] && echo "  [+] cmd_vel_mux" || echo "  [-] cmd_vel_mux"
    [ "$tf_running" = "1" ] && echo "  [+] robot_state_publisher" || echo "  [-] robot_state_publisher"

    # If nothing is up, try starting the systemd target as a fallback.
    if [ "$motor_running" = "0" ] && [ "$mux_running" = "0" ] && [ "$tf_running" = "0" ]; then
        log_info "Starting Pi edge stack via systemd target..."
        ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" \
            "sudo systemctl start rovac-edge.target" 2>/dev/null || true
    else
        log_info "Starting missing Pi edge components via systemd..."
        if [ "$motor_running" = "0" ]; then
            ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" \
                "sudo systemctl start rovac-edge-esp32.service || sudo systemctl start rovac-edge-bst4wd.service" 2>/dev/null || true
        fi
        if [ "$mux_running" = "0" ]; then
            ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" \
                "sudo systemctl start rovac-edge-mux.service" 2>/dev/null || true
        fi
        if [ "$tf_running" = "0" ]; then
            ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" \
                "sudo systemctl start rovac-edge-tf.service" 2>/dev/null || true
        fi
    fi

    # Wait for startup
    sleep 3

    # Verify it started
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "pgrep -f 'bst4wd_driver\\.py|esp32_at8236_driver\\.py' >/dev/null" 2>/dev/null; then
        log_info "Pi edge motor driver running"
    else
        log_error "Failed to start Pi edge stack"
        log_error "Check logs: ssh $PI_HOST 'sudo journalctl -u rovac-edge-bst4wd -u rovac-edge-esp32 -n 50 --no-pager'"
        return 1
    fi
}

# Start controller nodes on Mac
start_controllers() {
    log_section "Mac Controllers"

    # If the persistent launchd agent is installed, use it to avoid duplicate joy_node/mapper processes.
    local agent_plist="$HOME/Library/LaunchAgents/com.rovac.controller.plist"
    if [ -f "$agent_plist" ]; then
        log_info "Using launchd controller agent (com.rovac.controller)..."
        "$SCRIPT_DIR/install_mac_autostart.sh" start
        sleep 1
        if pgrep -f "rovac_controller_supervisor.sh" >/dev/null; then
            log_info "Controller agent running"
            return 0
        fi
        log_warn "Controller agent did not appear to start; check: tail -n 200 /tmp/rovac_controller.err"
        return 1
    fi

    # Manual mode (no launchd agent): start joy_node + joy_mapper directly.
    # Kill any existing controller processes
    pkill -f "ros2 run joy joy_node" 2>/dev/null || true
    pkill -f "joy_mapper_node.py" 2>/dev/null || true
    sleep 1

    log_info "Starting joy_node (device_id=$JOY_ID)..."
    nohup ros2 run joy joy_node --ros-args \
        -p device_id:="$JOY_ID" \
        -p autorepeat_rate:=20.0 \
        -p deadzone:=0.05 \
        -r joy:=/tank/joy \
        > /tmp/joy_node.log 2>&1 &
    sleep 1

    if pgrep -f "ros2 run joy joy_node" >/dev/null; then
        log_info "joy_node started"
    else
        log_error "Failed to start joy_node"
        log_error "Check: cat /tmp/joy_node.log"
        return 1
    fi

    log_info "Starting joy_mapper..."
    nohup "${ROVAC_PYTHON:-python3}" "$SCRIPT_DIR/joy_mapper_node.py" \
        > /tmp/joy_mapper.log 2>&1 &
    sleep 1

    if pgrep -f "joy_mapper_node.py" >/dev/null; then
        log_info "joy_mapper started"
    else
        log_error "Failed to start joy_mapper"
        log_error "Check: cat /tmp/joy_mapper.log"
        return 1
    fi
}

# Start Foxglove bridge
start_foxglove() {
    if [ "$START_FOXGLOVE" != "1" ]; then
        return 0
    fi
    
    log_section "Foxglove Bridge"
    
    if pgrep -f "foxglove_bridge" >/dev/null; then
        log_info "Foxglove bridge already running"
        return 0
    fi
    
    log_info "Starting Foxglove bridge on port $FOXGLOVE_PORT..."
    nohup ros2 launch foxglove_bridge foxglove_bridge_launch.xml \
        port:="$FOXGLOVE_PORT" \
        > /tmp/foxglove_bridge.log 2>&1 &
    sleep 2
    
    if pgrep -f "foxglove_bridge" >/dev/null; then
        log_info "Foxglove bridge started at ws://localhost:$FOXGLOVE_PORT"
    else
        log_warn "Failed to start Foxglove bridge"
    fi
}

# Wait for DDS discovery and verify topics
verify_system() {
    log_section "System Verification"
    
    log_info "Waiting for DDS discovery (3s)..."
    sleep 3
    
    # Check topics using Python (faster than ros2 topic list)
    ${ROVAC_PYTHON:-python3} -c "
import rclpy
import time
rclpy.init()
node = rclpy.create_node('verify')
time.sleep(2)
topics = [t for t, _ in node.get_topic_names_and_types()]
node.destroy_node()
rclpy.shutdown()

required = ['/cmd_vel_joy', '/tank/joy', '/odom']
found = []
missing = []
for t in required:
    if t in topics:
        found.append(t)
    else:
        missing.append(t)

print('Topics found:')
for t in found:
    print(f'  [+] {t}')
for t in missing:
    print(f'  [-] {t}')
" 2>&1 | grep -v -E "selected interface|deprecated|localhost_only"

    # Quick Pi health checks (ensure non-drive controls can work)
    if check_pi 2>/dev/null; then
        if ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "systemctl cat rovac-edge.target >/dev/null 2>&1"; then
            ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "
                (systemctl is-active --quiet rovac-edge-bst4wd.service || systemctl is-active --quiet rovac-edge-esp32.service) && echo '  [+] Pi motor service active' || echo '  [-] Pi motor service NOT active'
                systemctl is-active --quiet rovac-edge-mux.service && echo '  [+] Pi cmd_vel_mux service active' || echo '  [-] Pi cmd_vel_mux service NOT active'
                systemctl is-active --quiet rovac-edge-tf.service && echo '  [+] Pi TF publisher active' || echo '  [-] Pi TF publisher NOT active'
            " 2>/dev/null || true
        else
            ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "
                pgrep -f 'bst4wd_driver\\.py|esp32_at8236_driver\\.py' >/dev/null && echo '  [+] Pi motor driver running' || echo '  [-] Pi motor driver NOT running'
                pgrep -f 'cmd_vel_mux' >/dev/null && echo '  [+] Pi cmd_vel_mux running' || echo '  [-] Pi cmd_vel_mux NOT running'
            " 2>/dev/null || true
        fi
    fi
}

# Start all components
start_all() {
    source_ros
    
    log_info "Starting ROVAC system..."
    echo "  Mac: Controller (joy_node, joy_mapper)"
    echo "  Pi:  Edge (motors, sensors, LIDAR, camera)"
    echo ""
    
    start_pi_edge
    start_controllers
    start_foxglove
    verify_system
    
    log_section "Ready"
    log_info "Controller: Nintendo Switch Pro Controller"
    log_info "  Left Stick: Drive"
    log_info "  ZR/ZL: Forward/Reverse"
    log_info "  L/R: Turn left/right"
    log_info "  +/-: Speed up/down"
    echo ""
    log_info "Stop with: $0 stop"
}

# Stop all components
stop_all() {
    log_section "Stopping ROVAC"
    
    # Stop Mac processes
    log_info "Stopping Mac controllers..."
    local agent_plist="$HOME/Library/LaunchAgents/com.rovac.controller.plist"
    if [ -f "$agent_plist" ]; then
        "$SCRIPT_DIR/install_mac_autostart.sh" stop || true
    fi

    # Ensure any stray/manual instances are stopped too.
    pkill -f "ros2 run joy joy_node.*joy:=/tank/joy" 2>/dev/null || true
    pkill -f "joy_mapper_node.py" 2>/dev/null || true
    pkill -f "foxglove_bridge" 2>/dev/null || true
    
    # Stop Pi edge
    if [ "$STOP_PI_EDGE" = "1" ]; then
        if check_pi 2>/dev/null; then
            log_info "Stopping Pi edge stack..."
            if ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "systemctl cat rovac-edge.target >/dev/null 2>&1"; then
                ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "sudo systemctl stop rovac-edge.target" 2>/dev/null || true
            else
                ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "
                    pkill -f 'esp32_at8236_driver' 2>/dev/null || true
                    pkill -f 'robot_state_publisher' 2>/dev/null || true
                    pkill -f 'cmd_vel_mux' 2>/dev/null || true
                    pkill -f 'super_sensor_ros2_node' 2>/dev/null || true
                    pkill -f 'obstacle_avoidance_node' 2>/dev/null || true
                " 2>/dev/null || true
            fi
        fi
    fi
    
    log_info "ROVAC stopped"
}

# Show status
show_status() {
    source_ros 2>/dev/null || true
    
    log_section "Mac Processes"
    local agent_plist="$HOME/Library/LaunchAgents/com.rovac.controller.plist"
    if [ -f "$agent_plist" ]; then
        pgrep -f "rovac_controller_supervisor.sh" >/dev/null && echo "  [+] controller agent (launchd)" || echo "  [-] controller agent (launchd)"
    fi
    pgrep -f "joy_node" >/dev/null && echo "  [+] joy_node" || echo "  [-] joy_node"
    pgrep -f "joy_mapper_node.py" >/dev/null && echo "  [+] joy_mapper" || echo "  [-] joy_mapper"
    pgrep -f "foxglove_bridge" >/dev/null && echo "  [+] foxglove_bridge" || echo "  [-] foxglove_bridge"
    pgrep -f "slam_toolbox" >/dev/null && echo "  [+] slam_toolbox" || echo "  [-] slam_toolbox"
    
    log_section "Pi Processes"
    if check_pi 2>/dev/null; then
        if ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "systemctl cat rovac-edge.target >/dev/null 2>&1"; then
            ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "
                systemctl is-active --quiet rovac-edge.target && echo '  [+] rovac-edge.target (systemd)' || echo '  [-] rovac-edge.target (systemd)'
                systemctl is-active --quiet rovac-edge-bst4wd.service && echo '  [+] bst4wd motor (systemd)' || echo '  [-] bst4wd motor (systemd)'
                systemctl is-active --quiet rovac-edge-esp32.service && echo '  [+] esp32 motor (systemd)' || echo '  [-] esp32 motor (systemd)'
                systemctl is-active --quiet rovac-edge-tf.service && echo '  [+] tf (systemd)' || echo '  [-] tf (systemd)'
                systemctl is-active --quiet rovac-edge-mux.service && echo '  [+] mux (systemd)' || echo '  [-] mux (systemd)'
                systemctl is-active --quiet rovac-edge-lidar.service && echo '  [+] lidar (systemd)' || echo '  [-] lidar (systemd)'
                systemctl is-active --quiet rovac-edge-supersensor.service && echo '  [+] supersensor (systemd)' || echo '  [-] supersensor (systemd)'
            " 2>/dev/null || true
        else
            ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "
                pgrep -f 'bst4wd_driver' >/dev/null && echo '  [+] bst4wd_driver' || echo '  [-] bst4wd_driver'
                pgrep -f 'esp32_at8236_driver' >/dev/null && echo '  [+] esp32_at8236_driver' || echo '  [-] esp32_at8236_driver'
                pgrep -f 'robot_state_publisher' >/dev/null && echo '  [+] robot_state_publisher' || echo '  [-] robot_state_publisher'
                pgrep -f 'cmd_vel_mux' >/dev/null && echo '  [+] cmd_vel_mux' || echo '  [-] cmd_vel_mux'
            " 2>/dev/null || echo "  [!] Cannot connect to Pi"
        fi
    else
        echo "  [!] Pi not reachable"
    fi
    
    log_section "Topics (quick check)"
    ${ROVAC_PYTHON:-python3} -c "
import rclpy
import time
rclpy.init()
node = rclpy.create_node('status')
time.sleep(2)
topics = sorted([t for t, _ in node.get_topic_names_and_types()])
node.destroy_node()
rclpy.shutdown()
key_topics = ['/cmd_vel_joy', '/tank/joy', '/odom', '/cmd_vel']
for t in key_topics:
    if t in topics:
        print(f'  [+] {t}')
    else:
        print(f'  [-] {t}')
" 2>&1 | grep -E "^\s+\[" || echo "  [!] Could not list topics"
    echo ""
}

# Main
case "${1:-}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        stop_all
        sleep 2
        start_all
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        echo ""
        echo "Environment variables:"
        echo "  PI_HOST=$PI_HOST"
        echo "  JOY_ID=$JOY_ID"
        echo "  START_FOXGLOVE=$START_FOXGLOVE"
        echo "  FOXGLOVE_PORT=$FOXGLOVE_PORT"
        echo "  STOP_PI_EDGE=$STOP_PI_EDGE"
        exit 1
        ;;
esac
