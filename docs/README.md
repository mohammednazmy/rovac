# ROVAC Documentation

This directory now separates current operator documentation from archived iteration-era material.

## Start Here

- [`ACTIVE_REPO_MAP.md`](ACTIVE_REPO_MAP.md): active files and directories by subsystem
- [`architecture/architecture.md`](architecture/architecture.md): current architecture and ownership boundaries
- [`architecture/ARCHITECTURE_VERIFIED.md`](architecture/ARCHITECTURE_VERIFIED.md): deployment-aligned snapshot of the live stack
- [`guides/bringup.md`](guides/bringup.md): bringup and daily operator workflow
- [`troubleshooting/field_recovery_checklist.md`](troubleshooting/field_recovery_checklist.md): fast recovery checklist
- [`ros2_reference_card.md`](ros2_reference_card.md): daily ROS 2 commands
- [`robot_dimensions.md`](robot_dimensions.md): current frame geometry derived from the active URDF

## Current Documentation Areas

### Architecture

- [`architecture/architecture.md`](architecture/architecture.md)
- [`architecture/ARCHITECTURE_VERIFIED.md`](architecture/ARCHITECTURE_VERIFIED.md)

### Operations

- [`guides/bringup.md`](guides/bringup.md)
- [`troubleshooting/field_recovery_checklist.md`](troubleshooting/field_recovery_checklist.md)
- [`ros2_reference_card.md`](ros2_reference_card.md)
- [`guides/feedback_patterns.md`](guides/feedback_patterns.md)

### Specialized Reference

- [`robot_dimensions.md`](robot_dimensions.md)
- [`guides/pic16f917_programmer.md`](guides/pic16f917_programmer.md)
- [`QR_CODE_URL.txt`](QR_CODE_URL.txt)

## Documentation Policy

- Current runtime documentation should match the active ESP32 USB serial + Pi edge + Mac brain architecture.
- Historical plans, phase summaries, and superseded wiring or wireless-architecture docs belong under [`archive/`](archive/README.md).
- When runtime behavior changes, update both the operator-facing docs and the architecture snapshot in the same change.

## Source Of Truth

When docs disagree, trust these first:

- `CLAUDE.md`
- `AGENTS.md`
- `config/systemd/`
- `config/ros2_env.sh`
- `scripts/mac_brain_launch.sh`
- `ros2_ws/src/rovac_motor_driver/`
- `ros2_ws/src/tank_description/`

## Archive

Archived docs live under [`archive/`](archive/README.md). That includes older wireless-era plans, wiring references from earlier hardware generations, and project phase summaries.
