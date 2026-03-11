#!/usr/bin/env bash
#
# build.sh — Reliable build script for esp32_motor_wireless firmware
#
# Wraps idf.py with micro-ROS source verification and repair.
# The upstream libmicroros.mk chains 25+ git clones with ';' (not '&&'),
# so any single network hiccup silently skips a repo. This script
# verifies all expected repos exist before building, cloning any
# missing ones with retries.
#
# Usage:
#   ./build.sh                  # full build (set-target + build)
#   ./build.sh build            # build only (skip set-target)
#   ./build.sh flash            # build + flash
#   ./build.sh flash-monitor    # build + flash + open serial monitor
#   ./build.sh clean            # full clean (build + micro-ROS artifacts)
#   ./build.sh verify-sources   # just check/repair micro-ROS sources
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

COMPONENT_DIR="$SCRIPT_DIR/components/micro_ros_espidf_component"
UROS_SRC="$COMPONENT_DIR/micro_ros_src/src"

# ---- ESP-IDF setup ----
IDF_PATH="${IDF_PATH:-$HOME/esp/esp-idf-v5.2}"
if [ ! -f "$IDF_PATH/export.sh" ]; then
    echo "ERROR: ESP-IDF not found at $IDF_PATH"
    echo "  Set IDF_PATH or install ESP-IDF v5.2 at ~/esp/esp-idf-v5.2/"
    exit 1
fi

# Source ESP-IDF (suppress verbose output)
source "$IDF_PATH/export.sh" >/dev/null 2>&1 || true

# Verify idf.py is available
if ! command -v idf.py &>/dev/null; then
    echo "ERROR: idf.py not found after sourcing ESP-IDF"
    exit 1
fi

# ---- Expected micro-ROS source repos ----
# Format: "directory branch url"
REPOS=(
    "Micro-XRCE-DDS-Client ros2 https://github.com/eProsima/Micro-XRCE-DDS-Client"
    "rmw_microxrcedds jazzy https://github.com/micro-ROS/rmw_microxrcedds"
    "micro-CDR ros2 https://github.com/eProsima/micro-CDR"
    "rcl jazzy https://github.com/micro-ROS/rcl"
    "rclc jazzy https://github.com/ros2/rclc"
    "rcutils jazzy https://github.com/micro-ROS/rcutils"
    "micro_ros_msgs jazzy https://github.com/micro-ROS/micro_ros_msgs"
    "rosidl_typesupport jazzy https://github.com/micro-ROS/rosidl_typesupport"
    "rosidl_typesupport_microxrcedds jazzy https://github.com/micro-ROS/rosidl_typesupport_microxrcedds"
    "rosidl jazzy https://github.com/ros2/rosidl"
    "rosidl_dynamic_typesupport jazzy https://github.com/ros2/rosidl_dynamic_typesupport"
    "rmw jazzy https://github.com/ros2/rmw"
    "rcl_interfaces jazzy https://github.com/ros2/rcl_interfaces"
    "rosidl_defaults jazzy https://github.com/ros2/rosidl_defaults"
    "unique_identifier_msgs jazzy https://github.com/ros2/unique_identifier_msgs"
    "common_interfaces jazzy https://github.com/ros2/common_interfaces"
    "example_interfaces jazzy https://github.com/ros2/example_interfaces"
    "test_interface_files jazzy https://github.com/ros2/test_interface_files"
    "rmw_implementation jazzy https://github.com/ros2/rmw_implementation"
    "rcl_logging jazzy https://github.com/ros2/rcl_logging"
    "ros2_tracing jazzy https://github.com/ros2/ros2_tracing"
    "micro_ros_utilities jazzy https://github.com/micro-ROS/micro_ros_utilities"
    "rosidl_core jazzy https://github.com/ros2/rosidl_core"
)

# COLCON_IGNORE files to create (sub-packages to skip during cross-compile)
IGNORE_DIRS=(
    "rosidl/rosidl_typesupport_introspection_cpp"
    "rcl_logging/rcl_logging_log4cxx"
    "rcl_logging/rcl_logging_spdlog"
    "rclc/rclc_examples"
    "rcl/rcl_yaml_param_parser"
    "ros2_tracing/test_tracetools"
    "ros2_tracing/lttngpy"
)

