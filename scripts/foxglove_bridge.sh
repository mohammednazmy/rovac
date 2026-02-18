#!/bin/bash
# Foxglove Bridge Control Script for ROVAC
# Usage: ./foxglove_bridge.sh [start|stop|restart|status]

PLIST="$HOME/Library/LaunchAgents/com.rovac.foxglove-bridge.plist"
LOG="/tmp/foxglove_bridge.log"

start_bridge() {
    if pgrep -f foxglove_bridge > /dev/null; then
        echo "Foxglove bridge is already running"
        return 0
    fi

    echo "Starting foxglove_bridge..."
    source /opt/homebrew/Caskroom/miniforge/base/envs/ros_jazzy/setup.bash
    export ROS_DOMAIN_ID=42
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    export CYCLONEDDS_URI=file:///Users/mohammednazmy/robots/rovac/config/cyclonedds_mac.xml

    nohup ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765 > "$LOG" 2>&1 &
    sleep 3

    if pgrep -f foxglove_bridge > /dev/null; then
        echo "Foxglove bridge started on ws://localhost:8765"
        echo "Log: $LOG"
    else
        echo "Failed to start foxglove_bridge"
        tail -20 "$LOG"
        return 1
    fi
}

stop_bridge() {
    echo "Stopping foxglove_bridge..."
    pkill -f foxglove_bridge 2>/dev/null || true
    sleep 1
    if pgrep -f foxglove_bridge > /dev/null; then
        echo "Force killing..."
        pkill -9 -f foxglove_bridge 2>/dev/null || true
    fi
    echo "Foxglove bridge stopped"
}

status_bridge() {
    if pgrep -f foxglove_bridge > /dev/null; then
        echo "Foxglove bridge is running"
        pgrep -fl foxglove_bridge
        echo ""
        echo "Recent log:"
        tail -10 "$LOG" 2>/dev/null || echo "No log file"
    else
        echo "Foxglove bridge is not running"
    fi
}

enable_autostart() {
    echo "Enabling foxglove_bridge autostart..."
    launchctl load "$PLIST" 2>/dev/null || true
    echo "To start now: launchctl start com.rovac.foxglove-bridge"
    echo "To disable: launchctl unload $PLIST"
}

disable_autostart() {
    echo "Disabling foxglove_bridge autostart..."
    launchctl unload "$PLIST" 2>/dev/null || true
    echo "Autostart disabled"
}

case "${1:-status}" in
    start)
        start_bridge
        ;;
    stop)
        stop_bridge
        ;;
    restart)
        stop_bridge
        sleep 2
        start_bridge
        ;;
    status)
        status_bridge
        ;;
    enable)
        enable_autostart
        ;;
    disable)
        disable_autostart
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|enable|disable}"
        exit 1
        ;;
esac
