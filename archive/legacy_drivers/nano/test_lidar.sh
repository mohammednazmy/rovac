#!/bin/bash
# Test LIDAR data through Nano USB bridge

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-/dev/cu.wchusbserial2140}"

echo "=== LIDAR Nano USB Bridge Test ==="
echo "Testing device: $PORT"
echo

# Check if device exists
if [ ! -e "$PORT" ]; then
    echo "❌ ERROR: Device $PORT not found"
    echo "Please check USB connection and try:"
    echo "  ls /dev/cu.wchusbserial*"
    exit 1
fi

echo "✅ Device found: $PORT"
echo

# Test basic serial communication
echo "Testing basic serial communication..."
stty -f "$PORT" 115200 >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Serial port configured successfully"
else
    echo "❌ ERROR: Failed to configure serial port"
    exit 1
fi

echo
echo "Reading data for 5 seconds..."
echo "You should see dots appearing below:"
echo

# Run the Python test
python3 "$SCRIPT_DIR/verify_lidar_simple.py" "$PORT"

echo
echo "=== Test Complete ==="