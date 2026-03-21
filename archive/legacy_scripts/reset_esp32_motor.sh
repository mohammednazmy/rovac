#!/bin/bash
# Reset the ESP32 motor controller via serial to force micro-ROS reconnect.
#
# Used by rovac-edge-uros-agent.service ExecStartPost to ensure the ESP32
# re-establishes its XRCE-DDS session with the (possibly new) Agent instance.
#
# Waits for the Agent to be listening on UDP 8888 before resetting the ESP32,
# so the ESP32 can connect immediately after its ~8s boot sequence.

SERIAL_PORT="/dev/esp32_motor"
AGENT_PORT=8888
MAX_WAIT=15

if [ ! -c "$SERIAL_PORT" ]; then
    echo "ESP32 not connected at $SERIAL_PORT — skipping reset"
    exit 0
fi

# Wait for Agent to actually be listening before resetting ESP32
echo "Waiting for Agent to bind port $AGENT_PORT..."
for i in $(seq 1 $MAX_WAIT); do
    if ss -uln | grep -q ":${AGENT_PORT} "; then
        echo "Agent listening on port $AGENT_PORT (${i}s)"
        break
    fi
    sleep 1
done

if ! ss -uln | grep -q ":${AGENT_PORT} "; then
    echo "WARNING: Agent not listening after ${MAX_WAIT}s — resetting ESP32 anyway"
fi

# Brief extra delay to let Agent fully initialize
sleep 1

# Prevent DTR toggle from resetting ESP32 during serial open
stty -F "$SERIAL_PORT" 115200 -hupcl 2>/dev/null

# Send restart command — printf avoids bash history expansion issues with '!'
printf '!restart\n' > "$SERIAL_PORT"
echo "ESP32 restart command sent via $SERIAL_PORT"
