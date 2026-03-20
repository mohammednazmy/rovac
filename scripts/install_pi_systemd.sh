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
  # Verify ESP32 motor controller is detected
  ssh "$PI_HOST" "
    if [ -e /dev/esp32_motor ]; then
      echo '  [+] ESP32 motor controller detected at /dev/esp32_motor'
    else
      echo '  [!] No ESP32 motor controller detected (no /dev/esp32_motor — check USB + udev rules)'
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

  remote_sudo_install "/etc/systemd/system/rovac-edge.target" "$UNIT_DIR/rovac-edge.target"
  remote_sudo_install "/etc/systemd/system/rovac-edge-uros-agent.service" "$UNIT_DIR/rovac-edge-uros-agent.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-uros-agent-watchdog.service" "$UNIT_DIR/rovac-edge-uros-agent-watchdog.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-uros-agent-watchdog.timer" "$UNIT_DIR/rovac-edge-uros-agent-watchdog.timer"
  remote_sudo_install "/etc/systemd/system/rovac-edge-mux.service" "$UNIT_DIR/rovac-edge-mux.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-tf.service" "$UNIT_DIR/rovac-edge-tf.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-rplidar-c1.service" "$UNIT_DIR/rovac-edge-rplidar-c1.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-supersensor.service" "$UNIT_DIR/rovac-edge-supersensor.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-obstacle.service" "$UNIT_DIR/rovac-edge-obstacle.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-map-tf.service" "$UNIT_DIR/rovac-edge-map-tf.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-stereo-depth.service" "$UNIT_DIR/rovac-edge-stereo-depth.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-stereo-obstacle.service" "$UNIT_DIR/rovac-edge-stereo-obstacle.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-stereo.target" "$UNIT_DIR/rovac-edge-stereo.target"
  remote_sudo_install "/etc/systemd/system/rovac-edge-phone-sensors.service" "$UNIT_DIR/rovac-edge-phone-sensors.service"
  remote_sudo_install "/etc/systemd/system/rovac-phone-cameras.service" "$UNIT_DIR/rovac-phone-cameras.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-webcam.service" "$UNIT_DIR/rovac-edge-webcam.service"
  remote_sudo_install "/etc/systemd/system/rovac-camera.service" "$UNIT_DIR/rovac-camera.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-ps2-joy.service" "$UNIT_DIR/rovac-edge-ps2-joy.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-ps2-mapper.service" "$UNIT_DIR/rovac-edge-ps2-mapper.service"

  # QoS relays (best_effort→reliable for robot_localization)
  remote_sudo_install "/etc/systemd/system/rovac-edge-odom-relay.service" "$UNIT_DIR/rovac-edge-odom-relay.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-imu-relay.service" "$UNIT_DIR/rovac-edge-imu-relay.service"
  remote_sudo_install "/etc/systemd/system/rovac-edge-tf-relay.service" "$UNIT_DIR/rovac-edge-tf-relay.service"

  # rosbridge (phone sensors WebSocket)
  remote_sudo_install "/etc/systemd/system/rovac-edge-rosbridge.service" "$UNIT_DIR/rovac-edge-rosbridge.service"

  # EKF sensor fusion
  remote_sudo_install "/etc/systemd/system/rovac-edge-ekf.service" "$UNIT_DIR/rovac-edge-ekf.service"

  ssh "$PI_HOST" "sudo systemctl daemon-reload"

  # Stop any ad-hoc instances to avoid duplicates (safe if already stopped).
  ssh "$PI_HOST" "
    sudo systemctl stop rovac-edge.target 2>/dev/null || true
    sudo systemctl stop rovac-edge-uros-agent.service rovac-edge-mux.service rovac-edge-tf.service rovac-edge-rplidar-c1.service rovac-edge-supersensor.service rovac-edge-obstacle.service rovac-camera.service rovac-edge-ps2-joy.service rovac-edge-ps2-mapper.service 2>/dev/null || true
    pkill -f 'micro_ros_agent' 2>/dev/null || true
    pkill -f 'cmd_vel_mux\\.py' 2>/dev/null || true
    pkill -f 'lidar_wireless_monitor\\.py' 2>/dev/null || true
    pkill -f 'scrcpy --video-source=camera' 2>/dev/null || true
    pkill -f 'phone_camera_publisher\\.py' 2>/dev/null || true
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
    systemctl --no-pager -l status rovac-edge.target rovac-edge-uros-agent.service rovac-edge-uros-agent-watchdog.timer rovac-edge-rplidar-c1.service rovac-edge-mux.service rovac-edge-tf.service rovac-edge-supersensor.service rovac-edge-obstacle.service rovac-edge-map-tf.service rovac-edge-ps2-joy.service rovac-edge-ps2-mapper.service || true
  "
}

restart_stack() {
  ssh "$PI_HOST" "sudo systemctl restart rovac-edge.target"
}

uninstall_units() {
  echo "Disabling and removing units from $PI_HOST..."
  ssh "$PI_HOST" "
    sudo systemctl disable --now rovac-edge.target 2>/dev/null || true
    sudo systemctl disable --now rovac-edge-uros-agent.service rovac-edge-uros-agent-watchdog.timer rovac-edge-mux.service rovac-edge-tf.service rovac-edge-rplidar-c1.service rovac-edge-supersensor.service rovac-edge-obstacle.service rovac-edge-map-tf.service rovac-edge-stereo-depth.service rovac-edge-stereo-obstacle.service rovac-edge-phone-sensors.service rovac-phone-cameras.service rovac-camera.service rovac-edge-ps2-joy.service rovac-edge-ps2-mapper.service 2>/dev/null || true
    sudo rm -f /etc/systemd/system/rovac-edge.target
    sudo rm -f /etc/systemd/system/rovac-edge-uros-agent.service
    sudo rm -f /etc/systemd/system/rovac-edge-uros-agent-watchdog.service
    sudo rm -f /etc/systemd/system/rovac-edge-uros-agent-watchdog.timer
    sudo rm -f /etc/udev/rules.d/99-rovac-esp32.rules
    sudo rm -f /etc/systemd/system/rovac-edge-mux.service
    sudo rm -f /etc/systemd/system/rovac-edge-tf.service
    sudo rm -f /etc/systemd/system/rovac-edge-rplidar-c1.service
    sudo rm -f /etc/systemd/system/rovac-edge-supersensor.service
    sudo rm -f /etc/systemd/system/rovac-edge-obstacle.service
    sudo rm -f /etc/systemd/system/rovac-edge-map-tf.service
    sudo rm -f /etc/systemd/system/rovac-edge-stereo-depth.service
    sudo rm -f /etc/systemd/system/rovac-edge-stereo-obstacle.service
    sudo rm -f /etc/systemd/system/rovac-edge-stereo.target
    sudo rm -f /etc/systemd/system/rovac-edge-phone-sensors.service
    sudo rm -f /etc/systemd/system/rovac-phone-cameras.service
    sudo rm -f /etc/systemd/system/rovac-camera.service
    sudo rm -f /etc/systemd/system/rovac-edge-ps2-joy.service
    sudo rm -f /etc/systemd/system/rovac-edge-ps2-mapper.service
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
