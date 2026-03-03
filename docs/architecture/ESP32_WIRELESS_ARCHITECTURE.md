# ROVAC ESP32 Wireless Architecture Plan

**Date:** 2026-03-03 (updated)
**Status:** PROPOSED — pre-implementation decisions finalized
**Replaces:** Lenovo/Pi on-board computer architecture

## 1. Vision

Remove the on-board Linux computer (Lenovo ThinkCentre / Raspberry Pi) from the robot entirely. Replace it with a network of ESP32 microcontrollers that communicate wirelessly with the Mac over WiFi. The Mac becomes the sole ROS2 compute platform. The robot carries only ESP32s, motors, LIDAR, and a battery.

**Goals:**
- Significantly reduce robot weight and power consumption
- Simplify the power system (no 65W AC adapter for Lenovo)
- Establish an extensible ESP32 sensor network (add future sensors by adding more ESP32s)
- Native ROS2 integration via micro-ROS on the Gateway ESP32
- Any ROS2 machine on the LAN can interact with the robot *as long as* it can join the same ROS2 DDS graph (CycloneDDS peer config). The micro-ROS Agent remains a single endpoint that the Gateway connects to.

**Non-Goals (initial implementation):**
- No phone integration, cameras, stereo, ultrasonic, or obstacle stack (motors + encoders + XV11 only)
- No on-robot Linux computer (Pi/Lenovo are completely removed from runtime)
- No hard real-time guarantees over WiFi (safety relies on watchdogs + timeouts)

**Assumptions:**
- Mac runs ROS2 Jazzy and remains the only "heavy compute" machine (Nav2/SLAM/Foxglove/etc.)
- ROS2 uses `ROS_DOMAIN_ID=42` (same as today)
- Robot and Mac are on the same WiFi network and can reach each other (UDP for micro-ROS XRCE-DDS)

## 2. Architecture Overview

```
ON THE ROBOT (ESP32s only — no Linux computer)
════════════════════════════════════════════════════════════════════

 ┌───────────────────────┐           ┌────────────────────────────┐
 │  Motor ESP32-S3       │           │  LIDAR ESP32-WROOM-32      │
 │  (Arduino firmware)   │           │  (Arduino firmware)        │
 │                       │           │                            │
 │  PWM/GPIO → Motors    │           │  UART2(16,17) ← XV11 LIDAR│
 │  PCNT ← Encoders     │           │  PWM(GPIO25) → LIDAR motor │
 │                       │           │                            │
 │  Serial1 TX(17)───────┼──┐   ┌───┼──Serial1 TX(4)             │
 │  Serial1 RX(18)───────┼──┤   ├───┼──Serial1 RX(15)            │
 │  GND──────────────────┼──┤   ├───┼──GND                       │
 └───────────────────────┘  │   │   └────────────────────────────┘
                            │   │
                  921600 baud│   │921600 baud
                   (3 wires) │   │(3 wires)
                            │   │
              ┌─────────────┴───┴───────────────────────┐
              │       Gateway ESP32-S3                   │
              │       (ESP-IDF + micro-ROS firmware)     │
              │                                         │
              │  UART1(GPIO15 TX, GPIO16 RX) ↔ Motor    │
              │  UART2(GPIO13 TX, GPIO14 RX) ↔ LIDAR    │
              │  UART0(USB-CDC) → Debug console          │
              │                                         │
              │  ┌─ Core 1: UART parsing ──────────┐    │
              │  │  • Parse E <L> <R> from Motor    │    │
              │  │  • Parse XV11 binary from LIDAR  │    │
              │  │  • Compute encoder odometry      │    │
              │  │  • Accumulate LIDAR revolutions   │    │
              │  │  • Diff-drive kinematics          │    │
              │  └─────────────────────────────────┘    │
              │                                         │
              │  ┌─ Core 0: micro-ROS + WiFi ──────┐    │
              │  │  Publishes:                      │    │
              │  │    /odom      (20 Hz)            │    │
              │  │    /scan      (5 Hz)             │    │
              │  │    /tf        (20 Hz, odom→      │    │
              │  │               base_link ONLY)    │    │
              │  │    /diagnostics (1 Hz)           │    │
              │  │  Subscribes:                     │    │
              │  │    /cmd_vel                      │    │
              │  └─────────────────────────────────┘    │
              │                                         │
              │  WiFi STA → 192.168.1.220 (static)      │
              │  mDNS: rovac-gateway.local               │
              │  WS2812 LED(GPIO48): connection status   │
              └─────────────────────┬───────────────────┘
                                    │
                              WiFi UDP :8888
                              (micro-ROS XRCE-DDS)
                                    │
ON THE MAC                          │
════════════════════════════════════╪═══════════════════════════════
                                    │
              ┌─────────────────────┴───────────────────┐
              │  Mac (ROS2 Jazzy, conda ros_jazzy)      │
              │                                         │
              │  micro-ROS Agent (UDP :8888)             │
              │         ↕ DDS                           │
              │  cmd_vel_mux.py                          │
              │  robot_state_publisher (URDF TF tree)    │
              │  ps2_joy_mapper_node.py (PS2 on Mac USB) │
              │  joy_node (PS2 USB receiver)             │
              │  SLAM Toolbox / Nav2                     │
              │  MCP Server (port 8000)                  │
              │  Foxglove Bridge (port 8765)             │
              └─────────────────────────────────────────┘
```

### Why This Design

**Dedicated Gateway ESP32 (not WiFi on each peripheral):**
The WiFi stack consumes significant CPU and causes timing jitter. The Motor ESP32 does real-time PWM switching and hardware PCNT counting. The LIDAR ESP32 does 115200-baud UART forwarding with inline packet parsing. Keeping WiFi off these boards preserves their real-time behavior. The Gateway's only job is data processing and networking — it has no timing-critical hardware I/O that WiFi could disrupt.

