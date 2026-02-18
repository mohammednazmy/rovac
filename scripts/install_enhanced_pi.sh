#!/bin/bash
# Installation script for enhanced components on Pi

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[PI-INSTALL]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[PI-INSTALL]${NC} $1"; }
log_error() { echo -e "${RED}[PI-INSTALL]${NC} $1"; }

# Update package list
log_info "Updating package list..."
sudo apt update

# Install required system packages
log_info "Installing system packages..."
sudo apt install -y python3-pip python3-psutil

# Install Python packages
log_info "Installing Python packages..."
pip3 install numpy

# Create directories if they don't exist
mkdir -p ~/rovac_enhanced

# Copy enhanced components to Pi (assuming this script is run from Mac)
log_info "Copying enhanced components to Pi..."
scp ../robot_mcp_server/system_health_monitor.py pi@192.168.1.200:~/rovac_enhanced/
scp ../robot_mcp_server/sensor_fusion_node.py pi@192.168.1.200:~/rovac_enhanced/
scp ../robot_mcp_server/obstacle_avoidance_node.py pi@192.168.1.200:~/rovac_enhanced/

# Make scripts executable
ssh pi "chmod +x ~/rovac_enhanced/*.py"

log_info "Pi installation complete!"
log_info "Components installed in ~/rovac_enhanced/"
