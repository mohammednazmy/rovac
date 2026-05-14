#!/bin/bash
# Install stereo camera systemd services on Raspberry Pi
# Run from Mac: ./install_stereo_services.sh
# Or on Pi: bash install_stereo_services.sh --local

set -e

PI_HOST="${PI_HOST:-pi@192.168.1.200}"
PI_STEREO_DIR="/home/pi/robots/rovac/hardware/stereo_cameras"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

install_remote() {
    log_info "Installing stereo camera services on Pi..."

    # 1. Copy systemd service files
    log_info "Copying systemd service files..."
    scp "${SCRIPT_DIR}/systemd/rovac-edge-stereo-depth.service" "${PI_HOST}:/tmp/"
    scp "${SCRIPT_DIR}/systemd/rovac-edge-stereo-obstacle.service" "${PI_HOST}:/tmp/"
    scp "${SCRIPT_DIR}/systemd/rovac-edge-stereo.target" "${PI_HOST}:/tmp/"

    # 2. Copy updated cmd_vel_mux
    log_info "Copying updated cmd_vel_mux..."
    scp "${SCRIPT_DIR}/cmd_vel_mux_with_obstacle.py" "${PI_HOST}:/tmp/"

    # 3. Copy latest stereo node files
    log_info "Syncing stereo camera code..."
    scp "${SCRIPT_DIR}/ros2_stereo_depth_node.py" "${PI_HOST}:${PI_STEREO_DIR}/"
    scp "${SCRIPT_DIR}/obstacle_detector.py" "${PI_HOST}:${PI_STEREO_DIR}/"

    # 4. Execute installation on Pi
    log_info "Installing services on Pi..."
    ssh "${PI_HOST}" bash << 'REMOTE_SCRIPT'
set -e

echo "=== Installing systemd services ==="

# Move service files to systemd directory
sudo mv /tmp/rovac-edge-stereo-depth.service /etc/systemd/system/
sudo mv /tmp/rovac-edge-stereo-obstacle.service /etc/systemd/system/
sudo mv /tmp/rovac-edge-stereo.target /etc/systemd/system/

# Backup and update cmd_vel_mux
MUX_DIR="/home/pi/robots/rovac/ros2_ws/src/tank_description/tank_description"
if [ -f "${MUX_DIR}/cmd_vel_mux.py" ]; then
    cp "${MUX_DIR}/cmd_vel_mux.py" "${MUX_DIR}/cmd_vel_mux.py.backup"
    echo "Backed up original cmd_vel_mux.py"
fi
mv /tmp/cmd_vel_mux_with_obstacle.py "${MUX_DIR}/cmd_vel_mux.py"
chmod +x "${MUX_DIR}/cmd_vel_mux.py"
echo "Updated cmd_vel_mux.py with obstacle priority"

# Update rovac-edge.target to include stereo services
TARGET_FILE="/etc/systemd/system/rovac-edge.target"
if ! grep -q "rovac-edge-stereo" "${TARGET_FILE}"; then
    echo "Adding stereo services to rovac-edge.target..."
    sudo sed -i '/Wants=rovac-edge-obstacle.service/a Wants=rovac-edge-stereo-depth.service\nWants=rovac-edge-stereo-obstacle.service' "${TARGET_FILE}"
fi

# Reload systemd
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable rovac-edge-stereo-depth.service
sudo systemctl enable rovac-edge-stereo-obstacle.service
sudo systemctl enable rovac-edge-stereo.target

echo "=== Stereo services installed ==="
echo ""
echo "Services status:"
systemctl status rovac-edge-stereo-depth.service --no-pager || true
systemctl status rovac-edge-stereo-obstacle.service --no-pager || true

echo ""
echo "To start manually:"
echo "  sudo systemctl start rovac-edge-stereo.target"
echo ""
echo "To restart all edge services:"
echo "  sudo systemctl restart rovac-edge.target"
REMOTE_SCRIPT

    log_info "Installation complete!"
}

