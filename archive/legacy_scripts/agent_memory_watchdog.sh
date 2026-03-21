#!/bin/bash
#
# agent_memory_watchdog.sh — Restart micro-ROS Agent if RSS exceeds threshold.
#
# Safety net for catastrophic memory leaks. Fixed client keys + Hard
# Liveliness Check (added 2026-03-15) prevent stale session accumulation.
# Normal steady-state RSS is ~65-70MB (DDS discovery cache for all network
# participants). Threshold is set well above baseline to avoid false restarts.
#
# ESP32s detect Agent loss within 6s (ping interval 3s × 2 failures) and
# will auto-reconnect with fixed client keys (fast session reuse).

set -euo pipefail

THRESHOLD_KB=153600  # 150 MB

# Get Agent PID from systemd
MAIN_PID=$(systemctl show --property=MainPID --value rovac-edge-uros-agent.service 2>/dev/null || echo "0")

if [ "$MAIN_PID" = "0" ] || [ -z "$MAIN_PID" ]; then
    # Agent not running — nothing to watch
    exit 0
fi

# Read VmRSS from /proc (in kB)
RSS_LINE=$(grep -m1 '^VmRSS:' "/proc/$MAIN_PID/status" 2>/dev/null || echo "")
if [ -z "$RSS_LINE" ]; then
    # Process vanished between systemctl show and /proc read — harmless
    exit 0
fi

RSS_KB=$(echo "$RSS_LINE" | awk '{print $2}')

if [ "$RSS_KB" -gt "$THRESHOLD_KB" ]; then
    RSS_MB=$((RSS_KB / 1024))
    logger -t rovac-agent-watchdog "Agent RSS=${RSS_MB}MB exceeds ${THRESHOLD_KB}kB threshold — restarting"
    echo "Agent RSS=${RSS_MB}MB > threshold — restarting rovac-edge-uros-agent"
    systemctl restart rovac-edge-uros-agent.service
else
    # Periodic log at debug level (visible with journalctl -t rovac-agent-watchdog)
    RSS_MB=$((RSS_KB / 1024))
    logger -t rovac-agent-watchdog -p daemon.debug "Agent RSS=${RSS_MB}MB OK (threshold=${THRESHOLD_KB}kB)"
fi

exit 0
