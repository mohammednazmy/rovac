# Installation Guide

Complete setup instructions for the stereo camera system on both Raspberry Pi and Mac.

## Prerequisites

### Raspberry Pi 5

| Requirement | Version |
|-------------|---------|
| OS | Ubuntu 24.04 (arm64) |
| ROS2 | Jazzy |
| Python | 3.12+ |
| RAM | 4GB+ recommended |
| Storage | 16GB+ SD card |

### MacBook Pro (Development)

| Requirement | Version |
|-------------|---------|
| OS | macOS 14+ |
| Conda | Miniforge/Miniconda |
| Python | 3.12+ |
| ROS2 | Jazzy (via conda) |

## Hardware Setup

### Camera Connection

1. **Connect cameras to Pi USB ports**
   - Left camera → USB port closest to ethernet
   - Right camera → USB port next to left

2. **Verify camera detection**
   ```bash
   ls /dev/video*
   # Should show: /dev/video0 /dev/video1 ...

   v4l2-ctl --list-devices
   # Verify camera device mapping
   ```

3. **Test cameras individually**
   ```bash
   # Test left camera
   ffplay -f v4l2 -input_format mjpeg -video_size 1280x720 /dev/video1

   # Test right camera
   ffplay -f v4l2 -input_format mjpeg -video_size 1280x720 /dev/video0
   ```

### Camera Mounting

- Cameras should be mounted horizontally, ~103mm apart (baseline)
- Both cameras rotated 90° clockwise
- Cameras facing forward (same direction as robot motion)

## Raspberry Pi Setup

### 1. ROS2 Jazzy Installation

```bash
# Add ROS2 repository
sudo apt update
sudo apt install -y software-properties-common curl
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# Install ROS2 Jazzy
sudo apt update
sudo apt install -y ros-jazzy-ros-base ros-jazzy-cv-bridge ros-jazzy-image-transport
```

### 2. Python Dependencies

```bash
# System packages
sudo apt install -y python3-pip python3-opencv python3-numpy libopencv-dev

# Python packages
pip3 install --user opencv-contrib-python numpy
```

### 3. CycloneDDS Setup

```bash
# Install CycloneDDS
sudo apt install -y ros-jazzy-rmw-cyclonedds-cpp

# Create config directory
mkdir -p ~/ros2_config

# Create CycloneDDS config
cat > ~/ros2_config/cyclonedds_pi.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8" ?>
<CycloneDDS xmlns="https://cdds.io/config">
  <Domain id="any">
    <General>
      <AllowMulticast>false</AllowMulticast>
      <MaxMessageSize>65500B</MaxMessageSize>
    </General>
    <Discovery>
      <Peers>
        <Peer address="192.168.1.104"/>
        <Peer address="192.168.1.200"/>
      </Peers>
      <ParticipantIndex>auto</ParticipantIndex>
    </Discovery>
  </Domain>
</CycloneDDS>
EOF
```

### 4. Clone Repository

```bash
mkdir -p ~/robots/rovac/hardware
cd ~/robots/rovac/hardware
git clone <repository-url> stereo_cameras
cd stereo_cameras
```

### 5. Install Systemd Services

```bash
# Make install script executable
chmod +x install_stereo_services.sh

# Install services
./install_stereo_services.sh

# Enable auto-start
sudo systemctl enable rovac-edge-stereo.target

# Start services
sudo systemctl start rovac-edge-stereo.target
```

### 6. Environment Setup

Add to `~/.bashrc`:

```bash
# ROS2 Jazzy
source /opt/ros/jazzy/setup.bash

# CycloneDDS
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file://$HOME/ros2_config/cyclonedds_pi.xml

# ROS2 Domain
export ROS_DOMAIN_ID=42

# Local IP
export ROS_IP=192.168.1.200
```

## Mac Setup

### 1. Install Miniforge

```bash
# Download and install Miniforge
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash Miniforge3-$(uname)-$(uname -m).sh

# Restart terminal or source
source ~/.zshrc
```

### 2. Create ROS2 Environment

```bash
# Create conda environment
conda create -n ros_jazzy python=3.12 -y
conda activate ros_jazzy

# Install ROS2 packages
conda install -c conda-forge -c robostack-staging ros-jazzy-ros-base ros-jazzy-cv-bridge -y

# Install CycloneDDS
conda install -c conda-forge -c robostack-staging ros-jazzy-rmw-cyclonedds-cpp -y
```

### 3. Python Dependencies

```bash
conda activate ros_jazzy

# Core packages
pip install opencv-python opencv-contrib-python numpy

# Dashboard packages
pip install fastapi uvicorn jinja2 python-multipart websockets
```

### 4. CycloneDDS Configuration

