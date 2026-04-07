#!/bin/bash
#
# Pi-Native House Mapping Script
# Uses vorwerk_lidar (XV-11) and RF2O laser odometry for SLAM
#
# Usage:
#   ./map_house.sh start      - Start mapping mode
#   ./map_house.sh stop       - Stop mapping
#   ./map_house.sh save [name]- Save current map
#   ./map_house.sh status     - Show mapping status
#

# set -e

MAPS_DIR="$HOME/maps"
FOXGLOVE_PORT=8765
LIDAR_DEVICE="/dev/ttyAMA0"

# Phone integration (optional)
PHONE_INTEGRATION_DIR="$HOME/robot_mcp_server/phone_integration"
: "${PHONE_ENABLE:=1}"
: "${PHONE_ENABLE_CAMERA:=1}"
: "${PHONE_ENABLE_FUSION:=0}"
: "${PHONE_SENSOR_HOST:=localhost}"     # localhost (ADB forward) or phone WiFi IP
: "${PHONE_SENSOR_PORT:=8080}"          # port on phone SensorServer app
: "${PHONE_SENSOR_LOCAL_PORT:=18080}"   # local port for ADB forwarding (avoid Pi camera port 8080)
: "${PHONE_VIDEO_DEVICE:=/dev/video10}"
: "${PHONE_CAMERA_ID:=0}"
: "${PHONE_CAMERA_RES:=1280x720}"
: "${PHONE_CAMERA_FPS:=15}"
: "${PHONE_FRAME_ID:=phone_link}"
: "${PHONE_PARENT_FRAME_ID:=base_link}"
: "${PHONE_CAMERA_FRAME_ID:=phone_camera_link}"

# Colors
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

source_ros_quiet() {
    source /opt/ros/jazzy/setup.bash 2>/dev/null || true
    [ -f ~/ros2_ws/install/setup.bash ] && source ~/ros2_ws/install/setup.bash
    [ -f ~/yahboom_tank_ws/install/setup.bash ] && source ~/yahboom_tank_ws/install/setup.bash
    [ -f ~/roarm_ws_em0/install/setup.bash ] && source ~/roarm_ws_em0/install/setup.bash
}

phone_venv_activate() {
    local venv_activate="$PHONE_INTEGRATION_DIR/venv/bin/activate"
    if [ -f "$venv_activate" ]; then
        # shellcheck disable=SC1090
        source "$venv_activate"
        return 0
    fi
    return 1
}

phone_adb_connected() {
    command -v adb >/dev/null 2>&1 || return 1
    adb devices 2>/dev/null | grep -q "device$"
}

phone_setup_adb_forward() {
    phone_adb_connected || return 1
    adb forward tcp:"$PHONE_SENSOR_LOCAL_PORT" tcp:"$PHONE_SENSOR_PORT" >/dev/null 2>&1 || true
}

phone_launch_sensor_server() {
    phone_adb_connected || return 1
    adb shell am start -n github.umer0586.sensorserver/.MainActivity 2>/dev/null || true
    log_warn "If sensors don't connect: open SensorServer on phone and tap START"
}

phone_setup_v4l2loopback() {
    local video_nr="${PHONE_VIDEO_DEVICE#/dev/video}"
    if [ ! -c "$PHONE_VIDEO_DEVICE" ]; then
        sudo modprobe v4l2loopback devices=1 video_nr="$video_nr" card_label="Phone_Camera" exclusive_caps=1 2>/dev/null || true
        sleep 1
    fi
    sudo chmod 666 "$PHONE_VIDEO_DEVICE" 2>/dev/null || true
}

phone_start_sensors() {
    [ "${PHONE_ENABLE}" = "1" ] || return 0
    [ -d "$PHONE_INTEGRATION_DIR" ] || return 0

    if pgrep -f "phone_sensors_node.py" &>/dev/null; then
        log_info "Phone sensors already running"
        return 0
    fi

    local connect_port="$PHONE_SENSOR_PORT"
    if [ "$PHONE_SENSOR_HOST" = "localhost" ]; then
        phone_setup_adb_forward || log_warn "ADB not connected; phone sensors may not connect to localhost:$PHONE_SENSOR_LOCAL_PORT"
        phone_launch_sensor_server || true
        connect_port="$PHONE_SENSOR_LOCAL_PORT"
    fi

    log_info "Starting phone sensors (ws://$PHONE_SENSOR_HOST:$connect_port)..."
    (
        phone_venv_activate || log_warn "Phone venv not found; using system python"
        source_ros_quiet
        nohup python3 "$PHONE_INTEGRATION_DIR/phone_sensors_node.py" --ros-args \
            -p host:="$PHONE_SENSOR_HOST" \
            -p port:="$connect_port" \
            -p frame_id:="$PHONE_FRAME_ID" \
            -p parent_frame:="$PHONE_PARENT_FRAME_ID" \
            > /tmp/phone_sensors.log 2>&1 &
    )
    sleep 1
}

