# ROVAC

ROVAC is a general-purpose autonomous mobile robot running ROS 2 Jazzy, built on a Yahboom G1 tank chassis with a split-brain architecture:

- ESP32 on the robot handles motor control, odometry, and the BNO055 IMU
- Raspberry Pi 5 runs the always-on edge stack
- MacBook Pro runs SLAM, Nav2, EKF, Foxglove, teleop, and development workflows

This repository is shared by both machines:

- Mac: `~/robots/rovac`
- Pi: `/home/pi/robots/rovac`

## Current Architecture

| Layer | Device | Current responsibility |
|-------|--------|------------------------|
| Motor controller | NULLLAB Maker-ESP32 (ESP32-WROOM-32E) | PID motor control, encoder odometry, BNO055, USB COBS protocol |
| Edge | Raspberry Pi 5 | motor driver, sensor hub, lidar, stereo cameras, mux, TF, Sense HAT panel, safety nodes, systemd orchestration |
| Brain | MacBook Pro | SLAM Toolbox, Nav2, EKF, Foxglove, teleop, debugging |

## Quick Start

### Pi one-time setup

```bash
ssh pi@192.168.1.200
cd ~/robots/rovac
./scripts/install_pi_systemd.sh install
```

### Daily workflow on the Mac

```bash
cd ~/robots/rovac
conda activate ros_jazzy
source config/ros2_env.sh

ssh pi@192.168.1.200 'sudo systemctl status rovac-edge.target'

./scripts/mac_brain_launch.sh slam-ekf
python3 scripts/keyboard_teleop.py
```

### Basic verification

```bash
ros2 topic list --no-daemon
ros2 topic hz /odom
ros2 topic hz /imu/data
ros2 topic hz /scan
```

On macOS, use `--no-daemon` with `ros2 topic list`, but not with `ros2 topic hz`.

## Active Repo Map

| Path | Purpose |
|------|---------|
| `common/` | Shared serial protocol and COBS framing |
| `hardware/esp32_motor_wireless/` | Active ESP-IDF motor firmware |
| `hardware/esp32_sensor_hub/` | Active ESP-IDF sensor hub firmware (ultrasonic + IR cliff) |
| `ros2_ws/src/rovac_motor_driver/` | Pi-side C++ USB motor driver |
| `ros2_ws/src/rovac_sensor_driver/` | Pi-side C++ USB sensor hub driver |
| `ros2_ws/src/tank_description/` | URDF and live `cmd_vel` mux |
| `config/` | DDS, EKF, Nav2, SLAM, and systemd configuration |
| `scripts/` | Pi install/orchestration, Mac brain launch, teleop |
| `docs/` | Current architecture and operator documentation |
| `archive/` | Historical code and superseded iterations |

For the tighter subsystem map, start with `docs/ACTIVE_REPO_MAP.md`.

## Documentation

- `docs/ACTIVE_REPO_MAP.md`
- `docs/architecture/architecture.md`
- `docs/architecture/ARCHITECTURE_VERIFIED.md`
- `docs/guides/bringup.md`
- `docs/troubleshooting/field_recovery_checklist.md`
- `docs/ros2_reference_card.md`
- `hardware/README.md`

## Historical Material

The repo still contains retained legacy packages, vendor imports, and experimental areas. They are useful for reference, but they are not the current runtime path:

- `archive/legacy_hardware/` (L298N driver, Hiwonder ROS controller, WiFi micro-ROS, AT8236 Python driver, XV11 lidar, Super Sensor, retired phone-sensor app, USB webcams)
- `archive/legacy_systemd/` (superseded edge service units, e.g. rosbridge)
- `archive/experiments/`
- `docs/archive/`
- `robot_mcp_server/` as a sidecar or experimental subsystem

The vacuum/cleaning function was retired 2026-05-17; ROVAC is no longer a vacuum robot.

## Note on rplidar_ros

The LIDAR service uses `rplidar_ros` (patched Slamtec driver), which is cloned separately on the Pi and is not tracked in this shared Git repo. It is not needed on the Mac — the service runs on the Pi only.
