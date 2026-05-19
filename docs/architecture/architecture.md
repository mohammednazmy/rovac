# ROVAC Architecture

This document describes the current deployed architecture of the robot as represented by the active scripts, service units, and runtime packages in this repository.

For operator steps, see `docs/guides/bringup.md`.

## System Overview

ROVAC is a general-purpose autonomous mobile robot, split into three operational layers:

| Layer | Location | Responsibility |
|------|----------|----------------|
| Motor controller | ESP32 on robot | Closed-loop motor control, encoder odometry, BNO055 IMU, USB serial transport |
| Edge | Raspberry Pi 5 on robot | Motor driver bridge, sensor hub driver, lidar, stereo cameras, TF, mux, safety nodes, Sense HAT panel, service orchestration |
| Brain | MacBook Pro | SLAM, Nav2, EKF, Foxglove, teleop, development |

## Communication Boundaries

### ESP32 to Pi

- Physical link: USB serial
- Transport: COBS-framed binary protocol
- Shared definition: `common/serial_protocol.h`
- Pi consumer: `ros2_ws/src/rovac_motor_driver/`

### Pi to Mac

- Middleware: ROS 2 Jazzy over CycloneDDS
- Domain: `ROS_DOMAIN_ID=42`
- Profiles: `config/cyclonedds_mac.xml` and `config/cyclonedds_pi.xml`
- Bootstrap: `config/ros2_env.sh`

### Sensor hub to Pi

- Physical link: USB serial
- Transport: COBS-framed binary protocol (same `common/serial_protocol.h`)
- Pi consumer: `ros2_ws/src/rovac_sensor_driver/`
- Publishes 4x HC-SR04 ultrasonic ranges, 2x Sharp IR cliff ranges, and `/obstacle/points`

> The Android phone sensor package and its rosbridge bridge were retired 2026-04-11; the BNO055 on the ESP32 replaced the phone IMU. See `archive/legacy_hardware/`.

## Runtime Ownership

### Pi edge stack

The Pi is the always-on runtime owner for robot-local services:

- `rovac-edge.target`
- `rovac-edge-motor-driver.service`
- `rovac-edge-sensor-hub.service`
- `rovac-edge-rplidar-c1.service`
- `rovac-edge-mux.service`
- `rovac-edge-tf.service`
- `rovac-edge-map-tf.service`
- `rovac-edge-obstacle.service`
- `rovac-edge-health.service`
- `rovac-edge-ps2-joy.service`
- `rovac-edge-ps2-mapper.service`
- `rovac-edge-sense-hat-panel.service`
- `rovac-edge-stereo-cameras.service`
- `rovac-edge-diagnostics-splitter.service`

`rovac-edge-ekf.service` exists but is disabled — EKF runs on the Mac.

### Mac brain stack

The Mac starts and stops session-oriented workflows:

- `scripts/mac_brain_launch.sh slam`
- `scripts/mac_brain_launch.sh slam-ekf`
- `scripts/mac_brain_launch.sh nav <map>`
- `scripts/mac_brain_launch.sh ekf`
- `scripts/mac_brain_launch.sh foxglove`

The Mac also coordinates with the Pi by:

- stopping the fallback `map -> odom` static transform when SLAM is running
- disabling `publish_tf` in the motor driver when EKF is responsible for `odom -> base_link`

## Control Flow

```text
/cmd_vel_teleop
/cmd_vel_joy
/cmd_vel_obstacle
/cmd_vel_smoothed
        |
        v
cmd_vel mux
        |
        v
/cmd_vel
        |
        v
rovac_motor_driver
        |
        v
ESP32 motor controller
```

Design rules:

- Nothing should publish directly to `/cmd_vel` except the mux.
- Human inputs outrank obstacle and navigation commands.
- The ESP32 enforces its own command watchdog even when upstream publishers stop.

## Localization Flow

```text
ESP32 encoders + BNO055
        |
        v
/odom + /imu/data
        |
        v
EKF (Mac, primary path)
        |
        v
/odometry/filtered and odom -> base_link TF
        |
        v
SLAM Toolbox / Nav2
```

When EKF is not running, the Pi motor driver can publish `odom -> base_link` directly.

## Repo Truth Sources

When architecture docs and code disagree, trust these first:

- `CLAUDE.md`
- `AGENTS.md`
- `config/systemd/`
- `config/ros2_env.sh`
- `scripts/mac_brain_launch.sh`
- `ros2_ws/src/rovac_motor_driver/`
- `ros2_ws/src/tank_description/`

## Non-Core Areas

- `robot_mcp_server/` is a sidecar or experimental subsystem, not the primary bringup path.
- Older ROS packages under `ros2_ws/src/` are retained, but they do not define the current architecture.
- Historical docs and iteration summaries live under `docs/archive/`.
