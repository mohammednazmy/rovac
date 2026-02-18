#!/bin/bash
# Publish static map->odom transform when SLAM is not running
source /opt/ros/jazzy/setup.bash
source /home/pi/ros2_env.sh

exec ros2 run tf2_ros static_transform_publisher \
    --x 0 --y 0 --z 0 \
    --qx 0 --qy 0 --qz 0 --qw 1 \
    --frame-id map --child-frame-id odom
