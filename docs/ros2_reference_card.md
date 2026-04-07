# ROVAC ROS 2 Reference Card

Quick reference for the current ROVAC runtime.

## Environment Setup

### Mac

```bash
cd ~/robots/rovac
conda activate ros_jazzy
source config/ros2_env.sh
```

Important:

- use `ros2 topic list --no-daemon` on macOS
- do not use `--no-daemon` with `ros2 topic hz`
- give DDS discovery a few seconds after sourcing the environment

### Pi

```bash
ssh pi@192.168.1.200
source /opt/ros/jazzy/setup.bash
source ~/robots/rovac/ros2_ws/install/setup.bash
source ~/robots/rovac/config/ros2_env.sh
```

### ESP-IDF

```bash
source ~/esp/esp-idf-v5.2/export.sh
```

Never source ESP-IDF in the same shell as the ROS conda environment.

## Pi Service Commands

```bash
sudo systemctl status rovac-edge.target
sudo systemctl status rovac-edge-motor-driver.service
sudo systemctl status rovac-edge-rplidar-c1.service
sudo systemctl status rovac-edge-mux.service

sudo systemctl restart rovac-edge.target
sudo systemctl restart rovac-edge-motor-driver.service
sudo systemctl restart rovac-edge-rplidar-c1.service

sudo journalctl -u rovac-edge-motor-driver.service -f
sudo journalctl -u rovac-edge-rplidar-c1.service -n 100 --no-pager
```

## Topic Commands

```bash
ros2 topic list --no-daemon
ros2 topic list -t --no-daemon

ros2 topic hz /odom
ros2 topic hz /imu/data
ros2 topic hz /scan

ros2 topic echo /odom --once
ros2 topic echo /diagnostics --once
ros2 topic echo /rovac/edge/health --once
```

### Safe velocity tests

```bash
ros2 topic pub /cmd_vel_teleop geometry_msgs/msg/Twist \
  "{linear: {x: 0.1}, angular: {z: 0.0}}" --times 5

ros2 topic pub /cmd_vel_teleop geometry_msgs/msg/Twist \
  "{linear: {x: 0.0}, angular: {z: 0.0}}" --times 3
```

Never publish directly to `/cmd_vel`.

## Node And Parameter Commands

```bash
ros2 node list
ros2 node info /motor_driver_node
ros2 node info /ekf_node

ros2 param list /motor_driver_node
ros2 param get /motor_driver_node publish_tf
ros2 param set /motor_driver_node publish_tf false
```

## TF Commands

```bash
ros2 run tf2_tools view_frames
ros2 run tf2_ros tf2_echo odom base_link
ros2 run tf2_ros tf2_echo base_link laser_frame
ros2 topic hz /tf
```

## Build Commands

### Pi ROS workspace

```bash
cd ~/robots/rovac/ros2_ws
colcon build --packages-select rovac_motor_driver tank_description
```

### ESP32 firmware

```bash
cd ~/robots/rovac/hardware/esp32_motor_wireless
idf.py build
idf.py -p /dev/esp32_motor flash
```

## Useful Runtime Topics

| Topic | Expected owner |
|------|-----------------|
| `/odom` | `rovac_motor_driver` |
| `/imu/data` | `rovac_motor_driver` |
| `/diagnostics` | `rovac_motor_driver` |
| `/scan` | `rplidar_ros` |
| `/cmd_vel_teleop` | keyboard teleop |
| `/cmd_vel_joy` | PS2 mapper |
| `/cmd_vel_obstacle` | obstacle avoidance |
| `/cmd_vel_smoothed` | Nav2 |
| `/cmd_vel` | mux output |
| `/odometry/filtered` | EKF when active |

### TF ownership

- `map → odom`: Published by SLAM or static TF service
- `odom → base_link`: Published by motor_driver_node (or EKF when running)
- `base_link → laser_frame`: Published by robot_state_publisher (from URDF)

**TF gotcha:** If you see the robot jumping in Foxglove, check that only ONE node
publishes `odom → base_link`. When EKF is running, motor_driver must have `publish_tf: false`.

## Startup Checklist (After Pi Reboot)

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

## Mac-Side Launch Commands

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

## Common Troubleshooting

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
# Check battery voltage > 8V (TB67H450FNG UVLO lockout below 6.8V)
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

## Useful ROS2 One-Liners

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
