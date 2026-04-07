# Operator Feedback And Status Signals

This document covers operator-visible feedback in the current stack.

The important distinction is that most status information now comes from ROS topics, systemd state, Foxglove, and the command center UI. LED and buzzer behavior are optional and depend on the super sensor and controller integrations being connected.

## Primary Status Sources

Use these first:

- `sudo systemctl status rovac-edge.target`
- `/diagnostics`
- `/rovac/edge/health`
- Foxglove
- service logs via `journalctl`

## Optional Buzzer Meanings

Where a buzzer is wired through the super sensor or related control path, these meanings are reasonable conventions:

| Pattern | Meaning |
|---------|---------|
| short beep | acknowledgement |
| long beep | mode change or completed action |
| repeating triple beep | failure or blocked state |

These are conventions, not a guaranteed contract across all hardware configurations in the repo.

## Optional LED Meanings

If the RGB LED path is wired and active:

| Color | Meaning |
|-------|---------|
| Green | edge stack healthy / idle |
| Blue | teleop active |
| Yellow | warning or obstacle condition |
| Red | error, stop condition, or degraded runtime |
| Off | unavailable, disabled, or not wired |

## Practical Rule

If LED or buzzer state disagrees with ROS diagnostics or service state, trust the software-visible state first. The current runtime is designed around systemd and ROS observability, not around standalone light or sound codes.
