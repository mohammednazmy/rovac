#!/bin/bash
# ROS2 Multi-Machine Environment Configuration (Mac <-> Edge)
# Source this file before running ROS2 commands.
# Edge computer: Raspberry Pi 5 at 192.168.1.200

# NOTE: Do NOT use "set -u" here. This script is sourced (not executed),
# so shell options leak into the caller's interactive shell and break
# other sourced scripts (e.g., ROS2 setup.bash references $AMENT_TRACE_SETUP_FILES
# which is unset). The ${VAR:-default} syntax used throughout already handles
# unset variables safely.

ROVAC_DOMAIN_ID_DEFAULT=42
ROVAC_EDGE_IP_DEFAULT=192.168.1.200

# Auto-detect Mac IP from en0 (resilient to DHCP changes)
if [ "$(uname -s 2>/dev/null)" = "Darwin" ]; then
    ROVAC_MAC_IP_DEFAULT=$(ipconfig getifaddr en0 2>/dev/null || echo "192.168.1.89")
else
    ROVAC_MAC_IP_DEFAULT=192.168.1.89
fi

# Optional selector: set ROVAC_DDS=fastdds|cyclonedds to switch RMW automatically.
case "${ROVAC_DDS:-}" in
    fastdds|fastrtps)
        export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
        ;;
    cyclonedds|cyclone)
        export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
        ;;
esac

# Force ROVAC domain ID (unconditional — overrides ROS2 default of 0)
export ROS_DOMAIN_ID=$ROVAC_DOMAIN_ID_DEFAULT

# Default to CycloneDDS unless ROVAC_DDS explicitly selects otherwise
if [ -z "${ROVAC_DDS:-}" ]; then
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
fi

# Discovery settings for better multi-machine communication
: "${ROS_AUTOMATIC_DISCOVERY_RANGE:=SUBNET}"
export ROS_AUTOMATIC_DISCOVERY_RANGE

# Ensure cross-machine communication isn't loopback-only
: "${ROS_LOCALHOST_ONLY:=0}"
export ROS_LOCALHOST_ONLY

# Prefer the repo config dir on Mac; fall back to $HOME for the Pi copy.
ROVAC_CONFIG_DIR="$HOME/robots/rovac/config"
if [ ! -d "$ROVAC_CONFIG_DIR" ]; then
    ROVAC_CONFIG_DIR="$HOME"
fi

ROVAC_OS="$(uname -s 2>/dev/null || echo unknown)"
if [ "$ROVAC_OS" = "Darwin" ]; then
    ROVAC_LOCAL_IP_DEFAULT="$ROVAC_MAC_IP_DEFAULT"
    ROVAC_REMOTE_IP_DEFAULT="$ROVAC_EDGE_IP_DEFAULT"
    FASTDDS_PROFILE_DEFAULT="$ROVAC_CONFIG_DIR/fastdds_mac.xml"
    CYCLONE_PROFILE_DEFAULT="$ROVAC_CONFIG_DIR/cyclonedds_mac.xml"
else
    ROVAC_LOCAL_IP_DEFAULT="$ROVAC_EDGE_IP_DEFAULT"
    ROVAC_REMOTE_IP_DEFAULT="$ROVAC_MAC_IP_DEFAULT"
    FASTDDS_PROFILE_DEFAULT="$ROVAC_CONFIG_DIR/fastdds_pi.xml"
    CYCLONE_PROFILE_DEFAULT="$ROVAC_CONFIG_DIR/cyclonedds_pi.xml"
fi

: "${ROVAC_LOCAL_IP:=$ROVAC_LOCAL_IP_DEFAULT}"
: "${ROVAC_REMOTE_IP:=$ROVAC_REMOTE_IP_DEFAULT}"

# Static peers (optional). Multicast discovery works on this network; keep this OFF by default.
# Enable with: export ROVAC_USE_STATIC_PEERS=1
if [ "${ROVAC_USE_STATIC_PEERS:-0}" = "1" ] || [ -n "${ROS_STATIC_PEERS:-}" ]; then
    export ROS_STATIC_PEERS="${ROS_STATIC_PEERS:-${ROVAC_MAC_IP_DEFAULT};${ROVAC_EDGE_IP_DEFAULT}}"
else
    unset ROS_STATIC_PEERS 2>/dev/null || true
fi