```bash
# Create config directory
mkdir -p ~/robots/rovac/config

# Create CycloneDDS config
cat > ~/robots/rovac/config/cyclonedds_mac.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8" ?>
<CycloneDDS xmlns="https://cdds.io/config">
  <Domain id="any">
    <General>
      <AllowMulticast>false</AllowMulticast>
      <MaxMessageSize>65500B</MaxMessageSize>
    </General>
    <Discovery>
      <Peers>
        <Peer address="192.168.1.104"/>
        <Peer address="192.168.1.200"/>
      </Peers>
      <ParticipantIndex>auto</ParticipantIndex>
    </Discovery>
  </Domain>
</CycloneDDS>
EOF
```

### 5. Environment Script

Create `~/robots/rovac/config/ros2_env.sh`:

```bash
#!/bin/bash
# ROS2 Environment Setup for Mac

# Activate conda environment
source /opt/homebrew/Caskroom/miniforge/base/bin/activate ros_jazzy

# ROS2 settings
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file://$HOME/robots/rovac/config/cyclonedds_mac.xml
export ROS_DOMAIN_ID=42

# Network
export ROS_IP=192.168.1.104

echo "ROS2 Environment: DOMAIN=$ROS_DOMAIN_ID, RMW=$RMW_IMPLEMENTATION"
```

### 6. Clone Repository

```bash
mkdir -p ~/robots/rovac/hardware
cd ~/robots/rovac/hardware
git clone <repository-url> stereo_cameras
```

## Verification

### Test Pi Services

```bash
# Check service status
sudo systemctl status rovac-edge-stereo.target
sudo systemctl status rovac-edge-stereo-depth.service

# Check logs
journalctl -u rovac-edge-stereo-depth.service -f
```

### Test ROS2 Communication

On Mac:
```bash
# Source environment
source ~/robots/rovac/config/ros2_env.sh

# Wait for DDS discovery (3-5 seconds)
sleep 5

# List topics
ros2 topic list

# Expected output:
# /stereo/depth/image_raw
# /stereo/left/image_raw
# /obstacles
# ...

# Echo depth topic
ros2 topic hz /stereo/depth/image_raw
```

### Test Dashboard

```bash
# Source environment
source ~/robots/rovac/config/ros2_env.sh

# Start dashboard
cd ~/robots/rovac/hardware/stereo_cameras
python3 dashboard/server.py --ros2 --port 8080

# Open browser to http://localhost:8080
```

## Network Configuration

### Static IP Setup (Pi)

Edit `/etc/netplan/01-netcfg.yaml`:

```yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
  wifis:
    wlan0:
      dhcp4: no
      addresses:
        - 192.168.1.200/24
      gateway4: 192.168.1.104
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
      access-points:
        "YourNetwork":
          password: "YourPassword"
```

Apply:
```bash
sudo netplan apply
```

### Mac Network Bridge

The Mac should be on the same `192.168.1.x` subnet as the Pi (via direct Ethernet).

## Troubleshooting Installation

### Pi: Camera Not Found

```bash
# Check USB devices
lsusb

# Check video devices
ls -la /dev/video*

# Check kernel modules
lsmod | grep uvc

# Reload module if needed
sudo modprobe -r uvcvideo
sudo modprobe uvcvideo
```

### Mac: Conda Environment Issues

```bash
# Reinitialize conda
conda init zsh  # or bash

# Recreate environment
conda env remove -n ros_jazzy
conda create -n ros_jazzy python=3.12 -y
conda activate ros_jazzy
# ... reinstall packages
```

### ROS2: No Topics Visible

1. Check domain ID matches on both machines:
   ```bash
   echo $ROS_DOMAIN_ID  # Should be 42
   ```

2. Check CycloneDDS config:
   ```bash
   echo $CYCLONEDDS_URI
   cat $CYCLONEDDS_URI  # Remove file:// prefix
   ```

3. Test network connectivity:
   ```bash
   ping 192.168.1.200  # From Mac
   ping 192.168.1.104  # From Pi
   ```

4. Wait for DDS discovery (5-10 seconds on first connection)

### Dashboard: Connection Failed

1. Verify ROS2 topics exist:
   ```bash
   ros2 topic list | grep stereo
   ```

2. Check dashboard is using ROS2 mode:
   ```bash
   python3 dashboard/server.py --ros2  # Not simulated mode
   ```

3. Check API endpoint:
   ```bash
   curl http://localhost:8080/api/status
   ```

## Uninstallation

### Pi: Remove Services

```bash
# Stop and disable services
sudo systemctl stop rovac-edge-stereo.target
sudo systemctl disable rovac-edge-stereo.target

# Remove service files
sudo rm /etc/systemd/system/rovac-edge-stereo*.service
sudo rm /etc/systemd/system/rovac-edge-stereo*.target
sudo systemctl daemon-reload
```

### Mac: Remove Environment

```bash
# Remove conda environment
conda env remove -n ros_jazzy

# Remove config files (optional)
rm -rf ~/robots/rovac/config/cyclonedds_mac.xml
```
