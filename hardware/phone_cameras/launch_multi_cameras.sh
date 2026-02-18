#\!/bin/bash
# Launch Multiple Phone Cameras for ROS2 (with auto-restart)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="/tmp/phone_cameras"
mkdir -p "$LOG_DIR"

# Camera configuration
declare -A CAMERA_IDS
CAMERA_IDS[back]="0"
CAMERA_IDS[front]="1"
CAMERA_IDS[wide]="2"
CAMERA_IDS[front2]="3"

declare -A VIDEO_DEVICES
VIDEO_DEVICES[back]="/dev/video10"
VIDEO_DEVICES[front]="/dev/video11"
VIDEO_DEVICES[wide]="/dev/video12"
VIDEO_DEVICES[front2]="/dev/video13"

RESOLUTION="640x480"
FPS="15"

# Set environment
export HOME=/home/pi
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/pi/robots/rovac/config/cyclonedds_pi.xml

source /opt/ros/jazzy/setup.bash
[ -f /home/pi/ros2_env.sh ] && source /home/pi/ros2_env.sh

# Parse arguments
if [ $# -eq 0 ]; then
    CAMERAS=(back)
elif [ "$1" == "all" ]; then
    CAMERAS=(back front wide front2)
else
    CAMERAS=("$@")
fi

echo "=== Phone Multi-Camera Launcher (with auto-restart) ==="
echo "Cameras: ${CAMERAS[*]}"

# Setup v4l2loopback devices
setup_v4l2loopback() {
    echo "Setting up v4l2loopback devices..."
    sudo modprobe -r v4l2loopback 2>/dev/null || true
    sleep 1
    
    local devices=""
    local names=""
    for cam in "${CAMERAS[@]}"; do
        dev="${VIDEO_DEVICES[$cam]}"
        devnum="${dev#/dev/video}"
        devices="${devices:+$devices,}$devnum"
        names="${names:+$names,}Phone_${cam^}"
    done
    
    sudo modprobe v4l2loopback devices=${#CAMERAS[@]} \
        video_nr="$devices" \
        card_label="$names" \
        exclusive_caps=1
    sleep 1
    
    for cam in "${CAMERAS[@]}"; do
        sudo chmod 666 "${VIDEO_DEVICES[$cam]}" 2>/dev/null || true
    done
    echo "Created v4l2loopback devices"
}

# Start scrcpy for a camera
start_scrcpy() {
    local cam="$1"
    local cam_id="${CAMERA_IDS[$cam]}"
    local dev="${VIDEO_DEVICES[$cam]}"
    local log="$LOG_DIR/scrcpy_${cam}.log"
    
    scrcpy --video-source=camera \
           --camera-id="$cam_id" \
           --camera-size="$RESOLUTION" \
           --camera-fps="$FPS" \
           --v4l2-sink="$dev" \
           --no-video-playback \
           --no-audio \
           > "$log" 2>&1 &
    echo $\!
}

# Start ROS2 publisher for a camera
start_publisher() {
    local cam="$1"
    local dev="${VIDEO_DEVICES[$cam]}"
    local log="$LOG_DIR/ros2_${cam}.log"
    
    python3 "$SCRIPT_DIR/multi_camera_publisher.py" \
        --camera-name "$cam" \
        --device "$dev" \
        --fps "$FPS" \
        > "$log" 2>&1 &
    echo $\!
}

# Check phone connection
wait_for_phone() {
    local retries=30
    while [ $retries -gt 0 ]; do
        if adb devices | grep -q "device$"; then
            return 0
        fi
        echo "Waiting for phone connection... ($retries)"
        sleep 2
        retries=$((retries - 1))
    done
    return 1
}

# Cleanup
cleanup() {
    echo "Stopping cameras..."
    pkill -f "scrcpy.*video-source=camera" 2>/dev/null || true
    pkill -f "multi_camera_publisher" 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# Wait for phone
echo "Checking phone connection..."
if ! wait_for_phone; then
    echo "ERROR: No phone connected"
    exit 1
fi
echo "Phone connected: $(adb shell getprop ro.product.model 2>/dev/null | tr -d '')"

# Setup v4l2loopback
setup_v4l2loopback

# Main monitoring loop
declare -A SCRCPY_PIDS
declare -A PUB_PIDS

echo "Starting camera streams with auto-restart..."

while true; do
    for cam in "${CAMERAS[@]}"; do
        scrcpy_pid="${SCRCPY_PIDS[$cam]:-}"
        pub_pid="${PUB_PIDS[$cam]:-}"
        
        # Check/restart scrcpy
        if [ -z "$scrcpy_pid" ] || \! kill -0 "$scrcpy_pid" 2>/dev/null; then
            echo "$(date): Starting scrcpy for $cam"
            SCRCPY_PIDS[$cam]=$(start_scrcpy "$cam")
            sleep 2
        fi
        
        # Check/restart publisher
        if [ -z "$pub_pid" ] || \! kill -0 "$pub_pid" 2>/dev/null; then
            echo "$(date): Starting publisher for $cam"
            PUB_PIDS[$cam]=$(start_publisher "$cam")
            sleep 1
        fi
    done
    
    # Check every 5 seconds
    sleep 5
done
