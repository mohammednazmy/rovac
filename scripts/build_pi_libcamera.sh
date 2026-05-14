#!/bin/bash
#
# Build + install Pi-patched libcamera 0.5.2 and camera_ros 0.6.0 on a Pi 5
# running Ubuntu 24.04 (Noble). REQUIRED for OV5647 stereo cameras: Ubuntu's
# stock libcamera 0.2.0 and OSRF's ros-jazzy-libcamera 0.7.0 both fail with
# "Unable to acquire a CFE instance" — their pisp pipeline handler ABI doesn't
# match the Pi-tree kernel (6.8.0-1053-raspi). The Pi maintainers' v0.5.2 fork
# is paired with the matching kernel CFE driver API.
#
# Result of running this script:
#   /opt/rpi-libcamera/                      Pi-patched libcamera install
#   /etc/ld.so.conf.d/rpi-libcamera.conf     dynamic linker config
#   ~/robots/rovac/ros2_ws/install/camera_ros  camera_ros built from source
#   /boot/firmware/config.txt                explicit ov5647 dtoverlays
#
# This script is IDEMPOTENT — safe to re-run; it skips steps that are done.
#
# Run AS the regular pi user (uses sudo where needed):
#   bash ~/robots/rovac/scripts/build_pi_libcamera.sh

set -euo pipefail

# Pinned upstream versions. Bump when the Pi kernel is updated and the matching
# libcamera tag changes (check https://github.com/raspberrypi/libcamera/tags).
LIBCAMERA_TAG="v0.5.2+rpt20250903"
LIBCAMERA_REPO="https://github.com/raspberrypi/libcamera.git"
LIBCAMERA_PREFIX="/opt/rpi-libcamera"
CAMERA_ROS_TAG="0.6.0"
CAMERA_ROS_REPO="https://github.com/christianrauch/camera_ros.git"

ROVAC_DIR="${ROVAC_DIR:-$HOME/robots/rovac}"
WORK_DIR="${WORK_DIR:-$HOME/build}"

step()       { echo; echo "==> $1"; }
done_step()  { echo "    [DONE] $1"; }
skip_step()  { echo "    [SKIP] $1"; }

REBOOT_NEEDED=0

# ----------------------------------------------------------------------------
# 1. Install build dependencies
# ----------------------------------------------------------------------------
step "[1/6] Install libcamera build dependencies"
sudo apt-get install -y \
  meson ninja-build pkg-config \
  python3-yaml python3-ply python3-jinja2 \
  libyaml-dev libudev-dev libssl-dev libgnutls28-dev \
  libdrm-dev libxml2-dev libpython3-dev libsystemd-dev \
  libevent-dev libboost-dev libfmt-dev libgtest-dev \
  libcap-dev libtiff-dev libexif-dev \
  libavcodec-dev libavformat-dev libavutil-dev libswresample-dev libswscale-dev \
  >/dev/null
done_step "build deps"

# ----------------------------------------------------------------------------
# 2. Ensure /boot/firmware/config.txt has explicit ov5647 dtoverlays.
# Pi 5 needs per-port dtoverlays for the libcamera pisp pipeline to acquire
# each CFE — camera_auto_detect=1 alone is insufficient on Ubuntu Noble.
# ----------------------------------------------------------------------------
step "[2/6] Configure /boot/firmware/config.txt for dual OV5647 cameras"
if grep -q "^dtoverlay=ov5647,cam0" /boot/firmware/config.txt; then
  skip_step "config.txt already has explicit ov5647 dtoverlays"
else
  sudo cp /boot/firmware/config.txt "/boot/firmware/config.txt.bak.$(date +%Y%m%d-%H%M%S)"
  sudo sed -i "s|^camera_auto_detect=1|camera_auto_detect=0|" /boot/firmware/config.txt
  sudo bash -c 'cat >> /boot/firmware/config.txt <<EOF

# ROVAC stereo cameras: dual OV5647 NoIR on Pi 5 CAM0+CAM1
# Explicit per-port dtoverlays are required so libcamera pisp pipeline handler
# can acquire each Camera Front-End (CFE) device independently. The original
# camera_auto_detect=1 is insufficient for dual-CSI Pi 5 on Ubuntu Noble.
dtoverlay=ov5647,cam0
dtoverlay=ov5647,cam1
EOF'
  done_step "config.txt updated"
  REBOOT_NEEDED=1
fi

