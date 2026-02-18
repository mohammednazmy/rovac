# Yahboom ROS Robot Expansion Board V3.0

## Status: **ACTIVE - Primary Motor/IMU Controller**

The main motor control and IMU board for the ROVAC robot. Successfully integrated January 2025, replacing the BST-4WD V4.2 board.

## Quick Reference

| Property | Value |
|----------|-------|
| Device Path | `/dev/yahboom_board` |
| Baud Rate | 115200 |
| Firmware | V3.5 |
| Driver Library | Rosmaster_Lib v3.3.9 |
| ROS2 Service | `rovac-edge-yahboom.service` |
| USB Port | 4-1.2 (via udev symlink) |

## Key Specifications

| Specification | Value |
|---------------|-------|
| Microcontroller | STM32F103RCT6 (ARM Cortex-M3, 72MHz) |
| IMU Sensor | MPU9250 (9-axis: accel + gyro + mag) |
| Input Voltage | 6-12V DC |
| Motor Channels | 4x encoder motor drivers (2A each) |
| PWM Servo Channels | 4x (0-180°) |
| Bus Servo Channels | 6x (serial protocol) |
| Communication | USB Serial (CH340), UART, CAN, SBUS |
| Power Output | 5V/5A USB-C (powers Pi 5) |

## Detailed Specifications

### MCU - STM32F103RCT6

| Spec | Value |
|------|-------|
| Core | ARM Cortex-M3 (32-bit) |
| Clock | 72 MHz |
| Flash | 256 KB |
| RAM | 48 KB |
| GPIO | 51 pins |
| ADC | 16-channel 12-bit |
| PWM | 8 channels |

### IMU - MPU9250

| Sensor | Range | Resolution |
|--------|-------|------------|
| Accelerometer | ±2/±4/±8/±16g | 16-bit |
| Gyroscope | ±250/±500/±1000/±2000 °/s | 16-bit |
| Magnetometer | ±4800 µT | 14-bit |
| Sample Rate | Up to 1000 Hz (accel/gyro), 100 Hz (mag) |

### Motor Drivers

| Spec | Value |
|------|-------|
| Channels | 4 (M1, M2, M3, M4) |
| Chip | AM2875 H-bridge |
| Continuous Current | 2A per channel |
| Voltage | 6-12V (direct from input) |
| Encoder Support | Quadrature (A/B signals) |
| PWM Frequency | 20 kHz |

## ROS2 Integration

### Published Topics

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/imu/data` | sensor_msgs/Imu | 50 Hz | Accel, gyro, orientation |
| `/imu/mag` | sensor_msgs/MagneticField | 50 Hz | Magnetometer data |
| `/odom` | nav_msgs/Odometry | 20 Hz | Wheel odometry |
| `/wheel_encoders` | std_msgs/Int32MultiArray | 20 Hz | Raw encoder ticks [M1,M2,M3,M4] |
| `/battery_voltage` | std_msgs/Float32 | 1 Hz | Battery voltage (V) |

### Subscribed Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/cmd_vel` | geometry_msgs/Twist | Velocity commands (vx, vy, vz) |

### TF Frames

- Publishes: `odom` → `base_link` transform (20 Hz)
- IMU frame: `imu_link`

### Service Management

```bash
# Check service status
sudo systemctl status rovac-edge-yahboom

# View logs
sudo journalctl -u rovac-edge-yahboom -f

# Restart service
sudo systemctl restart rovac-edge-yahboom
```

## Python Driver API

### Installation

```bash
cd /home/pi/hardware/yahboom-ros-expansion-board-v3/py_install
sudo python3 setup.py install
```

### Basic Usage

```python
from Rosmaster_Lib import Rosmaster
import time

# Initialize (car_type: 1=X3, 2=X3_PLUS, 4=X1, 5=R2)
bot = Rosmaster(car_type=1, com="/dev/yahboom_board")
bot.create_receive_threading()
bot.set_auto_report_state(True)
time.sleep(0.3)

# Read firmware version
version = bot.get_version()  # Returns: 3.5

# Read battery voltage
voltage = bot.get_battery_voltage()  # Returns: 12.0 (Volts)
```

### Motor Control

```python
# Velocity control (recommended)
# vx: forward/back [-1.0, 1.0] m/s
# vy: left/right [-1.0, 1.0] m/s
# vz: rotation [-5.0, 5.0] rad/s
bot.set_car_motion(vx=0.5, vy=0.0, vz=0.0)  # Forward

# Direct PWM control [-100, 100]
bot.set_motor(m1=50, m2=50, m3=50, m4=50)

# Preset motions
# state: 0=stop, 1=forward, 2=backward, 3=left, 4=right, 5=spin_left, 6=spin_right
bot.set_car_run(state=1, speed=50)

# Stop
bot.set_car_motion(0, 0, 0)
```