phone_start_camera() {
    [ "${PHONE_ENABLE}" = "1" ] || return 0
    [ "${PHONE_ENABLE_CAMERA}" = "1" ] || return 0
    [ -d "$PHONE_INTEGRATION_DIR" ] || return 0

    if pgrep -f "phone_camera_simple.py" &>/dev/null || pgrep -f "phone_camera_node.py" &>/dev/null; then
        log_info "Phone camera node already running"
        return 0
    fi

    phone_setup_v4l2loopback

    local scrcpy_bin="/snap/bin/scrcpy"
    [ -x "$scrcpy_bin" ] || scrcpy_bin="$(command -v scrcpy 2>/dev/null || true)"
    if [ -n "$scrcpy_bin" ] && ! pgrep -f "scrcpy.*v4l2-sink=${PHONE_VIDEO_DEVICE}" &>/dev/null; then
        log_info "Starting scrcpy phone camera stream (camera_id=$PHONE_CAMERA_ID res=$PHONE_CAMERA_RES)..."
        SNAP_LAUNCHER_NOTICE_ENABLED=false nohup "$scrcpy_bin" \
            --video-source=camera \
            --camera-id="$PHONE_CAMERA_ID" \
            --camera-size="$PHONE_CAMERA_RES" \
            --no-playback \
            --v4l2-sink="$PHONE_VIDEO_DEVICE" \
            > /tmp/phone_scrcpy.log 2>&1 &
        sleep 2
    fi

    local width="${PHONE_CAMERA_RES%x*}"
    local height="${PHONE_CAMERA_RES#*x}"

    log_info "Starting phone camera ROS2 publisher ($PHONE_VIDEO_DEVICE)..."
    (
        phone_venv_activate || log_warn "Phone venv not found; using system python"
        source_ros_quiet
        nohup python3 "$PHONE_INTEGRATION_DIR/phone_camera_simple.py" --ros-args \
            -p video_device:="$PHONE_VIDEO_DEVICE" \
            -p width:="$width" \
            -p height:="$height" \
            -p fps:="$PHONE_CAMERA_FPS" \
            -p frame_id:="$PHONE_CAMERA_FRAME_ID" \
            > /tmp/phone_camera.log 2>&1 &
    )

    # Publish phone_link -> phone_camera_link TF for visualization/fusion.
    if ! pgrep -f "static_transform_publisher.*${PHONE_FRAME_ID}.*${PHONE_CAMERA_FRAME_ID}" &>/dev/null; then
        source_ros_quiet
        nohup ros2 run tf2_ros static_transform_publisher \
            0 0 0 0 0 0 "$PHONE_FRAME_ID" "$PHONE_CAMERA_FRAME_ID" \
            --ros-args -r __node:=phone_camera_tf \
            > /tmp/phone_camera_tf.log 2>&1 &
    fi

    sleep 1
}

phone_start_fusion() {
    [ "${PHONE_ENABLE}" = "1" ] || return 0
    [ "${PHONE_ENABLE_FUSION}" = "1" ] || return 0
    [ -d "$PHONE_INTEGRATION_DIR" ] || return 0

    if pgrep -f "lidar_camera_fusion_node.py" &>/dev/null; then
        log_info "Phone LIDAR-camera fusion already running"
        return 0
    fi

    log_info "Starting LIDAR-camera fusion (/phone/depth/*)..."
    (
        phone_venv_activate || log_warn "Phone venv not found; using system python"
        source_ros_quiet
        nohup python3 "$PHONE_INTEGRATION_DIR/lidar_camera_fusion_node.py" > /tmp/phone_fusion.log 2>&1 &
    )
    sleep 1
}

phone_start_all() {
    phone_start_sensors
    phone_start_camera
    phone_start_fusion
}

