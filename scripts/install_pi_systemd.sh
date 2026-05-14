#!/bin/bash
#
# Install and enable ROVAC systemd units on the Pi so the edge stack
# auto-starts at boot and auto-restarts on crashes.
#
# Usage:
#   ./scripts/install_pi_systemd.sh install    # copy unit files, enable + start (full bootstrap)
#   ./scripts/install_pi_systemd.sh status     # show service status
#   ./scripts/install_pi_systemd.sh restart    # restart rovac-edge.target
#   ./scripts/install_pi_systemd.sh udev       # re-apply udev rules only (no systemd touch)
#   ./scripts/install_pi_systemd.sh externals  # vcs import external.repos + apply tracked patches
#   ./scripts/install_pi_systemd.sh libcamera  # build + install Pi-patched libcamera + camera_ros
#   ./scripts/install_pi_systemd.sh uninstall  # disable + remove units
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

# List of all legacy / superseded ROVAC udev rule filenames the installer
# wipes before re-installing the canonical one. Keep this list authoritative
# so install + uninstall stay in sync. Add to the list when retiring a rules
# file; never remove an entry (a stale Pi may still have it).
LEGACY_RULE_FILES=(
  /etc/udev/rules.d/99-rovac-esp32.rules     # superseded by 99-rovac-usb.rules
  /etc/udev/rules.d/99-rovac-usb.rules       # canonical (re-installed below)
  /etc/udev/rules.d/99-esp32-lidar.rules     # retired XV11 experiment
  /etc/udev/rules.d/99-hiwonder-rrc.rules    # retired Hiwonder controller
  /etc/udev/rules.d/99-roarm.rules           # not yet integrated
  /etc/udev/rules.d/99-super-sensor.rules    # retired CH341 super-sensor
  /etc/udev/rules.d/99-encoder-bridge.rules  # retired Nano encoder bridge
)

