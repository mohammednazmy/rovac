#!/bin/bash
# Pi Edge Launch Script
# Runs on Raspberry Pi - sensors and actuators only
# The Mac handles Nav2, SLAM, and high-level processing

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[PI-EDGE]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[PI-EDGE]${NC} $1"; }
log_error() { echo -e "${RED}[PI-EDGE]${NC} $1"; }

# Source ROS2
source /opt/ros/jazzy/setup.bash
[ -f ~/yahboom_tank_ws/install/setup.bash ] && source ~/yahboom_tank_ws/install/setup.bash

# Load shared ROS2 environment config if available
ROS_ENV="$HOME/ros2_env.sh"
if [ ! -f "$ROS_ENV" ] && [ -f "$HOME/robots/rovac/config/ros2_env.sh" ]; then
    ROS_ENV="$HOME/robots/rovac/config/ros2_env.sh"
fi

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

log_info "Starting Pi Edge Node Stack..."
log_info "ROS_DOMAIN_ID: $ROS_DOMAIN_ID"

# Create a cleanup function
cleanup() {
    log_warn "Shutting down Pi edge nodes..."
    pkill -f "tank_motor_driver" 2>/dev/null || true
    pkill -f "bst4wd_sensors" 2>/dev/null || true
    pkill -f "xv11_lidar" 2>/dev/null || true
    pkill -f "phone_camera_publisher" 2>/dev/null || true
    pkill -f "cmd_vel_mux" 2>/dev/null || true
    # Kill screen sessions
    screen -S lidar -X quit 2>/dev/null || true
    screen -S phone_cam -X quit 2>/dev/null || true
    screen -S camera_pub -X quit 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start cmd_vel mux (routes /cmd_vel_joy + /cmd_vel_smoothed -> /cmd_vel)
if ! screen -ls | grep -q "\.mux"; then
    screen -S mux -X quit 2>/dev/null || true
    sleep 0.5
    log_info "Starting cmd_vel mux (in screen session 'mux')..."
    screen -dmS mux bash -c "source /opt/ros/jazzy/setup.bash && source ~/yahboom_tank_ws/install/setup.bash && source ~/ros2_env.sh 2>/dev/null && python3 ~/yahboom_tank_ws/src/tank_description/tank_description/cmd_vel_mux.py 2>&1 | tee /tmp/cmd_vel_mux.log"
    sleep 2
    if screen -ls | grep -q "\.mux"; then
        log_info "cmd_vel_mux started"
    else
        log_error "Failed to start cmd_vel_mux - check /tmp/cmd_vel_mux.log"
    fi
else
    log_info "cmd_vel_mux already running"
fi

# Start nodes in background
log_info "Starting motor driver..."
python3 ~/tank_motor_driver.py &
MOTOR_PID=$!
sleep 1

log_info "Starting sensors node..."
python3 ~/bst4wd_sensors_node.py &
SENSORS_PID=$!
sleep 1

# Start LIDAR if serial device exists
# This robot's XV11 LIDAR is wired to the Pi UART (ttyAMA0). If you move it,
# override with: export LIDAR_PORT=/dev/ttyUSB0 (or similar).
LIDAR_PORT="${LIDAR_PORT:-}"
if [ -z "$LIDAR_PORT" ]; then
    if [ -e /dev/ttyAMA0 ]; then
        LIDAR_PORT="/dev/ttyAMA0"
    elif [ -e /dev/ttyUSB0 ]; then
        LIDAR_PORT="/dev/ttyUSB0"
    elif [ -e /dev/ttyACM0 ]; then
        # Avoid selecting an Android phone (CDC ACM) as a LIDAR port.
        if udevadm info -q property -n /dev/ttyACM0 2>/dev/null | grep -qE '^ID_MODEL=SAMSUNG_Android$'; then
            LIDAR_PORT=""
        else
            LIDAR_PORT="/dev/ttyACM0"
        fi
    fi
fi

if [ -n "$LIDAR_PORT" ]; then
    # Kill any existing LIDAR screen session
    screen -S lidar -X quit 2>/dev/null || true
    sleep 0.5
    log_info "Starting LIDAR on $LIDAR_PORT (in screen session 'lidar')..."
    screen -dmS lidar bash -c "source /opt/ros/jazzy/setup.bash && source ~/yahboom_tank_ws/install/setup.bash && source ~/ros2_env.sh 2>/dev/null && ros2 run xv11_lidar_python xv11_lidar --ros-args -p port:=$LIDAR_PORT"
    sleep 2
    if screen -ls | grep -q lidar; then
        log_info "LIDAR screen session started"
    else
        log_error "Failed to start LIDAR screen session"
    fi
else
    log_warn "No LIDAR serial device found - skipping"
fi

# Start phone camera if Android phone is connected via ADB
if adb devices 2>/dev/null | grep -q "device$"; then
    log_info "Phone detected via ADB, starting camera stream..."
    
    # Kill existing camera sessions
    screen -S phone_cam -X quit 2>/dev/null || true
    screen -S camera_pub -X quit 2>/dev/null || true
    sleep 0.5
    
    # Setup v4l2loopback if not already loaded
    if [ ! -e /dev/video10 ]; then
        log_info "Setting up v4l2loopback..."
        sudo modprobe -r v4l2loopback 2>/dev/null || true
        sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="Phone_Camera" exclusive_caps=1
        sudo chmod 666 /dev/video10
        sleep 1
    fi
    
    # Start scrcpy camera stream (back camera by default)
    CAM_ID="${PHONE_CAMERA_ID:-0}"
    log_info "Starting scrcpy camera stream (camera $CAM_ID) -> /dev/video10"
    screen -dmS phone_cam bash -c "scrcpy --video-source=camera --camera-id=${CAM_ID} --camera-size=640x480 --camera-fps=15 --v4l2-sink=/dev/video10 --no-window --no-audio 2>&1 | tee /tmp/phone_cam.log"
    sleep 3
    
    # Start ROS2 camera publisher
    if [ -e /dev/video10 ]; then
        log_info "Starting phone camera ROS2 publisher..."
        screen -dmS camera_pub bash -c "source /opt/ros/jazzy/setup.bash && source ~/ros2_env.sh 2>/dev/null && python3 ~/phone_camera_publisher.py /dev/video10 /phone/camera/image_raw 2>&1 | tee /tmp/camera_pub.log"
        sleep 1
        if screen -ls | grep -q camera_pub; then
            log_info "Phone camera publisher started"
        else
            log_error "Failed to start camera publisher"
        fi
    fi
else
    log_warn "No Android phone detected via ADB - camera disabled"
    log_warn "Connect phone via USB and enable USB debugging"
fi

log_info "Pi Edge Stack Running!"
log_info "Topics published:"
echo "  /cmd_vel (subscribed by motor driver)"
echo "  /scan (LIDAR)"
echo "  /sensors/ultrasonic/range"
echo "  /sensors/imu"
echo "  /phone/camera/image_raw (phone camera)"
echo "  /phone/camera/image_raw/compressed"
echo ""
log_info "Screen sessions:"
screen -ls | grep -E "lidar|phone_cam|camera_pub" || echo "  (none)"
echo ""
log_info "Press Ctrl+C to stop all nodes"

# Wait for any process to exit
wait
