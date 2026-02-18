#!/bin/bash
#
# Install macOS launchd LaunchAgent to auto-start the controller stack
# (joy_node + joy_mapper) at login and keep it running.
#
# Usage:
#   ./scripts/install_mac_autostart.sh install
#   ./scripts/install_mac_autostart.sh start
#   ./scripts/install_mac_autostart.sh stop
#   ./scripts/install_mac_autostart.sh restart
#   ./scripts/install_mac_autostart.sh uninstall
#   ./scripts/install_mac_autostart.sh status
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

LABEL="com.rovac.controller"
PLIST_PATH="$HOME/Library/LaunchAgents/${LABEL}.plist"
SUPERVISOR="$ROVAC_DIR/scripts/rovac_controller_supervisor.sh"

uid="$(id -u)"
domain="gui/${uid}"

is_loaded() {
  launchctl print "${domain}/${LABEL}" >/dev/null 2>&1
}

ensure_plist_dir() {
  mkdir -p "$(dirname "$PLIST_PATH")"
}

write_plist() {
  ensure_plist_dir
  cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${SUPERVISOR}</string>
  </array>

  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>

  <key>WorkingDirectory</key>
  <string>${ROVAC_DIR}</string>

  <key>StandardOutPath</key>
  <string>/tmp/rovac_controller.out</string>
  <key>StandardErrorPath</key>
  <string>/tmp/rovac_controller.err</string>

  <!-- Throttle restarts to avoid tight crash loops -->
  <key>ThrottleInterval</key>
  <integer>2</integer>
</dict>
</plist>
EOF
}

bootout_if_loaded() {
  # Ignore errors if it's not loaded.
  launchctl bootout "${domain}" "$PLIST_PATH" 2>/dev/null || true
}

reset_logs() {
  : >/tmp/rovac_controller.out 2>/dev/null || true
  : >/tmp/rovac_controller.err 2>/dev/null || true
  : >/tmp/joy_node.log 2>/dev/null || true
  : >/tmp/joy_mapper.log 2>/dev/null || true
}

bootstrap_and_start() {
  if is_loaded; then
    launchctl kickstart -k "${domain}/${LABEL}" 2>/dev/null || true
    return 0
  fi

  launchctl bootstrap "${domain}" "$PLIST_PATH"
  launchctl enable "${domain}/${LABEL}" 2>/dev/null || true
  launchctl kickstart -k "${domain}/${LABEL}" 2>/dev/null || true
}

status() {
  echo "Plist: $PLIST_PATH"
  if [ -f "$PLIST_PATH" ]; then
    echo "  [+] exists"
  else
    echo "  [-] missing"
  fi
  launchctl print "${domain}/${LABEL}" 2>/dev/null | sed -n '1,60p' || echo "  [-] not loaded"
  echo "Logs:"
  ls -la /tmp/rovac_controller.out /tmp/rovac_controller.err 2>/dev/null || true
}

case "${1:-}" in
  install)
    if [ ! -x "$SUPERVISOR" ]; then
      echo "ERROR: supervisor not executable: $SUPERVISOR" >&2
      exit 1
    fi
    write_plist
    bootout_if_loaded
    reset_logs
    bootstrap_and_start
    echo "Installed and started: $LABEL"
    ;;
  start)
    if [ ! -f "$PLIST_PATH" ]; then
      echo "ERROR: missing LaunchAgent plist: $PLIST_PATH" >&2
      echo "Run: $0 install" >&2
      exit 1
    fi
    bootstrap_and_start
    echo "Started: $LABEL"
    ;;
  stop)
    bootout_if_loaded
    echo "Stopped: $LABEL"
    ;;
  restart)
    bootout_if_loaded
    reset_logs
    bootstrap_and_start
    echo "Restarted: $LABEL"
    ;;
  uninstall)
    bootout_if_loaded
    rm -f "$PLIST_PATH"
    echo "Uninstalled: $LABEL"
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 {install|uninstall|status}" >&2
    exit 1
    ;;
esac
