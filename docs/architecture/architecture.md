# ROVAC Architecture

This document describes the actual, deployed architecture of the ROVAC robot.

## System Model

> **Operational reference:** See `docs/bringup.md` for exact power‑on, startup, and recovery procedures.

ROVAC follows a **Pi‑centric edge architecture**. The Raspberry Pi mounted on the robot is responsible for all real‑time sensing, actuation, and safety‑critical logic.

Higher‑level tools (SLAM, visualization, development) may run off‑robot, but the Pi remains authoritative.

## Major Responsibilities

### Raspberry Pi 5 (On‑Robot, `192.168.1.200`)
- Motor/IMU control via Yahboom ROS Expansion Board V3 (USB serial)
- Sensor drivers (LIDAR, ultrasonic, IMU, camera)
- ROS 2 publishers/subscribers
- Autonomous behaviors (coverage, safety)
- DDS configuration and networking
- systemd services (`rovac-edge.target`)

### MacBook Pro (Brain, `192.168.1.104`)
- SLAM and mapping
- Navigation planning (Nav2)
- Foxglove visualization
- Joystick controllers (joy_node + joy_mapper via launchd)
- Development and debugging

## Communication

- ROS 2 with DDS
  - **CycloneDDS (canonical / default)** (unicast peer discovery; multicast disabled)
  - FastDDS (supported override)
- Shared `ROS_DOMAIN_ID`
- Peer discovery configured via XML

## Repository Philosophy

This repository mirrors `/home/pi` on the robot.

- Files are organized for **operation first**, not abstraction
- Version history reflects real deployments
- Maps and backups are intentionally tracked

If it runs on the robot, it belongs here.
