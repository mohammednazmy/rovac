#!/bin/bash
# Launch official Hiwonder ROS2 nodes for ROVAC tank chassis
#
# This starts TWO official Hiwonder nodes:
#   1. ros_robot_controller_node — board I/O (serial, IMU, battery, motors)
#   2. odom_publisher — cmd_vel → motor speeds + odometry
#
# All code is from official Hiwonder LanderPi repo.
# Only adaptation: ROVAC tread dimensions in odom_publisher_node.py

set -eo pipefail

# Source ROS2 environment
source /opt/ros/jazzy/setup.bash
source /home/pi/robots/rovac/ros2_ws/install/setup.bash
source /home/pi/robots/rovac/config/ros2_env.sh

# MACHINE_TYPE must contain "Tank" for differential drive kinematics
export MACHINE_TYPE=ROVAC_Tank

echo "[launch_official] Starting official Hiwonder nodes for ROVAC_Tank..."
echo "[launch_official] Board: /dev/rrc (1Mbaud), Motor type: JGB37"
echo "[launch_official] Tread diameter: 42mm, separation: 155mm"

# Start ros_robot_controller_node (board driver)
ros2 run ros_robot_controller ros_robot_controller &
RRC_PID=$!
echo "[launch_official] ros_robot_controller PID=$RRC_PID"

# Wait for board node to initialize before starting controller
sleep 2

# Start odom_publisher (cmd_vel → motors + odometry)
ros2 run controller odom_publisher &
ODOM_PID=$!
echo "[launch_official] odom_publisher PID=$ODOM_PID"

echo "[launch_official] Both nodes running. CTRL-C to stop."

# Trap SIGTERM/SIGINT to cleanly stop both nodes
cleanup() {
    echo "[launch_official] Shutting down..."
    kill $ODOM_PID 2>/dev/null
    kill $RRC_PID 2>/dev/null
    wait $ODOM_PID 2>/dev/null
    wait $RRC_PID 2>/dev/null
    echo "[launch_official] Done."
}
trap cleanup SIGTERM SIGINT

# Wait for either process to exit
wait -n $RRC_PID $ODOM_PID 2>/dev/null
cleanup
