ros2 node list
ros2 daemon stop
ros2 topic list

sudo systemctl restart rovac-edge-rplidar-c1


# ROVAC ROS2 Reference Card

Quick-reference for working with the ROVAC robot from either the Mac (brain) or Pi (edge).

---

## 1. Environment Setup

### Mac (Brain)

```bash
# Activate conda + ROS2 environment (ALWAYS do this first in any new terminal)

conda activate ros_jazzy
source ~/robots/rovac/config/ros2_env.sh

# What ros2_env.sh sets for you:
#   ROS_DOMAIN_ID=42
#   RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
#   CYCLONEDDS_URI=file://.../cyclonedds_mac.xml
```

**Important Mac quirks:**
- Always use `--no-daemon` with `ros2 topic list` (the daemon hangs with CycloneDDS)
- `ros2 topic hz` does NOT accept `--no-daemon` — just run it normally
- CycloneDDS unicast discovery takes 5-8 seconds — be patient

### Pi (Edge) — via SSH

```bash
ssh pi@192.168.1.200    # password: pi

# Most ROS2 commands on Pi need the full environment:
source /opt/ros/jazzy/setup.bash
source ~/robots/rovac/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file:///home/pi/robots/rovac/config/cyclonedds_pi.xml

# Or use ros2_env.sh (auto-detects Pi vs Mac):
source ~/robots/rovac/config/ros2_env.sh
```

**Why all the exports?** CycloneDDS with unicast requires explicit peer configuration.
Without `CYCLONEDDS_URI`, the DDS layer won't know to talk to the other machine,
and even local topics may not all show up.

### ESP-IDF (Firmware Development Only)

```bash
# NEVER in the same terminal as conda ros_jazzy — they conflict
source ~/esp/esp-idf-v5.2/export.sh
```

---

## 2. Systemd Services (Pi Edge)

All edge services are managed by systemd on the Pi. They auto-start on boot via `rovac-edge.target`.

### Service Commands

```bash
# Check the overall edge stack
sudo systemctl status rovac-edge.target

# Check a specific service
sudo systemctl status rovac-edge-motor-driver
sudo systemctl status rovac-edge-rplidar-c1
sudo systemctl status rovac-edge-mux

# Restart a single service (does NOT affect others)
sudo systemctl restart rovac-edge-rplidar-c1

# Stop / start a service
sudo systemctl stop rovac-edge-rplidar-c1
sudo systemctl start rovac-edge-rplidar-c1

# View live logs for a service
sudo journalctl -u rovac-edge-motor-driver -f

# View recent logs (last 5 minutes)
sudo journalctl -u rovac-edge-rplidar-c1 --since "5 min ago" --no-pager

# Restart the entire edge stack
sudo systemctl restart rovac-edge.target

# Reinstall/update all service files after editing them
cd ~/robots/rovac && ./scripts/install_pi_systemd.sh install
```

### Active Services

| Service | What it does | Publishes |
|---------|-------------|-----------|
| `rovac-edge-motor-driver` | C++ USB serial driver (ESP32) | `/odom`, `/tf`, `/imu/data`, `/diagnostics` |
| `rovac-edge-rplidar-c1` | RPLIDAR C1 DTOF scanner | `/scan` |
| `rovac-edge-mux` | Velocity priority mux | `/cmd_vel` (output) |
| `rovac-edge-tf` | robot_state_publisher | `/tf_static`, `/robot_description` |
| `rovac-edge-map-tf` | map→odom static TF | `/tf` (map frame) |
| `rovac-edge-rosbridge` | WebSocket bridge (:9090) | Bridges phone sensor topics |
| `rovac-edge-obstacle` | Obstacle avoidance | `/cmd_vel_obstacle` |
| `rovac-edge-ps2-joy` | PS2 controller input | `/joy` |
| `rovac-edge-ps2-mapper` | Joy → velocity | `/cmd_vel_joy` |
| `rovac-edge-supersensor` | HC-SR04 ultrasonic | `/super_sensor/*` |
| `rovac-edge-ekf` | Extended Kalman Filter | **DISABLED** — run from Mac |

---

## 3. ROS2 Topic Commands

### Listing & Discovery

```bash
# List all visible topics
ros2 topic list --no-daemon          # Mac (always use --no-daemon)
ros2 topic list                      # Pi

# List topics with their message types
ros2 topic list -t --no-daemon
```

