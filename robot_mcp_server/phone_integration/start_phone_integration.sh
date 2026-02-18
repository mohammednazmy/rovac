#!/bin/bash
#
# Phone Integration Startup Script
# Starts all phone sensor and camera streaming to ROS2
#
# Usage:
#   ./start_phone_integration.sh start   - Start phone integration
#   ./start_phone_integration.sh stop    - Stop all phone processes
#   ./start_phone_integration.sh status  - Check status
#   ./start_phone_integration.sh sensors - Start sensors only
#   ./start_phone_integration.sh camera  - Start camera only
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$HOME/.ros/log/phone_integration"
SENSOR_PORT=8080
VIDEO_DEVICE="/dev/video10"
VENV_DIR="$SCRIPT_DIR/venv"

# Activate virtual environment
activate_venv() {
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
    fi
}

# Colors
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
NC="\033[0m"

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Source ROS2 and venv
source_ros() {
    activate_venv
    source /opt/ros/jazzy/setup.bash
    [ -f ~/yahboom_tank_ws/install/setup.bash ] && source ~/yahboom_tank_ws/install/setup.bash
}

# Check ADB connection
check_adb() {
    if ! adb devices | grep -q "device$"; then
        log_error "No Android device connected via ADB"
        log_info "Enable USB debugging on your phone and reconnect"
        return 1
    fi
    log_info "ADB device connected: $(adb devices | grep device$ | cut -f1)"
    return 0
}

# Setup ADB port forwarding for SensorServer
setup_adb_forward() {
    log_info "Setting up ADB port forwarding for SensorServer..."

    # Remove existing forwards
    adb forward --remove-all 2>/dev/null || true

    # Forward SensorServer port
    adb forward tcp:$SENSOR_PORT tcp:$SENSOR_PORT

    log_info "Port forwarding: localhost:$SENSOR_PORT -> phone:$SENSOR_PORT"
}

# Setup v4l2loopback for camera
setup_v4l2loopback() {
    log_info "Setting up v4l2loopback..."

    # Load module if not loaded
    if ! lsmod | grep -q v4l2loopback; then
        sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="Phone_Camera" exclusive_caps=1
    fi

    # Ensure permissions
    sudo chmod 666 $VIDEO_DEVICE 2>/dev/null || true

    log_info "v4l2loopback ready at $VIDEO_DEVICE"
}

# Start SensorServer app on phone
start_sensor_server_app() {
    log_info "Launching SensorServer app on phone..."

    # Launch the app
    adb shell am start -n github.umer0586.sensorserver/.MainActivity 2>/dev/null || true
    sleep 2

    # Note: User needs to manually start the server in the app
    log_warn "Please start the WebSocket server in SensorServer app on your phone"
    log_info "1. Open SensorServer app on phone"
    log_info "2. Tap 'Start' to begin streaming"
    log_info "3. The sensors node will auto-connect once server is running"
}

# Start phone sensors node
start_sensors_node() {
    source_ros
    mkdir -p "$LOG_DIR"

    log_info "Starting phone sensors node..."

    python3 "$SCRIPT_DIR/phone_sensors_node.py" \
        --ros-args \
        -p host:=localhost \
        -p port:=$SENSOR_PORT \
        -p frame_id:=phone_link \
        -p parent_frame:=base_link \
        -p phone_x:=0.05 \
        -p phone_y:=0.0 \
        -p phone_z:=0.12 \
        > "$LOG_DIR/phone_sensors.log" 2>&1 &

    echo $! > "$LOG_DIR/phone_sensors.pid"
    log_info "Phone sensors node started (PID: $!)"
}

# Start phone camera node
start_camera_node() {
    source_ros
    mkdir -p "$LOG_DIR"

    log_info "Starting phone camera node..."

    python3 "$SCRIPT_DIR/phone_camera_node.py" \
        --ros-args \
        -p video_device:=$VIDEO_DEVICE \
        -p camera:=back_main \
        -p width:=1280 \
        -p height:=720 \
        -p fps:=30 \
        -p frame_id:=phone_camera_link \
        -p publish_raw:=true \
        -p publish_compressed:=true \
        -p jpeg_quality:=75 \
        > "$LOG_DIR/phone_camera.log" 2>&1 &

    echo $! > "$LOG_DIR/phone_camera.pid"
    log_info "Phone camera node started (PID: $!)"
}

