#!/bin/bash
# Test the full PS2 controller → motor chain on the edge computer
# Usage: ssh asimo@192.168.1.218 'bash ~/robots/rovac/tools/test_ps2_chain.sh'

set -e

echo "=========================================="
echo " ROVAC PS2 Controller Chain Test"
echo "=========================================="
echo ""

# Step 1: Check USB receiver
echo "[1/5] USB Receiver..."
if lsusb | grep -q "2563:0575"; then
    echo "  ✓ ShanWan USB receiver found"
else
    echo "  ✗ USB receiver NOT found! Plug in the receiver."
    exit 1
fi

# Step 2: Check input device
echo "[2/5] Input Device..."
if [ -e /dev/input/js0 ]; then
    echo "  ✓ /dev/input/js0 exists"
else
    echo "  ✗ /dev/input/js0 missing! Check USB hub."
    exit 1
fi

if [ -r /dev/input/js0 ]; then
    echo "  ✓ /dev/input/js0 readable"
else
    echo "  ✗ /dev/input/js0 not readable! Check group membership (need 'input' group)"
    exit 1
fi

# Step 3: Check systemd services
echo "[3/5] Services..."
for svc in rovac-edge-ps2-joy rovac-edge-ps2-mapper; do
    status=$(systemctl is-active "$svc.service" 2>/dev/null || echo "inactive")
    if [ "$status" = "active" ]; then
        echo "  ✓ $svc: active"
    else
        echo "  ✗ $svc: $status"
    fi
done

# Step 4: Check ROS2 topics
echo "[4/5] ROS2 Topics..."
source /opt/ros/jazzy/setup.bash
source ~/robots/rovac/config/ros2_env.sh 2>/dev/null || true

echo "  Checking /joy topic (5 sec)..."
hz_output=$(timeout 5 ros2 topic hz /joy --window 5 2>&1 | grep "average rate" | tail -1)
if [ -n "$hz_output" ]; then
    echo "  ✓ /joy: $hz_output"
else
    echo "  ✗ /joy: NO messages (is the controller awake? Press START!)"
fi

echo "  Checking /cmd_vel_joy topic (5 sec)..."
hz_output=$(timeout 5 ros2 topic hz /cmd_vel_joy --window 5 2>&1 | grep "average rate" | tail -1)
if [ -n "$hz_output" ]; then
    echo "  ✓ /cmd_vel_joy: $hz_output"
else
    echo "  ✗ /cmd_vel_joy: NO messages"
fi

# Step 5: Raw event test
echo "[5/5] Raw Events (3 seconds — press buttons NOW!)..."
echo "  Listening on /dev/input/event6..."
count=$(timeout 3 cat /dev/input/event6 2>/dev/null | wc -c)
if [ "$count" -gt 0 ]; then
    echo "  ✓ Received $count bytes of event data"
else
    echo "  ✗ No events received. Controller is ASLEEP or unpaired."
    echo ""
    echo "  TO WAKE: Press START on the PS2 controller."
    echo "  Green LED on receiver should light up."
    echo "  Then re-run this test."
fi

echo ""
echo "=========================================="
echo " Test complete."
echo "=========================================="