### Checking Data Flow

```bash
# Check publishing rate (most useful diagnostic command)
ros2 topic hz /scan                  # Expect ~10 Hz
ros2 topic hz /odom                  # Expect ~20 Hz
ros2 topic hz /imu/data              # Expect ~20 Hz
ros2 topic hz /cmd_vel               # Only when driving

# See one message from a topic
ros2 topic echo /odom --once
ros2 topic echo /diagnostics --once
ros2 topic echo /scan --once

# Watch messages continuously (Ctrl+C to stop)
ros2 topic echo /imu/data
```

### Topic Details

```bash
# Show message type for a topic
ros2 topic type /scan
# → sensor_msgs/msg/LaserScan

# Show QoS, publishers, and subscribers
ros2 topic info /scan -v

# Show the fields in a message type
ros2 interface show sensor_msgs/msg/LaserScan
ros2 interface show nav_msgs/msg/Odometry
ros2 interface show sensor_msgs/msg/Imu
```

### Publishing Test Messages

```bash
# Publish a velocity command (ALWAYS use mux input topics, NEVER /cmd_vel directly)
# ALWAYS use --times N (not --rate alone — stale publishers override teleop!)
ros2 topic pub /cmd_vel_teleop geometry_msgs/msg/Twist \
  "{linear: {x: 0.1}, angular: {z: 0.0}}" --times 5

# Stop motors
ros2 topic pub /cmd_vel_teleop geometry_msgs/msg/Twist \
  "{linear: {x: 0.0}, angular: {z: 0.0}}" --times 3
```

---

## 4. ROS2 Node Commands

```bash
# List all running nodes
ros2 node list

# Get info about a specific node (publishers, subscribers, services)
ros2 node info /motor_driver_node
ros2 node info /rplidar_node

# List parameters for a node
ros2 param list /motor_driver_node

# Get a parameter value
ros2 param get /motor_driver_node publish_tf

# Set a parameter at runtime
ros2 param set /motor_driver_node publish_tf false
```

---

## 5. TF (Transforms)

```bash
# List all active TF frames
ros2 run tf2_tools view_frames        # Generates frames.pdf

# Check a specific transform
ros2 run tf2_ros tf2_echo base_link laser_frame
ros2 run tf2_ros tf2_echo odom base_link

# Monitor TF publishing rate
ros2 topic hz /tf
```

### ROVAC TF Tree

```
map → odom → base_link → laser_frame
                       → imu_link
                       → (wheel frames)
```

- `map → odom`: Published by SLAM or static TF service
- `odom → base_link`: Published by motor_driver_node (or EKF when running)
- `base_link → laser_frame`: Published by robot_state_publisher (from URDF)

**TF gotcha:** If you see the robot jumping in Foxglove, check that only ONE node
publishes `odom → base_link`. When EKF is running, motor_driver must have `publish_tf: false`.

---

## 6. Key Topics Reference

### Motor System (from ESP32 via motor_driver_node)

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/odom` | Odometry | 20 Hz | Dead-reckoning from encoder ticks |
| `/tf` | TFMessage | 20 Hz | odom→base_link (disabled when EKF runs) |
| `/imu/data` | Imu | 20 Hz | BNO055 9-axis orientation + gyro + accel |
| `/diagnostics` | DiagnosticArray | 1 Hz | ESP32 health: heap, PID, IMU calibration |
| `/cmd_vel` | Twist | varies | Motor commands (INPUT from mux) |

### Sensors

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/scan` | LaserScan | ~10 Hz | RPLIDAR C1 (~500 points, 16m range) |
| `/phone/imu` | Imu | 50 Hz | Phone IMU via rosbridge |
| `/phone/gps/fix` | NavSatFix | 1 Hz | Phone GPS via rosbridge |

### Velocity Mux (priority order — highest wins)

| Input Topic | Priority | Timeout | Source |
|-------------|----------|---------|--------|
| `/cmd_vel_teleop` | 1 (highest) | 0.5s | Keyboard teleop |
| `/cmd_vel_joy` | 2 | 1.0s | PS2 joystick |
| `/cmd_vel_obstacle` | 3 | 0.5s | Obstacle avoidance |
| `/cmd_vel_smoothed` | 4 (lowest) | 1.0s | Nav2 autonomous |