**micro-ROS on the Gateway (not a transparent TCP bridge):**
Instead of forwarding raw serial bytes over TCP and running custom Python drivers on the Mac, the Gateway parses serial data, computes odometry, accumulates LIDAR scans, and publishes standard ROS2 topics via micro-ROS. This means the Mac runs only standard ROS2 nodes — no custom serial drivers needed. Other ROS2 machines interact by joining the same DDS graph as the Mac (they do not connect directly to the ESP32).

**UART between on-board ESP32s (not ESP-NOW or WiFi):**
Wired UART over short cables (<30cm) provides extremely low jitter and loss compared to wireless, and is easy to reason about/debug. The real-time peripherals should have the most reliable link possible. The Gateway firmware must still implement framing/resync and maintain UART error counters (noise/loose wires can still corrupt bytes).

**WiFi UDP for micro-ROS (not TCP):**
micro-ROS uses XRCE-DDS over UDP. UDP avoids TCP's head-of-line blocking — if one packet is lost, subsequent packets aren't delayed. For sensor data that's continuously refreshed (odometry at 20Hz, scans at 5Hz), a dropped packet is harmless.

## 3. Hardware Components

### Boards

| Board | Role | Status | Framework |
|-------|------|--------|-----------|
| ESP32-S3 WROOM (Lonely Binary 2518V5) #1 | Motor controller + encoder reader | Existing, deployed | Arduino |
| ESP32-WROOM-32 (38-pin devboard) | XV11 LIDAR bridge | Existing, deployed | Arduino |
| ESP32-S3 WROOM (Lonely Binary 2518V5) #2 | **Gateway** (new role) | **Verified healthy** (2026-03-03) | **ESP-IDF + micro-ROS** |

### Gateway Board Verification (2026-03-03)

Health check confirmed all subsystems operational:

| Check | Result |
|-------|--------|
| USB-CDC Serial | OK — `/dev/cu.usbmodem1101` on Mac |
| Chip | ESP32-S3 (QFN56) rev v0.2, dual-core LX7 240 MHz |
| Flash | 16,384 KB @ 80 MHz |
| PSRAM | 8,388,608 bytes (8 MB OPI), 8,386,096 free |
| Free Heap | 317,156 bytes |
| MAC | `dc:b4:d9:08:59:54` |
| WS2812 LED (GPIO48) | OK — green flash verified |
| WiFi scan | 6 networks found, **"Hurry" at RSSI -28 dBm** (excellent) |
| UART1 (GPIO15 TX / GPIO16 RX) | Configured at 921600 baud — OK |
| UART2 (GPIO13 TX / GPIO14 RX) | Configured at 921600 baud — OK |
| Arduino compile + upload | OK — via `arduino-cli` (esp32:esp32@3.3.5) |

The board is ready for Gateway firmware development. No hardware issues detected.

### Wiring

**6 jumper wires total** (3 per connection: TX, RX, GND). No additional components needed.

```
Motor ESP32-S3                Gateway ESP32-S3            LIDAR ESP32-WROOM-32
┌────────────────┐            ┌────────────────┐          ┌────────────────────┐
│           GPIO17 (TX)──────→│GPIO16 (RX) UART1          │                    │
│           GPIO18 (RX)←──────│GPIO15 (TX) UART1          │                    │
│           GND───────────────│GND             │          │                    │
│                │            │                │          │                    │
│                │            │GPIO13 (TX) UART2─────────→│GPIO15 (RX) UART1   │
│                │            │GPIO14 (RX) UART2←─────────│GPIO4  (TX) UART1   │
│                │            │GND─────────────────────────│GND                │
│                │            │                │          │                    │
│  GPIO4-7: Motors            │  WiFi STA mode │          │  GPIO16/17: XV11   │
│  GPIO8-11: Encoders         │  USB-CDC: debug│          │  GPIO25: RPM PWM   │
│  GPIO19/20: USB debug       │  GPIO48: LED   │          │  GPIO2: LED        │
└────────────────┘            └────────────────┘          └────────────────────┘
```

### GPIO Pin Assignments

**Motor ESP32-S3** (existing pins unchanged, new UART added):

| Function | GPIO | Notes |
|----------|------|-------|
| AIN1 (Motor A) | 4 (primary), 21 (alt) | Existing |
| AIN2 (Motor A) | 5 | Existing |
| BIN1 (Motor B) | 6 | Existing |
| BIN2 (Motor B) | 7 | Existing |
| Encoder Right A/B | 8, 9 | Existing (PCNT) |
| Encoder Left A/B | 10, 11 | Existing (PCNT) |
| **UART1 TX → Gateway** | **17** | **NEW** (safe Priority-2) |
| **UART1 RX ← Gateway** | **18** | **NEW** (safe Priority-2) |
| USB-CDC (debug) | 19, 20 | Existing (keep for debug) |

**LIDAR ESP32-WROOM-32** (existing pins unchanged, new UART added):

| Function | GPIO | Notes |
|----------|------|-------|
| XV11 UART2 RX (data FROM LIDAR) | 16 | Existing |
| XV11 UART2 TX (data TO LIDAR) | 17 | Existing |
| LIDAR motor PWM | 25 | Existing (TIP120) |
| Status LED | 2 | Existing |
| **UART1 TX → Gateway** | **4** | **NEW** (remapped from default) |
| **UART1 RX ← Gateway** | **15** | **NEW** (remapped, has boot pullup — OK for RX) |
| UART0 TX/RX (CP2102 USB) | 1, 3 | Existing (keep for debug) |

**Gateway ESP32-S3** (all new):

| Function | GPIO | Notes |
|----------|------|-------|
| UART1 TX → Motor ESP32 | 15 | Safe Priority-2 |
| UART1 RX ← Motor ESP32 | 16 | Safe Priority-2 |
| UART2 TX → LIDAR ESP32 | 13 | Safe Priority-2 |
| UART2 RX ← LIDAR ESP32 | 14 | Safe Priority-2 |
| WS2812 Status LED | 48 | Built-in on board |
| USB-CDC (debug console) | 19, 20 | Built-in |
| WiFi | Internal RF | No GPIO needed |

