#!/bin/bash
# Launch Hiwonder ROS Robot Controller V1.2 Driver

source /opt/ros/jazzy/setup.bash

if [ -f /home/pi/robots/rovac/ros2_ws/install/setup.bash ]; then
    source /home/pi/robots/rovac/ros2_ws/install/setup.bash
fi

if [ -f /home/pi/robots/rovac/config/ros2_env.sh ]; then
    source /home/pi/robots/rovac/config/ros2_env.sh
fi

exec python3 /home/pi/robots/rovac/hardware/hiwonder-ros-controller/hiwonder_driver.py --ros-args \
    -p port:=/dev/hiwonder_board \
    -p baud:=1000000 \
    -p wheel_separation:=0.155 \
    -p wheel_radius:=0.032 \
    -p max_speed_rps:=3.0 \
    -p motor_left_id:=0 \
    -p motor_right_id:=1 \
    -p motor_left_flip:=true \
    -p motor_right_flip:=false \
    -p cmd_vel_timeout:=0.5 \
    -p odom_frame_id:=odom \
    -p base_frame_id:=base_link \
    -p imu_frame_id:=imu_link \
    -p publish_tf:=true \
    -p imu_gyro_scale:=0.017453292519943 \
    -p use_imu_for_heading:=true