### IMU Data

```python
# Accelerometer (m/s²)
ax, ay, az = bot.get_accelerometer_data()

# Gyroscope (rad/s)
gx, gy, gz = bot.get_gyroscope_data()

# Magnetometer (µT)
mx, my, mz = bot.get_magnetometer_data()

# Attitude angles (degrees)
roll, pitch, yaw = bot.get_imu_attitude_data(ToAngle=True)

# Attitude angles (radians)
roll, pitch, yaw = bot.get_imu_attitude_data(ToAngle=False)
```

### Encoders

```python
# Get cumulative encoder ticks
m1, m2, m3, m4 = bot.get_motor_encoder()

# Get velocity (m/s)
vx, vy, vz = bot.get_motion_data()
```

### Servo Control

```python
# PWM servo (id: 1-4, angle: 0-180)
bot.set_pwm_servo(servo_id=1, angle=90)

# All PWM servos at once
bot.set_pwm_servo_all(s1=90, s2=90, s3=90, s4=90)

# Bus servo (id: 1-254, pulse: 96-4000, time: 0-2000ms)
bot.set_uart_servo(servo_id=1, pulse_value=2000, run_time=500)
```

### Utilities

```python
# Buzzer (duration in ms, 0=off, 1=continuous)
bot.set_beep(100)

# RGB LED strip (led_id: 0-13 or 0xFF for all)
bot.set_colorful_lamps(led_id=0xFF, red=255, green=0, blue=0)

# LED effects (0=off, 1=flow, 2=marquee, 3=breath, 4=gradient, 5=stars)
bot.set_colorful_effect(effect=3, speed=5)

# PID tuning (kp, ki, kd: 0-10.0)
bot.set_pid_param(kp=0.5, ki=0.1, kd=0.3, forever=True)
pid = bot.get_motion_pid()  # Returns [kp, ki, kd]
```

## Serial Protocol

### Packet Format

```
Byte 0:    0xFF (header)
Byte 1:    0xFC (device ID)
Byte 2:    Length (of remaining bytes)
Byte 3:    Function code
Bytes 4-N: Data (little-endian)
Byte N+1:  Checksum (sum of bytes 2 to N, mod 256)
```

### Key Function Codes

| Code | Function | Direction |
|------|----------|-----------|
| 0x01 | Auto Report Enable | → Board |
| 0x02 | Beep Control | → Board |
| 0x03 | PWM Servo Single | → Board |
| 0x04 | PWM Servo All | → Board |
| 0x05 | RGB LED | → Board |
| 0x06 | RGB Effect | → Board |
| 0x0A | Speed Report | ← Board |
| 0x0B | MPU9250 Raw Data | ← Board |
| 0x0C | IMU Attitude | ← Board |
| 0x0D | Encoder Report | ← Board |
| 0x10 | Motor PWM Direct | → Board |
| 0x11 | Car Run (preset) | → Board |
| 0x12 | Car Motion (vel) | → Board |
| 0x13 | Motor PID | ↔ |
| 0x20 | Bus Servo | → Board |
| 0x51 | Firmware Version | ← Board |

## Wiring Diagram

```
                    YAHBOOM ROS EXPANSION BOARD V3.0
    ┌──────────────────────────────────────────────────────────────┐
    │                                                              │
    │  POWER INPUT                            USB-C OUTPUT         │
    │  ┌─────┐                                ┌─────┐              │
    │  │XT60 │◄── 12V Battery                 │USB-C│──► Pi 5      │
    │  └─────┘    (6-12V)                     └─────┘   (5V/5A)    │
    │                                                              │
    │  ┌─────────────────────┐     ┌─────────────────────┐         │
    │  │     MOTOR OUT       │     │     SERVO OUT       │         │
    │  │  M1   M2   M3   M4  │     │  S1   S2   S3   S4  │         │
    │  │  +−   +−   +−   +−  │     │  ●    ●    ●    ●   │         │
    │  └─────────────────────┘     └─────────────────────┘         │
    │                                                              │
    │  ┌─────────────────────┐     ┌─────────────────────┐         │
    │  │    ENCODER IN       │     │    BUS SERVO        │         │
    │  │ E1   E2   E3   E4   │     │  1  2  3  4  5  6   │         │
    │  │ AB   AB   AB   AB   │     │  ●  ●  ●  ●  ●  ●   │         │
    │  └─────────────────────┘     └─────────────────────┘         │
    │                                                              │
    │  ┌──────────┐  ┌────────┐  ┌────────┐  ┌──────────┐          │
    │  │ MICRO-USB│  │  UART  │  │  CAN   │  │   RGB    │          │
    │  │ (CH340)  │  │  TTL   │  │  Bus   │  │   LED    │          │
    │  └────┬─────┘  └────────┘  └────────┘  └──────────┘          │
    │       │                                                      │
    └───────┼──────────────────────────────────────────────────────┘
            │ USB Cable
            ▼
    Raspberry Pi 5 USB Port
    → /dev/ttyUSB0
    → /dev/yahboom_board (via udev)
```

