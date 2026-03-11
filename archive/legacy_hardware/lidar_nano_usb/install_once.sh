#!/usr/bin/env bash

set -euo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "=== LIDAR Nano USB: one-time install ==="
echo "(Tip: for a basic GUI installer, run: ./install_ui.py)"

PLATFORM="$(uname -s)"

check_pyserial() {
  if python3 - <<'PY' >/dev/null 2>&1
import serial  # noqa: F401
PY
  then
    echo "✓ python3 + pyserial available"
  else
    echo "⚠️  pyserial not available for python3"
    echo "   Install it once (example): python3 -m pip install --user pyserial"
  fi
}

case "$PLATFORM" in
  Darwin)
    echo "Platform: macOS"
    check_pyserial

    if command -v systemextensionsctl >/dev/null 2>&1; then
      if systemextensionsctl list 2>/dev/null | grep -q "cn\\.wch\\.CH34xVCPDriver"; then
        echo "✓ WCH CH34x driver extension present"
        systemextensionsctl list 2>/dev/null | grep "cn\\.wch\\.CH34xVCPDriver" || true
      else
        echo "⚠️  WCH CH34x driver extension not detected (cn.wch.CH34xVCPDriver)"
        echo "   On a clean Mac, CH340 devices often require the WCH driver to expose /dev/cu.wchusbserial*."
        echo "   Install the WCH CH34x DriverKit driver once, then re-plug the device."
      fi
    else
      echo "⚠️  systemextensionsctl not found; cannot check DriverKit extension status."
    fi

    echo ""
    echo "Next checks:"
    echo "  python3 tools/usb_audit.py        # safe, no serial reads"
    echo "  python3 tools/find_lidar_port.py"
    echo "  python3 tools/bridge_probe.py     # safe, bounded sample"
    ;;

  Linux)
    echo "Platform: Linux"
    check_pyserial

    RULE_SRC="$REPO_DIR/udev/99-lidar-nano-usb.rules"
    RULE_DST="/etc/udev/rules.d/99-lidar-nano-usb.rules"

    if [ ! -f "$RULE_SRC" ]; then
      echo "❌ Missing udev rule template: $RULE_SRC"
      exit 1
    fi

    if [ "${EUID:-$(id -u)}" -ne 0 ]; then
      echo "ℹ️  To create a stable /dev/rovac_lidar symlink, install the udev rule once:"
      echo "  sudo cp $RULE_SRC $RULE_DST"
      echo "  sudo udevadm control --reload-rules"
      echo "  sudo udevadm trigger"
      echo ""
      echo "Also ensure your user can access serial devices (commonly the 'dialout' group)."
      echo ""
      echo "After installing, the device should appear as /dev/rovac_lidar (when plugged in)."
    else
      cp "$RULE_SRC" "$RULE_DST"
      udevadm control --reload-rules
      udevadm trigger
      echo "✓ Installed udev rule: $RULE_DST"
      echo "✓ Reloaded udev rules"
      echo ""
      echo "After re-plug, check: ls -la /dev/rovac_lidar"
    fi

    echo ""
    echo "Next checks:"
    echo "  python3 tools/find_lidar_port.py"
    echo "  python3 tools/bridge_probe.py     # safe, bounded sample"
    ;;

  *)
    echo "Platform: $PLATFORM"
    echo "⚠️  No automated installer for this platform."
    echo "- Ensure a CH340/USB-serial driver is installed once."
    echo "- Then use:"
    echo "  python3 tools/usb_audit.py"
    echo "  python3 tools/find_lidar_port.py"
    echo "  python3 tools/bridge_probe.py"
    ;;
esac
