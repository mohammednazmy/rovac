# Robot Bringup Guide

This document describes the **exact power-on and startup procedure** for the robot, including recovery paths and diagnostics.

---

## Power-On Sequence

1. Ensure battery is charged and main power switch is **OFF**
2. Connect:
   - Motor power
   - USB devices (LiDAR ESP32 bridge, camera, controller dongles)
3. Switch **main power ON**
4. Raspberry Pi boots automatically (no display required)
5. Wait ~45-60s for systemd services to start

---

## Network Assumptions

- Both Mac and Pi connect through the **home network** (AT&T router at `192.168.1.254`)
  - Mac: `192.168.1.104` (WiFi, en0)
  - Pi: `192.168.1.200` (static via netplan, eth0)
- DDS is **unicast-only** (multicast disabled) to ensure reliable peer discovery across interfaces.
- Do not rely on mDNS (`robot.local`) for this setup.

```
Mac (192.168.1.104)                    Pi (192.168.1.200)
     en0 (WiFi)                             eth0
         |                                    |
         +---- AT&T Router (192.168.1.254) ---+
                    (Home Network)
```

---

## SSH Access

An SSH alias is configured in `~/.ssh/config`, so you only need:

```bash
ssh pi
```

Recovery access:
- Connect to the same home network
- Verify Pi is reachable: `ping 192.168.1.200`
- Fall back to full address if alias is missing: `ssh pi@192.168.1.200`

---

## ROS 2 / DDS Environment

Environment setup is handled by:

- `config/ros2_env.sh` (Mac) / `~/ros2_env.sh` (Pi -- auto-detects OS and loads Pi-specific config)

This configures:
- ROS 2 distro (Jazzy)
- DDS implementation (CycloneDDS)
- `ROS_DOMAIN_ID=42`
- Peer configuration via XML

To manually source on Mac:
```bash
source config/ros2_env.sh
```

To manually source on Pi:
```bash
source ~/ros2_env.sh
```

Verify:
```bash
echo $RMW_IMPLEMENTATION    # should print rmw_cyclonedds_cpp
echo $CYCLONEDDS_URI        # should point to the XML config file
```

---

## Normal Startup (Expected Path)

1. Power on robot
2. Pi auto-starts the edge stack (if installed):
   - `rovac-edge.target` (hiwonder board + TF publisher + mux + stereo cameras)
3. Mac auto-starts the controller stack at login (if installed):
   - launchd `com.rovac.controller` (joy_node + joy_mapper)
4. Run brain nodes on Mac as needed (SLAM/Nav2/Foxglove)
5. Robot responds to controller input

### One-time Persistence Install (recommended)
```bash
cd ~/robots/rovac
./scripts/install_mac_autostart.sh install
./scripts/install_pi_systemd.sh install
```

---

## Recovery Startup

Use this if:
- No controller
- No network
- ROS graph is broken

Steps:

```bash
# From Mac (recommended)
cd ~/robots/rovac
./scripts/standalone_control.sh restart

# Or restart edge stack directly on Pi
ssh pi 'sudo systemctl restart rovac-edge.target'
```

Manually launch brain nodes on Mac if needed:
`./scripts/mac_brain_launch.sh slam|nav|foxglove`

---

## systemd Services (on Pi)

All services are grouped under **`rovac-edge.target`**.

### Active Core Services

| Service | Description |
|---------|-------------|
| `rovac-edge-hiwonder.service` | Hiwonder ROS Controller V1.2 (motors, QMI8658 IMU at ~72 Hz, dead-reckoning odom, battery) |
| `rovac-edge-tf.service` | URDF/TF publisher (robot_state_publisher) |
| `rovac-edge-mux.service` | cmd_vel multiplexer (`/cmd_vel_obstacle` + `/cmd_vel_joy` + `/cmd_vel_smoothed` -> `/cmd_vel`) |
| `rovac-edge-map-tf.service` | Static map→odom TF (fallback when SLAM not running) |
| `rovac-edge-supersensor.service` | Super Sensor board (4x HC-SR04 ultrasonic) |
| `rovac-edge-stereo.target` | Stereo camera subsystem (groups depth + obstacle services) |
| `rovac-edge-stereo-depth.service` | Stereo depth computation from dual USB cameras |
| `rovac-edge-stereo-obstacle.service` | Obstacle detection from stereo depth → `/cmd_vel_obstacle` |

### Inactive Services (hardware not currently connected)

| Service | Description |
|---------|-------------|
| `rovac-edge-lidar.service` | XV11 LIDAR via ESP32 bridge (`/dev/esp32_lidar`) |
| `rovac-edge-phone-sensors.service` | Phone IMU/GPS |
| `rovac-edge-webcam.service` | NexiGo webcam |
| `rovac-edge-sensors.service` | Deprecated — old BST-4WD board GPIO sensors (still running, high CPU) |
| `rovac-edge-hiwonder.service` | **Disabled** — replaced by `rovac-edge-hiwonder.service` |
| `rovac-edge-motor.service` | **Failed** — old GPIO motor driver, replaced by hiwonder |