MAX_RETRIES=3

# ---- Functions ----

clone_repo() {
    local dir="$1" branch="$2" url="$3"
    local target="$UROS_SRC/$dir"

    for attempt in $(seq 1 $MAX_RETRIES); do
        echo "  Cloning $dir (attempt $attempt/$MAX_RETRIES)..."
        if git clone --depth 1 -b "$branch" "$url" "$target" 2>/dev/null; then
            return 0
        fi
        rm -rf "$target"
        [ "$attempt" -lt "$MAX_RETRIES" ] && sleep 2
    done

    echo "  FAILED to clone $dir after $MAX_RETRIES attempts"
    return 1
}

verify_and_repair_sources() {
    if [ ! -d "$UROS_SRC" ]; then
        echo "micro-ROS sources not yet cloned (will be done by idf.py)"
        return 0
    fi

    echo "Verifying micro-ROS source repos..."
    local missing=0
    local repaired=0

    for repo_line in "${REPOS[@]}"; do
        read -r dir branch url <<< "$repo_line"
        if [ ! -d "$UROS_SRC/$dir" ]; then
            echo "  MISSING: $dir"
            if clone_repo "$dir" "$branch" "$url"; then
                ((repaired++))
            else
                ((missing++))
            fi
        fi
    done

    # Ensure COLCON_IGNORE files exist
    for ignore_dir in "${IGNORE_DIRS[@]}"; do
        local target="$UROS_SRC/$ignore_dir/COLCON_IGNORE"
        if [ -d "$UROS_SRC/$ignore_dir" ] && [ ! -f "$target" ]; then
            touch "$target"
        fi
    done

    if [ "$missing" -gt 0 ]; then
        echo "ERROR: $missing repo(s) still missing after repair. Check network."
        return 1
    elif [ "$repaired" -gt 0 ]; then
        echo "Repaired $repaired missing repo(s)."
        # Need to rebuild micro-ROS libs since sources changed
        echo "Cleaning micro-ROS build artifacts (sources changed)..."
        rm -rf "$COMPONENT_DIR/micro_ros_src/install"
        rm -rf "$COMPONENT_DIR/micro_ros_src/build"
        rm -rf "$COMPONENT_DIR/micro_ros_src/log"
        rm -rf "$COMPONENT_DIR/include"
        rm -rf "$COMPONENT_DIR/libmicroros.a"
        rm -rf "$SCRIPT_DIR/build"
    else
        echo "All 23 repos present."
    fi
}

do_clean() {
    echo "Cleaning build artifacts..."
    rm -rf "$SCRIPT_DIR/build"
    rm -rf "$SCRIPT_DIR/sdkconfig"
    rm -rf "$COMPONENT_DIR/micro_ros_dev"
    rm -rf "$COMPONENT_DIR/micro_ros_src"
    rm -rf "$COMPONENT_DIR/include"
    rm -rf "$COMPONENT_DIR/libmicroros.a"
    rm -rf "$COMPONENT_DIR/esp32_toolchain.cmake"
    echo "Clean complete."
}

do_build() {
    local skip_target="${1:-false}"

    # Verify/repair sources if they exist
    verify_and_repair_sources

    if [ "$skip_target" = "false" ] && [ ! -f "$SCRIPT_DIR/sdkconfig" ]; then
        echo "Setting target to ESP32..."
        idf.py set-target esp32
    fi

    echo "Building firmware..."
    idf.py build

    echo ""
    echo "Build complete. Binary: build/esp32_motor_wireless.bin"
}

# ---- Main ----

CMD="${1:-full}"

case "$CMD" in
    full)
        do_build false
        ;;
    build)
        do_build true
        ;;
    flash)
        do_build true
        echo "Flashing..."
        idf.py flash
        ;;
    flash-monitor|fm)
        do_build true
        echo "Flashing and starting monitor..."
        idf.py flash monitor
        ;;
    monitor)
        idf.py monitor
        ;;
    clean)
        do_clean
        ;;
    verify-sources|verify)
        verify_and_repair_sources
        ;;
    size)
        idf.py size
        ;;
    *)
        echo "Usage: $0 [full|build|flash|flash-monitor|monitor|clean|verify-sources|size]"
        exit 1
        ;;
esac
