# Hiwonder ROS Robot Controller V1.2

The active motor/IMU controller board for ROVAC. Replaced the Yahboom ROS Expansion Board V3.0.

## Specifications

| Attribute | Value |
|-----------|-------|
| **MCU** | STM32F407VET6 (Cortex-M4, 168 MHz) |
| **IMU** | QMI8658 (6-axis: accelerometer + gyroscope, **NO magnetometer**) |
| **USB Chips** | 2x CH9102 (`1a86:55d4`) — UART1 + UART2 |
| **Device Path** | `/dev/hiwonder_board` (udev symlink → `/dev/ttyACM0`) |
| **Baud Rate** | 1,000,000 (1 Mbaud) |
| **Protocol** | `[0xAA][0x55][FuncCode][DataLen][Data...][CRC8]` |
| **Motor Channels** | 4 available, 2 active (M1 left, M2 right — tank config) |
| **Encoder Handling** | Internal PID at 100 Hz (TIM7 loop) — NOT sent to host |
| **Motor Config** | TANKBLACK: left motor inverted |
| **Firmware** | RRCLite (source docs at `/home/pi/RRCLite/`) |
| **Motor Switch** | Physical switch on board — must be ON for motors to spin |

## Comparison with Previous Board

| Feature | Yahboom V3.0 (old) | Hiwonder V1.2 (current) |
|---------|---------------------|-------------------------|
| MCU | STM32F103RCT6 (Cortex-M3, 72 MHz) | STM32F407VET6 (Cortex-M4, 168 MHz) |
| IMU | MPU9250 (9-axis: accel + gyro + mag) | QMI8658 (6-axis: accel + gyro only) |
| USB Chip | CH340 (`1a86:7523`) | CH9102 (`1a86:55d4`) |
| Device | `/dev/ttyUSB0` → `/dev/yahboom_board` | `/dev/ttyACM0` → `/dev/hiwonder_board` |
| Baud Rate | 115,200 | 1,000,000 |
| Encoder Data | Sent to host | Internal PID only |
| Odometry | From encoder feedback | Dead-reckoning (commanded speeds + gyro Z) |
| Battery Type | Float64 | Float32 |
| Service | `rovac-edge-yahboom` | `rovac-edge-hiwonder` |

## ROS2 Driver

**File:** `/home/pi/hardware/hiwonder-ros-controller/hiwonder_driver.py`

A standalone ROS2 node (Python script, not a ROS2 package).

### Published Topics

| Topic | Type | Rate | Description |
|-------|------|------|-------------|
| `/imu/data` | `sensor_msgs/Imu` | ~72 Hz | QMI8658 accel (m/s^2) + gyro (rad/s). No orientation (`orientation_covariance[0] = -1`) |
| `/odom` | `nav_msgs/Odometry` | 20 Hz | Dead-reckoning from commanded speeds, uses IMU gyro Z for heading |
| `/battery_voltage` | `std_msgs/Float32` | ~1 Hz | Battery voltage in volts |
| `/diagnostics` | `diagnostic_msgs/DiagnosticArray` | 1 Hz | Board health |
| `odom -> base_link` | TF transform | 20 Hz | Odometry transform |

### Subscribed Topics

| Topic | Type | Description |
|-------|------|-------------|
| `/cmd_vel` | `geometry_msgs/Twist` | Velocity commands (differential drive) |

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `port` | `/dev/ttyACM0` | Serial port |
| `baud` | `1000000` | Baud rate |
| `wheel_separation` | `0.155` | Distance between wheels (m) |
| `wheel_radius` | `0.032` | Wheel radius (m) |
| `max_speed_rps` | `3.0` | Max motor speed (revolutions/s) |
| `motor_left_id` | `0` | Left motor (M1 port) |
| `motor_right_id` | `1` | Right motor (M2 port) |
| `motor_left_flip` | `true` | Invert left motor (TANKBLACK wiring) |
| `motor_right_flip` | `false` | Right motor not inverted |
| `cmd_vel_timeout` | `0.5` | Watchdog timeout (s) — stops motors if no cmd_vel |
| `imu_gyro_scale` | `0.01745329` | Degrees to radians (pi/180) |
| `use_imu_for_heading` | `true` | Use gyro Z for heading in odometry |
| `publish_tf` | `true` | Publish odom -> base_link TF |

## Serial Protocol

### Packet Format

```
[0xAA][0x55][FuncCode][DataLen][Data...][CRC8-MAXIM]
```

### Function Codes Used

| Code | Function | Sub-command | Description |
|------|----------|-------------|-------------|
| `0x03` | FUNC_MOTOR | `0x01` | Set multi-motor speed (r/s, float per motor) |
| `0x03` | FUNC_MOTOR | `0x03` | Stop all motors |
| `0x07` | FUNC_IMU | — | IMU data: 24 bytes = 6 floats (ax, ay, az, gx, gy, gz) |
| `0x00` | FUNC_SYS | `0x04` | Battery voltage (uint16, millivolts) |

## Systemd Service

**File:** `/etc/systemd/system/rovac-edge-hiwonder.service`

```bash
# Check status
sudo systemctl status rovac-edge-hiwonder.service

# View logs
sudo journalctl -u rovac-edge-hiwonder -f

# Restart
sudo systemctl restart rovac-edge-hiwonder.service
```

## Troubleshooting

### Motors not spinning
1. Check the **physical motor power switch** on the board — must be ON
2. Verify USB serial: `ls -la /dev/ttyACM0`
3. Check service: `sudo systemctl status rovac-edge-hiwonder.service`
4. Check logs: `sudo journalctl -u rovac-edge-hiwonder -n 50`

### No IMU data
1. The QMI8658 is 6-axis only — `/imu/mag` is NOT available (no magnetometer)
2. Check topic: `ros2 topic hz /imu/data --no-daemon` (expect ~72 Hz)

### Odometry drift
- Odometry uses dead-reckoning from commanded speeds, not encoder feedback
- Heading relies on IMU gyro Z integration, which drifts over time
- For accurate heading, connect the phone for magnetometer (`/phone/magnetic_field`)

## Firmware Documentation

RRCLite firmware docs are at `/home/pi/RRCLite/3. RRCLite Program Analysis/`:
- Lessons 1-3: Architecture, LED/Buzzer, Button
- Lesson 4: ADC voltage detection
- Lesson 5: QMI8658 accelerometer/gyroscope
- Lessons 6-9: RGB LED, PWM servo, bus servo
- Lessons 10-12: DC motor, quadrature encoder, PID control
- Lessons 13-15: Host communication protocol (send/receive)