### Useful Commands

```bash
# Check overall edge stack status
ssh pi 'sudo systemctl status rovac-edge.target'

# Restart entire edge stack
ssh pi 'sudo systemctl restart rovac-edge.target'

# Check a specific service
ssh pi 'sudo systemctl status rovac-edge-hiwonder.service'

# View logs for a service (last 100 lines)
ssh pi 'sudo journalctl -u rovac-edge-hiwonder.service -n 100 --no-pager'

# View logs for the mux
ssh pi 'sudo journalctl -u rovac-edge-mux.service -n 100 --no-pager'
```

Disable for debugging:
```bash
ssh pi 'sudo systemctl stop rovac-edge.target'
```

### Manual Start on Pi

If systemd services are not installed, you can start the ROS 2 environment manually on the Pi:

```bash
source ~/ros2_env.sh
```

The `ros2_env.sh` script auto-detects the OS (Linux vs. Darwin) and loads the correct DDS config and IP addresses for the Pi.

---

## DDS Configuration (CycloneDDS Unicast)

**Current Setup:** CycloneDDS with **unicast-only** peer discovery (multicast disabled).

This configuration was chosen because:
- Multicast routing can be unreliable across WiFi and wired interfaces on a home network
- Unicast peer lists guarantee discovery between the two known machines
- Eliminates multicast routing issues across different network interfaces

### Configuration Files

| File | Location | Binds To |
|------|----------|----------|
| `cyclonedds_mac.xml` | `config/` | `192.168.1.104` on en0 (WiFi) |
| `cyclonedds_pi.xml` | `~/cyclonedds_pi.xml` on Pi | `192.168.1.200` on eth0 |

Both configs use the same structure:
```xml
<Interfaces>
  <NetworkInterface address="<local-ip>" priority="default" multicast="false"/>
</Interfaces>
<Discovery>
  <ParticipantIndex>auto</ParticipantIndex>
  <Peers>
    <Peer address="192.168.1.104"/>
    <Peer address="192.168.1.200"/>
  </Peers>
</Discovery>
```

### Verify DDS is Working

**Important:** On macOS, the ROS 2 daemon hangs with CycloneDDS. Always use `--no-daemon` with introspection commands.

```bash
# On Mac - check environment
source config/ros2_env.sh
echo "RMW: $RMW_IMPLEMENTATION"
echo "CYCLONEDDS_URI: $CYCLONEDDS_URI"

# List topics (use --no-daemon to avoid daemon hang on macOS)
# Should see Pi topics after ~3s discovery
ros2 topic list --no-daemon
```

### Common DDS Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ros2 topic list` hangs | macOS daemon issue with CycloneDDS | Use `ros2 topic list --no-daemon` |
| No topics discovered | Wrong interface in XML | Verify `192.168.1.104` on Mac en0, `192.168.1.200` on Pi eth0 |
| No topics discovered | Pi nodes not running | `ssh pi 'sudo systemctl status rovac-edge.target'` |
| Partial discovery | Firewall blocking UDP | `sudo pfctl -d` on Mac |
| Topics appear then vanish | IP address changed (DHCP) | Confirm static IPs match XML configs |

### Legacy: Static Peers (Not Recommended)

The `ROS_STATIC_PEERS` environment variable is **not used** with CycloneDDS.
Peer discovery is configured in the XML files instead.

---

## "Robot Won't Move" Checklist

### 1. Power
- Motor driver LED on
- Battery voltage OK

### 2. Status Feedback
- Check LED color (Green = OK, Red = Error)
- Listen for beeps
- See `docs/feedback_patterns.md` for codes

### 3. ROS Graph
```bash
ros2 topic list --no-daemon
```
- `/cmd_vel` present

### 4. Input
```bash
ros2 topic echo /cmd_vel_joy --no-daemon
```
- Values changing when controller moves

### 5. Edge Stack (Pi)
```bash
ssh pi 'sudo systemctl status rovac-edge.target'
ssh pi 'sudo systemctl status rovac-edge-hiwonder.service'
```

### 6. DDS
- Correct XML loaded (`echo $CYCLONEDDS_URI`)
- No firewall blocking DDS UDP
- Using `--no-daemon` for all `ros2` CLI commands on Mac

### 7. Safety
- Deadman button held
- No emergency stop active

### 8. Motors
- Hiwonder board node running (`rovac-edge-hiwonder.service`)
- USB serial `/dev/hiwonder_board` accessible
- **Motor power switch must be ON** for motors to spin

---

## Notes

- If in doubt, reboot and follow **Normal Startup** again
- Always use `--no-daemon` with `ros2` CLI commands on macOS to avoid CycloneDDS daemon hangs
- LIDAR uses `/dev/esp32_lidar` (ESP32 bridge), not `/dev/ttyAMA0`
- Keep this file updated when hardware or launch flow changes
