# Super Sensor Module

A plug-and-play USB sensor array for robotics applications featuring:
- 4x HC-SR04 ultrasonic sensors (wide-angle coverage)
- RGB LED indicator
- Pan servo for sweeping scans
- Simple JSON serial protocol
- ROS2 integration for ROVAC robot

## Quick Start (ROVAC)

The Super Sensor is pre-configured as a systemd service on the ROVAC Raspberry Pi:

```bash
# Check service status
sudo systemctl status rovac-edge-supersensor.service

# View logs
sudo journalctl -u rovac-edge-supersensor.service -f

# Restart if needed
sudo systemctl restart rovac-edge-supersensor.service
```

**Device symlink:** `/dev/super_sensor` → USB hub port 4-1.4

## Hardware Requirements

| Component | Qty | Notes |
|-----------|-----|-------|
| Arduino Nano | 1 | CH340 or FTDI USB chip |
| HC-SR04 Ultrasonic | 4 | Standard 5V version |
| RGB LED Module | 1 | Common cathode (R, G, B, GND pins) |
| Hitec HS-322HD Servo | 1 | Or similar 5V servo |
| 330Ω Resistors | 3 | For RGB LED (if no built-in limiting) |

### Optional (Recommended)
- External 5V 1A power supply for servo under heavy loads
- 100µF capacitor across servo power rails

## Wiring Diagram

```
                          ARDUINO NANO
                     ┌───────────────────┐
                     │     [USB-B]       │
                     │                   │
  US1 Trig ──────────┤ D2            VIN ├──── External 5V (optional)
  RGB Red ───[330Ω]──┤ D3/PWM        GND ├──── Common Ground
  US1 Echo ──────────┤ D4            RST │
  RGB Green ─[330Ω]──┤ D5/PWM         5V ├──── 5V Bus
  RGB Blue ──[330Ω]──┤ D6/PWM         A7 │
  US2 Trig ──────────┤ D7             A6 │
  US2 Echo ──────────┤ D8             A5 │
  Servo PWM ─────────┤ D9/PWM         A4 │
                     │ D10            A3 │
                     │ D11            A2 ├──── US4 Echo
  US3 Trig ──────────┤ D12            A1 ├──── US4 Trig
                     │ D13            A0 ├──── US3 Echo
                     │               REF │
                     └───────────────────┘

Physical Sensor Positions (on robot):
  - US1 (D2/D4)  = front_top
  - US2 (D7/D8)  = left
  - US3 (D12/A0) = right
  - US4 (A1/A2)  = front_bottom
```

## Pin Reference Table

| Arduino Pin | Component | Wire/Function |
|-------------|-----------|---------------|
| D2 | Ultrasonic 1 (Front-Top) | Trigger |
| D3 | RGB LED | Red (PWM) |
| D4 | Ultrasonic 1 (Front-Top) | Echo |
| D5 | RGB LED | Green (PWM) |
| D6 | RGB LED | Blue (PWM) |
| D7 | Ultrasonic 2 (Left) | Trigger |
| D8 | Ultrasonic 2 (Left) | Echo |
| D9 | Servo | PWM Signal (Yellow) |
| D12 | Ultrasonic 3 (Right) | Trigger |
| A0 | Ultrasonic 3 (Right) | Echo |
| A1 | Ultrasonic 4 (Front-Bottom) | Trigger |
| A2 | Ultrasonic 4 (Front-Bottom) | Echo |
| 5V | All Components | Power |
| GND | All Components | Ground |

## Serial Protocol

**Baud Rate:** 115200

### Commands

| Command | Description | Response |
|---------|-------------|----------|
| `SCAN` | Read all ultrasonic sensors | `{"us":[ft,l,r,fb]}` |
| `LED r g b` | Set RGB LED (0-255 each) | `{"led":[r,g,b]}` |
| `SERVO angle` | Set servo (0-180°) | `{"servo":angle}` |
| `STATUS` | Full system status | `{"us":[...],"servo":n,"led":[...]}` |
| `SWEEP start end` | Scan while sweeping servo | `{"sweep":[...]}` |
| `PING` | Health check | `PONG` |
| `HELP` | List commands | Command list |

### Example Session

```
> PING
PONG

> SCAN
{"us":[45,52,120,89]}

> LED 255 0 0
{"led":[255,0,0]}

> SERVO 90
{"servo":90}

> STATUS
{"us":[45,52,120,89],"servo":90,"led":[255,0,0]}
```

## ROS2 Integration

### Systemd Service (ROVAC)

The Super Sensor runs as a systemd service on the ROVAC robot:

```bash
# Service file: /etc/systemd/system/rovac-edge-supersensor.service
# Part of: rovac-edge.target

sudo systemctl status rovac-edge-supersensor.service
sudo systemctl restart rovac-edge-supersensor.service
sudo journalctl -u rovac-edge-supersensor.service -f
```

### Manual Launch

```bash
source /opt/ros/jazzy/setup.bash
python3 super_sensor_ros2_node.py --ros-args \
  -p port:=/dev/super_sensor \
  -p publish_rate:=10.0 \
  -p obstacle_threshold:=30
```

