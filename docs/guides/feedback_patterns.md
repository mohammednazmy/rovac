# Robot Feedback Patterns

This document describes the audio (buzzer) and visual (LED) feedback patterns used by the robot to communicate status and recovery states.

---

## 🔊 Buzzer Patterns

The robot uses a piezo buzzer for audible feedback.

| Pattern Name | Sequence | Meaning |
|--------------|----------|---------|
| **short** | `•` (0.1s) | Command received / Acknowledge |
| **long** | `▬` (0.5s) | Operation complete / Mode switch |
| **happy** | `• • ▬` | Success / Ready / Connected |
| **sad** | `▬ ▬ ▬` | Error / Disconnected / Failure |
| **sos** | `••• ▬▬▬ •••` | Emergency / Critical Error |

**Test Command:**
```bash
# Via MCP tool
call_tool beep times=1 pattern="happy"
```

---

## 💡 LED Status

The RGB LED indicates power and software state.

| Color | Meaning |
|-------|---------|
| **Green** | Normal Operation / Idle |
| **Blue** | Teleoperation Active (Manual Control) |
| **Red** | Error / E-Stop Active |
| **Yellow** | Warning / Obstacle Detected |
| **Cyan** | Autonomous Mode (Nav2/SLAM) |
| **Magenta** | Service Processing (Thinking) |
| **White** | Flashlight / Camera Illuminator |
| **Off** | Deep Sleep / Power Save |

**Test Command:**
```bash
# Via MCP tool
call_tool set_led color="blue"
call_tool flash_led color="red" times=5
```

---

## Recovery State Indicators

When restarting the stack (recommended: `./scripts/standalone_control.sh restart`):

1.  **Power On:** Power LED (Hardware) lights up.
2.  **Service Start:** System default (usually Green or Off).
3.  **Controller Connect:** Controller vibration + Solid **Blue** (typically set by `joy_mapper_node`).
4.  **Error:** If robot fails to move, listen for **sad** beeps or look for **Red** LED flashes.
