#!/bin/bash
"""
Install script for enhanced ROVAC system components
"""

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INSTALL]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[INSTALL]${NC} $1"; }
log_error() { echo -e "${RED}[INSTALL]${NC} $1"; }

# Check if running on Mac (where ROS2 should be available)
if [[ "$OSTYPE" != "darwin"* ]]; then
    log_error "This installer should be run on macOS where ROS2 is installed"
    exit 1
fi

# Source ROS2 environment
source_ros() {
    log_info "Sourcing ROS2 environment..."
    
    # Try conda environment first
    if command -v conda &> /dev/null; then
        eval "$(conda shell.bash hook)"
        if conda activate ros_jazzy 2>/dev/null; then
            log_info "Activated conda environment: ros_jazzy"
        else
            log_warn "Could not activate ros_jazzy conda environment"
        fi
    fi
    
    # Source ROS2 setup
    if [ -f "$ROVAC_DIR/config/ros2_env.sh" ]; then
        source "$ROVAC_DIR/config/ros2_env.sh"
        log_info "Sourced ROVAC ROS2 environment"
    elif [ -f "/opt/ros/jazzy/setup.bash" ]; then
        source "/opt/ros/jazzy/setup.bash"
        log_info "Sourced system ROS2 environment"
    else
        log_error "Could not find ROS2 environment setup"
        exit 1
    fi
}

# Install Python dependencies
install_dependencies() {
    log_info "Installing Python dependencies..."
    
    # Check if in virtual environment
    if [ -d "$ROVAC_DIR/robot_mcp_server/venv" ]; then
        source "$ROVAC_DIR/robot_mcp_server/venv/bin/activate"
        log_info "Activated MCP server virtual environment"
    fi
    
    # Install required packages
    pip_packages=("psutil" "numpy" "opencv-python")
    for package in "${pip_packages[@]}"; do
        if ! python3 -c "import $package" 2>/dev/null; then
            log_info "Installing $package..."
            pip install "$package"
        else
            log_info "$package already installed"
        fi
    done
}

# Make scripts executable
make_executable() {
    log_info "Making scripts executable..."
    
    chmod +x "$ROVAC_DIR/robot_mcp_server/system_health_monitor.py"
    chmod +x "$ROVAC_DIR/robot_mcp_server/sensor_fusion_node.py"
    chmod +x "$ROVAC_DIR/robot_mcp_server/obstacle_avoidance_node.py"
    chmod +x "$ROVAC_DIR/robot_mcp_server/frontier_exploration_node.py"
    chmod +x "$ROVAC_DIR/robot_mcp_server/diagnostics_collector.py"
    chmod +x "$ROVAC_DIR/scripts/joy_mapper_enhanced.py"
    
    log_info "Scripts made executable"
}

# Create systemd service for enhanced system (optional)
create_systemd_service() {
    log_info "Creating systemd service file template..."
    
    SERVICE_FILE="$ROVAC_DIR/config/systemd/rovac-enhanced.service"
    
    # Create config directory if it doesn't exist
    mkdir -p "$ROVAC_DIR/config/systemd"
    
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=ROVAC Enhanced System Components
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$ROVAC_DIR
ExecStart=$ROVAC_DIR/scripts/run_enhanced_system.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    
    log_info "Created systemd service template at $SERVICE_FILE"
    log_info "Note: This service would run on the Pi, not macOS"
}

# Create launch script
create_launch_script() {
    log_info "Creating launch script..."
    
    LAUNCH_SCRIPT="$ROVAC_DIR/scripts/run_enhanced_system.sh"
    
    cat > "$LAUNCH_SCRIPT" << 'EOF'
#!/bin/bash
# Launch script for enhanced ROVAC system components

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source ROS2 environment
source "$ROVAC_DIR/config/ros2_env.sh"

# Source conda environment if available
if command -v conda &> /dev/null; then
    eval "$(conda shell.bash hook)"
    conda activate ros_jazzy 2>/dev/null || true
fi

# Run all enhanced nodes
echo "Starting enhanced ROVAC system components..."

# Start nodes in separate screens for easy management
screen -dmS health_monitor bash -c "cd $ROVAC_DIR && python3 robot_mcp_server/system_health_monitor.py"
screen -dmS sensor_fusion bash -c "cd $ROVAC_DIR && python3 robot_mcp_server/sensor_fusion_node.py"
screen -dmS obstacle_avoidance bash -c "cd $ROVAC_DIR && python3 robot_mcp_server/obstacle_avoidance_node.py"
screen -dmS diagnostics_collector bash -c "cd $ROVAC_DIR && python3 robot_mcp_server/diagnostics_collector.py"

echo "Enhanced system components started in screen sessions:"
echo "  - health_monitor"
echo "  - sensor_fusion"
echo "  - obstacle_avoidance"
echo "  - diagnostics_collector"

echo "Use 'screen -ls' to see running sessions"
echo "Use 'screen -r <session_name>' to attach to a session"
echo "Use 'screen -S <session_name> -X quit' to stop a session"
EOF
    
    chmod +x "$LAUNCH_SCRIPT"
    log_info "Created launch script at $LAUNCH_SCRIPT"
}

# Create Pi installation script
create_pi_install_script() {
    log_info "Creating Pi installation script..."
    
    PI_INSTALL_SCRIPT="$ROVAC_DIR/scripts/install_enhanced_pi.sh"
    
    cat > "$PI_INSTALL_SCRIPT" << 'EOF'
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
EOF
    
    chmod +x "$PI_INSTALL_SCRIPT"
    log_info "Created Pi installation script at $PI_INSTALL_SCRIPT"
}

# Main installation
main() {
    log_info "Starting enhanced ROVAC system installation..."
    
    source_ros
    install_dependencies
    make_executable
    create_launch_script
    create_pi_install_script
    #create_systemd_service  # Commented out as this would be for Pi
    
    log_info "Installation complete!"
    log_info "Enhanced components installed:"
    log_info "  - System Health Monitor"
    log_info "  - Sensor Fusion Node"
    log_info "  - Obstacle Avoidance Node"
    log_info "  - Frontier Exploration Node"
    log_info "  - Diagnostics Collector"
    log_info "  - Enhanced Joy Mapper"
    echo ""
    log_info "To run the enhanced system:"
    log_info "  cd $ROVAC_DIR && ./scripts/run_enhanced_system.sh"
    echo ""
    log_info "To install components on Pi:"
    log_info "  cd $ROVAC_DIR && ./scripts/install_enhanced_pi.sh"
}

# Run main installation
main "$@"