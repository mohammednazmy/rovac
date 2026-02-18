# ROVAC Architecture (Verified)

**Last Updated:** 2026-02-18

**System:**
- **Brain:** MacBook Pro (Nav2, SLAM, Controllers, Logic) at `192.168.1.104`
- **Edge:** Raspberry Pi 5 (Drivers, Sensors, Mux) at `192.168.1.200`
- **Network:** Home network (`192.168.1.x` subnet, AT&T router at `192.168.1.254`)
- **Internet:** Direct via home network (no tethering needed)
- **Middleware:** ROS 2 Jazzy + CycloneDDS (unicast-only)

## Working Components

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| Hiwonder Board Node | Working | Pi | `hiwonder_driver.py` - Motors, IMU (QMI8658 6-axis), Odom (dead-reckoning), Battery via USB serial `/dev/hiwonder_board` (CH9102, 1Mbaud) |
| Yahboom Board Node | **Replaced** | Pi | Disabled — replaced by Hiwonder ROS Controller V1.2 |
| cmd_vel Mux | Working | Pi | Routes `/cmd_vel_obstacle` (highest) + `/cmd_vel_joy` + `/cmd_vel_smoothed` -> `/cmd_vel` |
| TF Publisher | Working | Pi | `robot_state_publisher` - URDF transforms |
| Super Sensor | Working | Pi | `super_sensor_node` - 4x HC-SR04 ultrasonic via Arduino Nano |
| Obstacle Detector | Working | Pi | `obstacle_detector` (stereo depth) + `obstacle_avoidance_node` (super sensor) |
| Stereo Cameras | Working | Pi | 2x USB cameras, StereoSGBM depth, ~2-3 Hz, 102.67mm baseline |
| LIDAR (XV11) | Disconnected | Pi | ESP32 USB bridge at `/dev/esp32_lidar`, service `rovac-edge-lidar.service` |
| Phone Camera | Disconnected | Pi | scrcpy + v4l2loopback, service `rovac-edge-camera.service` |
| Joy Node | Working | Mac | `ros2 run joy joy_node` via launchd - reads Pro Controller |
| Joy Mapper | Working | Mac | `joy_mapper_node.py` via launchd - maps inputs to topics |
| DDS (CycloneDDS) | Working | Both | Unicast peer discovery (multicast disabled) |

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                    MAC (192.168.1.104)                          │
│                                                                                 │
│  Pro Controller ──> joy_node ──> /tank/joy ──> joy_mapper_node                 │
│                                                        │                        │
│                                    ┌───────────────────┼───────────────────┐   │
│                                    │                   │                   │   │
│                                    v                   v                   v   │
│                              /cmd_vel_joy      /sensors/*_cmd        /tank/speed│
└────────────────────────────────────┬───────────────────┬───────────────────┬───┘
                                     │                   │                   │
                              Home Network (WiFi/Eth via 192.168.1.254)
                                     │                   │                   │
┌────────────────────────────────────v───────────────────v───────────────────v───┐
│                                    PI (192.168.1.200)                           │
│                                                                                 │
│  /cmd_vel_obstacle ─┐                                                        │
│  /cmd_vel_joy ─────>│ cmd_vel_mux ──> /cmd_vel ──> hiwonder_driver ──> Motors │
│  /cmd_vel_smoothed ─┘                                      │                  │
│                                                             │                  │
│  hiwonder_driver ──> /imu/data (~72Hz, 6-axis QMI8658)    │                  │
│                   ──> /odom (dead-reckoning + gyro Z)       │                  │
│                   ──> /battery_voltage (Float32)            │                  │
│                   ──> /diagnostics                          │                  │
│                                                                                 │
│  super_sensor_node ──> /super_sensor/ranges                                    │
│  obstacle_detector ──> /obstacles                                              │
│  robot_state_publisher ──> /tf, /tf_static                                     │
│                                                                                 │
│  [Disconnected] XV11 LIDAR ──> /scan                                           │
│  [Disconnected] Phone Camera ──> /phone/camera/image_raw                       │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Controller Mapping (Nintendo Pro Controller on macOS)

| Control | Topic | Action |
|---------|-------|--------|
| Left Stick | `/cmd_vel_joy` | Drive (linear.x + angular.z) |
| Right Stick X | `/sensors/servo_cmd` | Pan servo (-90 to +90 degrees) |
| ZL Trigger | `/cmd_vel_joy` | Reverse (proportional) |
| ZR Trigger | `/cmd_vel_joy` | Forward (proportional) |
| L Bumper | `/cmd_vel_joy` | Turn left |
| R Bumper | `/cmd_vel_joy` | Turn right |
| D-Pad Up/Down | `/tank/speed` | Speed +/- 10% |
| Y Button | `/tank/speed` | Cycle speed mode (30/60/100%) |
| A Button | `/sensors/led_cmd` | Toggle LED on/off |
| X Button | `/sensors/led_cmd` | Cycle LED colors |
| B Button | `/sensors/buzzer_cmd` | Buzzer (held) |

## Quick Start

### 0. One-time Persistence Setup (recommended)
```bash
cd ~/robots/rovac
./scripts/install_mac_autostart.sh install   # macOS launchd: joy_node + joy_mapper
./scripts/install_pi_systemd.sh install      # Pi systemd: motors + sensors + mux + lidar
```

### 1. Power On
1. Turn on Robot (battery switch). Pi auto-connects to home network.
2. No need to connect Ethernet cable or Android phone anymore.

### 2. Start Control Stack (Mac Terminal)
```bash
cd ~/robots/rovac
conda activate ros_jazzy
source config/ros2_env.sh
```

### 3. Verify System (Mac)
```bash
# Check topics (wait 3s for discovery)
# IMPORTANT: --no-daemon flag is needed on macOS
ros2 topic list --no-daemon

# Expected topics:
#   /cmd_vel
#   /cmd_vel_joy
#   /cmd_vel_obstacle
#   /tank/speed
#   /imu/data          (QMI8658 6-axis, ~72Hz)
#   /odom              (dead-reckoning, 20Hz)
#   /battery_voltage   (Float32)
#   /diagnostics
#   /super_sensor/ranges
#   /obstacles
#   /stereo/depth/image_raw
#   /tf
#   /tf_static
#   /sensors/servo_cmd
#   /sensors/led_cmd
#   /sensors/buzzer_cmd
```

### 4. Drive the Robot
- Connect Pro Controller via Bluetooth
- Use Left Stick to drive
- Use triggers for forward/reverse

### 5. Stop
```bash
./scripts/standalone_control.sh stop
```

## Manual Start (Debugging)

### On Pi (SSH)
```bash
ssh pi

# Systemd (preferred)
sudo systemctl status rovac-edge.target
sudo systemctl restart rovac-edge.target
sudo journalctl -u rovac-edge-hiwonder.service -n 100 --no-pager

# Manual env (fallback)
cd ~/robots/rovac
git pull
source config/ros2_env.sh
```

### On Mac
```bash
cd ~/robots/rovac
conda activate ros_jazzy
source config/ros2_env.sh

# launchd (preferred)
./scripts/install_mac_autostart.sh status
./scripts/install_mac_autostart.sh restart

# Manual start (fallback)
ros2 run joy joy_node --ros-args -p device_id:=0 -p autorepeat_rate:=20.0 -r joy:=/tank/joy &
python3 scripts/joy_mapper_node.py &
```

## Configuration Files

| File | Location | Purpose |
|------|----------|---------|
| `config/ros2_env.sh` | Both (same repo on Mac + Pi) | ROS2 environment setup (auto-detects OS) |
| `config/cyclonedds_mac.xml` | Both (used on Mac) | DDS config - peers to `192.168.1.104`, `.200` |
| `config/cyclonedds_pi.xml` | Both (used on Pi) | DDS config - peers to `192.168.1.200`, `.104` |
| `scripts/joy_mapper_node.py` | Mac | Controller input mapping |
| `scripts/standalone_control.sh` | Mac | Full stack launcher |

## Network Topology

```
Mac (192.168.1.104)                    Pi (192.168.1.200)
     en0 (WiFi)                             eth0
         │                                    │
         └──── AT&T Router (192.168.1.254) ───┘
                    (Home Network)
```

## CycloneDDS Configuration

**IMPORTANT:** Both Mac and Pi configs must include BOTH peer addresses for full discovery:
- `192.168.1.104` (Mac)
- `192.168.1.200` (Pi - required for Pi-to-Pi local communication!)

Without the Pi's own address as a peer, nodes running on Pi cannot discover each other via unicast DDS.

## Troubleshooting

### Robot not moving when using controller?
1. Check joy_node is receiving input: `ros2 topic echo /tank/joy --no-daemon`
2. Check joy_mapper is publishing: `ros2 topic echo /cmd_vel_joy --no-daemon`
3. Check Pi edge stack: `ssh pi "sudo systemctl status rovac-edge.target"`
4. Check mux + yahboom logs: `ssh pi "sudo journalctl -u rovac-edge-mux.service -n 50 --no-pager; sudo journalctl -u rovac-edge-hiwonder.service -n 50 --no-pager"`

### Buttons (LED, buzzer) not working?
1. Sensors service must be active: `ssh pi "sudo systemctl status rovac-edge-sensors.service"`
2. Restart it: `ssh pi "sudo systemctl restart rovac-edge-sensors.service"`
3. If buzzer still fails, confirm SPI is disabled (GPIO8): `ssh pi "grep -n '^dtparam=spi' /boot/firmware/config.txt"`

### No topics discovered?
1. Wait 3-5 seconds (unicast discovery is slower)
2. Check CycloneDDS config: `echo $CYCLONEDDS_URI`
3. Verify network: `ping 192.168.1.200`
4. Check Pi DDS config has BOTH peer addresses
5. Always use `--no-daemon` flag: `ros2 topic list --no-daemon`

### LIDAR not publishing? (currently disconnected)
1. Check service: `ssh pi "sudo systemctl status rovac-edge-lidar.service"`
2. Restart LIDAR: `ssh pi "sudo systemctl restart rovac-edge-lidar.service"`
3. Confirm ESP32 USB bridge device: `ssh pi "ls -la /dev/esp32_lidar"`

### Phone camera not publishing? (currently disconnected)
1. Check service: `ssh pi "sudo systemctl status rovac-edge-camera.service"`
2. Restart camera: `ssh pi "sudo systemctl restart rovac-edge-camera.service"`
3. Confirm ADB sees phone: `ssh pi "adb devices"`

### GPIO busy error?
1. Kill orphan processes: `ssh pi "pkill -9 -f hiwonder_driver"`
2. Check USB serial: `ssh pi "ls -la /dev/hiwonder_board"`