# ----------------------------------------------------------------------------
# 3. Build + install Pi-patched libcamera 0.5.2
# ----------------------------------------------------------------------------
step "[3/6] Build + install Pi-patched libcamera $LIBCAMERA_TAG"
if [ -f "$LIBCAMERA_PREFIX/lib/aarch64-linux-gnu/libcamera.so.0.5.2" ]; then
  skip_step "libcamera already installed at $LIBCAMERA_PREFIX"
else
  mkdir -p "$WORK_DIR"
  cd "$WORK_DIR"
  if [ -d libcamera ]; then
    cd libcamera
    git fetch --tags origin
  else
    git clone "$LIBCAMERA_REPO"
    cd libcamera
  fi
  git checkout "$LIBCAMERA_TAG"

  rm -rf build
  meson setup build \
    --buildtype=release \
    --prefix="$LIBCAMERA_PREFIX" \
    -Dpipelines=rpi/vc4,rpi/pisp \
    -Dipas=rpi/vc4,rpi/pisp \
    -Dv4l2=true \
    -Dgstreamer=disabled \
    -Dtest=false \
    -Dlc-compliance=disabled \
    -Dcam=enabled \
    -Dqcam=disabled \
    -Ddocumentation=disabled \
    -Dpycamera=disabled

  ninja -C build -j"$(nproc)"
  sudo ninja -C build install
  done_step "libcamera $LIBCAMERA_TAG built + installed to $LIBCAMERA_PREFIX"
fi

# ----------------------------------------------------------------------------
# 4. Configure ld.so so the system dynamic linker finds Pi libcamera
# ----------------------------------------------------------------------------
step "[4/6] Configure ld.so for $LIBCAMERA_PREFIX"
echo "$LIBCAMERA_PREFIX/lib/aarch64-linux-gnu" \
  | sudo tee /etc/ld.so.conf.d/rpi-libcamera.conf >/dev/null
sudo ldconfig
done_step "ld.so configured"

# ----------------------------------------------------------------------------
# 5. Remove conflicting apt camera_ros (linked against wrong libcamera SONAME)
# ----------------------------------------------------------------------------
step "[5/6] Remove apt ros-jazzy-camera-ros if present (wrong SONAME)"
if dpkg -l ros-jazzy-camera-ros >/dev/null 2>&1; then
  sudo apt-get remove --purge -y ros-jazzy-camera-ros >/dev/null
  sudo apt-get autoremove -y >/dev/null
  done_step "removed apt camera_ros"
else
  skip_step "apt camera_ros not installed"
fi

# ----------------------------------------------------------------------------
# 6. Clone (if needed) + build camera_ros from source against Pi libcamera.
# Note: camera_ros may already be present if `vcs import` was run from
#       external.repos. In that case we just rebuild it.
# ----------------------------------------------------------------------------
step "[6/6] Build camera_ros $CAMERA_ROS_TAG against Pi libcamera"
CAMERA_ROS_DIR="$ROVAC_DIR/ros2_ws/src/camera_ros"
if [ ! -d "$CAMERA_ROS_DIR" ]; then
  echo "    cloning camera_ros (not present via vcs import)..."
  git clone "$CAMERA_ROS_REPO" "$CAMERA_ROS_DIR"
fi
(cd "$CAMERA_ROS_DIR" && git fetch --tags origin && git checkout "$CAMERA_ROS_TAG")

# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
cd "$ROVAC_DIR/ros2_ws"
PKG_CONFIG_PATH="$LIBCAMERA_PREFIX/lib/aarch64-linux-gnu/pkgconfig:${PKG_CONFIG_PATH:-}" \
CMAKE_PREFIX_PATH="$LIBCAMERA_PREFIX:${CMAKE_PREFIX_PATH:-}" \
  colcon build --packages-select camera_ros \
    --cmake-args -DCMAKE_BUILD_TYPE=Release
done_step "camera_ros $CAMERA_ROS_TAG built"

# ----------------------------------------------------------------------------
# Verify
# ----------------------------------------------------------------------------
step "[verify] enumerate cameras via Pi-patched libcamera"
"$LIBCAMERA_PREFIX/bin/cam" --list 2>&1 | tail -10

echo
echo "============================================================"
echo "DONE — Pi libcamera + camera_ros are built and installed."
echo "============================================================"
if [ "$REBOOT_NEEDED" = "1" ]; then
  echo "REBOOT REQUIRED — /boot/firmware/config.txt was updated."
  echo "Run: sudo reboot"
  echo "After reboot, cameras will be claimable via the pisp pipeline."
fi
