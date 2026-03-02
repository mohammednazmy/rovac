#!/bin/bash
# Launch ESP32 USB motor driver for ROVAC
#
# Controls motors + reads encoders via ESP32-S3 over USB-serial.
# Firmware may target AT8236 or BST-4WD TB6612; serial protocol is the same.

set -eo pipefail

# Source ROS2 environment
source /opt/ros/jazzy/setup.bash
source /home/pi/robots/rovac/config/ros2_env.sh

DRIVER_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[esp32] Starting ESP32 motor driver..."
echo "[esp32] Motor: H-bridge controlled by ESP32-S3 USB-serial (/dev/esp32_motor)"
echo "[esp32] Encoder: ESP32-S3 PCNT hardware, 50Hz streaming"
echo "[esp32] Max motor speed: 255/255 (full), Ticks/rev: 2640"

exec python3 "$DRIVER_DIR/esp32_at8236_driver.py"
