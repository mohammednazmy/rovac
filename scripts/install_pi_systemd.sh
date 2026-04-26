#!/bin/bash
#
# Install and enable ROVAC systemd units on the Pi so the edge stack
# auto-starts at boot and auto-restarts on crashes.
#
# Usage:
#   ./scripts/install_pi_systemd.sh install   # copy unit files, enable + start
#   ./scripts/install_pi_systemd.sh status    # show service status
#   ./scripts/install_pi_systemd.sh restart   # restart rovac-edge.target
#   ./scripts/install_pi_systemd.sh uninstall # disable + remove units
#
# Env:
#   PI_HOST=pi@192.168.1.200
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PI_HOST="${PI_HOST:-pi@192.168.1.200}"
UNIT_DIR="$ROVAC_DIR/config/systemd"

remote_sudo_install() {
  local remote_path="$1"
  local local_path="$2"
  ssh "$PI_HOST" "sudo tee '$remote_path' >/dev/null" <"$local_path"
}

remote_install_if_missing() {
  local remote_path="$1"
  local local_path="$2"
  local mode="${3:-0644}"

  if ssh "$PI_HOST" "test -f '$remote_path'"; then
    return 0
  fi

  echo "  [+] Installing missing: $remote_path"
  ssh "$PI_HOST" "tee '$remote_path' >/dev/null" <"$local_path"
  ssh "$PI_HOST" "chmod '$mode' '$remote_path'" >/dev/null 2>&1 || true
}

check_hardware_notes() {
  ssh "$PI_HOST" "
    if [ -e /dev/esp32_motor ]; then
      echo '  [+] ESP32 motor controller detected at /dev/esp32_motor'
    else
      echo '  [!] No ESP32 motor controller detected (no /dev/esp32_motor — check USB + udev rules)'
    fi
    if [ -e /dev/esp32_sensor ]; then
      echo '  [+] ESP32 sensor hub detected at /dev/esp32_sensor'
    else
      echo '  [!] No ESP32 sensor hub detected (no /dev/esp32_sensor — check USB + udev rules)'
    fi
    if [ -e /dev/rplidar_c1 ]; then
      echo '  [+] RPLIDAR C1 detected at /dev/rplidar_c1'
    else
      echo '  [!] No RPLIDAR C1 detected (no /dev/rplidar_c1 — check USB + udev rules)'
    fi
  " 2>/dev/null || true
}

