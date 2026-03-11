#!/bin/bash
#
# Install and enable ROVAC systemd units on the Lenovo ThinkCentre M910q
# so the edge stack auto-starts at boot.
#
# Reads Pi-targeted service files and adapts them for the Lenovo:
#   User=pi          -> User=asimo
#   /home/pi/        -> /home/asimo/
#   cyclonedds_pi    -> cyclonedds_lenovo
#
# Usage (from Mac):
#   ./scripts/install_lenovo_systemd.sh install
#   ./scripts/install_lenovo_systemd.sh status
#   ./scripts/install_lenovo_systemd.sh restart
#   ./scripts/install_lenovo_systemd.sh uninstall
#
# Env:
#   EDGE_HOST=asimo@192.168.1.218
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

EDGE_HOST="${EDGE_HOST:-asimo@192.168.1.218}"
UNIT_DIR="$ROVAC_DIR/config/systemd"

# Transform a Pi service file for the Lenovo environment
adapt_service() {
  sed \
    -e 's|User=pi|User=asimo|g' \
    -e 's|Group=pi|Group=asimo|g' \
    -e 's|/home/pi|/home/asimo|g' \
    -e 's|cyclonedds_pi\.xml|cyclonedds_lenovo.xml|g'
}

remote_sudo_install() {
  local remote_path="$1"
  local local_path="$2"
  adapt_service <"$local_path" | ssh "$EDGE_HOST" "sudo tee '$remote_path' >/dev/null"
}

remote_sudo_install_raw() {
  local remote_path="$1"
  local local_path="$2"
  ssh "$EDGE_HOST" "sudo tee '$remote_path' >/dev/null" <"$local_path"
}

check_hardware() {
  ssh "$EDGE_HOST" "
    echo '--- Hardware check ---'
    if [ -e /dev/esp32_motor ]; then
      echo '  [+] ESP32 motor controller at /dev/esp32_motor'
    else
      echo '  [!] No /dev/esp32_motor (check USB + udev)'
    fi
    if [ -e /dev/esp32_lidar ]; then
      echo '  [+] ESP32 LIDAR bridge at /dev/esp32_lidar'
    else
      echo '  [!] No /dev/esp32_lidar (check USB + udev)'
    fi
    if [ -e /dev/input/js0 ]; then
      echo '  [+] PS2 controller at /dev/input/js0'
    else
      echo '  [!] No joystick at /dev/input/js0'
    fi
  " 2>/dev/null || true
}

install_units() {
  if [ ! -d "$UNIT_DIR" ]; then
    echo "ERROR: missing $UNIT_DIR" >&2
    exit 1
  fi

  echo "Installing ROVAC systemd units to $EDGE_HOST (Lenovo)..."

  # Pre-flight: verify monorepo is cloned
  if ! ssh "$EDGE_HOST" "test -d /home/asimo/robots/rovac/config"; then
    echo "ERROR: Monorepo not found at /home/asimo/robots/rovac/" >&2
    exit 1
  fi

  # Deploy udev rules
  echo "Installing udev rules..."
  remote_sudo_install_raw "/etc/udev/rules.d/99-rovac-lenovo.rules" \
    "$ROVAC_DIR/config/udev/99-rovac-lenovo.rules"
  ssh "$EDGE_HOST" "sudo udevadm control --reload-rules && sudo udevadm trigger" || true

  # Deploy systemd units (adapted from Pi files)
  echo "Deploying systemd units..."

  # Target
  remote_sudo_install "/etc/systemd/system/rovac-edge.target" "$UNIT_DIR/rovac-edge.target"

  # Core services
  for svc in \
    rovac-edge-esp32.service \
    rovac-edge-mux.service \
    rovac-edge-tf.service \
    rovac-edge-map-tf.service \
    rovac-edge-lidar.service \
    rovac-edge-obstacle.service \
    rovac-edge-ps2-joy.service \
    rovac-edge-ps2-mapper.service \
    rovac-edge-supersensor.service; do
    if [ -f "$UNIT_DIR/$svc" ]; then
      echo "  [+] $svc"
      remote_sudo_install "/etc/systemd/system/$svc" "$UNIT_DIR/$svc"
    fi
  done

  ssh "$EDGE_HOST" "sudo systemctl daemon-reload"

  # Stop any running instances first
  ssh "$EDGE_HOST" "
    sudo systemctl stop rovac-edge.target 2>/dev/null || true
    sudo systemctl stop rovac-edge-esp32.service rovac-edge-mux.service \
      rovac-edge-tf.service rovac-edge-lidar.service \
      rovac-edge-ps2-joy.service rovac-edge-ps2-mapper.service 2>/dev/null || true
  " || true

  # Enable the target (services start via WantedBy)
  ssh "$EDGE_HOST" "sudo systemctl enable rovac-edge.target"
  echo "Enabled: rovac-edge.target"
  echo "(Not starting yet — motor firmware needs flashing first)"

  check_hardware
}

show_status() {
  ssh "$EDGE_HOST" "
    echo '=== rovac-edge.target ==='
    systemctl is-enabled rovac-edge.target 2>/dev/null || echo 'not installed'
    systemctl is-active rovac-edge.target 2>/dev/null || echo 'inactive'
    echo
    systemctl --no-pager -l status \
      rovac-edge.target \
      rovac-edge-esp32.service \
      rovac-edge-mux.service \
      rovac-edge-tf.service \
      rovac-edge-lidar.service \
      rovac-edge-ps2-joy.service \
      rovac-edge-ps2-mapper.service \
      2>/dev/null || true
  "
}

restart_stack() {
  ssh "$EDGE_HOST" "sudo systemctl restart rovac-edge.target"
}

uninstall_units() {
  echo "Disabling and removing units from $EDGE_HOST..."
  ssh "$EDGE_HOST" "
    sudo systemctl disable --now rovac-edge.target 2>/dev/null || true
    for svc in rovac-edge-esp32 rovac-edge-mux rovac-edge-tf rovac-edge-map-tf \
               rovac-edge-lidar rovac-edge-obstacle rovac-edge-ps2-joy \
               rovac-edge-ps2-mapper rovac-edge-supersensor; do
      sudo systemctl disable --now \${svc}.service 2>/dev/null || true
      sudo rm -f /etc/systemd/system/\${svc}.service
    done
    sudo rm -f /etc/systemd/system/rovac-edge.target
    sudo rm -f /etc/udev/rules.d/99-rovac-lenovo.rules
    sudo systemctl daemon-reload
    sudo udevadm control --reload-rules
  "
}

case "${1:-}" in
  install)
    install_units
    show_status
    ;;
  status)
    show_status
    ;;
  restart)
    restart_stack
    show_status
    ;;
  uninstall)
    uninstall_units
    ;;
  *)
    echo "Usage: $0 {install|status|restart|uninstall}" >&2
    exit 1
    ;;
esac
