#!/bin/bash
#
# ROVAC Controller Supervisor (macOS)
#
# Runs joy_node + joy_mapper and restarts them if either crashes.
# Intended to be launched by launchd (LaunchAgent) for persistence across reboots.
#

set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROVAC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

LOG_PREFIX="[ROVAC_CONTROLLER]"

log() {
  # ISO-8601-ish timestamp
  echo "$(date '+%Y-%m-%dT%H:%M:%S%z') $LOG_PREFIX $*"
}

cleanup_children() {
  if [ -n "${JOY_PID:-}" ] && kill -0 "$JOY_PID" 2>/dev/null; then
    kill "$JOY_PID" 2>/dev/null || true
  fi
  if [ -n "${MAPPER_PID:-}" ] && kill -0 "$MAPPER_PID" 2>/dev/null; then
    kill "$MAPPER_PID" 2>/dev/null || true
  fi
  # Give them a moment to exit cleanly
  sleep 0.5
  if [ -n "${JOY_PID:-}" ] && kill -0 "$JOY_PID" 2>/dev/null; then
    kill -9 "$JOY_PID" 2>/dev/null || true
  fi
  if [ -n "${MAPPER_PID:-}" ] && kill -0 "$MAPPER_PID" 2>/dev/null; then
    kill -9 "$MAPPER_PID" 2>/dev/null || true
  fi
}

cleanup() {
  log "Shutting down..."
  cleanup_children
}

trap cleanup EXIT INT TERM

kill_strays() {
  # Ensure we don't end up with duplicate controller stacks if something was started manually.
  pkill -f "ros2 run joy joy_node.*joy:=/tank/joy" 2>/dev/null || true
  pkill -f "$ROVAC_DIR/scripts/joy_mapper_node.py" 2>/dev/null || true
}

CONDA_BIN="/opt/homebrew/bin/conda"
if [ ! -x "$CONDA_BIN" ]; then
  log "ERROR: conda not found at $CONDA_BIN"
  exit 1
fi

# Bring up ROS2 + ROVAC env for this process.
eval "$("$CONDA_BIN" shell.bash hook)"
conda activate ros_jazzy

if [ ! -f "$ROVAC_DIR/config/ros2_env.sh" ]; then
  log "ERROR: missing $ROVAC_DIR/config/ros2_env.sh"
  exit 1
fi
source "$ROVAC_DIR/config/ros2_env.sh"

ROVAC_PYTHON="${CONDA_PREFIX}/bin/python3"
if [ ! -x "$ROVAC_PYTHON" ]; then
  ROVAC_PYTHON="${CONDA_PREFIX}/bin/python"
fi
if [ ! -x "$ROVAC_PYTHON" ]; then
  log "ERROR: could not find conda python in ${CONDA_PREFIX}/bin"
  exit 1
fi

# Controller selection
JOY_ID="${JOY_ID:-0}"
JOY_AUTOREPEAT="${JOY_AUTOREPEAT:-20.0}"
JOY_DEADZONE="${JOY_DEADZONE:-0.05}"

JOY_LOG="${JOY_LOG:-/tmp/joy_node.log}"
MAPPER_LOG="${MAPPER_LOG:-/tmp/joy_mapper.log}"

JOY_CMD=(
  "${CONDA_PREFIX}/bin/ros2" run joy joy_node --ros-args
  -p "device_id:=${JOY_ID}"
  -p "autorepeat_rate:=${JOY_AUTOREPEAT}"
  -p "deadzone:=${JOY_DEADZONE}"
  -r "joy:=/tank/joy"
  -r "__node:=joy_node"
)

MAPPER_CMD=(
  "$ROVAC_PYTHON" "$ROVAC_DIR/scripts/joy_mapper_node.py"
)

log "Starting controller supervisor (JOY_ID=$JOY_ID)"

backoff_sec=1
max_backoff_sec=10

while true; do
  kill_strays

  log "Launching joy_node..."
  cycle_start_epoch="$(date +%s)"
  "${JOY_CMD[@]}" >>"$JOY_LOG" 2>&1 &
  JOY_PID=$!

  # Give joy_node a moment to start publishing before mapper logs its rest state.
  sleep 0.5

  log "Launching joy_mapper..."
  "${MAPPER_CMD[@]}" >>"$MAPPER_LOG" 2>&1 &
  MAPPER_PID=$!

  # Monitor: restart both if either exits.
  while true; do
    if ! kill -0 "$JOY_PID" 2>/dev/null; then
      log "joy_node exited; restarting stack"
      break
    fi
    if ! kill -0 "$MAPPER_PID" 2>/dev/null; then
      log "joy_mapper exited; restarting stack"
      break
    fi
    sleep 0.5
  done

  # Cleanup and restart
  cleanup_children || true
  unset JOY_PID MAPPER_PID || true

  cycle_runtime_sec="$(( $(date +%s) - cycle_start_epoch ))"
  if [ "$cycle_runtime_sec" -lt 3 ]; then
    if [ "$backoff_sec" -lt "$max_backoff_sec" ]; then
      backoff_sec="$(( backoff_sec * 2 ))"
      if [ "$backoff_sec" -gt "$max_backoff_sec" ]; then
        backoff_sec="$max_backoff_sec"
      fi
    fi
    log "Stack exited quickly (${cycle_runtime_sec}s); backing off ${backoff_sec}s (is the controller connected?)"
  else
    backoff_sec=1
  fi

  sleep "$backoff_sec"
done
