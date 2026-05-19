# Operator Feedback And Status Signals

This document covers operator-visible feedback in the current stack for
ROVAC, a general-purpose autonomous mobile robot.

The important distinction is that most status information comes from ROS
topics, systemd state, Foxglove, and the command center UI. On-robot LED
status comes from the Raspberry Pi Sense HAT panel
(`rovac-edge-sense-hat-panel.service`). Standalone buzzer behavior is legacy
and is not part of the current hardware set.

## Primary Status Sources

Use these first:

- `sudo systemctl status rovac-edge.target`
- `/diagnostics`
- `/rovac/edge/health`
- Foxglove
- service logs via `journalctl`

## Sense HAT Panel LED Status

On-robot status is shown on the Raspberry Pi Sense HAT 8x8 LED matrix, driven
by `rovac-edge-sense-hat-panel.service`. It displays a mode glyph (IDLE / TELEOP
/ NAV / SLAM / ESTOP) with corner alarm badges for ESP32 health, Mac
connectivity, and cliff detection. See the root `CLAUDE.md` "Sense HAT Panel"
section for the full glyph and badge reference.

> Note: standalone buzzer / RGB-LED codes from earlier hardware iterations
> (the retired Super Sensor) are no longer part of the robot. They are not a
> status source on the current stack.

## Practical Rule

If the Sense HAT panel state disagrees with ROS diagnostics or service state,
trust the software-visible state first. The current runtime is designed around
systemd and ROS observability.