phone_stop_all() {
    pkill -f "lidar_camera_fusion_node.py" 2>/dev/null || true
    pkill -f "phone_camera_simple.py" 2>/dev/null || true
    pkill -f "phone_camera_node.py" 2>/dev/null || true
    pkill -f "phone_sensors_node.py" 2>/dev/null || true
    pkill -f "static_transform_publisher.*${PHONE_FRAME_ID}.*${PHONE_CAMERA_FRAME_ID}" 2>/dev/null || true
    pkill -f "scrcpy.*v4l2-sink=${PHONE_VIDEO_DEVICE}" 2>/dev/null || true
    command -v adb >/dev/null 2>&1 && adb forward --remove tcp:"$PHONE_SENSOR_LOCAL_PORT" >/dev/null 2>&1 || true
}

# Source ROS2 environment
source_ros() {
    log_info "Sourcing ROS2 environment..."
    source /opt/ros/jazzy/setup.bash || log_warn "Failed to source ROS2"
    if [ -f ~/ros2_ws/install/setup.bash ]; then source ~/ros2_ws/install/setup.bash; fi
    if [ -f ~/yahboom_tank_ws/install/setup.bash ]; then source ~/yahboom_tank_ws/install/setup.bash; fi
    if [ -f ~/roarm_ws_em0/install/setup.bash ]; then source ~/roarm_ws_em0/install/setup.bash; fi
}

ensure_joysticks() {
    # Dynamically find the first joystick
    JOY_DEV=$(ls /dev/input/js* 2>/dev/null | head -n 1)
    
    if [ -z "$JOY_DEV" ]; then
        log_info "No joystick found. Reloading joydev module..."
        sudo rmmod joydev 2>/dev/null || true
        sudo modprobe joydev
        sleep 2
        JOY_DEV=$(ls /dev/input/js* 2>/dev/null | head -n 1)
    fi

    if [ -n "$JOY_DEV" ]; then
        log_info "Found controller at $JOY_DEV"
        CONTROLLER_1="$JOY_DEV"
    else
        log_warn "No controller found! Please connect USB or pair Bluetooth."
        CONTROLLER_1=""
    fi
}

mkdir -p "$MAPS_DIR"

