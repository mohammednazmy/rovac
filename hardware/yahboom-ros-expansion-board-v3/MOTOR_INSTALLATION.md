# Motor Installation Guide

## Motors: 520 DC Gear Motors with Hall Encoders

| Specification | Value |
|---------------|-------|
| Motor Type | 520 DC Gear Motor |
| Encoder | High-Precision Hall Encoder (Quadrature A/B) |
| Voltage | 12V |
| RPM Options | 110 / 170 / 320 RPM |
| Shaft | 6mm D-Shaped Eccentric |
| Quantity | 4 motors |

## Yahboom ROS V3 Board Motor Connections

### Motor Output Terminals

```
    YAHBOOM ROS EXPANSION BOARD V3.0
    ┌──────────────────────────────────────┐
    │                                      │
    │  MOTOR OUTPUTS (6-12V)               │
    │  ┌────────────────────────────────┐  │
    │  │   M1      M2      M3      M4   │  │
    │  │  (+)(-)  (+)(-)  (+)(-)  (+)(-)│  │
    │  └────────────────────────────────┘  │
    │                                      │
    │  ENCODER INPUTS                      │
    │  ┌────────────────────────────────┐  │
    │  │   E1      E2      E3      E4   │  │
    │  │  A B     A B     A B     A B   │  │
    │  │  G V     G V     G V     G V   │  │
    │  └────────────────────────────────┘  │
    │                                      │
    │  G = GND, V = 5V/3.3V                │
    │  A = Encoder Channel A               │
    │  B = Encoder Channel B               │
    └──────────────────────────────────────┘
```

### Wiring Each Motor

Each 520 motor with Hall encoder typically has 6 wires:

| Wire Color | Function | Connect To |
|------------|----------|------------|
| Red | Motor + | M# (+) terminal |
| Black | Motor - | M# (-) terminal |
| Yellow/Green | Encoder A | E# A pin |
| White/Blue | Encoder B | E# B pin |
| Red (thin) | Encoder VCC | E# V pin (5V) |
| Black (thin) | Encoder GND | E# G pin |

**Note:** Wire colors may vary by manufacturer. Check your motor's datasheet.

### Motor Position Mapping

For a 4-wheeled tank/skid-steer robot:

```
        FRONT
    ┌───────────┐
    │  M1   M2  │
    │  ●     ●  │
    │           │
    │  ●     ●  │
    │  M3   M4  │
    └───────────┘
        REAR

M1 = Front Left
M2 = Front Right
M3 = Rear Left
M4 = Rear Right
```

## Pre-Installation Checklist

- [ ] Robot is powered OFF
- [ ] Battery disconnected
- [ ] All 4 motors ready
- [ ] Screwdriver for terminals
- [ ] Multimeter (optional, for testing)

## Installation Steps

### Step 1: Mount Motors Physically

1. Mount motors to the chassis
2. Attach wheels to motor shafts
3. Ensure motors are secure and aligned

### Step 2: Connect Motor Power Wires

1. Connect each motor's power wires to the corresponding M# terminal
2. **Polarity matters** - if motor spins wrong direction, swap + and -

```bash
# Test pattern (after connecting):
# Forward command should spin all wheels forward
# If a wheel spins backward, swap its + and - wires
```

### Step 3: Connect Encoder Wires

1. Connect encoder A and B signals to E# terminals
2. Connect encoder power (5V and GND)
3. Ensure connections are secure

### Step 4: Power On and Test

1. Reconnect battery
2. Power on robot
3. Verify Yahboom service starts:
   ```bash
   sudo systemctl status rovac-edge-yahboom.service
   ```

## Post-Installation Testing

### Test 1: Verify Encoder Readings

```bash
# SSH to Pi
ssh pi

# Watch encoder values
source /home/pi/ros2_env.sh
ros2 topic echo /wheel_encoders
```

Manually rotate each wheel and verify:
- Encoder values change
- Forward rotation increases count
- Backward rotation decreases count

### Test 2: Test Motor Direction

```python
# On Pi - run this script to test each motor
from Rosmaster_Lib import Rosmaster
import time

bot = Rosmaster(car_type=1, com="/dev/yahboom_board")
bot.create_receive_threading()
time.sleep(0.3)

print("Testing M1 (Front Left)...")
bot.set_motor(30, 0, 0, 0)
time.sleep(1)
bot.set_motor(0, 0, 0, 0)
input("Did M1 spin forward? (y/n): ")

print("Testing M2 (Front Right)...")
bot.set_motor(0, 30, 0, 0)
time.sleep(1)
bot.set_motor(0, 0, 0, 0)
input("Did M2 spin forward? (y/n): ")

print("Testing M3 (Rear Left)...")
bot.set_motor(0, 0, 30, 0)
time.sleep(1)
bot.set_motor(0, 0, 0, 0)
input("Did M3 spin forward? (y/n): ")

print("Testing M4 (Rear Right)...")
bot.set_motor(0, 0, 0, 30)
time.sleep(1)
bot.set_motor(0, 0, 0, 0)
input("Did M4 spin forward? (y/n): ")

print("Test complete!")
```

### Test 3: Test Velocity Control

```python
# Test forward motion
bot.set_car_motion(vx=0.2, vy=0.0, vz=0.0)  # Forward 0.2 m/s
time.sleep(2)
bot.set_car_motion(0, 0, 0)  # Stop
```

### Test 4: Verify Odometry

```bash
# On Pi
ros2 topic echo /odom
```

Drive robot forward and verify:
- `pose.position.x` increases
- `twist.linear.x` shows velocity

## Calibration

### PID Tuning (if needed)

If motors don't respond smoothly or odometry drifts:

```python
from Rosmaster_Lib import Rosmaster
bot = Rosmaster(car_type=1, com="/dev/yahboom_board")

# Check current PID values
current_pid = bot.get_motion_pid()
print(f"Current PID: kp={current_pid[0]}, ki={current_pid[1]}, kd={current_pid[2]}")

# Adjust if needed (default is usually fine)
# bot.set_pid_param(kp=0.5, ki=0.1, kd=0.3, forever=True)
```

### Encoder Calibration

The Yahboom board expects a certain encoder resolution. If odometry is significantly off:

1. Measure actual wheel diameter
2. Count encoder ticks per revolution
3. Update the ROS2 node parameters if needed

## Troubleshooting

### Motor doesn't spin
1. Check battery voltage (needs >7V for motors)
2. Verify motor wire connections
3. Test with direct PWM: `bot.set_motor(50, 0, 0, 0)`

### Motor spins wrong direction
- Swap the + and - wires for that motor

### Encoder values don't change
1. Check encoder power (5V)
2. Check A/B signal connections
3. Verify encoder is working (LED may flash when rotating)

### Odometry drifts
1. Check PID values
2. Verify encoder connections for all 4 motors
3. Ensure wheels have good traction

## Quick Reference Commands

```bash
# Check service status
sudo systemctl status rovac-edge-yahboom.service

# View encoder data
ros2 topic echo /wheel_encoders

# View odometry
ros2 topic echo /odom

# View motor velocity
ros2 topic echo /cmd_vel

# Send test velocity (from Mac)
ros2 topic pub /cmd_vel geometry_msgs/Twist "{linear: {x: 0.1}, angular: {z: 0.0}}" -1
```

## Service Restart After Installation

After motors are installed and tested:

```bash
sudo systemctl restart rovac-edge-yahboom.service
sudo systemctl status rovac-edge-yahboom.service
```
