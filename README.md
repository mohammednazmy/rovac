# ROVAC

ROVAC is a ROS 2 Jazzy mobile robot built on a Yahboom G1 tank chassis with a split-brain architecture:

- ESP32 on the robot handles motor control, odometry, and the BNO055 IMU
- Raspberry Pi 5 runs the always-on edge stack
- MacBook Pro runs SLAM, Nav2, EKF, Foxglove, teleop, and development workflows

This repository is shared by both machines:

- Mac: `~/robots/rovac`
- Pi: `/home/pi/robots/rovac`

## Current Architecture

| Layer | Device | Current responsibility |
|-------|--------|------------------------|
| Motor controller | ESP32-WROOM-32E | PID motor control, encoder odometry, BNO055, USB COBS protocol |
| Edge | Raspberry Pi 5 | motor driver, lidar, mux, TF, rosbridge, safety nodes, systemd orchestration |
| Brain | MacBook Pro | SLAM Toolbox, Nav2, EKF, Foxglove, teleop, debugging |
| Optional sensor package | Samsung Galaxy A16 | GPS, IMU, magnetometer, and camera feeds |

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
| `ros2_ws/src/rovac_motor_driver/` | Pi-side C++ USB motor driver |
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

- `archive/`
- `docs/archive/`
- `archive/legacy_ros_packages/` (Yahboom vendor packages and older lidar drivers)
- `robot_mcp_server/` as a sidecar or experimental subsystem

## Note on rplidar_ros

The LIDAR service uses `rplidar_ros` (patched Slamtec driver), which is cloned separately on the Pi and is not tracked in this shared Git repo. It is not needed on the Mac — the service runs on the Pi only.
