# Active Repo Map

This is the fastest way to orient yourself in the repository without getting lost in historical packages or experiments.

## Start Here

If you are new to the repo, read these in order:

1. `README.md`
2. `CLAUDE.md`
3. `docs/architecture/architecture.md`
4. `docs/guides/bringup.md`

## Current Runtime Path

```text
ESP32 motor firmware
  hardware/esp32_motor_wireless/
        |
        v
Shared protocol
  common/serial_protocol.h
        |
        v
Pi motor driver + edge services
  ros2_ws/src/rovac_motor_driver/
  config/systemd/
        |
        v
Mac brain workflows
  scripts/mac_brain_launch.sh
  scripts/keyboard_teleop.py
```

## Core Directories

| Path | Why it matters | Start with |
|------|----------------|------------|
| `common/` | Shared binary protocol and COBS framing | `serial_protocol.h` |
| `hardware/esp32_motor_wireless/` | Active ESP32 firmware | `main/main.c`, `main/serial_transport.c`, `main/motor_control.c` |
| `ros2_ws/src/rovac_motor_driver/` | Active Pi-side motor bridge | `src/motor_driver_node.cpp` |
| `ros2_ws/src/tank_description/` | URDF and velocity mux | `urdf/tank.urdf`, `tank_description/cmd_vel_mux.py` |
| `config/` | DDS, EKF, Nav2, SLAM, and systemd config | `ros2_env.sh`, `ekf_params.yaml`, `systemd/` |
| `scripts/` | Operator workflows and deployment | `install_pi_systemd.sh`, `mac_brain_launch.sh`, `keyboard_teleop.py` |
| `docs/` | Current architecture and operator docs | this file plus `guides/bringup.md` |

## Optional But Active Areas

| Path | Role |
|------|------|
| `super_sensor/` and `hardware/super_sensor/` | Ultrasonic sensor stack and obstacle integration |
| `hardware/android_phone_sensors/` | Phone IMU/GPS/Camera app (rosbridge WebSocket on Pi :9090) |
| `hardware/stereo_cameras/` | Stereo depth and obstacle detection |
| `hardware/webcam/` | USB webcam integration |
| `robot_mcp_server/` | Experimental/sidecar MCP and AI-facing interfaces |

## Historical Or Reference Areas

These remain in the repo, but they are not the starting point for the current stack:

| Path | Why it exists |
|------|---------------|
| `archive/` | Prior robot iterations and deprecated code |
| `docs/archive/` | Archived phase notes, old wiring docs, and wireless-era plans |
| `archive/legacy_ros_packages/` | Yahboom vendor packages (controller, peripherals, ros_robot_controller) and older lidar drivers (vorwerk, xv11) |
| `hardware/esp32_xv11_bridge/` | Previous lidar bridge design |
| `hardware/esp32_at8236_driver/` | Older motor-driver path |
| `hardware/yahboom-*` | Older board-specific hardware references |

## Change By Subsystem

### Motor stack

Start with:

- `hardware/esp32_motor_wireless/`
- `common/serial_protocol.h`
- `ros2_ws/src/rovac_motor_driver/`
- `config/systemd/rovac-edge-motor-driver.service`

### Navigation and localization

Start with:

- `scripts/mac_brain_launch.sh`
- `scripts/ekf_launch.py`
- `config/ekf_params.yaml`
- `config/navsat_params.yaml`
- `config/slam_params.yaml`
- `config/nav2_params.yaml`

### Command flow and teleop

Start with:

- `ros2_ws/src/tank_description/tank_description/cmd_vel_mux.py`
- `scripts/keyboard_teleop.py`
- `scripts/ps2_joy_mapper_node.py`
- `config/systemd/rovac-edge-mux.service`

### Deployment and runtime management

Start with:

- `config/ros2_env.sh`
- `scripts/install_pi_systemd.sh`
- `config/systemd/rovac-edge.target`
- `scripts/edge/edge_health_node.py`

## Notes

- `rplidar_ros` is cloned separately on the Pi (patched Slamtec driver) and is not tracked in this shared Git repo.
- Legacy packages and scripts remain in-tree for reference; active docs point away from them.
