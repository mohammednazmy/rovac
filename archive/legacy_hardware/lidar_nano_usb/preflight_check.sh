#!/bin/bash
# Preflight check for LIDAR USB module
# Run this before any serial port operations to avoid session hangs

set -e

echo "=== LIDAR USB Preflight Check ==="

# Find the device
DEVICE=$(ls /dev/cu.wchusbserial* /dev/cu.usbserial* 2>/dev/null | head -1)

if [ -z "$DEVICE" ]; then
    echo "❌ No USB serial device found"
    echo "   - Check if the LIDAR module is plugged in"
    echo "   - Try: ls /dev/cu.* /dev/tty.*"
    exit 1
fi

echo "✓ Device found: $DEVICE"

# Check for stuck processes
STUCK=$(lsof "$DEVICE" 2>/dev/null | tail -n +2)

if [ -n "$STUCK" ]; then
    echo "⚠️  WARNING: Processes holding the serial port:"
    echo "$STUCK"
    echo ""
    read -p "Kill these processes? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        lsof "$DEVICE" 2>/dev/null | awk 'NR>1 {print $2}' | xargs kill -9 2>/dev/null || true
        sleep 1
        echo "✓ Processes killed"
    else
        echo "⚠️  Processes still running - serial operations may hang!"
        exit 1
    fi
else
    echo "✓ No stuck processes"
fi

# Test port access
if stty -f "$DEVICE" 115200 2>/dev/null; then
    echo "✓ Port accessible and configured at 115200 baud"
else
    echo "❌ Cannot configure port"
    exit 1
fi

echo ""
echo "=== Preflight Complete ==="
echo "Device ready: $DEVICE"
