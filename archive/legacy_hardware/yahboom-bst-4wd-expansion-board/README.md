# Yahboom BST-4WD Multi-functional Expansion Board

## Overview

The BST-4WD is a multi-functional robot expansion board designed for building smart robot cars. It's the current motor controller used in the ROVAC project (Yahboom G1 Tank). The board provides motor drivers, servo outputs, and multiple sensor interfaces in an integrated package.

**Note:** This board is being replaced by the Yahboom ROS Expansion Board V3.0 for improved ROS2 integration and better IMU capabilities.

## Key Specifications

| Specification | Value |
|---------------|-------|
| Board Version | V4.2 / V4.5 |
| Motor Driver Chip | TB6612FNG (×2) |
| Motor Channels | 4 (2 per TB6612) |
| Servo Channels | 6 (via PCA9685 or direct PWM) |
| Input Voltage | 6-12V DC |
| Motor Current | 1.2A continuous, 3.2A peak (per channel) |
| Logic Voltage | 5V / 3.3V |
| Communication | GPIO (PWM), I2C |
| Compatible Controllers | Raspberry Pi, Arduino UNO, STM32, 51 MCU |

## Motor Driver: TB6612FNG

The board uses dual TB6612FNG H-bridge motor driver ICs.

### TB6612FNG Specifications
| Spec | Value |
|------|-------|
| Channels | 2 per chip (4 total on board) |
| Motor Voltage | 2.5V - 13.5V |
| Output Current | 1.2A continuous, 3.2A peak |
| Standby Current | < 1µA |
| PWM Frequency | Up to 100 kHz |
| Logic Voltage | 2.7V - 5.5V |

### Control Logic (per motor channel)

| IN1 | IN2 | PWM | Motor Action |
|-----|-----|-----|--------------|
| HIGH | LOW | Duty | Forward at speed |
| LOW | HIGH | Duty | Reverse at speed |
| LOW | LOW | X | Coast (free spin) |
| HIGH | HIGH | X | Brake (short) |

## Current ROVAC GPIO Pinout

Based on the existing `tank_motor_driver.py` implementation:

### Motor Control Pins (BCM Numbering)

| Function | GPIO Pin | Board Pin | Description |
|----------|----------|-----------|-------------|
| ENA | GPIO16 | Pin 36 | Left motor PWM (speed) |
| ENB | GPIO13 | Pin 33 | Right motor PWM (speed) |
| IN1 | GPIO20 | Pin 38 | Left motor forward |
| IN2 | GPIO21 | Pin 40 | Left motor backward |
| IN3 | GPIO19 | Pin 35 | Right motor forward |
| IN4 | GPIO26 | Pin 37 | Right motor backward |

### Wiring Diagram

```
Raspberry Pi 5                    BST-4WD Board
─────────────────                 ─────────────
GPIO16 (Pin 36) ─────────────────► ENA (Left PWM)
GPIO13 (Pin 33) ─────────────────► ENB (Right PWM)
GPIO20 (Pin 38) ─────────────────► IN1 (Left FWD)
GPIO21 (Pin 40) ─────────────────► IN2 (Left BWD)
GPIO19 (Pin 35) ─────────────────► IN3 (Right FWD)
GPIO26 (Pin 37) ─────────────────► IN4 (Right BWD)
GND ─────────────────────────────► GND
```

### Pin Layout on 40-Pin Header

```
                3V3  (1)  (2)  5V
          SDA1/GPIO2 (3)  (4)  5V
          SCL1/GPIO3 (5)  (6)  GND
               GPIO4 (7)  (8)  GPIO14/TXD
                 GND (9)  (10) GPIO15/RXD
              GPIO17 (11) (12) GPIO18
              GPIO27 (13) (14) GND
              GPIO22 (15) (16) GPIO23
                 3V3 (17) (18) GPIO24
    MOSI/GPIO10 (19) (20) GND
    MISO/GPIO9  (21) (22) GPIO25
    SCLK/GPIO11 (23) (24) GPIO8/CE0
                GND  (25) (26) GPIO7/CE1
     ID_SD/GPIO0 (27) (28) GPIO1/ID_SC
              GPIO5  (29) (30) GND
              GPIO6  (31) (32) GPIO12
      ENB ► GPIO13   (33) (34) GND
      IN3 ► GPIO19   (35) (36) GPIO16 ◄ ENA
      IN4 ► GPIO26   (37) (38) GPIO20 ◄ IN1
                GND  (39) (40) GPIO21 ◄ IN2
```

## Sensor Interfaces

The BST-4WD board provides multiple sensor connection points:

### Ultrasonic Module
| Pin | Function |
|-----|----------|
| VCC | 5V |
| GND | Ground |
| TRIG | Trigger (GPIO output) |
| ECHO | Echo (GPIO input) |

### 4-Channel Line Tracking
| Pin | Function |
|-----|----------|
| VCC | 5V |
| GND | Ground |
| IN1-IN4 | Digital outputs (black = LOW) |

### 2-Channel Infrared Obstacle Avoidance
| Pin | Function |
|-----|----------|
| VCC | 5V |
| GND | Ground |
| OUT1, OUT2 | Obstacle detection outputs |

### 2-Channel Light Seeking
| Pin | Function |
|-----|----------|
| VCC | 5V |
| GND | Ground |
| OUT1, OUT2 | Light detection outputs |

### RGB LED Module
| Pin | Function |
|-----|----------|
| GND | Ground |
| LED R | Red (HIGH = on) |
| LED G | Green (HIGH = on) |
| LED B | Blue (HIGH = on) |

