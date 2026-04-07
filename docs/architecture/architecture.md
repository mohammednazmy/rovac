# ROVAC Architecture

This document describes the current deployed architecture of the robot as represented by the active scripts, service units, and runtime packages in this repository.

For operator steps, see `docs/guides/bringup.md`.

## System Overview

ROVAC is split into four operational layers:

| Layer | Location | Responsibility |
|------|----------|----------------|
| Motor controller | ESP32 on robot | Closed-loop motor control, encoder odometry, BNO055 IMU, USB serial transport |
| Edge | Raspberry Pi 5 on robot | Sensor drivers, motor driver bridge, TF, mux, safety nodes, rosbridge, service orchestration |
| Brain | MacBook Pro | SLAM, Nav2, EKF, Foxglove, teleop, development |
| Optional sensor package | Android phone | GPS, IMU, magnetometer, camera streams |

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

### Phone to Pi

- Transport: rosbridge WebSocket on Pi port 9090
- App source: `hardware/android_phone_sensors/`
- ROS topics: `/phone/imu` (50Hz), `/phone/gps/fix` (1Hz), `/phone/camera/image_raw/compressed` (~2FPS)
- DDS exposes these to the Mac automatically

## Runtime Ownership

### Pi edge stack

The Pi is the always-on runtime owner for robot-local services:

- `rovac-edge.target`
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

Optional peripherals such as phone sensors, phone cameras, stereo depth, and webcam live outside the default edge target but are still part of the active repository.

### Mac brain stack

The Mac starts and stops session-oriented workflows:

- `scripts/mac_brain_launch.sh slam`
- `scripts/mac_brain_launch.sh slam-ekf`
- `scripts/mac_brain_launch.sh nav <map>`
- `scripts/mac_brain_launch.sh ekf`
- `scripts/mac_brain_launch.sh ekf-gps`
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