install_local() {
    # For running directly on Pi
    log_info "Installing stereo camera services locally..."

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # Copy service files
    sudo cp "${SCRIPT_DIR}/systemd/rovac-edge-stereo-depth.service" /etc/systemd/system/
    sudo cp "${SCRIPT_DIR}/systemd/rovac-edge-stereo-obstacle.service" /etc/systemd/system/
    sudo cp "${SCRIPT_DIR}/systemd/rovac-edge-stereo.target" /etc/systemd/system/

    # Backup and update cmd_vel_mux
    MUX_DIR="/home/pi/robots/rovac/ros2_ws/src/tank_description/tank_description"
    if [ -f "${MUX_DIR}/cmd_vel_mux.py" ]; then
        cp "${MUX_DIR}/cmd_vel_mux.py" "${MUX_DIR}/cmd_vel_mux.py.backup"
    fi
    cp "${SCRIPT_DIR}/cmd_vel_mux_with_obstacle.py" "${MUX_DIR}/cmd_vel_mux.py"
    chmod +x "${MUX_DIR}/cmd_vel_mux.py"

    # Update target file
    TARGET_FILE="/etc/systemd/system/rovac-edge.target"
    if ! grep -q "rovac-edge-stereo" "${TARGET_FILE}"; then
        sudo sed -i '/Wants=rovac-edge-obstacle.service/a Wants=rovac-edge-stereo-depth.service\nWants=rovac-edge-stereo-obstacle.service' "${TARGET_FILE}"
    fi

    # Reload and enable
    sudo systemctl daemon-reload
    sudo systemctl enable rovac-edge-stereo-depth.service
    sudo systemctl enable rovac-edge-stereo-obstacle.service
    sudo systemctl enable rovac-edge-stereo.target

    log_info "Installation complete!"
}

uninstall() {
    log_info "Uninstalling stereo camera services..."

    ssh "${PI_HOST}" bash << 'REMOTE_SCRIPT'
set -e

# Stop services
sudo systemctl stop rovac-edge-stereo.target || true
sudo systemctl stop rovac-edge-stereo-obstacle.service || true
sudo systemctl stop rovac-edge-stereo-depth.service || true

# Disable services
sudo systemctl disable rovac-edge-stereo.target || true
sudo systemctl disable rovac-edge-stereo-obstacle.service || true
sudo systemctl disable rovac-edge-stereo-depth.service || true

# Remove service files
sudo rm -f /etc/systemd/system/rovac-edge-stereo-depth.service
sudo rm -f /etc/systemd/system/rovac-edge-stereo-obstacle.service
sudo rm -f /etc/systemd/system/rovac-edge-stereo.target

# Remove from target
sudo sed -i '/rovac-edge-stereo/d' /etc/systemd/system/rovac-edge.target

# Restore original cmd_vel_mux if backup exists
MUX_DIR="/home/pi/robots/rovac/ros2_ws/src/tank_description/tank_description"
if [ -f "${MUX_DIR}/cmd_vel_mux.py.backup" ]; then
    mv "${MUX_DIR}/cmd_vel_mux.py.backup" "${MUX_DIR}/cmd_vel_mux.py"
    echo "Restored original cmd_vel_mux.py"
fi

sudo systemctl daemon-reload

echo "Stereo services uninstalled"
REMOTE_SCRIPT

    log_info "Uninstall complete"
}

status() {
    ssh "${PI_HOST}" bash << 'REMOTE_SCRIPT'
echo "=== Stereo Camera Services Status ==="
echo ""
echo "--- Stereo Depth Node ---"
systemctl status rovac-edge-stereo-depth.service --no-pager || echo "Not running"
echo ""
echo "--- Obstacle Detector ---"
systemctl status rovac-edge-stereo-obstacle.service --no-pager || echo "Not running"
echo ""
echo "--- Edge Target ---"
systemctl status rovac-edge.target --no-pager || echo "Not running"
REMOTE_SCRIPT
}

case "${1:-install}" in
    install)
        install_remote
        ;;
    --local)
        install_local
        ;;
    uninstall)
        uninstall
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {install|--local|uninstall|status}"
        exit 1
        ;;
esac