## Servo Control

The board supports up to 6 servo channels. Control method depends on board version:

### Direct PWM (GPIO)
Servos connected to GPIO pins with software PWM at 50 Hz.

### PCA9685 (I2C) - If equipped
| Setting | Value |
|---------|-------|
| I2C Address | 0x40 (default) |
| Channels | 16 (6 typically used) |
| PWM Frequency | 50 Hz (for servos) |
| Resolution | 12-bit (4096 steps) |

## Power System

### Input Power
```
Battery (7.4V-12V)
    │
    └──► BST-4WD Power Input
              │
              ├──► Motor Driver (direct)
              ├──► 5V Regulator ──► Sensors, servos
              └──► 3.3V Regulator ──► Logic
```

### Power Outputs
| Rail | Voltage | Current | Use |
|------|---------|---------|-----|
| VM | Battery | 5A+ | Motors |
| 5V | Regulated | 2A | Sensors, servos |
| 3.3V | Regulated | 500mA | Logic |

## Current Driver Implementation

The ROVAC project uses a simplified binary control mode in `tank_motor_driver.py`:

```python
# GPIO pins (BCM numbering)
self.ENA = 16; self.ENB = 13  # PWM for speed
self.IN1 = 20; self.IN2 = 21  # Left motor direction
self.IN3 = 19; self.IN4 = 26  # Right motor direction

# Control method
lgpio.gpio_write(self.gpio_handle, self.IN1, forward)
lgpio.gpio_write(self.gpio_handle, self.IN2, backward)
lgpio.tx_pwm(self.gpio_handle, self.ENA, 100, duty_cycle)  # 100Hz PWM
```

### Movement Logic

| Command | Left Motor | Right Motor |
|---------|------------|-------------|
| Forward | IN1=1, IN2=0, ENA=100% | IN3=1, IN4=0, ENB=100% |
| Backward | IN1=0, IN2=1, ENA=100% | IN3=0, IN4=1, ENB=100% |
| Turn Left | IN1=0, IN2=1, ENA=100% | IN3=1, IN4=0, ENB=100% |
| Turn Right | IN1=1, IN2=0, ENA=100% | IN3=0, IN4=1, ENB=100% |
| Stop | IN1=0, IN2=0, ENA=0% | IN3=0, IN4=0, ENB=0% |

## Protection Features

| Protection | Description |
|------------|-------------|
| Reverse Polarity | Protects against wrong battery connection |
| Overcurrent | TB6612 has internal current limiting |
| Thermal Shutdown | TB6612 shuts down at ~150°C |
| Low Voltage Lockout | Prevents operation at low battery |
| Locked Rotor Restart | Auto-restart after motor stall |

## Comparison with Replacement Board

| Feature | BST-4WD V4.5 | Yahboom ROS Board V3.0 |
|---------|--------------|------------------------|
| Motor Driver | TB6612FNG | Dedicated driver + STM32 |
| Motor Channels | 4 | 4 with encoder support |
| Motor Current | 1.2A/3.2A | Higher capacity |
| IMU | External MPU6050 | Integrated MPU9250 (9-axis) |
| Communication | Direct GPIO | UART protocol |
| ROS2 Support | Manual implementation | Full SDK provided |
| Onboard MCU | None | STM32F103RCT6 |
| Pi 5 Power | No | Yes (5V/5A PD protocol) |

## Known Limitations

1. **No encoder support:** Motor speed feedback requires external implementation
2. **Limited current:** 1.2A continuous may be insufficient for larger motors
3. **GPIO intensive:** Uses 6 GPIO pins for motor control alone
4. **No onboard processing:** All control logic runs on Pi
5. **PWM jitter:** Software PWM at low frequencies can cause motor jitter

## Troubleshooting

### Motors not responding
1. Check power connection (battery voltage)
2. Verify GPIO pin assignments match wiring
3. Ensure lgpio is installed: `pip install lgpio`
4. Check gpiochip number (Pi 5 uses gpiochip4)

### Motors jittering
1. Increase PWM frequency (try 1 kHz instead of 100 Hz)
2. Use hardware PWM pins if available
3. Check for loose connections
4. Verify battery is fully charged

### One motor weaker than other
1. Check wiring connections
2. Swap motors to isolate issue
3. Test with multimeter for voltage at motor terminals

## Resources

- **Product Page:** [Yahboom G1 Tank](https://category.yahboom.net/products/g1tank)
- **GitHub:** [YahboomTechnology/Raspberry-pi-G1-Tank](https://github.com/YahboomTechnology/Raspberry-pi-G1-Tank)
- **Study Page:** [4WD Expansion Board](https://www.yahboom.net/study/4wd-ban)
- **TB6612FNG Datasheet:** [Toshiba TB6612FNG](https://www.sparkfun.com/datasheets/Robotics/TB6612FNG.pdf)

## Migration Notes

When upgrading to the Yahboom ROS Expansion Board V3.0:

1. **Motor wiring:** Connect motors to new board's motor terminals
2. **Communication:** Change from GPIO to UART protocol
3. **IMU:** Remove external MPU6050, use integrated MPU9250
4. **Driver code:** Replace `tank_motor_driver.py` with Yahboom SDK driver
5. **Power:** Use new board's 5V/5A output for Pi 5

## Files in ROVAC Project

| File | Purpose |
|------|---------|
| `robot_mcp_server/tank_motor_driver.py` | Current motor driver node |
| `config/systemd/rovac-edge-motor.service` | Systemd service for motor driver |
| `scripts/standalone_control.sh` | Startup script |
