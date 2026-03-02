#!/bin/bash
# ROS2 Multi-Machine Environment Configuration (Mac <-> Edge)
# Source this file before running ROS2 commands.
# Edge computer: Lenovo ThinkCentre M910q at 192.168.1.218 (replaced Pi 5)

set -u

ROVAC_DOMAIN_ID_DEFAULT=42
ROVAC_MAC_IP_DEFAULT=192.168.1.104
ROVAC_EDGE_IP_DEFAULT=192.168.1.218

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
    CYCLONE_PROFILE_DEFAULT="$ROVAC_CONFIG_DIR/cyclonedds_lenovo.xml"
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

echo "ROS2 Environment: DOMAIN=$ROS_DOMAIN_ID, RMW=${RMW_IMPLEMENTATION:-unset}, LOCAL_IP=$ROVAC_LOCAL_IP, REMOTE_IP=$ROVAC_REMOTE_IP"