## udev Configuration

```bash
# /etc/udev/rules.d/99-rovac-usb.rules
SUBSYSTEM=="tty", KERNELS=="4-1.2", MODE="0666", GROUP="dialout", SYMLINK+="yahboom_board"
```

## Troubleshooting

### Board Not Detected

1. Check USB cable (must be data cable, not charge-only)
2. Verify connection: `ls -la /dev/yahboom_board`
3. Check kernel messages: `dmesg | grep CH340`
4. Verify USB port: `lsusb | grep 1a86:7523`

### No IMU Data (all zeros)

1. Call `bot.create_receive_threading()` first
2. Enable auto-report: `bot.set_auto_report_state(True)`
3. Wait for data: `time.sleep(0.5)`
4. Verify version reads: `bot.get_version()` should return 3.5

### Motors Not Moving

1. Check battery voltage (needs 7V+ for motors)
2. Verify beep works: `bot.set_beep(100)`
3. Check motor wiring polarity
4. Test direct PWM: `bot.set_motor(50, 50, 50, 50)`

### Encoder Drift

1. Check PID parameters: `bot.get_motion_pid()`
2. Adjust PID: `bot.set_pid_param(kp, ki, kd, forever=True)`
3. Default may need tuning for your motors

## Files Structure

```
yahboom-ros-expansion-board-v3/
├── README.md                          # This file
├── py_install/                        # Driver installation
│   └── py_install/
│       ├── Rosmaster_Lib/
│       │   ├── __init__.py
│       │   └── Rosmaster_Lib.py      # Driver (1332 lines)
│       ├── setup.py
│       └── README.md
├── 3.Insturction_Manual*.zip         # Official documentation
├── 6.Annex_File/                     # Extracted resources
│   ├── B_ROSMASTER drive library/    # Driver source
│   └── E_HardwareInfo/               # Schematics, protocol docs
│       ├── Communication_Protocol/   # Protocol spreadsheets
│       └── SCH of expansion board/   # Board schematics
└── X3-ROS2-source_code*.zip          # Full ROS2 source (optional)
```

**On Pi:**
```
/home/pi/hardware/yahboom-ros-expansion-board-v3/
├── yahboom_ros2_node.py              # ROS2 node
├── launch_yahboom_node.sh            # Launch script
└── py_install/                       # Driver library
```

## Comparison: BST-4WD V4.2 vs Yahboom V3.0

| Feature | BST-4WD V4.2 | Yahboom V3.0 |
|---------|--------------|--------------|
| Status | **Deprecated** | **Active** |
| MCU | TB6612FNG (motor driver only) | STM32F103RCT6 |
| IMU | External MPU6050 (6-axis) | Integrated MPU9250 (9-axis) |
| Motors | 4x (1.2A continuous) | 4x (2A continuous) |
| Encoders | Limited support | Full quadrature |
| Servos | 2x PWM | 4x PWM + 6x Bus |
| Communication | Basic I2C | USB, UART, CAN, SBUS |
| Pi Power | Separate | Integrated 5V/5A USB-C |
| ROS2 | Custom node | Official SDK + Custom |

## Resources

| Resource | Link |
|----------|------|
| Product Page | [yahboom.net](https://category.yahboom.net/products/ros-driver-board) |
| GitHub | [YahboomTechnology/ROS-robot-expansion-board](https://github.com/YahboomTechnology/ROS-robot-expansion-board) |
| Tutorial | [yahboom.net/study/Pi5-Board](https://www.yahboom.net/study/Pi5-Board) |
| Amazon | [B0CZHPCVLX](https://www.amazon.com/dp/B0CZHPCVLX) |
| Support | support@yahboom.com |
