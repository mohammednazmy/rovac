# ROVAC Architecture (Verified)

Last aligned against the repository on 2026-05-18.

This file is a deployment-aligned snapshot of what the current repository is set up to run. It is intentionally narrower than the broader architecture document. ROVAC is a general-purpose autonomous mobile robot — the vacuum/cleaning function was retired 2026-05-17.

## Verified Against

- `config/systemd/rovac-edge.target`
- `config/systemd/rovac-edge-*.service`
- `config/ros2_env.sh`
- `scripts/mac_brain_launch.sh`
- `scripts/ekf_launch.py`
- `common/serial_protocol.h`
- `ros2_ws/src/rovac_motor_driver/`
- `ros2_ws/src/tank_description/`

## Current Topology

| Layer | Host | Current responsibility |
|------|------|------------------------|
| ESP32 motor controller | On robot | Motor control, odometry, BNO055, serial framing |
| ESP32 sensor hub | On robot | 4x HC-SR04 ultrasonic + 2x Sharp IR cliff, serial framing |
| Pi edge stack | `192.168.1.200` | Drivers, mux, TF, safety, stereo cameras, Sense HAT panel |
| Mac brain | DHCP on `en0` | SLAM, Nav2, EKF, Foxglove, teleop |
| DDS | CycloneDDS | Unicast-only peer discovery, `ROS_DOMAIN_ID=42` |

## Core Runtime Components

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| ESP32 motor firmware | Active | `hardware/esp32_motor_wireless/` | USB serial COBS transport |
| ESP32 sensor hub firmware | Active | `hardware/esp32_sensor_hub/` | USB serial COBS transport |
| Shared serial protocol | Active | `common/serial_protocol.h` | Message types, payloads, CRC |
| Pi motor driver | Active | `ros2_ws/src/rovac_motor_driver/` | Publishes `/odom`, `/imu/data`, `/diagnostics`, optional `/tf` |
| Pi sensor hub driver | Active | `ros2_ws/src/rovac_sensor_driver/` | Publishes ultrasonic/cliff ranges and `/obstacle/points` |
| Velocity mux | Active | `ros2_ws/src/tank_description/tank_description/cmd_vel_mux.py` | Human override over safety and Nav2 |
| URDF / TF model | Active | `ros2_ws/src/tank_description/urdf/tank.urdf` | Current frame geometry |
| Mac brain launcher | Active | `scripts/mac_brain_launch.sh` | `slam`, `slam-ekf`, `nav`, `ekf`, `foxglove`, `all` |
| Pi edge installer | Active | `scripts/install_pi_systemd.sh` | Installs units and udev rules on the Pi |
| Optional MCP server | Sidecar | `robot_mcp_server/` | Not part of core bringup |

## Verified Pi Services

These are the services the default edge target tries to start:

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

`rovac-edge-ekf.service` exists in `config/systemd/` but is disabled — EKF runs on the Mac.

## Key Topics

| Topic | Source | Notes |
|------|--------|-------|
| `/odom` | `rovac_motor_driver` | Wheel odometry from ESP32 |
| `/imu/data` | `rovac_motor_driver` | BNO055 output from ESP32 |
| `/diagnostics` | `rovac_motor_driver` | Motor/IMU health |
| `/scan` | `rplidar_ros` on Pi | Expected from RPLIDAR C1 |
| `/cmd_vel_teleop` | Keyboard teleop | Highest mux priority |
| `/cmd_vel_joy` | PS2 mapper | Human control |
| `/cmd_vel_obstacle` | Safety nodes | Overrides Nav2 but not human control |
| `/cmd_vel_smoothed` | Nav2 | Lowest mux priority |
| `/cmd_vel` | Mux output | Only the mux should publish here |
| `/odometry/filtered` | EKF on Mac | Produced when EKF is running |

## Control Arbitration

Current priority order in the live mux implementation:

1. `/cmd_vel_teleop`
2. `/cmd_vel_joy`
3. `/cmd_vel_obstacle`
4. `/cmd_vel_smoothed`

This matches the current human-override design in `cmd_vel_mux.py`.

## Notes

- `rplidar_ros` is pulled by `vcs import` per `ros2_ws/src/external.repos` (patched Slamtec driver) and is not tracked in this shared Git repo. The LIDAR service runs on the Pi only.
- Retired hardware (L298N, Hiwonder, WiFi micro-ROS, AT8236 driver, XV11 lidar, Super Sensor, Android phone sensors, USB webcams) lives under `archive/legacy_hardware/`; superseded service units under `archive/legacy_systemd/`.
- Historical docs from older wireless, XV-11, and Hiwonder eras have been moved under `docs/archive/`.

## Practical Reading Order

If you need to change behavior:

1. Start with `docs/ACTIVE_REPO_MAP.md`
2. Read the relevant live config in `config/`
3. Read the responsible runtime package or script
4. Confirm how the Pi service or Mac launcher actually starts it