### Published Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/super_sensor/range/front_top` | sensor_msgs/Range | Front-top ultrasonic (meters) |
| `/super_sensor/range/front_bottom` | sensor_msgs/Range | Front-bottom ultrasonic (meters) |
| `/super_sensor/range/left` | sensor_msgs/Range | Left ultrasonic (meters) |
| `/super_sensor/range/right` | sensor_msgs/Range | Right ultrasonic (meters) |
| `/super_sensor/ranges` | std_msgs/Float32MultiArray | All ranges [ft,l,r,fb] in meters |
| `/super_sensor/obstacle_detected` | std_msgs/Bool | True if any sensor < threshold |
| `/super_sensor/status` | std_msgs/String | JSON status message |

### Subscribed Topics (Control)

| Topic | Type | Description |
|-------|------|-------------|
| `/super_sensor/led_cmd` | std_msgs/Int32MultiArray | Set LED [R, G, B] (0-255) |
| `/super_sensor/servo_cmd` | std_msgs/Int32MultiArray | Set servo angle [0-180] |

### Services

| Service | Type | Description |
|---------|------|-------------|
| `/super_sensor/sweep` | std_srvs/Trigger | Perform 180° sweep scan |

### ROS2 Usage Examples

```bash
# View all topics
ros2 topic list | grep super_sensor

# Echo range data
ros2 topic echo /super_sensor/range/front_top

# Echo all ranges
ros2 topic echo /super_sensor/ranges

# Set LED to red
ros2 topic pub --once /super_sensor/led_cmd std_msgs/Int32MultiArray "{data: [255, 0, 0]}"

# Set LED to green
ros2 topic pub --once /super_sensor/led_cmd std_msgs/Int32MultiArray "{data: [0, 255, 0]}"

# Set servo to 90 degrees
ros2 topic pub --once /super_sensor/servo_cmd std_msgs/Int32MultiArray "{data: [90]}"

# Trigger sweep scan
ros2 service call /super_sensor/sweep std_srvs/srv/Trigger
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `port` | string | `/dev/super_sensor` | Serial port path |
| `publish_rate` | float | 10.0 | Publish rate in Hz |
| `obstacle_threshold` | int | 30 | Obstacle distance threshold (cm) |
| `frame_id` | string | `super_sensor_link` | TF frame ID |

## udev Rules

The device is assigned a stable symlink via udev rules:

```bash
# /etc/udev/rules.d/99-rovac-usb.rules
SUBSYSTEM=="tty", KERNELS=="4-1.4", MODE="0666", GROUP="dialout", SYMLINK+="super_sensor"
```

This ensures `/dev/super_sensor` always points to the correct USB port regardless of enumeration order.

## Python Driver

### Installation

```bash
pip install pyserial
```

### Quick Start

```python
from super_sensor_driver import SuperSensor

sensor = SuperSensor()
sensor.connect()

# Read all sensors
scan = sensor.scan()
print(f"Front Top: {scan.front_left}cm")
print(f"Front Bottom: {scan.right}cm")
print(f"Left: {scan.front_right}cm")
print(f"Right: {scan.left}cm")
print(f"Obstacle: {scan.has_obstacle}")

# Control LED
sensor.set_led(255, 0, 0)  # Red
sensor.set_led(0, 255, 0)  # Green

# Control servo
sensor.set_servo(90)

sensor.disconnect()
```

### CLI Usage

```bash
# List available ports
python super_sensor_driver.py --list-ports

# Read sensors
python super_sensor_driver.py scan

# Set LED
python super_sensor_driver.py led 0 255 0

# Set servo
python super_sensor_driver.py servo 90

# Get status
python super_sensor_driver.py status
```

## Troubleshooting

### No Response from Arduino
1. Check USB connection: `ls -la /dev/super_sensor`
2. Verify service is running: `sudo systemctl status rovac-edge-supersensor`
3. Check logs: `sudo journalctl -u rovac-edge-supersensor -n 50`
4. Wait 2 seconds after connecting (Arduino resets)

### Erratic Readings
1. Add 5ms+ delay between sensor readings (already in firmware)
2. Check for acoustic interference between sensors
3. Verify 5V power is stable (try external supply)
4. Add 100µF capacitor near sensors

### Servo Jitter
1. Add 100µF capacitor across servo power
2. Use external 5V supply for servo
3. Check servo signal wire (D9)

### LED Not Working
1. Check LED polarity (common cathode = GND shared)
2. Verify 330Ω resistors are installed
3. Test each color via ROS2:
   ```bash
   ros2 topic pub --once /super_sensor/led_cmd std_msgs/Int32MultiArray "{data: [255, 0, 0]}"
   ```

## Files

```
super_sensor/
├── firmware/
│   └── super_sensor/
│       └── super_sensor.ino       # Arduino firmware
├── super_sensor_driver.py         # Python driver + CLI
├── super_sensor_ros2_node.py      # ROS2 node
├── super_sensor_cli/              # CLI installer app
├── super_sensor_gui/              # GUI app (macOS/Linux)
├── offline_deps/                  # Bundled dependencies
│   ├── pyserial/                  # pyserial wheel
│   └── arduino-cli/               # arduino-cli binaries
└── README.md                      # This file
```
