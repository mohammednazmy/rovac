#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[gen_compile_commands_ros2] workspace: $ROOT"

if ! command -v colcon >/dev/null 2>&1; then
  echo "ERROR: colcon not found in PATH. Install with: pipx install colcon-core --include-deps" >&2
  exit 1
fi

if [[ -z "${ROS_DISTRO:-}" ]]; then
  cat >&2 <<'TXT'
WARNING: ROS_DISTRO is not set. That usually means you haven't sourced a ROS2 environment.

Typical fixes:
- If you installed ROS2 via a setup script, run: source /opt/ros/<distro>/setup.bash
- If you use a conda/robostack ROS2 env, activate it first, then re-run this script.
- If you use Docker, run the build inside the container.

I can still attempt a build, but it may fail due to missing ament/cmake packages.
TXT
fi

# Prefer a dedicated build directory for clangd artifacts
BUILD_DIR="${BUILD_DIR:-build}"
INSTALL_DIR="${INSTALL_DIR:-install}"
LOG_DIR="${LOG_DIR:-log}"

echo "[gen_compile_commands_ros2] running colcon build (this may take a while)"

# Try to ensure compile_commands are generated for CMake packages.
# For mixed packages, bear is often best; use if available.
if command -v bear >/dev/null 2>&1; then
  echo "[gen_compile_commands_ros2] using bear to capture compilation database"
  bear --append --output compile_commands.json -- \
    colcon build \
      --build-base "$BUILD_DIR" \
      --install-base "$INSTALL_DIR" \
      --log-base "$LOG_DIR" \
      --cmake-args -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
else
  echo "[gen_compile_commands_ros2] bear not found; relying on CMake export flags"
  colcon build \
    --build-base "$BUILD_DIR" \
    --install-base "$INSTALL_DIR" \
    --log-base "$LOG_DIR" \
    --cmake-args -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

  # If colcon didn't produce a unified compile_commands.json, try to link one.
  if [[ ! -f compile_commands.json ]]; then
    CANDIDATE=$(find "$BUILD_DIR" -maxdepth 3 -type f -name compile_commands.json | head -n 1 || true)
    if [[ -n "$CANDIDATE" ]]; then
      echo "[gen_compile_commands_ros2] linking $CANDIDATE -> $ROOT/compile_commands.json"
      ln -sf "$CANDIDATE" "$ROOT/compile_commands.json"
    else
      echo "[gen_compile_commands_ros2] WARNING: no compile_commands.json found under $BUILD_DIR" >&2
    fi
  fi
fi

echo "[gen_compile_commands_ros2] done"
if [[ -f compile_commands.json ]]; then
  echo "[gen_compile_commands_ros2] wrote: $ROOT/compile_commands.json"
else
  echo "[gen_compile_commands_ros2] WARNING: compile_commands.json not created" >&2
fi
