#!/bin/bash
# Start script for ROVAC Web Dashboard

echo "Starting ROVAC Web Dashboard..."
echo "=============================="

# Activate the robot MCP server virtual environment
if [ -f "~/robots/rovac/robot_mcp_server/venv/bin/activate" ]; then
    source ~/robots/rovac/robot_mcp_server/venv/bin/activate
    echo "Activated virtual environment"
else
    echo "Warning: Virtual environment not found, using system Python"
fi

# Change to the robot_mcp_server directory
cd ~/robots/rovac/robot_mcp_server

# Start the web dashboard
echo "Starting web dashboard on http://localhost:5000"
echo "Press Ctrl+C to stop"

python3 web_dashboard.py