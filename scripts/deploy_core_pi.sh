#!/bin/bash
# Deploy core robot components to Pi
# This includes the motor driver and other essential scripts.

set -e

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[DEPLOY]${NC} $1"; }

PI_HOST="pi@192.168.1.200"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

log_info "Deploying core components to $PI_HOST..."

# Deploy Motor Driver
log_info "Copying tank_motor_driver.py..."
scp "$PROJECT_ROOT/robot_mcp_server/tank_motor_driver.py" $PI_HOST:~/tank_motor_driver.py

# Restart relevant services
log_info "Restarting motor service..."
ssh $PI_HOST "sudo systemctl restart rovac-edge-motor.service"

log_info "Core deployment complete!"