if [ "${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}" = "rmw_fastrtps_cpp" ]; then
    export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
    : "${FASTRTPS_DEFAULT_PROFILES_FILE:=$FASTDDS_PROFILE_DEFAULT}"
    export FASTRTPS_DEFAULT_PROFILES_FILE
    export RMW_FASTRTPS_USE_QOS_FROM_XML=0
    unset CYCLONEDDS_URI 2>/dev/null || true
elif [ "${RMW_IMPLEMENTATION:-rmw_cyclonedds_cpp}" = "rmw_cyclonedds_cpp" ]; then
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    : "${CYCLONEDDS_URI:=file://$CYCLONE_PROFILE_DEFAULT}"
    export CYCLONEDDS_URI
    unset FASTRTPS_DEFAULT_PROFILES_FILE 2>/dev/null || true
else
    unset FASTRTPS_DEFAULT_PROFILES_FILE 2>/dev/null || true
    unset CYCLONEDDS_URI 2>/dev/null || true
fi

# ── Auto-sync Mac IP to CycloneDDS configs ────────────────
# Updates both Mac self-peer and Pi Mac-peer when the Mac's DHCP IP changes.
# Only runs on Mac, only when the IP actually changed.
if [ "$ROVAC_OS" = "Darwin" ] && [ "${RMW_IMPLEMENTATION:-}" = "rmw_cyclonedds_cpp" ]; then
    _ROVAC_IP_STAMP="$HOME/.rovac_mac_ip"
    _ROVAC_LAST_IP=""
    [ -f "$_ROVAC_IP_STAMP" ] && _ROVAC_LAST_IP=$(cat "$_ROVAC_IP_STAMP" 2>/dev/null)

    if [ "$ROVAC_MAC_IP_DEFAULT" != "$_ROVAC_LAST_IP" ] && [ -n "$ROVAC_MAC_IP_DEFAULT" ]; then
        # Update Mac CycloneDDS self-peer
        _ROVAC_MAC_XML="$ROVAC_CONFIG_DIR/cyclonedds_mac.xml"
        if [ -f "$_ROVAC_MAC_XML" ] && [ -n "$_ROVAC_LAST_IP" ]; then
            sed -i '' "s|<Peer address=\"${_ROVAC_LAST_IP}\"/>|<Peer address=\"${ROVAC_MAC_IP_DEFAULT}\"/>|" "$_ROVAC_MAC_XML" 2>/dev/null
        fi

        # Sync to Pi: update Mac peer in Pi's CycloneDDS config + restart services
        if ssh -o ConnectTimeout=2 -o BatchMode=yes "pi@$ROVAC_EDGE_IP_DEFAULT" true 2>/dev/null; then
            _ROVAC_PI_XML="/home/pi/robots/rovac/config/cyclonedds_pi.xml"
            if [ -n "$_ROVAC_LAST_IP" ]; then
                ssh -o ConnectTimeout=3 "pi@$ROVAC_EDGE_IP_DEFAULT" \
                    "sed -i 's|<Peer address=\"${_ROVAC_LAST_IP}\"/>|<Peer address=\"${ROVAC_MAC_IP_DEFAULT}\"/>|' $_ROVAC_PI_XML" 2>/dev/null
            else
                # First run or stamp cleared — replace any Mac peer (not the Pi self-peer)
                ssh -o ConnectTimeout=3 "pi@$ROVAC_EDGE_IP_DEFAULT" \
                    "sed -i '/<\!-- Mac -->/{ n; s|<Peer address=\"[^\"]*\"/>|<Peer address=\"${ROVAC_MAC_IP_DEFAULT}\"/>| }' $_ROVAC_PI_XML" 2>/dev/null
            fi
            # Restart edge services to pick up new peer config
            ssh -o ConnectTimeout=3 "pi@$ROVAC_EDGE_IP_DEFAULT" \
                "sudo systemctl restart rovac-edge.target" 2>/dev/null &
            echo "  IP changed: ${_ROVAC_LAST_IP:-unknown} → $ROVAC_MAC_IP_DEFAULT (synced to Pi, restarting edge services)"
            echo "$ROVAC_MAC_IP_DEFAULT" > "$_ROVAC_IP_STAMP"
        else
            echo "  IP changed but Pi unreachable — update Pi config manually (will retry next source)"
        fi
    fi
fi

echo "ROS2 Environment: DOMAIN=$ROS_DOMAIN_ID, RMW=${RMW_IMPLEMENTATION:-unset}, LOCAL_IP=$ROVAC_LOCAL_IP, REMOTE_IP=$ROVAC_REMOTE_IP"