# Start all phone integration
start_all() {
    log_info "Starting phone integration..."

    check_adb || exit 1
    setup_adb_forward
    setup_v4l2loopback
    start_sensor_server_app

    sleep 2

    start_sensors_node
    start_camera_node

    log_info "Phone integration started successfully!"
    log_info "Check status with: $0 status"
}

# Stop all phone integration
stop_all() {
    log_info "Stopping phone integration..."

    # Kill sensor node
    if [ -f "$LOG_DIR/phone_sensors.pid" ]; then
        kill $(cat "$LOG_DIR/phone_sensors.pid") 2>/dev/null || true
        rm -f "$LOG_DIR/phone_sensors.pid"
    fi

    # Kill camera node
    if [ -f "$LOG_DIR/phone_camera.pid" ]; then
        kill $(cat "$LOG_DIR/phone_camera.pid") 2>/dev/null || true
        rm -f "$LOG_DIR/phone_camera.pid"
    fi

    # Kill scrcpy
    pkill -f "scrcpy.*v4l2-sink" 2>/dev/null || true

    # Remove ADB forwards
    adb forward --remove-all 2>/dev/null || true

    log_info "Phone integration stopped"
}

# Check status
check_status() {
    echo "=== Phone Integration Status ==="
    echo ""

    # ADB status
    echo -n "ADB Connection: "
    if adb devices | grep -q "device$"; then
        echo -e "${GREEN}Connected${NC}"
        adb devices | grep device$ | head -1
    else
        echo -e "${RED}Not connected${NC}"
    fi
    echo ""

    # Port forwarding
    echo -n "Port Forwarding: "
    if adb forward --list | grep -q "$SENSOR_PORT"; then
        echo -e "${GREEN}Active${NC}"
    else
        echo -e "${YELLOW}Not set${NC}"
    fi
    echo ""

    # Sensors node
    echo -n "Sensors Node: "
    if [ -f "$LOG_DIR/phone_sensors.pid" ] && kill -0 $(cat "$LOG_DIR/phone_sensors.pid") 2>/dev/null; then
        echo -e "${GREEN}Running${NC} (PID: $(cat $LOG_DIR/phone_sensors.pid))"
    else
        echo -e "${RED}Not running${NC}"
    fi

    # Camera node
    echo -n "Camera Node: "
    if [ -f "$LOG_DIR/phone_camera.pid" ] && kill -0 $(cat "$LOG_DIR/phone_camera.pid") 2>/dev/null; then
        echo -e "${GREEN}Running${NC} (PID: $(cat $LOG_DIR/phone_camera.pid))"
    else
        echo -e "${RED}Not running${NC}"
    fi

    # scrcpy
    echo -n "scrcpy: "
    if pgrep -f "scrcpy.*v4l2-sink" > /dev/null; then
        echo -e "${GREEN}Running${NC}"
    else
        echo -e "${YELLOW}Not running${NC}"
    fi

    # v4l2loopback
    echo -n "v4l2loopback: "
    if [ -c "$VIDEO_DEVICE" ]; then
        echo -e "${GREEN}$VIDEO_DEVICE exists${NC}"
    else
        echo -e "${RED}Not available${NC}"
    fi
    echo ""

    # ROS2 topics
    source_ros 2>/dev/null
    echo "=== Phone ROS2 Topics ==="
    ros2 topic list 2>/dev/null | grep "/phone/" || echo "No phone topics found"
}

# Main
case "${1:-}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    status)
        check_status
        ;;
    sensors)
        check_adb || exit 1
        setup_adb_forward
        start_sensor_server_app
        sleep 2
        start_sensors_node
        ;;
    camera)
        check_adb || exit 1
        setup_v4l2loopback
        start_camera_node
        ;;
    restart)
        stop_all
        sleep 2
        start_all
        ;;
    *)
        echo "Usage: $0 {start|stop|status|sensors|camera|restart}"
        echo ""
        echo "Commands:"
        echo "  start   - Start full phone integration (sensors + camera)"
        echo "  stop    - Stop all phone integration"
        echo "  status  - Check integration status"
        echo "  sensors - Start sensors only"
        echo "  camera  - Start camera only"
        echo "  restart - Restart all integration"
        exit 1
        ;;
esac
