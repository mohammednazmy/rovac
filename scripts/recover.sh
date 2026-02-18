#!/bin/bash
# Emergency Recovery Script (Mac <-> Pi)
#
# This script restarts the persistent pieces of the stack:
# - macOS launchd controller agent (joy_node + joy_mapper)
# - Pi systemd edge stack (motors + sensors + mux + lidar)
#
# Usage:
#   ./scripts/recover.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PI_HOST="${PI_HOST:-pi@192.168.1.200}"

echo "[ROVAC] Field recovery: restarting controller + edge stack"

cd "$ROVAC_DIR"

# Restart Mac controller agent if installed.
if [ -f "$HOME/Library/LaunchAgents/com.rovac.controller.plist" ]; then
  ./scripts/install_mac_autostart.sh restart
else
  echo "[ROVAC] NOTE: launchd controller agent not installed (run ./scripts/install_mac_autostart.sh install)"
fi

# Restart Pi edge stack if reachable.
if ping -c 1 -W 2 192.168.1.200 >/dev/null 2>&1; then
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" "sudo systemctl restart rovac-edge.target" || true
else
  echo "[ROVAC] WARN: cannot reach Pi at 192.168.1.200"
fi

echo "[ROVAC] Status:"
./scripts/standalone_control.sh status || true
