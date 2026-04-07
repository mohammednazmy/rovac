# Robot Bringup Guide

This guide documents the current operator workflow for the USB-serial ESP32 + Pi edge + Mac brain architecture.

## Assumptions

- Pi edge host is reachable at `pi@192.168.1.200`
- Both machines use the same repository checkout path layout
- ROS 2 distro is Jazzy
- DDS is CycloneDDS with unicast peer configuration from `config/ros2_env.sh`

## One-Time Setup

### Pi edge services

```bash
ssh pi@192.168.1.200
cd ~/robots/rovac
./scripts/install_pi_systemd.sh install
```

This installs udev rules and the `rovac-edge.target` service group.

### Optional Mac helpers

If you rely on login-time helper processes, install them explicitly. They are not required for the core runtime path documented here.

## Daily Bringup

### 1. Power the robot

- Verify the battery is charged
- Turn the motor power switch ON
- Wait for the Pi to boot and edge services to come up

### 2. Verify the Pi edge stack

```bash
ssh pi@192.168.1.200 'sudo systemctl status rovac-edge.target'
```

If unit files changed:

```bash
ssh pi@192.168.1.200 'sudo systemctl daemon-reload && sudo systemctl restart rovac-edge.target'
```

### 3. Prepare the Mac environment

```bash
cd ~/robots/rovac
conda activate ros_jazzy
source config/ros2_env.sh
```

Verify:

```bash
echo "$ROS_DOMAIN_ID"
echo "$RMW_IMPLEMENTATION"
echo "$CYCLONEDDS_URI"
```

### 4. Check discovery

```bash
ros2 topic list --no-daemon
```

On macOS, use `--no-daemon` with topic listing. Do not use it with `ros2 topic hz`.

### 5. Start a brain workflow

```bash
./scripts/mac_brain_launch.sh slam-ekf
./scripts/mac_brain_launch.sh slam
./scripts/mac_brain_launch.sh nav ~/maps/house.yaml
./scripts/mac_brain_launch.sh foxglove
```

### 6. Teleoperate

```bash
python3 scripts/keyboard_teleop.py
```

By default the teleop script SSHes to the Pi and publishes to `/cmd_vel_teleop`.

## What The Pi Starts By Default

`rovac-edge.target` currently starts:

- `rovac-edge-motor-driver.service`
- `rovac-edge-rplidar-c1.service`
- `rovac-edge-mux.service`
- `rovac-edge-tf.service`
- `rovac-edge-map-tf.service`
- `rovac-edge-obstacle.service`
- `rovac-edge-supersensor.service`
- `rovac-edge-health.service`
- `rovac-edge-rosbridge.service`
- `rovac-edge-ps2-joy.service`
- `rovac-edge-ps2-mapper.service`

Optional services for phone sensors, phone cameras, stereo, and webcam are available but are not part of the default edge target.

## Primary Verification Commands

```bash
# Pi service state
ssh pi@192.168.1.200 'sudo systemctl status rovac-edge.target'

# Topics on the Mac
ros2 topic list --no-daemon
ros2 topic hz /odom
ros2 topic hz /imu/data
ros2 topic hz /scan

# Health and diagnostics
ros2 topic echo /diagnostics --once
ros2 topic echo /rovac/edge/health --once
```

## Recovery Commands

```bash
# Restart the entire edge stack
ssh pi@192.168.1.200 'sudo systemctl restart rovac-edge.target'

# Restart one service
ssh pi@192.168.1.200 'sudo systemctl restart rovac-edge-motor-driver.service'

# Lidar only
ssh pi@192.168.1.200 'sudo systemctl restart rovac-edge-rplidar-c1.service'

# Show recent logs
ssh pi@192.168.1.200 'sudo journalctl -u rovac-edge-motor-driver.service -n 100 --no-pager'
```

## Optional Sensor Workflows

### Phone sensors

```bash
ssh pi@192.168.1.200 'sudo systemctl start rovac-edge-phone-sensors.service'
```

### Phone cameras

```bash
ssh pi@192.168.1.200 'sudo systemctl start rovac-phone-cameras.service'
```

### Stereo

```bash
ssh pi@192.168.1.200 'sudo systemctl start rovac-edge-stereo.target'
```

## Note on rplidar_ros

The LIDAR service uses `rplidar_ros` (patched Slamtec driver), cloned separately on the Pi. It is not tracked in this shared Git repo and is not needed on the Mac.

## DDS Troubleshooting

CycloneDDS with **unicast-only** peer discovery (multicast disabled) is used because multicast routing is unreliable across WiFi interfaces on a home network.

### Configuration files

| File | Binds to |
|------|----------|
| `config/cyclonedds_mac.xml` | Mac en0 (WiFi, DHCP — auto-detected) |
| `config/cyclonedds_pi.xml` | Pi wlan0 (`192.168.1.200`) |

### Verify DDS is working

```bash
source config/ros2_env.sh
echo "RMW: $RMW_IMPLEMENTATION"        # rmw_cyclonedds_cpp
echo "DDS: $CYCLONEDDS_URI"            # should point to .xml
ros2 topic list --no-daemon            # wait 3-5s for discovery
```

### Common DDS issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ros2 topic list` hangs | macOS daemon issue with CycloneDDS | Use `--no-daemon` |
| No topics discovered | Wrong interface in XML | Verify Mac IP matches en0, run `source config/ros2_env.sh` to re-sync |
| No topics discovered | Pi nodes not running | `ssh pi@192.168.1.200 'sudo systemctl status rovac-edge.target'` |
| Partial discovery | Firewall blocking UDP | `sudo pfctl -d` on Mac |
| Topics appear then vanish | IP changed (DHCP) | Re-run `source config/ros2_env.sh` (auto-detects and syncs) |

## "Robot Won't Move" Checklist

1. **Power**: Motor driver switch ON, battery voltage > 8V
2. **Motor service**: `ssh pi@192.168.1.200 'systemctl is-active rovac-edge-motor-driver'`
3. **USB connected**: `ssh pi@192.168.1.200 'ls -la /dev/esp32_motor'`
4. **Odom flowing**: `ros2 topic hz /odom` — expect ~20 Hz
5. **Stale publishers**: `ssh pi@192.168.1.200 'pgrep -a -f "ros2 topic pub.*cmd_vel"'` — kill any found
6. **Mux running**: `ssh pi@192.168.1.200 'systemctl is-active rovac-edge-mux'`
7. **DDS working**: `echo $ROS_DOMAIN_ID` should be 42, `echo $CYCLONEDDS_URI` should point to XML
8. **Input reaching mux**: `ros2 topic echo /cmd_vel_teleop --once` — verify values when pressing keys

## Notes

- The current bringup path is Pi systemd plus Mac brain launch scripts.
- Legacy scripts still exist in-tree but are no longer the primary path.
- Keep this file aligned with service names, topic owners, and the current architecture docs.
