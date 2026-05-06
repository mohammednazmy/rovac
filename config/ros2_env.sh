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
export ROVAC_LOCAL_IP
export ROVAC_REMOTE_IP

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

# ── CycloneDDS config render + auto-sync (atomic, idempotent) ─────────
# The rendered cyclonedds_{mac,pi}.xml files are gitignored because this
# script writes to them on every source. They are produced from their
# matching .template by substituting __MAC_IP__.
#
# Design notes:
#  • The local file is rendered every source via tmp+rename (atomic).
#    This is cheap (~1ms) and guarantees the local file always reflects
#    the current Mac IP — no drift possible from interrupted past runs.
#  • The Pi sync runs only when the Mac IP differs from the IP recorded
#    in the stamp file ($HOME/.rovac_mac_ip).
#  • The stamp is updated ONLY after the Pi sync succeeds. If Pi is
#    unreachable or the SSH render fails, the stamp stays stale, and the
#    next source will retry the Pi sync. This is the explicit fix for
#    the previous stamp/file-content drift bug, where the Mac's local
#    file got mutated but the stamp was not — leading to a future sed
#    against a pattern that no longer matched.
if [ "${RMW_IMPLEMENTATION:-}" = "rmw_cyclonedds_cpp" ]; then
    _ROVAC_LOCAL_XML="$CYCLONE_PROFILE_DEFAULT"
    _ROVAC_LOCAL_TEMPLATE="${_ROVAC_LOCAL_XML}.template"

    # Render local CycloneDDS config from template (atomic tmp+rename).
    # Runs on both Mac and Pi — every source produces a fresh, correct file.
    if [ -f "$_ROVAC_LOCAL_TEMPLATE" ] && [ -n "${ROVAC_MAC_IP_DEFAULT:-}" ]; then
        _ROVAC_TMP=$(mktemp "${_ROVAC_LOCAL_XML}.tmp.XXXXXX" 2>/dev/null) || _ROVAC_TMP=""
        if [ -n "$_ROVAC_TMP" ]; then
            if sed "s|__MAC_IP__|${ROVAC_MAC_IP_DEFAULT}|g" "$_ROVAC_LOCAL_TEMPLATE" > "$_ROVAC_TMP" 2>/dev/null; then
                mv -f "$_ROVAC_TMP" "$_ROVAC_LOCAL_XML"
            else
                rm -f "$_ROVAC_TMP"
            fi
        fi
        unset _ROVAC_TMP
    fi
    unset _ROVAC_LOCAL_XML _ROVAC_LOCAL_TEMPLATE
fi

# ── Mac→Pi auto-sync (Mac only, on IP change, atomic) ────────────────
if [ "$ROVAC_OS" = "Darwin" ] && [ "${RMW_IMPLEMENTATION:-}" = "rmw_cyclonedds_cpp" ]; then
    _ROVAC_IP_STAMP="$HOME/.rovac_mac_ip"
    _ROVAC_LAST_IP=""
    [ -f "$_ROVAC_IP_STAMP" ] && _ROVAC_LAST_IP=$(cat "$_ROVAC_IP_STAMP" 2>/dev/null)

    if [ -n "${ROVAC_MAC_IP_DEFAULT:-}" ] && [ "$ROVAC_MAC_IP_DEFAULT" != "$_ROVAC_LAST_IP" ]; then
        _ROVAC_PI_XML="/home/pi/robots/rovac/config/cyclonedds_pi.xml"
        _ROVAC_PI_TEMPLATE="${_ROVAC_PI_XML}.template"

        if ssh -o ConnectTimeout=2 -o BatchMode=yes "pi@$ROVAC_EDGE_IP_DEFAULT" true 2>/dev/null; then
            # Render Pi xml via atomic tmp+rename. The remote shell uses set -e
            # so any failure (missing template, sed error, mv error) propagates
            # back as a non-zero SSH exit code and we won't update the stamp.
            if ssh -o ConnectTimeout=5 -o BatchMode=yes "pi@$ROVAC_EDGE_IP_DEFAULT" "
                set -e
                test -f '$_ROVAC_PI_TEMPLATE' || { echo 'Pi template missing: $_ROVAC_PI_TEMPLATE' >&2; exit 10; }
                _tmp=\$(mktemp '${_ROVAC_PI_XML}.tmp.XXXXXX')
                sed 's|__MAC_IP__|${ROVAC_MAC_IP_DEFAULT}|g' '$_ROVAC_PI_TEMPLATE' > \"\$_tmp\"
                mv -f \"\$_tmp\" '$_ROVAC_PI_XML'
            " 2>&1; then
                # Stamp update happens BEFORE the background restart. The restart
                # is fire-and-forget; treating it as required would block the
                # shell sourcing for ~10s on every IP change.
                echo "$ROVAC_MAC_IP_DEFAULT" > "$_ROVAC_IP_STAMP"
                ssh -o ConnectTimeout=3 -o BatchMode=yes "pi@$ROVAC_EDGE_IP_DEFAULT" \
                    "sudo systemctl restart rovac-edge.target" 2>/dev/null &
                echo "  Mac IP changed: ${_ROVAC_LAST_IP:-unknown} → $ROVAC_MAC_IP_DEFAULT (synced to Pi, restarting edge services)"
            else
                echo "  Mac IP changed: ${_ROVAC_LAST_IP:-unknown} → $ROVAC_MAC_IP_DEFAULT (Mac local config updated; Pi sync FAILED — will retry next source)"
            fi
        else
            echo "  Mac IP changed: ${_ROVAC_LAST_IP:-unknown} → $ROVAC_MAC_IP_DEFAULT (Mac local config updated; Pi unreachable — will retry next source)"
        fi
        unset _ROVAC_PI_XML _ROVAC_PI_TEMPLATE
    fi
    unset _ROVAC_IP_STAMP _ROVAC_LAST_IP
fi

echo "ROS2 Environment: DOMAIN=$ROS_DOMAIN_ID, RMW=${RMW_IMPLEMENTATION:-unset}, LOCAL_IP=$ROVAC_LOCAL_IP, REMOTE_IP=$ROVAC_REMOTE_IP"