install_ros2_ws_externals() {
  # External ROS2 packages declared in ros2_ws/src/external.repos are pulled
  # via vcstool. We DO NOT vendor them in this monorepo to avoid history bloat
  # and to keep upstream patches a `git pull` away. Pinned to a SHA in the
  # repos file so installs are reproducible.
  local repos_file="$ROVAC_DIR/ros2_ws/src/external.repos"
  if [ ! -f "$repos_file" ]; then
    echo "  (no $repos_file - skipping external clone bootstrap)"
    return 0
  fi

  echo "Bootstrapping external ROS2 packages from external.repos..."
  if ! ssh "$PI_HOST" "command -v vcs >/dev/null 2>&1"; then
    echo "  vcstool not installed on Pi - installing python3-vcstool via apt..."
    if ! ssh "$PI_HOST" "sudo apt-get install -y python3-vcstool 2>&1 | tail -3"; then
      echo "  WARNING: apt install of python3-vcstool failed; skipping external clone." >&2
      echo "  Install manually: ssh pi 'sudo apt-get install -y python3-vcstool'" >&2
      return 0
    fi
  fi

  # vcs import is non-destructive: skips existing directories. Use --force to
  # overwrite (don't enable in normal install — would blow away local edits).
  ssh "$PI_HOST" "
    cd /home/pi/robots/rovac/ros2_ws/src
    vcs import --input external.repos 2>&1 | sed 's/^/  /'
  "

  # Apply patches from external_patches/ idempotently. Each patch's filename
  # encodes the target package: <package>-<short-description>.patch
  # Idempotency: if the patch already applies forward, apply it; if it only
  # applies in reverse, it's already on the tree and we skip; otherwise warn.
  echo "Applying external patches..."
  ssh "$PI_HOST" '
    cd /home/pi/robots/rovac/ros2_ws/src
    if [ ! -d external_patches ]; then
      echo "  (no external_patches/ — nothing to apply)"
      exit 0
    fi
    shopt -s nullglob
    for p in external_patches/*.patch; do
      pkg="$(basename "$p" .patch | cut -d- -f1)"
      if [ ! -d "$pkg" ]; then
        echo "  SKIP $p (package $pkg not present)"
        continue
      fi
      cd "$pkg"
      if git apply --check "../$p" 2>/dev/null; then
        git apply "../$p" && echo "  APPLIED $p to $pkg"
      elif git apply --reverse --check "../$p" 2>/dev/null; then
        echo "  already-applied $p in $pkg"
      else
        echo "  WARN: $p does not apply cleanly to $pkg (manual review needed)" >&2
      fi
      cd - >/dev/null
    done
  '
}

build_pi_libcamera() {
  # Pi 5 + OV5647 stereo cameras require the Pi-patched libcamera fork
  # (v0.5.2+rpt20250903), built from source against the running kernel's
  # rp1-cfe ABI. The Ubuntu apt libcamera (0.2.0) lacks Pi 5 support; the
  # OSRF ros-jazzy-libcamera (0.7.0) ABI doesn't match the kernel.
  # The build script is idempotent — it skips if already installed.
  echo "Building/verifying Pi-patched libcamera + camera_ros (idempotent)..."
  local local_script="$ROVAC_DIR/scripts/build_pi_libcamera.sh"
  if [ ! -f "$local_script" ]; then
    echo "  WARNING: $local_script not found - skipping libcamera build."
    return 0
  fi
  # Rsync the script to the Pi so it always matches the repo version
  rsync -av "$local_script" "$PI_HOST":/home/pi/robots/rovac/scripts/build_pi_libcamera.sh >/dev/null
  ssh "$PI_HOST" "bash /home/pi/robots/rovac/scripts/build_pi_libcamera.sh 2>&1 | sed 's/^/  /'"
}

install_udev_rules() {
  # Single source of truth: config/udev/99-rovac-usb.rules in the repo.
  # Step 1: wipe legacy/conflicting ROVAC udev rule files. These accumulate
  # over time as hardware experiments come and go; they cause silent SYMLINK
  # collisions (e.g. serial=="0001" -> esp32_lidar from the retired XV11
  # experiment shadowed /dev/esp32_sensor for weeks).
  echo "Wiping legacy ROVAC udev rule files..."
  ssh "$PI_HOST" "sudo rm -f ${LEGACY_RULE_FILES[*]}"

  # Step 2: install the canonical rule file
  echo "Installing canonical udev rules (99-rovac-usb.rules)..."
  remote_sudo_install "/etc/udev/rules.d/99-rovac-usb.rules" "$ROVAC_DIR/config/udev/99-rovac-usb.rules"

  # Step 3: reload udevd and re-evaluate all currently-attached devices
  ssh "$PI_HOST" "sudo udevadm control --reload-rules && sudo udevadm trigger --action=add"
  ssh "$PI_HOST" "sudo udevadm settle --timeout=5" || true

  # Step 4: verify expected symlinks exist. If any are missing the install is
  # broken and the systemd target won't come up - fail loudly here rather
  # than let the user chase 'dependency failed' errors later.
  echo "Verifying USB symlinks..."
  if ! ssh "$PI_HOST" '
    missing=()
    for sym in esp32_motor esp32_sensor rplidar_c1; do
      if [ -e "/dev/$sym" ]; then
        echo "  OK: /dev/$sym -> $(readlink /dev/$sym)"
      else
        echo "  MISSING: /dev/$sym"
        missing+=("$sym")
      fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
      echo "ERROR: ${#missing[@]} expected USB symlink(s) missing." >&2
      echo "Check that each device is plugged in and that lsusb sees it:" >&2
      lsusb >&2
      exit 1
    fi
  '; then
    echo "ERROR: USB symlink verification failed. Aborting." >&2
    return 1
  fi
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

  install_udev_rules

  install_ros2_ws_externals

  # Build Pi-patched libcamera + camera_ros (needed for stereo cameras).
  # Idempotent: skips if already built. Adds 10-15 min on first install only.
  build_pi_libcamera

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

  # Sense HAT panel (status display + on-robot joystick)
  remote_sudo_install "/etc/systemd/system/rovac-edge-sense-hat-panel.service" "$UNIT_DIR/rovac-edge-sense-hat-panel.service"

  # EKF sensor fusion (disabled by default — run from Mac)
  remote_sudo_install "/etc/systemd/system/rovac-edge-ekf.service" "$UNIT_DIR/rovac-edge-ekf.service"

  # Stereo cameras (dual OV5647 NoIR via libcamera + camera_ros). Replaces the
  # retired USB-webcam stereo stack (depth + obstacle + webcam services moved
  # to archive/legacy_hardware/stereo_cameras_usb on 2026-05-14).
  remote_sudo_install "/etc/systemd/system/rovac-edge-stereo-cameras.service" "$UNIT_DIR/rovac-edge-stereo-cameras.service"

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
    sudo rm -f ${LEGACY_RULE_FILES[*]}
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
  udev)
    install_udev_rules
    ;;
  externals)
    install_ros2_ws_externals
    ;;
  libcamera)
    build_pi_libcamera
    ;;
  uninstall)
    uninstall_units
    ;;
  *)
    echo "Usage: $0 {install|status|restart|udev|externals|libcamera|uninstall}" >&2
    exit 1
    ;;
esac