case "$1" in
    start)
        source_ros
        echo "=== Starting House Mapping ==="
        
	        # Start motor driver first
	        log_info "Starting Motor Driver..."
	        if ! pgrep -f "tank_motor_driver" &>/dev/null; then
	            nohup ros2 run tank_description tank_motor_driver > /tmp/motor_driver.log 2>&1 &
	            sleep 1
	        fi

	        # Start cmd_vel mux (routes /cmd_vel_joy -> /cmd_vel for motor driver)
	        log_info "Starting cmd_vel mux..."
	        if ! pgrep -f "cmd_vel_mux" &>/dev/null; then
	            nohup ros2 run tank_description cmd_vel_mux > /tmp/cmd_vel_mux.log 2>&1 &
	            sleep 1
	        fi
	        
	        # Check LIDAR device
	        if [ ! -e "$LIDAR_DEVICE" ]; then
	            log_error "LIDAR device not found: $LIDAR_DEVICE"
	            # Continue anyway? No, SLAM needs LIDAR.
             exit 1
        fi
        
        # Start LIDAR (vorwerk_lidar for XV-11)
        log_info "Starting XV-11 LIDAR..."
        if ! pgrep -f "lidar_node" &>/dev/null; then
            nohup ros2 run vorwerk_lidar lidar_node --ros-args \
                -p port:="$LIDAR_DEVICE" \
                -p frame_id:=laser_frame \
                > /tmp/lidar.log 2>&1 &
            sleep 3
        fi
        
        # Start RF2O Laser Odometry
        log_info "Starting RF2O laser odometry..."
        if ! pgrep -f "rf2o_laser_odometry" &>/dev/null; then
            nohup ros2 run rf2o_laser_odometry rf2o_laser_odometry_node --ros-args \
                -p laser_scan_topic:=/scan \
                -p odom_topic:=/odom \
                -p publish_tf:=true \
                -p base_frame_id:=base_link \
                -p odom_frame_id:=odom \
                -p laser_frame_id:=laser_frame \
                > /tmp/rf2o.log 2>&1 &
            sleep 2
        fi
        
        # Start SLAM Toolbox
        log_info "Starting SLAM Toolbox..."
        if ! pgrep -f "slam_toolbox" &>/dev/null; then
            # Check for custom params file
            PARAMS_FILE=""
            if [ -f ~/yahboom_tank_ws/src/tank_description/config/slam_params.yaml ]; then
                PARAMS_FILE="slam_params_file:=$HOME/yahboom_tank_ws/src/tank_description/config/slam_params.yaml"
            fi
            
            nohup ros2 launch slam_toolbox online_async_launch.py $PARAMS_FILE > /tmp/slam.log 2>&1 &
            sleep 5
        fi
        
        # Start Foxglove bridge
        log_info "Starting Foxglove bridge..."
        if ! pgrep -f "foxglove_bridge" &>/dev/null; then
            nohup ros2 run foxglove_bridge foxglove_bridge --ros-args \
                -p port:=$FOXGLOVE_PORT \
                -p address:=0.0.0.0 \
                > /tmp/foxglove.log 2>&1 &
            sleep 2
        fi

        # Phone sensors + camera (optional)
        phone_start_all || true
        
        # Start joy nodes for controllers
        ensure_joysticks
        if [ -n "$CONTROLLER_1" ]; then
            log_info "Starting controller input..."
            
            # Extract ID
            JOY_ID=$(echo "$CONTROLLER_1" | grep -oE '[0-9]+$')

            pkill -f "joy_node" 2>/dev/null || true
            sleep 1
            
            # Joy Node
            nohup ros2 run joy joy_node --ros-args \
                -p device_id:=$JOY_ID \
                -p autorepeat_rate:=20.0 \
                -p coalesce_interval:=0.01 \
                -r joy:=/tank/joy \
                > /tmp/joy.log 2>&1 &
            sleep 1
            
            # Joy Mapper (for Servo/LEDs)
            pkill -f "joy_mapper_node" 2>/dev/null || true
            # Run with sudo if needed for permissions, or assuming pi is fixed
            nohup python3 -u /home/pi/robots/rovac/scripts/joy_mapper_node.py > /tmp/joy_mapper.log 2>&1 &

            # teleop_twist_joy was unstable; left stick is handled by joy_mapper_node
            log_info "Left stick handled by joy_mapper_node (teleop_twist_joy disabled)"
        else
            log_warn "No controller found at /dev/input/js*"
        fi

        # Status hub + map save trigger (Foxglove widgets)
        if ! pgrep -f "robot_status_hub.py" &>/dev/null; then
            nohup python3 /home/pi/robots/rovac/scripts/robot_status_hub.py > /tmp/robot_status_hub.log 2>&1 &
        fi
        if ! pgrep -f "map_save_trigger_node.py" &>/dev/null; then
            nohup python3 /home/pi/robots/rovac/scripts/map_save_trigger_node.py > /tmp/map_save_trigger.log 2>&1 &
        fi
        if ! pgrep -f "autonomy_control_node.py" &>/dev/null; then
            nohup python3 /home/pi/robots/rovac/scripts/autonomy_control_node.py > /tmp/autonomy_control.log 2>&1 &
        fi
        if ! pgrep -f "coverage_lawnmower_node.py" &>/dev/null; then
            nohup python3 /home/pi/robots/rovac/scripts/coverage_lawnmower_node.py > /tmp/coverage_lawnmower.log 2>&1 &
        fi
        
        local ip=$(hostname -I | awk '{print $1}')
        echo ""
        echo "=== Mapping Started ==="
        echo "Foxglove:  ws://$ip:$FOXGLOVE_PORT"
        echo ""
        echo "Instructions:"
        echo "  - Connect Foxglove Studio to visualize map"
        echo "  - Drive with Controller (Left Stick)"
        echo "  - Save map with: ./map_house.sh save [name]"
        echo "  - Stop with: ./map_house.sh stop"
        ;;
        
	    stop)
	        log_info "Stopping mapping..."
	        pkill -f slam_toolbox 2>/dev/null || true
	        pkill -f rf2o_laser_odometry 2>/dev/null || true
	        pkill -f "lidar_node" 2>/dev/null || true
	        pkill -f "xv11_lidar" 2>/dev/null || true
	        pkill -f foxglove_bridge 2>/dev/null || true
	        pkill -f joy_node 2>/dev/null || true
	        pkill -f joy_mapper_node 2>/dev/null || true
	        pkill -f teleop_node 2>/dev/null || true
	        pkill -f cmd_vel_mux 2>/dev/null || true
	        pkill -f tank_motor_driver 2>/dev/null || true
	        pkill -f robot_status_hub.py 2>/dev/null || true
	        pkill -f map_save_trigger_node.py 2>/dev/null || true
	        pkill -f autonomy_control_node.py 2>/dev/null || true
        pkill -f coverage_lawnmower_node.py 2>/dev/null || true
        phone_stop_all
        log_info "Mapping stopped"
        ;;
        
    save)
        source_ros
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        MAP_NAME="${2:-house_map_$TIMESTAMP}"
        
        log_info "Saving map as: $MAP_NAME"
        
        if ! pgrep -f slam_toolbox &>/dev/null; then
            log_error "SLAM is not running. Start mapping first."
            exit 1
        fi
        
        ros2 run nav2_map_server map_saver_cli -f "$MAPS_DIR/$MAP_NAME"
        
        if [ -f "$MAPS_DIR/$MAP_NAME.pgm" ]; then
            log_info "Map saved successfully"
            echo "Files:"
            ls -la "$MAPS_DIR/$MAP_NAME"*
        else
            log_error "Failed to save map"
        fi
        ;;
        
	    status)
	        source_ros
	        echo "=== Mapping Status ==="
	        
	        pgrep -f "lidar_node" &>/dev/null && echo "[+] LIDAR: Running" || echo "[-] LIDAR: Stopped"
	        pgrep -f rf2o_laser_odometry &>/dev/null && echo "[+] Odometry: Running" || echo "[-] Odometry: Stopped"
	        pgrep -f slam_toolbox &>/dev/null && echo "[+] SLAM: Running" || echo "[-] SLAM: Stopped"
	        pgrep -f foxglove_bridge &>/dev/null && echo "[+] Foxglove: Running" || echo "[-] Foxglove: Stopped"
	        pgrep -f cmd_vel_mux &>/dev/null && echo "[+] cmd_vel_mux: Running" || echo "[-] cmd_vel_mux: Stopped"
	        pgrep -f tank_motor_driver &>/dev/null && echo "[+] Motor Driver: Running" || echo "[-] Motor Driver: Stopped"
	        pgrep -f joy_node &>/dev/null && echo "[+] Joy: Running" || echo "[-] Joy: Stopped"

	        topic_has_pub() {
	            local topic=$1
	            local count
            count=$(timeout 2 ros2 topic info "$topic" --verbose 2>/dev/null | rg -m1 "Publisher count" | awk '{print $3}')
            if [ -n "$count" ] && [ "$count" -gt 0 ]; then
                echo "  [+] $topic"
            else
                echo "  [-] $topic"
            fi
        }

        topic_sample() {
            local topic=$1
            if timeout 1.5 ros2 topic echo "$topic" --once &>/dev/null; then
                echo "  [+] $topic data"
            else
                echo "  [-] $topic data"
            fi
        }

        echo ""
        echo "Sensors:"
        topic_has_pub /scan
        topic_has_pub /image_raw/compressed
        topic_has_pub /sensors/ultrasonic/range
        topic_has_pub /sensors/ir_obstacle
        topic_has_pub /sensors/ir_receiver

        echo ""
        echo "Phone Sensors:"
        pgrep -f "phone_sensors_node.py" &>/dev/null && echo "  [+] phone_sensors_node.py" || echo "  [-] phone_sensors_node.py"
        pgrep -f "phone_camera_simple.py" &>/dev/null && echo "  [+] phone_camera_simple.py" || echo "  [-] phone_camera_simple.py"
        pgrep -f "lidar_camera_fusion_node.py" &>/dev/null && echo "  [+] lidar_camera_fusion_node.py" || echo "  [-] lidar_camera_fusion_node.py"
        pgrep -f "scrcpy.*v4l2-sink=${PHONE_VIDEO_DEVICE}" &>/dev/null && echo "  [+] scrcpy (v4l2)" || echo "  [-] scrcpy (v4l2)"
        topic_has_pub /phone/imu
        topic_has_pub /phone/magnetic_field
        topic_has_pub /phone/illuminance
        topic_has_pub /phone/gps
        topic_has_pub /phone/image_raw/compressed

        echo ""
        echo "Topics:"
        ros2 topic list 2>/dev/null | grep -E '/scan|/map|/odom|/cmd_vel|/cmd_vel_joy' | head -10 | sed 's/^/  /'
        
        echo ""
        echo "Saved Maps:"
        ls -la "$MAPS_DIR"/*.pgm 2>/dev/null | tail -5 | sed 's/^/  /' || echo "  No maps saved yet"
        ;;
        
    *)
        echo "Pi-Native House Mapping Script"
        echo ""
        echo "Usage: $0 {start|stop|save [name]|status}"
        echo ""
        echo "Commands:"
        echo "  start       - Start mapping mode with LIDAR, SLAM, and controller"
        echo "  stop        - Stop all mapping processes"
        echo "  save [name] - Save current map (default: house_map_timestamp)"
        echo "  status      - Show current mapping status"
        exit 1
        ;;
esac