---

## 7. Startup Checklist (After Pi Reboot)

```bash
ssh pi@192.168.1.200

# 1. Are all services up?
sudo systemctl status rovac-edge.target

# 2. Are USB devices connected?
ls -la /dev/esp32_motor /dev/rplidar_c1

# 3. Is the motor driver healthy?
sudo systemctl status rovac-edge-motor-driver --no-pager -l

# 4. Is the LIDAR healthy?
sudo systemctl status rovac-edge-rplidar-c1 --no-pager -l

# 5. Verify data is actually flowing (need full DDS env)
source ~/robots/rovac/config/ros2_env.sh
ros2 topic hz /odom          # Expect ~20 Hz
ros2 topic hz /scan           # Expect ~10 Hz
ros2 topic hz /imu/data       # Expect ~20 Hz

# 6. If any topic shows no data, restart that service
sudo systemctl restart rovac-edge-rplidar-c1    # for /scan
sudo systemctl restart rovac-edge-motor-driver   # for /odom, /imu
```

---

## 8. Mac-Side Launch Commands

```bash
# Activate environment first
conda activate ros_jazzy
source ~/robots/rovac/config/ros2_env.sh

# Keyboard teleop (auto-SSHes to Pi for lowest latency)
python3 ~/robots/rovac/scripts/keyboard_teleop.py

# SLAM mapping
./scripts/mac_brain_launch.sh slam

# Navigation with existing map
./scripts/mac_brain_launch.sh nav ~/maps/house.yaml

# Foxglove visualization
./scripts/mac_brain_launch.sh foxglove

# Command Center TUI
~/robots/rovac/scripts/command_center/launch.sh
```

---

## 9. Common Troubleshooting

### "I see zero topics"
```bash
# Did you source the environment?
echo $ROS_DOMAIN_ID        # Should be 42
echo $RMW_IMPLEMENTATION   # Should be rmw_cyclonedds_cpp
echo $CYCLONEDDS_URI       # Should point to a .xml file

# On Mac, always use --no-daemon
ros2 topic list --no-daemon

# Wait 5-8 seconds — CycloneDDS unicast discovery is slow
```

### "Topic exists but no data" (hz shows nothing)
```bash
# Check the service is actually running
sudo systemctl status rovac-edge-<service-name>

# Check logs for errors
sudo journalctl -u rovac-edge-<service-name> --since "5 min ago" --no-pager

# Restart the service
sudo systemctl restart rovac-edge-<service-name>

# Re-check
ros2 topic hz /<topic-name>
```

### "Motors won't move from teleop"
```bash
# Check for stale publishers hogging the mux
ssh pi@192.168.1.200 'pgrep -a -f "ros2 topic pub.*cmd_vel"'
# Kill any found — they override your teleop commands

# Verify mux is running
ssh pi@192.168.1.200 'systemctl is-active rovac-edge-mux'

# Check the motor power switch is ON
# Check battery voltage > 8V (TB67H450FNG UVLO lockout below 8V)
```

### "Robot position jumping in Foxglove"
```bash
# Two things publishing odom→base_link TF = jumping
# Ensure only ONE is active:
ros2 param get /motor_driver_node publish_tf    # Should be false when EKF runs

# Make sure only ONE EKF instance is running (Pi service should be DISABLED)
ssh pi@192.168.1.200 'systemctl is-active rovac-edge-ekf'   # Should be "inactive"
```

### "USB device not found"
```bash
# Check what's connected
ls -la /dev/esp32_motor /dev/rplidar_c1
lsusb

# If missing: unplug USB, wait 5s, replug
# Check dmesg for USB errors
sudo dmesg | tail -20

# CH340 (ESP32) can be finicky — try different port/cable
```

---

## 10. Useful ROS2 One-Liners

```bash
# Record a bag file (saves topic data for replay)
ros2 bag record /scan /odom /imu/data /tf -o my_recording

# Play back a bag file
ros2 bag play my_recording

# Check what's in a bag file
ros2 bag info my_recording

# Kill the ROS2 daemon (if things seem stuck on Mac)
ros2 daemon stop

# See all ROS2 packages installed
ros2 pkg list

# Run a specific node manually (for debugging)
ros2 run rplidar_ros rplidar_node --ros-args -p serial_port:=/dev/rplidar_c1
```
