# Yahboom AT8236 Dual Motor Driver Module

## Overview

The Yahboom AT8236 is a dual-channel H-bridge motor driver module capable of controlling two DC motors with encoders. It uses two AT8236 driver chips and supports 5-12V power input with built-in protection circuits. This module is a potential alternative or supplement to the Yahboom ROS Expansion Board for motor control applications.

**Purchase Link:** [Amazon - B0BVW7PBYW](https://www.amazon.com/dp/B0BVW7PBYW)

## Key Specifications

| Specification | Value |
|---------------|-------|
| Driver Chip | AT8236 (×2) |
| Motor Channels | 2 |
| Input Voltage | 5-12V DC |
| Rated Current (per channel) | 3.6A continuous |
| Peak Current (per channel) | 6A |
| Onboard Regulator Output | 5V/3A or 3.3V/500mA |
| PWM Frequency | Up to 20 kHz recommended |
| Control Interface | 4 GPIO pins (2× IN1/IN2) |

## AT8236 Chip Features

The AT8236 is a single-channel DC brushed motor driver with:
- Wide voltage range: 5.5V-36V
- Low RDS(ON): 200mΩ (HS+LS combined)
- Peak drive current: 6A
- Continuous current: 4A
- PWM control interface
- Synchronous rectification for efficiency
- Low power sleep mode

## Protection Features

| Protection | Description |
|------------|-------------|
| Reverse Polarity | Input anti-reverse connection protection |
| Over-current | Automatic current limiting |
| Short Circuit | Output short circuit protection |
| Under-voltage Lockout | Prevents operation at low voltage |
| Over-temperature | Thermal shutdown protection |

## Module Interfaces

### Power Input
| Connector | Type | Function |
|-----------|------|----------|
| VM+ / VM- | KF301-2P (5.08mm) | Motor power input (5-12V) |
| Cascade Input | KF301-2P | Power input from another module |

### Power Output
| Connector | Voltage | Current | Function |
|-----------|---------|---------|----------|
| 5V | 5V regulated | 3A max | MCU power supply |
| 3.3V | 3.3V regulated | 500mA max | Logic power |
| Cascade Output | VM pass-through | - | Power to next module |

### Motor Outputs
| Channel | Terminals | Function |
|---------|-----------|----------|
| Motor A | AO1, AO2 | Motor A power output |
| Motor B | BO1, BO2 | Motor B power output |

### Control Inputs
| Pin | Function |
|-----|----------|
| AIN1 | Motor A input 1 (PWM/Logic) |
| AIN2 | Motor A input 2 (PWM/Logic) |
| BIN1 | Motor B input 1 (PWM/Logic) |
| BIN2 | Motor B input 2 (PWM/Logic) |
| VM_ADC | Voltage monitor (analog) |
| GND | Common ground |

## H-Bridge Control Logic

### Direction Control Truth Table

| IN1 | IN2 | Motor Action | Mode |
|-----|-----|--------------|------|
| LOW | LOW | Coast (free spin) | Off |
| HIGH | LOW | Forward | Active |
| LOW | HIGH | Reverse | Active |
| HIGH | HIGH | Brake (short) | Active |

### PWM Speed Control Methods

**Method 1: Fast Decay (Recommended for precision)**
```
Forward: PWM on IN1, IN2 = LOW
Reverse: IN1 = LOW, PWM on IN2
```

**Method 2: Slow Decay (Smoother operation)**
```
Forward: IN1 = HIGH, PWM on IN2 (inverted)
Reverse: PWM on IN1 (inverted), IN2 = HIGH
```

### PWM Frequency
- **Recommended:** 20 kHz (inaudible, efficient)
- **Range:** 1 kHz - 100 kHz
- **Formula:** Period = 50µs at 20 kHz

## Wiring for Raspberry Pi 5

### GPIO Connections

```
Raspberry Pi 5              AT8236 Module
─────────────────           ─────────────
GPIO12 (PWM0) ────────────► AIN1 (Motor A)
GPIO13 (PWM1) ────────────► AIN2 (Motor A)
GPIO18 (PWM0) ────────────► BIN1 (Motor B)
GPIO19 (PWM1) ────────────► BIN2 (Motor B)
GND ──────────────────────► GND
```

**Alternative GPIO Assignment:**
```
GPIO17 ────────────► AIN1
GPIO27 ────────────► AIN2
GPIO22 ────────────► BIN1
GPIO23 ────────────► BIN2
```

### Power Wiring

```
12V Battery
    │
    └──► VM+ ──► AT8236 Module ──► VM-
                     │
                     ├──► 5V out ──► Pi 5 (optional)
                     ├──► AO1/AO2 ──► Motor A
                     └──► BO1/BO2 ──► Motor B
```

### Complete Wiring Diagram

```
                    ┌─────────────────────────────────┐
                    │      AT8236 Motor Driver        │
                    │                                 │
 12V Battery ──────►│ VM+                       AO1 ├──► Motor A (+)
                    │                           AO2 ├──► Motor A (-)
              GND ──│ VM-                            │
                    │                           BO1 ├──► Motor B (+)
                    │ 5V ──► (optional Pi power) BO2 ├──► Motor B (-)
                    │ 3.3V                           │
                    │ GND                            │
                    │                                 │
 Pi GPIO12 ────────►│ AIN1                           │
 Pi GPIO13 ────────►│ AIN2                           │
 Pi GPIO18 ────────►│ BIN1                           │
 Pi GPIO19 ────────►│ BIN2                           │
 Pi GND ───────────►│ GND                            │
                    │                                 │
                    │ VM_ADC ──► (optional voltage   │
                    │            monitoring)         │
                    └─────────────────────────────────┘
```

## Python Control Example (Raspberry Pi)

### Using RPi.GPIO with Software PWM

```python
import RPi.GPIO as GPIO
import time

# Pin definitions
AIN1 = 12  # Motor A input 1
AIN2 = 13  # Motor A input 2
BIN1 = 18  # Motor B input 1
BIN2 = 19  # Motor B input 2

# Setup
GPIO.setmode(GPIO.BCM)
GPIO.setup([AIN1, AIN2, BIN1, BIN2], GPIO.OUT)

# Create PWM objects (20 kHz)
pwm_a1 = GPIO.PWM(AIN1, 20000)
pwm_a2 = GPIO.PWM(AIN2, 20000)
pwm_b1 = GPIO.PWM(BIN1, 20000)
pwm_b2 = GPIO.PWM(BIN2, 20000)

# Start with 0% duty cycle
pwm_a1.start(0)
pwm_a2.start(0)
pwm_b1.start(0)
pwm_b2.start(0)

def motor_a(speed):
    """Control Motor A. Speed: -100 to 100"""
    if speed >= 0:
        pwm_a1.ChangeDutyCycle(min(speed, 100))
        pwm_a2.ChangeDutyCycle(0)
    else:
        pwm_a1.ChangeDutyCycle(0)
        pwm_a2.ChangeDutyCycle(min(-speed, 100))

def motor_b(speed):
    """Control Motor B. Speed: -100 to 100"""
    if speed >= 0:
        pwm_b1.ChangeDutyCycle(min(speed, 100))
        pwm_b2.ChangeDutyCycle(0)
    else:
        pwm_b1.ChangeDutyCycle(0)
        pwm_b2.ChangeDutyCycle(min(-speed, 100))

def stop_all():
    """Stop both motors"""
    pwm_a1.ChangeDutyCycle(0)
    pwm_a2.ChangeDutyCycle(0)
    pwm_b1.ChangeDutyCycle(0)
    pwm_b2.ChangeDutyCycle(0)

def brake_all():
    """Brake both motors (short windings)"""
    pwm_a1.ChangeDutyCycle(100)
    pwm_a2.ChangeDutyCycle(100)
    pwm_b1.ChangeDutyCycle(100)
    pwm_b2.ChangeDutyCycle(100)

# Example usage
try:
    motor_a(50)   # Motor A forward at 50%
    motor_b(-75)  # Motor B reverse at 75%
    time.sleep(2)
    stop_all()
finally:
    GPIO.cleanup()
```

### Using pigpio for Hardware PWM

```python
import pigpio
import time

pi = pigpio.pi()

# Pin definitions
AIN1, AIN2 = 12, 13
BIN1, BIN2 = 18, 19

# Set PWM frequency (20 kHz)
for pin in [AIN1, AIN2, BIN1, BIN2]:
    pi.set_PWM_frequency(pin, 20000)
    pi.set_PWM_range(pin, 1000)  # 0-1000 for finer control

def motor_a(speed):
    """Speed: -1000 to 1000"""
    if speed >= 0:
        pi.set_PWM_dutycycle(AIN1, min(speed, 1000))
        pi.set_PWM_dutycycle(AIN2, 0)
    else:
        pi.set_PWM_dutycycle(AIN1, 0)
        pi.set_PWM_dutycycle(AIN2, min(-speed, 1000))

def motor_b(speed):
    """Speed: -1000 to 1000"""
    if speed >= 0:
        pi.set_PWM_dutycycle(BIN1, min(speed, 1000))
        pi.set_PWM_dutycycle(BIN2, 0)
    else:
        pi.set_PWM_dutycycle(BIN1, 0)
        pi.set_PWM_dutycycle(BIN2, min(-speed, 1000))

# Usage
motor_a(500)   # 50% forward
motor_b(-750)  # 75% reverse
time.sleep(2)
pi.stop()
```

## Arduino Control Example

```cpp
// Pin definitions
const int AIN1 = 9;   // PWM pin
const int AIN2 = 10;  // PWM pin
const int BIN1 = 5;   // PWM pin
const int BIN2 = 6;   // PWM pin

void setup() {
  pinMode(AIN1, OUTPUT);
  pinMode(AIN2, OUTPUT);
  pinMode(BIN1, OUTPUT);
  pinMode(BIN2, OUTPUT);
}

void motorA(int speed) {
  // Speed: -255 to 255
  if (speed >= 0) {
    analogWrite(AIN1, constrain(speed, 0, 255));
    analogWrite(AIN2, 0);
  } else {
    analogWrite(AIN1, 0);
    analogWrite(AIN2, constrain(-speed, 0, 255));
  }
}

void motorB(int speed) {
  // Speed: -255 to 255
  if (speed >= 0) {
    analogWrite(BIN1, constrain(speed, 0, 255));
    analogWrite(BIN2, 0);
  } else {
    analogWrite(BIN1, 0);
    analogWrite(BIN2, constrain(-speed, 0, 255));
  }
}

void stopAll() {
  analogWrite(AIN1, 0);
  analogWrite(AIN2, 0);
  analogWrite(BIN1, 0);
  analogWrite(BIN2, 0);
}

void loop() {
  motorA(128);   // 50% forward
  motorB(-192);  // 75% reverse
  delay(2000);
  stopAll();
  delay(1000);
}
```

## ROS2 Integration

### Simple Motor Driver Node

```python
#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import pigpio

class AT8236DriverNode(Node):
    def __init__(self):
        super().__init__('at8236_driver')

        # GPIO setup
        self.pi = pigpio.pi()
        self.AIN1, self.AIN2 = 12, 13
        self.BIN1, self.BIN2 = 18, 19

        for pin in [self.AIN1, self.AIN2, self.BIN1, self.BIN2]:
            self.pi.set_PWM_frequency(pin, 20000)
            self.pi.set_PWM_range(pin, 1000)

        # Parameters
        self.declare_parameter('wheel_base', 0.2)  # meters
        self.declare_parameter('max_speed', 1000)  # PWM units

        # Subscriber
        self.subscription = self.create_subscription(
            Twist, '/cmd_vel', self.cmd_vel_callback, 10)

        self.get_logger().info('AT8236 driver node started')

    def cmd_vel_callback(self, msg):
        linear = msg.linear.x
        angular = msg.angular.z
        wheel_base = self.get_parameter('wheel_base').value
        max_speed = self.get_parameter('max_speed').value

        # Differential drive kinematics
        left_speed = linear - (angular * wheel_base / 2)
        right_speed = linear + (angular * wheel_base / 2)

        # Normalize and scale to PWM
        max_vel = max(abs(left_speed), abs(right_speed), 1.0)
        left_pwm = int((left_speed / max_vel) * max_speed)
        right_pwm = int((right_speed / max_vel) * max_speed)

        self.set_motor_a(left_pwm)
        self.set_motor_b(right_pwm)

    def set_motor_a(self, speed):
        if speed >= 0:
            self.pi.set_PWM_dutycycle(self.AIN1, min(speed, 1000))
            self.pi.set_PWM_dutycycle(self.AIN2, 0)
        else:
            self.pi.set_PWM_dutycycle(self.AIN1, 0)
            self.pi.set_PWM_dutycycle(self.AIN2, min(-speed, 1000))

    def set_motor_b(self, speed):
        if speed >= 0:
            self.pi.set_PWM_dutycycle(self.BIN1, min(speed, 1000))
            self.pi.set_PWM_dutycycle(self.BIN2, 0)
        else:
            self.pi.set_PWM_dutycycle(self.BIN1, 0)
            self.pi.set_PWM_dutycycle(self.BIN2, min(-speed, 1000))

    def destroy_node(self):
        self.pi.stop()
        super().destroy_node()

def main():
    rclpy.init()
    node = AT8236DriverNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

## Cascading Multiple Modules

For 4WD or more motors, multiple AT8236 modules can be cascaded:

```
                    ┌──────────────┐     ┌──────────────┐
12V Battery ───────►│ Module 1     │────►│ Module 2     │
                    │ (Motors A,B) │     │ (Motors C,D) │
                    │              │     │              │
                    │ VM cascade ──┼────►│ VM cascade   │
                    └──────────────┘     └──────────────┘
                          │                    │
                          │                    │
                    GPIO 12,13,18,19     GPIO 20,21,22,23
```

Each module requires 4 GPIO pins for control.

## Comparison with Other Motor Drivers

| Feature | AT8236 Module | L298N | Yahboom ROS Board |
|---------|--------------|-------|-------------------|
| Channels | 2 | 2 | 4 |
| Current (continuous) | 3.6A | 2A | ~2A |
| Current (peak) | 6A | 3A | ~4A |
| Voltage Range | 5-12V | 5-35V | 6-12V |
| Efficiency | High (MOSFET) | Low (BJT) | High |
| Onboard Regulator | 5V/3A, 3.3V | 5V/500mA | Multiple |
| MCU Integration | None | None | STM32 onboard |
| Protection | Full suite | Basic | Full suite |
| Price | ~$5-8 | ~$3-5 | ~$79 |

## Potential Use Cases for ROVAC

### Option 1: Standalone 2WD Control
Use this module to directly control 2 motors from the Raspberry Pi GPIO, bypassing the ROS Expansion Board for motor control.

### Option 2: 4WD Expansion
Cascade with the ROS Expansion Board or another AT8236 module for 4-motor control.

### Option 3: Arduino/ESP32 Motor Control
Connect to an Arduino Nano or ESP32 for offloaded motor control with encoder processing.

### Option 4: Backup/Test Module
Keep as a spare or use for testing motor configurations without risking the main control board.

## Compatible Motors

| Motor Type | Typical Specs | Compatibility |
|------------|---------------|---------------|
| TT DC Motor | 3-6V, 200mA | ✓ Excellent |
| TT Motor w/ Encoder | 3-6V, 300mA | ✓ Excellent |
| 520 Motor | 6-12V, 1-2A | ✓ Good |
| 310 Motor | 6V, 500mA | ✓ Excellent |
| 370 Motor | 6-12V, 1-3A | ✓ Good |
| 775 Motor | 12V, 3-5A | ⚠ At limit |

## Resources

- **Product Page:** [Yahboom Store](https://category.yahboom.net/products/dual-md-module)
- **Documentation:** [Yahboom Tutorial](https://www.yahboom.net/study/Dual-MD-Module)
- **GitHub:** [YahboomTechnology/2-Channel-Motor-Driver-Module](https://github.com/YahboomTechnology/2-Channel-Motor-Driver-Module)
- **Support:** support@yahboom.com

## Notes for ROVAC Integration

1. **Potential Uses:**
   - Direct motor control from Pi GPIO (simpler than ROS Board UART)
   - Testing and prototyping motor configurations
   - Backup motor driver
   - Control additional actuators (linear actuators, extra wheels)

2. **Advantages:**
   - Direct GPIO control (no serial protocol needed)
   - High current capacity (3.6A continuous)
   - Built-in 5V/3A regulator
   - Cascadable for more motors

3. **Considerations:**
   - Uses 4 GPIO pins per module
   - No encoder input processing (must be done separately)
   - No onboard MCU (relies on Pi for control logic)

4. **When to Use This vs. ROS Board:**
   - Use AT8236 for: Simple 2WD, prototyping, high-current motors
   - Use ROS Board for: Full ROS2 integration, IMU data, encoder processing