install_units() {
  if [ ! -d "$UNIT_DIR" ]; then
    echo "ERROR: missing $UNIT_DIR" >&2
    exit 1
  fi

  echo "Installing systemd units to $PI_HOST..."

  # Pre-flight: verify monorepo is cloned on Pi
  if ! ssh "$PI_HOST" "test -d /home/pi/robots/rovac/config"; then
    echo "ERROR: Monorepo not found at /home/pi/robots/rovac/" >&2
    echo "Run: ssh pi 'mkdir -p /home/pi/robots && git clone git@github.com:mohammednazmy/rovac.git /home/pi/robots/rovac'" >&2
    exit 1
  fi

  # Deploy udev rules for ESP32 motor controller
  echo "Installing udev rules..."
  remote_sudo_install "/etc/udev/rules.d/99-rovac-esp32.rules" "$ROVAC_DIR/config/udev/99-rovac-esp32.rules"
  ssh "$PI_HOST" "sudo udevadm control --reload-rules && sudo udevadm trigger" || true

  # Remove dead services from previous installations (WiFi micro-ROS era)
  echo "Cleaning up legacy services..."
  ssh "$PI_HOST" "
    sudo systemctl disable --now rovac-edge-uros-agent.service rovac-edge-uros-agent-watchdog.service rovac-edge-uros-agent-watchdog.timer rovac-edge-odom-relay.service rovac-edge-imu-relay.service rovac-edge-tf-relay.service rovac-edge-esp32.service 2>/dev/null || true
    sudo rm -f /etc/systemd/system/rovac-edge-uros-agent.service /etc/systemd/system/rovac-edge-uros-agent-watchdog.service /etc/systemd/system/rovac-edge-uros-agent-watchdog.timer /etc/systemd/system/rovac-edge-odom-relay.service /etc/systemd/system/rovac-edge-imu-relay.service /etc/systemd/system/rovac-edge-tf-relay.service /etc/systemd/system/rovac-edge-esp32.service
  " || true

  # Target
  remote_sudo_install "/etc/systemd/system/rovac-edge.target" "$UNIT_DIR/rovac-edge.target"

  # Motor driver (USB serial COBS binary protocol to ESP32)
  remote_sudo_install "/etc/systemd/system/rovac-edge-motor-driver.service" "$UNIT_DIR/rovac-edge-motor-driver.service"

  # Sensor hub (USB serial COBS binary — 4x ultrasonic + 2x cliff)
  remote_sudo_install "/etc/systemd/system/rovac-edge-sensor-hub.service" "$UNIT_DIR/rovac-edge-sensor-hub.service"

  # RPLIDAR C1 (USB serial, native ROS2 driver)
  remote_sudo_install "/etc/systemd/system/rovac-edge-rplidar-c1.service" "$UNIT_DIR/rovac-edge-rplidar-c1.service"

  # Core services
  remote_sudo_install "/etc/systemd/system/rovac-edge-mux.service" "$UNIT_DIR/rovac-edge-mux.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-tf.service" "$UNIT_DIR/rovac-edge-tf.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-map-tf.service" "$UNIT_DIR/rovac-edge-map-tf.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-obstacle.service" "$UNIT_DIR/rovac-edge-obstacle.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-supersensor.service" "$UNIT_DIR/rovac-edge-supersensor.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-health.service" "$UNIT_DIR/rovac-edge-health.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-diagnostics-splitter.service" "$UNIT_DIR/rovac-edge-diagnostics-splitter.service"

  # PS2 wireless controller
  remote_sudo_install "/etc/systemd/system/rovac-edge-ps2-joy.service" "$UNIT_DIR/rovac-edge-ps2-joy.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-ps2-mapper.service" "$UNIT_DIR/rovac-edge-ps2-mapper.service"

  # EKF sensor fusion (disabled by default — run from Mac)
  remote_sudo_install "/etc/systemd/system/rovac-edge-ekf.service" "$UNIT_DIR/rovac-edge-ekf.service"

  # Optional peripherals
  remote_sudo_install "/etc/systemd/system/rovac-edge-stereo-depth.service" "$UNIT_DIR/rovac-edge-stereo-depth.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-stereo-obstacle.service" "$UNIT_DIR/rovac-edge-stereo-obstacle.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-stereo.target" "$UNIT_DIR/rovac-edge-stereo.target"
  remote_sudo_install "/etc/systemd/system/rovac-edge-webcam.service" "$UNIT_DIR/rovac-edge-webcam.service"

  ssh "$PI_HOST" "sudo systemctl daemon-reload"

  # Stop any ad-hoc instances to avoid duplicates (safe if already stopped).
  ssh "$PI_HOST" "
    sudo systemctl stop rovac-edge.target 2>/dev/null || true
    pkill -f 'cmd_vel_mux\\.py' 2>/dev/null || true
  " || true

  ssh "$PI_HOST" "sudo systemctl enable --now rovac-edge.target"
  ssh "$PI_HOST" "sudo systemctl restart rovac-edge.target"
  echo "Enabled: rovac-edge.target"

  check_hardware_notes
}

show_status() {
  ssh "$PI_HOST" "
    systemctl is-enabled rovac-edge.target 2>/dev/null || true
    systemctl is-active rovac-edge.target 2>/dev/null || true
    echo
    systemctl --no-pager -l status rovac-edge.target rovac-edge-motor-driver.service rovac-edge-sensor-hub.service rovac-edge-rplidar-c1.service rovac-edge-mux.service rovac-edge-tf.service rovac-edge-map-tf.service rovac-edge-obstacle.service rovac-edge-health.service rovac-edge-ps2-joy.service rovac-edge-ps2-mapper.service || true
  "
}

restart_stack() {
  ssh "$PI_HOST" "sudo systemctl restart rovac-edge.target"
}

uninstall_units() {
  echo "Disabling and removing units from $PI_HOST..."
  ssh "$PI_HOST" "
    sudo systemctl disable --now rovac-edge.target 2>/dev/null || true
    sudo rm -f /etc/systemd/system/rovac-edge*.service
    sudo rm -f /etc/systemd/system/rovac-edge*.target
    sudo rm -f /etc/systemd/system/rovac-edge*.timer
    sudo rm -f /etc/systemd/system/rovac-camera.service
    sudo rm -f /etc/systemd/system/rovac-phone-cameras.service
    sudo rm -f /etc/udev/rules.d/99-rovac-esp32.rules
    sudo rm -f /etc/udev/rules.d/99-rovac-usb.rules
    sudo systemctl daemon-reload
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