### UART Baud Rates

| Link | Baud Rate | Rationale |
|------|-----------|-----------|
| Gateway ↔ Motor ESP32 | **921600** | 8× faster than 115200; reduces per-byte latency. ESP32-to-ESP32 over <30cm wires handles this reliably. |
| Gateway ↔ LIDAR ESP32 | **921600** | Same rationale. The XV11 data arrives at 115200 from the LIDAR itself, but faster forwarding reduces buffering in the LIDAR ESP32. |
| LIDAR ESP32 ↔ XV11 LIDAR | 115200 | Hardware constraint (XV11 protocol). |

## 4. Gateway ESP32 Firmware Design (NEW — ESP-IDF + micro-ROS)

This is the primary new development effort. The Gateway is the robot's "brain-on-a-chip."

### Build System

- **Framework:** ESP-IDF v5.2+ (required by micro_ros_espidf_component)
- **micro-ROS component:** [micro_ros_espidf_component](https://github.com/micro-ROS/micro_ros_espidf_component)
- **Target:** ESP32-S3 with OPI PSRAM, 16MB flash
- **Partition scheme:** 3MB APP / 9.9MB FATFS (sufficient for micro-ROS + app)

### Processing Pipeline

```
UART1 RX (Motor ESP32)                    UART2 RX (LIDAR ESP32)
        │                                          │
        ▼                                          ▼
  Parse "E <L> <R>" lines              Parse XV11 22-byte packets
        │                              (0xFA header, index 0xA0-0xF9)
        ▼                                          │
  Compute encoder deltas                           ▼
  (reject outliers > 2000)             Accumulate 90 packets (360°)
        │                              Extract range mm→m, validate
        ▼                                          │
  Arc-integration odometry                         ▼
  (x, y, θ with FPU sin/cos)          Build LaserScan message
        │                              (360 ranges, 360 intensities)
        ▼                                          │
  Publish /odom (20 Hz)                Publish /scan (~5 Hz)
  Publish /tf odom→base_link                       │
        │                                          │
        └──────────── micro-ROS WiFi UDP ──────────┘
                            │
                            ▼
                    micro-ROS Agent (Mac)
                            │
                            ▼
                     ROS2 DDS network


  /cmd_vel subscriber (micro-ROS)
        │
        ▼
  Diff-drive kinematics:
    v_left  = linear.x - angular.z × wheel_sep / 2
    v_right = linear.x + angular.z × wheel_sep / 2
  Scale to motor range:
    speed = velocity × (max_motor / max_linear)
  Clamp to [-255, 255]
        │
        ▼
  Send "M <left> <right>\n" via UART1 TX
```

### Constants to Port from Python

These values from `esp32_at8236_driver.py` must be compiled into the Gateway firmware:

```c
#define WHEEL_SEPARATION   0.155f   // meters
#define WHEEL_RADIUS       0.032f   // meters
#define TICKS_PER_REV      2640     // 11 PPR × 4 edges × 60:1 gear
#define MAX_MOTOR_SPEED    255      // PWM range
#define MAX_LINEAR_SPEED   0.5f     // m/s
#define MAX_ANGULAR_SPEED  6.5f     // rad/s
#define ODOM_PUBLISH_HZ    20       // Hz
#define ENCODER_STREAM_HZ  50       // Hz (request from Motor ESP32)
#define CMD_VEL_TIMEOUT_MS 500      // ms (driver-side watchdog)
```

### Calibration + Sign Conventions (Don’t Skip)

Before trusting Nav2/SLAM, explicitly validate conventions end-to-end:

- Twist convention: `linear.x > 0` drives forward, `angular.z > 0` turns left (CCW)
- Motor mapping: which side is "left" vs "right" and whether either side needs inversion
- Encoder mapping: tick sign must match motor direction so forward motion produces positive forward odom
- Wheel parameters: wheel radius and wheel separation should be calibrated (even small errors cause drift)

The Gateway should expose these as compile-time constants at first, then move them to runtime-configurable settings (NVS + debug console) once the pipeline works.

### micro-ROS Configuration

**Publishers:**

| Topic | Message Type | QoS | Rate |
|-------|-------------|-----|------|
| `/odom` | nav_msgs/Odometry | Best Effort, Keep Last 5 | 20 Hz |
| `/scan` | sensor_msgs/LaserScan | Best Effort, Keep Last 5 | ~5 Hz |
| `/tf` | tf2_msgs/TFMessage | Best Effort, Keep Last 10 | 20 Hz (only `odom→base_link`) |
| `/diagnostics` | diagnostic_msgs/DiagnosticArray | Reliable, Keep Last 1 | 1 Hz |

**TF responsibility split (ROS2 standard pattern):**
- **Gateway** publishes **only** `odom → base_link` on `/tf` (the one dynamic transform it computes from odometry)
- **Mac `robot_state_publisher`** publishes all static URDF transforms on `/tf` (`base_link → laser_frame`, `base_link → imu_link`, etc.)
- **SLAM / localization** (Mac) publishes `map → odom` on `/tf`
- The Gateway does **not** need to know the URDF. If robot geometry changes (add a sensor, change mounting), update the URDF on the Mac — no firmware reflash.

**Subscribers:**

| Topic | Message Type | QoS |
|-------|-------------|-----|
| `/cmd_vel` | geometry_msgs/Twist | Reliable, Keep Last 1 |

**Buffer configuration:**

```
RMW_UXRCE_MAX_OUTPUT_BUFFER_SIZE = 8192   // budget for LaserScan (+ intensities) and framing overhead
RMW_UXRCE_MAX_INPUT_BUFFER_SIZE  = 512    // cmd_vel is small
RMW_UXRCE_MAX_PUBLISHERS         = 4
RMW_UXRCE_MAX_SUBSCRIBERS        = 1
RMW_UXRCE_MAX_HISTORY            = 10
```

Note: if RAM becomes tight, drop `/scan.intensities` (or publish at a lower rate) before reducing buffer sizes.

### Dual-Core Task Pinning

| Core | Tasks | Rationale |
|------|-------|-----------|
| Core 0 | WiFi stack, micro-ROS XRCE-DDS, TCP/IP | WiFi interrupts are pinned to core 0 by ESP-IDF default |
| Core 1 | UART1 RX/TX (motor), UART2 RX (LIDAR), odometry computation, LIDAR accumulation | Real-time serial processing must not be interrupted by WiFi |

### WiFi Configuration

- **Mode:** STA (station — connects to home WiFi)
- **Static IP:** `192.168.1.220` (gateway `192.168.1.254`, subnet `255.255.255.0`)
- **IP conflict avoidance:** reserve `192.168.1.220` in the router DHCP settings so it cannot be assigned to another device
- **mDNS hostname:** `rovac-gateway` (discoverable as `rovac-gateway.local`)
- **Power save:** `WIFI_PS_NONE` (disabled — lowest latency)
- **Auto-reconnect:** Yes, with exponential backoff

**WiFi Credentials (NVS-backed with compiled defaults):**

| Setting | Compiled Default | NVS Key |
|---------|-----------------|---------|
| SSID | `Hurry` | `wifi_ssid` |
| Password | `Gaza@2023` | `wifi_pass` |

On first boot, the compiled defaults are written to NVS. All subsequent connections read from NVS. To change the WiFi network (e.g., move the robot to a different location), use the USB debug console — no firmware reflash required.

**Provisioning via USB debug console:**

| Command | Effect |
|---------|--------|
| `!wifi` | Show current SSID, IP, RSSI, channel, NVS-stored values |
| `!wifi_ssid <SSID>` | Store new SSID in NVS (takes effect on `!reconnect` or `!restart`) |
| `!wifi_pass <PASSWORD>` | Store new password in NVS |
| `!wifi_ip <IP>` | Store new static IP in NVS (default: `192.168.1.220`) |
| `!reconnect` | Disconnect WiFi and reconnect with current NVS settings |

The `!wifi` command always shows **both** the active connection state and the NVS-stored values, so the operator can see if a change is pending (NVS differs from active).

### micro-ROS Agent Addressing (Critical)

micro-ROS over UDP is *client → agent*. The Gateway must know the agent's IP address and port.

| Setting | Compiled Default | NVS Key |
|---------|-----------------|---------|
| Agent IP | `192.168.1.104` (Mac's LAN IP) | `agent_ip` |
| Agent Port | `8888` (UDP) | `agent_port` |

Same NVS-backed provisioning pattern as WiFi:

| Command | Effect |
|---------|--------|
| `!agent` | Show current agent IP, port, connection state |
| `!agent_ip <IP>` | Store new agent IP in NVS (takes effect on `!reconnect`) |
| `!agent_port <PORT>` | Store new agent port in NVS |

- **Failure mode:** if the agent address is wrong, WiFi can be "connected" but micro-ROS will never connect (LED stays Yellow). The `!agent` command helps diagnose this — it shows the target IP/port and whether pings are reaching the agent.

### Motor Command Forwarding Policy (Safety + Smoothness)

Do not rely on "only forward when /cmd_vel arrives" because publishers can be bursty and the Motor ESP32 has an independent watchdog.

- Gateway maintains a **fixed-rate motor TX loop** (example: 20 Hz) that sends the most recent motor command over UART.
- Gateway enforces **CMD_VEL_TIMEOUT_MS**: if no fresh `/cmd_vel` has arrived within the timeout, Gateway sends a STOP (0,0) and continues sending STOP at the fixed rate.
- On micro-ROS disconnect (agent down) or WiFi down: Gateway immediately transitions to STOP (0,0) and keeps sending STOP at the fixed rate.

### Peripheral UART Bringup / Handshake (Missing Today)

At boot, the Gateway should actively validate both UART links and put peripherals into a known state.

- Motor ESP32:
  - Verify it is alive (identify/version/status)
  - Ensure encoder streaming is enabled at `ENCODER_STREAM_HZ`
  - Reset encoder baseline at a well-defined moment (and track resets to avoid odom jumps)
- LIDAR ESP32:
  - Verify it is alive (identify/version/status)
  - If supported, set/confirm target RPM
  - Detect stalled streams and resync packet boundaries

UART robustness requirements:
- Maintain per-UART counters: bytes/sec, framing/parse errors, buffer overruns, time-since-last-valid-message
- Implement resync logic that can recover from a single dropped/inserted byte without needing a full reboot

### micro-ROS Reconnection State Machine

```
                    ┌──────────┐
          ┌────────→│ WAITING  │◄──── Power on / hard reset
          │         │  AGENT   │
          │         └────┬─────┘
          │              │ rmw_uros_ping_agent() == RMW_RET_OK
          │              ▼
          │         ┌──────────┐
          │         │CONNECTED │──── Normal operation
          │         │          │     (publish/subscribe active)
          │         └────┬─────┘
          │              │ ping fails / publish fails
          │              ▼
          │         ┌──────────────┐
          │         │DISCONNECTED  │
          │         │              │──── Destroy entities
          └─────────│ Retry (5×)   │     Reset odometry baseline (NOT pose)
                    │ Then restart │     Continue UART parsing on Core 1
                    └──────────────┘
```

**Critical safety property:** During disconnection, UART parsing and odometry integration continue on Core 1. The Gateway maintains accurate pose even when WiFi is down. When the agent reconnects, the next published `/odom` message has the current (correct) pose — no discontinuity.

The Motor ESP32's 1-second hardware watchdog is independent of the Gateway. If the Gateway crashes entirely, the Motor ESP32 stops the motors within 1 second.

### USB-CDC Debug Console

The Gateway exposes a debug shell on USB-CDC (UART0) for development and troubleshooting.

**Diagnostic commands:**

| Command | Response |
|---------|----------|
| `!id` | Device identification (name, firmware version, chip, MAC) |
| `!status` | Uptime, WiFi RSSI, micro-ROS state, UART bytes/sec per channel |
| `!odom` | Current odometry pose (x, y, θ) and velocity |
| `!lidar` | LIDAR stats (packets/sec, RPM, valid points, errors) |
| `!wifi` | WiFi state (active SSID/IP/RSSI/channel) + NVS-stored values |
| `!agent` | micro-ROS agent target IP/port, connection state, ping status |

**Provisioning commands (NVS-backed, persist across reboots):**

| Command | Effect |
|---------|--------|
| `!wifi_ssid <SSID>` | Store new WiFi SSID in NVS |
| `!wifi_pass <PASSWORD>` | Store new WiFi password in NVS |
| `!wifi_ip <IP>` | Store new static IP in NVS (default: `192.168.1.220`) |
| `!agent_ip <IP>` | Store new micro-ROS agent IP in NVS (default: `192.168.1.104`) |
| `!agent_port <PORT>` | Store new micro-ROS agent UDP port in NVS (default: `8888`) |

**Action commands:**

| Command | Effect |
|---------|--------|
| `!reconnect` | Disconnect WiFi + micro-ROS, reconnect with current NVS settings |
| `!restart` | Full ESP32 restart |
| `!nvs_dump` | Show all NVS key-value pairs (for debugging) |
| `!nvs_reset` | Erase all NVS data, revert to compiled defaults on next boot |

### Status LED (WS2812 on GPIO48)

| Color | Meaning |
|-------|---------|
| Red (solid) | No WiFi connection |
| Yellow (solid) | WiFi connected, no micro-ROS agent |
| Green (solid) | Fully connected, idle |
| Green (blinking) | Fully connected, data flowing |
| Blue (blinking) | Firmware update mode |

## 5. Motor ESP32 Firmware Changes (MINIMAL)

The Motor ESP32-S3 keeps its existing Arduino firmware with one change: serial communication switches from USB-CDC (`Serial`) to hardware UART (`Serial1`) on GPIO17/18.

### Changes Required

**File:** `hardware/ESP32-S3–WROOM/examples/10_at8236_motor_control/10_at8236_motor_control.ino`

1. Add UART pin definitions:
   ```cpp
   #define GATEWAY_TX_PIN  17   // UART1 TX to Gateway
   #define GATEWAY_RX_PIN  18   // UART1 RX from Gateway
   #define GATEWAY_BAUD    921600
   ```

2. In `setup()`, initialize `Serial1` for Gateway communication:
   ```cpp
   Serial1.begin(GATEWAY_BAUD, SERIAL_8N1, GATEWAY_RX_PIN, GATEWAY_TX_PIN);
   ```

3. Replace all `Serial.println()` / `Serial.read()` / `Serial.write()` with `Serial1` equivalents for host communication. Keep `Serial` (USB-CDC) for debug output.

4. Apply the same changes to `hardware/esp32_bst4wd_firmware/esp32_bst4wd_firmware.ino` (alternate motor driver firmware).

**No changes to:** Motor control logic, encoder PCNT, watchdog, dead zone, GPIO pin recovery, serial protocol format.

## 6. LIDAR ESP32 Firmware Changes (MINIMAL)

The LIDAR ESP32-WROOM-32 keeps its existing Arduino firmware with one change: host communication switches from UART0/USB (`Serial`) to UART1 (`Serial1`) on GPIO4/15.

### Changes Required

**File:** `hardware/esp32_xv11_bridge/esp32_xv11_bridge.ino`

1. Add UART pin definitions:
   ```cpp
   #define GATEWAY_TX_PIN  4    // UART1 TX to Gateway
   #define GATEWAY_RX_PIN  15   // UART1 RX from Gateway
   #define GATEWAY_BAUD    921600
   ```

2. In `setup()`, initialize `Serial1`:
   ```cpp
   Serial1.begin(GATEWAY_BAUD, SERIAL_8N1, GATEWAY_RX_PIN, GATEWAY_TX_PIN);
   ```

3. Replace `Serial.write(byte)` in the LIDAR forwarding loop with `Serial1.write(byte)`. Replace `Serial.available()` / `Serial.read()` in command processing with `Serial1` equivalents. Keep `Serial` (UART0/CP2102) for USB debug.

**No changes to:** XV11 UART2 communication, RPM regulation, packet parsing, motor PWM control.

## 7. Mac-Side Changes

### New Processes to Run

| Process | What It Does | How to Start |
|---------|-------------|-------------|
| **micro-ROS Agent** | Bridges ESP32 micro-ROS ↔ ROS2 DDS | `ros2 run micro_ros_agent micro_ros_agent udp4 --port 8888` |
| **robot_state_publisher** | Publishes URDF TF tree (base_link→laser_frame, etc.) | `ros2 run robot_state_publisher robot_state_publisher --ros-args -p robot_description:="$(cat ~/robots/rovac/ros2_ws/src/tank_description/urdf/tank.urdf)"` |
| **cmd_vel_mux** | Priority routing: joystick > obstacle > navigation → /cmd_vel | `python3 ~/robots/rovac/ros2_ws/src/tank_description/tank_description/cmd_vel_mux.py` |
| **joy_node** | Reads PS2 USB receiver on Mac | `ros2 run joy joy_node` |
| **ps2_joy_mapper_node** | Maps PS2 /joy → /cmd_vel_joy | `python3 ~/robots/rovac/scripts/ps2_joy_mapper_node.py` |
| **static TF (map→odom)** | Fallback when SLAM is not running | `ros2 run tf2_ros static_transform_publisher 0 0 0 0 0 0 map odom` |

### New Mac Bringup Script

A new script `scripts/mac_wireless_bringup.sh` replaces `standalone_control.sh`:

```bash
# Usage: ./scripts/mac_wireless_bringup.sh [start|stop|status]
# Starts: micro-ROS agent, robot_state_publisher, cmd_vel_mux,
#         joy_node, ps2_mapper, static TF
# Optional: slam, nav, foxglove (via mac_brain_launch.sh)
```

Bringup script requirements:
- Activate the `ros_jazzy` conda env and source `config/ros2_env.sh` first (so `ROS_DOMAIN_ID=42` and CycloneDDS settings are consistent across all processes)
- Start the micro-ROS Agent in the same environment as the rest of the ROS2 graph

### Install micro-ROS Agent on Mac

```bash
# Option 1: Install from apt/brew (if available for Jazzy)
# Option 2: Build from source
cd ~/robots/rovac/ros2_ws
git clone -b jazzy https://github.com/micro-ROS/micro-ROS-Agent.git src/micro_ros_agent
colcon build --packages-select micro_ros_agent
```

### DDS Configuration Changes

**`config/ros2_env.sh`** — Update:
- Edge IP is no longer required for runtime (no Pi/Lenovo participants)
- The micro-ROS Agent communicates with the Gateway over UDP (this is separate from DDS peer discovery)
- Keep CycloneDDS unicast behavior consistent with the existing setup: include the Mac's own IP as a peer (multicast is disabled)
- If you want the "any ROS2 machine can interact" goal, add those machines as CycloneDDS peers (or maintain a separate "LAN" CycloneDDS profile)

**`config/cyclonedds_mac.xml`** — Simplify:
- Keep `<Peer address="192.168.1.104"/>` for local Mac participant discovery (unicast-only)
- Remove the Linux edge peer (Lenovo/Pi) from `<Peers>` if it is no longer present
- Optionally add additional LAN peers if you want other machines to join the ROS2 graph

### Files to Remove/Update in config/

| File | Action |
|------|--------|
| `config/cyclonedds_pi.xml` | Legacy (keep for reference) |
| `config/cyclonedds_lenovo.xml` | Legacy (keep for reference) |
| `config/fastdds_pi.xml` | Legacy (keep for reference) |
| `config/fastdds_peers.xml` | Legacy (keep for reference) |
| `config/udev/99-rovac-esp32.rules` | Legacy (keep for reference) |
| `config/udev/99-rovac-lenovo.rules` | Legacy (keep for reference) |
| `config/cyclonedds_mac.xml` | **Update** (remove edge peer, keep Mac self peer) |
| `config/ros2_env.sh` | **Update** (no edge required; keep LAN option) |
| `config/slam_params.yaml` | **Keep** (unchanged) |
| `config/nav2_params.yaml` | **Keep** (unchanged) |

### Systemd Services — All Obsolete

All files in `config/systemd/` become historical reference. They are not deployed anywhere in the new architecture. The Mac uses a bringup script (not systemd).

| Service | Replacement |
|---------|-------------|
| `rovac-edge-esp32.service` | Gateway micro-ROS (cmd_vel → motor, encoder → odom) |
| `rovac-edge-lidar.service` | Gateway micro-ROS (XV11 parsing → /scan) |
| `rovac-edge-mux.service` | `cmd_vel_mux.py` on Mac |
| `rovac-edge-tf.service` | `robot_state_publisher` on Mac |
| `rovac-edge-map-tf.service` | `static_transform_publisher` on Mac |
| `rovac-edge-obstacle.service` | Dropped for now (LIDAR provides obstacle detection via Nav2 costmap) |
| `rovac-edge-supersensor.service` | Dropped for now (future: ESP32 replacement) |
| `rovac-edge-ps2-joy.service` | `joy_node` on Mac (PS2 receiver plugged into Mac) |
| `rovac-edge-ps2-mapper.service` | `ps2_joy_mapper_node.py` on Mac |

## 8. ROS2 Topic Mapping

| Topic | Old Source | New Source | Consumers |
|-------|-----------|-----------|-----------|
| `/scan` | `xv11_lidar_publisher.py` on Lenovo | Gateway ESP32 micro-ROS | SLAM, Nav2, Foxglove |
| `/odom` | `esp32_at8236_driver.py` on Lenovo | Gateway ESP32 micro-ROS | Nav2, Foxglove |
| `/tf` (`odom→base_link`) | `esp32_at8236_driver.py` on Lenovo | **Gateway ESP32 micro-ROS** (only this one dynamic transform) | SLAM, Nav2 |
| `/tf` (`base_link→laser_frame`, etc.) | `robot_state_publisher` on Lenovo | **`robot_state_publisher` on Mac** (all static URDF transforms) | SLAM, Nav2 |
| `/tf` (`map→odom`) | N/A (SLAM on Lenovo was not active) | **SLAM Toolbox / AMCL on Mac** | Nav2 |
| `/cmd_vel` | `cmd_vel_mux.py` on Lenovo | `cmd_vel_mux.py` on Mac → micro-ROS Agent → Gateway | Gateway → Motor ESP32 |
| `/cmd_vel_joy` | `ps2_joy_mapper_node.py` on Lenovo | `ps2_joy_mapper_node.py` on Mac | cmd_vel_mux |
| `/diagnostics` | `esp32_at8236_driver.py` on Lenovo | Gateway ESP32 micro-ROS | Foxglove |

## 9. Repository File Changes

### New Files to Create

| File | Purpose |
|------|---------|
| `hardware/esp32_gateway/` | New directory for Gateway ESP32-S3 firmware |
| `hardware/esp32_gateway/main/gateway_main.c` | Gateway application entry point |
| `hardware/esp32_gateway/main/uart_motor.c/h` | Motor ESP32 UART handler (parse E, send M) |
| `hardware/esp32_gateway/main/uart_lidar.c/h` | LIDAR ESP32 UART handler (parse XV11 packets) |
| `hardware/esp32_gateway/main/odometry.c/h` | Differential drive odometry (arc integration) |
| `hardware/esp32_gateway/main/lidar_scan.c/h` | LIDAR revolution accumulation |
| `hardware/esp32_gateway/main/microros_app.c/h` | micro-ROS publishers/subscribers/TF |
| `hardware/esp32_gateway/main/wifi_manager.c/h` | WiFi STA + mDNS + reconnection |
| `hardware/esp32_gateway/main/debug_console.c/h` | USB-CDC debug shell |
| `hardware/esp32_gateway/main/status_led.c/h` | WS2812 connection status |
| `hardware/esp32_gateway/CMakeLists.txt` | ESP-IDF build configuration |
| `hardware/esp32_gateway/sdkconfig.defaults` | ESP-IDF SDK config (partition, WiFi, UART, PSRAM) |
| `hardware/esp32_gateway/README.md` | Gateway documentation |
| `scripts/mac_wireless_bringup.sh` | Mac bringup script for wireless architecture |

### Existing Files to Modify

| File | Change |
|------|--------|
| `hardware/ESP32-S3–WROOM/examples/10_at8236_motor_control/10_at8236_motor_control.ino` | Add Serial1 UART on GPIO17/18, dual-serial support |
| `hardware/esp32_bst4wd_firmware/esp32_bst4wd_firmware.ino` | Same Serial1 change |
| `hardware/esp32_xv11_bridge/esp32_xv11_bridge.ino` | Add Serial1 UART on GPIO4/15, dual-serial support |
| `config/ros2_env.sh` | Remove edge IP, simplify for Mac-only |
| `config/cyclonedds_mac.xml` | Remove edge peer, add localhost |
| `scripts/ps2_joy_mapper_node.py` | Minor: ensure it works on Mac (topic names, joy device) |
| `scripts/mac_brain_launch.sh` | Remove Pi connectivity check |
| `robot_mcp_server/start_mcp_server.sh` | Update for Mac conda environment |
| `CLAUDE.md` | Update architecture description, quick reference, hardware table |

### Existing Files — No Changes Needed

| File | Why |
|------|-----|
| `ros2_ws/src/tank_description/urdf/tank.urdf` | URDF is robot-geometry, not architecture-dependent |
| `config/slam_params.yaml` | SLAM consumes /scan regardless of source |
| `config/nav2_params.yaml` | Nav2 consumes /odom, /scan, /tf regardless of source |
| `foxglove_layouts/*.json` | Foxglove subscribes to standard topics |
| `ros2_ws/src/rf2o_laser_odometry/` | Optional laser odom, runs on Mac, no changes |
| `robot_mcp_server/mcp_server.py` | Already handles ROS2 topics generically |

### Files That Become Legacy/Historical

These files no longer have a runtime role but should be kept in the repo for reference:

| Directory/File | Reason |
|---------------|--------|
| `config/systemd/` | Historical reference for edge service architecture |
| `config/cyclonedds_pi.xml`, `cyclonedds_lenovo.xml` | Historical |
| `config/udev/` | Historical |
| `scripts/standalone_control.sh` | Replaced by `mac_wireless_bringup.sh` |
| `scripts/install_lenovo_systemd.sh` | No Lenovo |
| `scripts/install_pi_systemd.sh` | No Pi |
| `scripts/deploy_core_pi.sh` | No Pi |
| `scripts/pi_edge_launch.sh` | No Pi |
| `hardware/esp32_at8236_driver/esp32_at8236_driver.py` | Replaced by Gateway micro-ROS |
| `hardware/esp32_at8236_driver/launch_esp32_at8236.sh` | Replaced by Gateway micro-ROS |
| `ros2_ws/src/xv11_lidar_python/` | Replaced by Gateway micro-ROS |
| `ros2_ws/src/vorwerk_lidar/` | Replaced by Gateway micro-ROS |

## 10. Implementation Phases

### Phase 1: Gateway Firmware (Estimated: largest effort)

1. Set up ESP-IDF v5.2 development environment on Mac
2. Create `hardware/esp32_gateway/` project with micro_ros_espidf_component
3. Implement WiFi STA + mDNS + auto-reconnect
4. Implement UART1 handler (Motor ESP32 protocol: parse `E`, send `M`)
5. Implement UART2 handler (LIDAR binary stream: parse XV11 packets)
6. Port odometry computation from Python to C (arc integration, covariance)
7. Port LIDAR scan accumulation from Python to C (revolution detection, range extraction)
8. Port differential drive kinematics from Python to C
9. Implement micro-ROS publishers (/odom, /scan, /tf, /diagnostics)
10. Implement micro-ROS subscriber (/cmd_vel)
11. Implement reconnection state machine
12. Implement USB-CDC debug console
13. Implement WS2812 status LED
14. Test with micro-ROS Agent on Mac

### Phase 2: Peripheral ESP32 Firmware Changes

1. Modify Motor ESP32 firmware: add Serial1 on GPIO17/18 at 921600 baud
2. Add dual-serial support: Serial1 for Gateway, Serial (USB-CDC) for debug
3. Flash and test Motor ESP32 with Gateway connected via UART
4. Modify LIDAR ESP32 firmware: add Serial1 on GPIO4/15 at 921600 baud
5. Add dual-serial support: Serial1 for Gateway, Serial (UART0/CP2102) for debug
6. Flash and test LIDAR ESP32 with Gateway connected via UART

### Phase 3: Mac-Side Setup

1. Install micro-ROS Agent on Mac (build from source for Jazzy)
2. Create `scripts/mac_wireless_bringup.sh` bringup script
3. Update `config/ros2_env.sh` (remove edge IP references)
4. Update `config/cyclonedds_mac.xml` (remove edge peer, keep Mac self peer; LAN peers optional)
5. Adapt `scripts/ps2_joy_mapper_node.py` for Mac (verify topic names)
6. Test PS2 controller → joy_node → mapper → /cmd_vel_joy on Mac
7. Test full topic chain: /cmd_vel_joy → mux → /cmd_vel → Agent → Gateway → Motor ESP32

### Phase 4: Integration Testing

1. Verify /scan on Mac (SLAM Toolbox can map)
2. Verify /odom on Mac (Nav2 can navigate)
3. Verify /tf chain (rviz2 shows correct robot pose)
4. Test PS2 driving with full wireless stack
5. Test SLAM mapping session
6. Test Nav2 autonomous navigation
7. Measure end-to-end latency (cmd_vel → motor response)
8. Test WiFi disconnection and reconnection recovery
9. Long-duration stability test (1+ hours continuous operation)

### Phase 5: Documentation and Cleanup

1. Update `CLAUDE.md` with new architecture
2. Update `docs/architecture/` with verified architecture document
3. Update `docs/guides/bringup.md` for wireless bringup
4. Update MEMORY.md with new architecture details
5. Move legacy files to `archive/` (optional)

## 11. Testing Plan

**macOS note:** when using `ros2 topic ...` commands, prefer `--no-daemon` (the ROS2 daemon can hang with CycloneDDS on macOS).

### Unit Tests (per component)

| Component | Test Method |
|-----------|-------------|
| Motor ESP32 Serial1 | Connect USB debug, send M commands via Serial1, verify motor response |
| LIDAR ESP32 Serial1 | Connect USB debug, verify XV11 data streams on Serial1 |
| Gateway UART parsing | Send known E/M data on UART, verify parsing via USB debug |
| Gateway odometry | Send known encoder sequences, verify computed pose matches expected |
| Gateway LIDAR accumulation | Send known XV11 packets, verify LaserScan output |
| Gateway micro-ROS | Run Agent on Mac, verify topics appear with `ros2 topic list --no-daemon` |

### Integration Tests

| Test | Pass Criteria |
|------|--------------|
| `/scan` visible on Mac | `ros2 topic hz /scan --no-daemon` shows ~5 Hz |
| `/odom` visible on Mac | `ros2 topic hz /odom --no-daemon` shows ~20 Hz |
| `/tf` chain complete | `ros2 run tf2_ros tf2_echo map base_link` resolves |
| PS2 → motor | Joystick input moves motors within 50ms |
| SLAM mapping | `slam_toolbox` produces occupancy grid from /scan |
| Nav2 navigation | Robot navigates to goal pose autonomously |
| WiFi disconnect | Motors stop within 1.5s (1s ESP32 watchdog + 0.5s margin) |
| WiFi reconnect | Topics resume within 5s of WiFi restoration |
| 1-hour stability | No crashes, no pose drift beyond expected encoder error |

## 12. Power Budget

| Component | Current | Voltage | Power |
|-----------|---------|---------|-------|
| Motor ESP32-S3 (no WiFi) | ~80 mA | 3.3V | 0.3W |
| LIDAR ESP32-WROOM (no WiFi) | ~80 mA | 3.3V | 0.3W |
| Gateway ESP32-S3 (WiFi active) | ~240 mA | 3.3V | 0.8W |
| XV11 LIDAR motor | ~400 mA | 5V | 2.0W |
| **Total electronics** | | | **~3.4W** |
| Drive motors (2×, moderate load) | ~1-2A | 12V | 12-24W |
| **Total with drive motors** | | | **~15-28W** |

Compare to previous architecture: Lenovo alone = **65W**. This is a **~70% power reduction**.

## 13. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| micro-ROS reconnection failure (unrecoverable state) | Medium | High | State machine with ESP.restart() as last resort. Motor ESP32 watchdog provides independent safety. |
| WiFi latency spikes (>100ms) | Low | Medium | Motor ESP32 1s watchdog. Odometry continues locally on Gateway during spike. |
| LaserScan too large for micro-ROS UDP | Low | High | Configure RMW buffer ≥4096 bytes. Fragment if needed. Test early in Phase 1. |
| ESP-IDF + micro-ROS build complexity | Medium | Medium | Follow official micro_ros_espidf_component examples. ESP32-S3 is a supported target. |
| UART data corruption (vibration, loose wires) | Low | Medium | 921600 baud over <30cm is reliable. Add UART RX buffer overflow monitoring. Solder connections for production. |
| micro-ROS Agent crash on Mac | Low | Medium | Wrap in supervisor script with auto-restart. Gateway reconnection state machine handles agent restarts. |

## 14. Future Extensibility

### Adding a New ESP32 Sensor Node

When the Gateway's UART ports are full (UART1 = motor, UART2 = LIDAR, UART0 = debug):

**Option A:** Give the new ESP32 its own WiFi + micro-ROS. It connects directly to the micro-ROS Agent on the Mac. No Gateway involvement.

**Option B:** Replace the Arduino Nano super sensor with an ESP32 running micro-ROS over WiFi. Each new sensor ESP32 is an independent micro-ROS client.

**Option C:** Use the Gateway's UART0 (sacrifice USB debug for a third UART channel). Debug via WiFi status topics instead.

### Upgrading to Zenoh (Future)

When `rmw_zenoh_pico` matures (estimated 2027+), the Gateway could switch from XRCE-DDS to Zenoh, eliminating the need for the micro-ROS Agent entirely. The Gateway would participate directly in the ROS2 DDS network. No Mac-side agent process needed.

## 15. Open Questions

1. **micro-ROS Agent on Mac:** Is `ros-jazzy-micro-ros-agent` available as a pre-built package for macOS/conda, or must it be built from source?
2. **LaserScan message size:** Need to verify that a 360-point LaserScan serializes within the XRCE-DDS UDP MTU, or determine fragmentation requirements.
3. **PS2 controller on Mac:** Does the ShanWan ZD-V+ USB receiver work on macOS without the `SDL_JOYSTICK_HIDAPI=0` workaround (which was Linux-specific)?
4. **ESP-IDF on Mac:** Verify ESP-IDF v5.2+ toolchain installs cleanly on macOS (Apple Silicon).
