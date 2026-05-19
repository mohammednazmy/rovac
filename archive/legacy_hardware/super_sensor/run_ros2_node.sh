#!/bin/bash
source /opt/ros/jazzy/setup.bash
source /home/pi/robots/rovac/config/ros2_env.sh
cd /home/pi/robots/rovac/hardware/super_sensor
exec python3 super_sensor_ros2_node.py --ros-args -p port:=/dev/ttyUSB1
