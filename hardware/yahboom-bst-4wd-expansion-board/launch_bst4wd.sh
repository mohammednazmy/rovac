#!/bin/bash
# Launch BST-4WD motor driver for ROVAC
#
# Controls motors via TB6612FNG on BST-4WD board (Pi GPIO).
# Reads encoders from ESP32 PCNT hardware via USB serial.

set -eo pipefail

# Source ROS2 environment
source /opt/ros/jazzy/setup.bash
source /home/pi/robots/rovac/config/ros2_env.sh

DRIVER_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[bst4wd] Starting BST-4WD motor driver..."
echo "[bst4wd] Motor: TB6612FNG via GPIO (L: 20/21/16, R: 19/26/13)"
echo "[bst4wd] Encoder: Nano interrupt-driven via /dev/encoder_bridge"
echo "[bst4wd] Max PWM: 60%, Ticks/rev: 2640"

exec python3 "$DRIVER_DIR/bst4wd_driver.py"
