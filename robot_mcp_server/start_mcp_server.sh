#!/bin/bash
# Start MCP Server with ROS2 environment

# Source ROS2
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash

# Change to server directory
cd /home/pi/robot_mcp_server

# Activate virtualenv
source venv/bin/activate

# Start MCP server
exec python3 mcp_server.py
