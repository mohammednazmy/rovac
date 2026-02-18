# Arduino Nano V3.0 (ATmega328P + CH340)

## Overview

The Arduino Nano V3.0 is a compact microcontroller board based on the ATmega328P. It's ideal for creating custom USB sensors and peripheral devices that can interface with the Raspberry Pi via USB serial. The CH340 chip provides USB-to-serial conversion.

**Purchase Link:** [Amazon - B07G99NNXL](https://www.amazon.com/dp/B07G99NNXL)

## Key Specifications

| Specification | Value |
|---------------|-------|
| Microcontroller | ATmega328P |
| Architecture | 8-bit AVR |
| Clock Speed | 16 MHz |
| Operating Voltage | 5V |
| Input Voltage (recommended) | 7-12V |
| Input Voltage (limits) | 6-20V |
| Flash Memory | 32 KB (2 KB bootloader) |
| SRAM | 2 KB |
| EEPROM | 1 KB |
| USB Chip | CH340G |

## Pin Configuration

| Pin Type | Count | Details |
|----------|-------|---------|
| Digital I/O | 14 | D0-D13 |
| PWM Outputs | 6 | D3, D5, D6, D9, D10, D11 |
| Analog Inputs | 8 | A0-A7 |
| UART | 1 | D0 (RX), D1 (TX) |
| I2C | 1 | A4 (SDA), A5 (SCL) |
| SPI | 1 | D10-D13 |

## Pinout Diagram

```
                    ┌─────────────────┐
                    │    USB Mini-B   │
                    └────────┬────────┘
                             │
        ┌────────────────────┴────────────────────┐
        │                                         │
   D13 ─┤ 1                                   30 ├─ D12
   3V3 ─┤ 2                                   29 ├─ D11 (MOSI/PWM)
   REF ─┤ 3                                   28 ├─ D10 (SS/PWM)
   A0  ─┤ 4                                   27 ├─ D9  (PWM)
   A1  ─┤ 5                                   26 ├─ D8
   A2  ─┤ 6                                   25 ├─ D7
   A3  ─┤ 7                                   24 ├─ D6  (PWM)
   A4  ─┤ 8  (SDA)                            23 ├─ D5  (PWM)
   A5  ─┤ 9  (SCL)                            22 ├─ D4
   A6  ─┤ 10                                  21 ├─ D3  (PWM/INT1)
   A7  ─┤ 11                                  20 ├─ D2  (INT0)
   5V  ─┤ 12                                  19 ├─ GND
   RST ─┤ 13                                  18 ├─ RST
   GND ─┤ 14                                  17 ├─ D0  (RX)
   VIN ─┤ 15                                  16 ├─ D1  (TX)
        │                                         │
        └─────────────────────────────────────────┘
```

## CH340G USB-to-Serial Chip

The CH340G provides USB communication:
- Converts USB to UART (TTL serial)
- Supports baud rates up to 2 Mbps
- Driver required on some systems

### Driver Installation

**Linux (Raspberry Pi OS):**
```bash
# Usually built into kernel, check with:
dmesg | grep ch34
# If not present:
sudo apt-get install ch341-dkms
```

**macOS:**
```bash
# Install via Homebrew
brew install --cask wch-ch34x-usb-serial-driver
```

**Windows:** Download from [WCH website](http://www.wch-ic.com/downloads/CH341SER_EXE.html)

## Power Options

| Method | Voltage | Notes |
|--------|---------|-------|
| USB | 5V | Via Mini-B USB connector |
| VIN Pin | 7-12V | Through onboard regulator |
| 5V Pin | 5V | Direct, bypass regulator |

**Warning:** Do not supply power to both VIN and 5V pins simultaneously.

## Communication Interfaces

### UART (Serial)
```
D0 (RX) ◄── Receive
D1 (TX) ──► Transmit
Baud: Up to 115200 (recommended)
```

### I2C
```
A4 (SDA) ◄──► Data
A5 (SCL) ◄──► Clock
Speed: 100 kHz (standard), 400 kHz (fast)
```

### SPI
```
D13 (SCK)  ──► Clock
D12 (MISO) ◄── Master In, Slave Out
D11 (MOSI) ──► Master Out, Slave In
D10 (SS)   ──► Slave Select
```

## Use Cases for ROVAC Robotics

### 1. Custom USB Sensor Modules

Create dedicated sensor processors that communicate with Pi via USB:

```
                    ┌─────────────────────┐
                    │    Arduino Nano     │
Ultrasonic ────────►│ A0              USB ├───► Pi 5 USB Port
IR Sensors ────────►│ A1-A3               │
Encoders ──────────►│ D2, D3 (interrupts) │
                    └─────────────────────┘
```

### 2. Motor Encoder Counter

Offload real-time encoder counting to the Nano:

```cpp
// Example: High-speed encoder counting
volatile long encoderCount = 0;

void setup() {
  Serial.begin(115200);
  attachInterrupt(digitalPinToInterrupt(2), countPulse, RISING);
}

void loop() {
  Serial.println(encoderCount);
  delay(10);
}

void countPulse() {
  encoderCount++;
}
```

### 3. Analog Sensor Hub

Read multiple analog sensors and send to Pi:

```cpp
// Read 6 analog sensors, send as CSV
void loop() {
  for (int i = 0; i < 6; i++) {
    Serial.print(analogRead(i));
    if (i < 5) Serial.print(",");
  }
  Serial.println();
  delay(50);
}
```

### 4. PWM LED/Servo Controller

Control LEDs or servos via serial commands from Pi:

```cpp
#include <Servo.h>
Servo myServo;

void setup() {
  Serial.begin(115200);
  myServo.attach(9);
}

void loop() {
  if (Serial.available()) {
    int angle = Serial.parseInt();
    myServo.write(angle);
  }
}
```

### 5. Button/Switch Interface

Read physical buttons and report to Pi:

```cpp
const int buttons[] = {2, 3, 4, 5, 6, 7};
const int numButtons = 6;

void setup() {
  Serial.begin(115200);
  for (int i = 0; i < numButtons; i++) {
    pinMode(buttons[i], INPUT_PULLUP);
  }
}

void loop() {
  for (int i = 0; i < numButtons; i++) {
    Serial.print(!digitalRead(buttons[i]));
  }
  Serial.println();
  delay(50);
}
```

## Connecting to Raspberry Pi

### USB Connection (Recommended)
```
Arduino Nano USB ──► Pi 5 USB Port
                     │
                     └──► /dev/ttyUSB0 (or /dev/ttyACM0)
```

### Direct Serial (if USB not available)
```
Nano TX (D1) ──► Pi RX (GPIO15)
Nano RX (D0) ◄── Pi TX (GPIO14)
Nano GND ────── Pi GND
Nano 5V ◄────── Pi 5V (or separate supply)

Note: Use level shifter for 5V ↔ 3.3V
```

## Python Communication Example

```python
import serial

# Connect to Arduino Nano
nano = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)

# Read sensor data
while True:
    line = nano.readline().decode('utf-8').strip()
    if line:
        values = line.split(',')
        print(f"Sensors: {values}")
```

## ROS2 Integration

Create a simple ROS2 node to publish Nano sensor data:

```python
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import serial

class NanoSensorNode(Node):
    def __init__(self):
        super().__init__('nano_sensor_node')
        self.publisher = self.create_publisher(String, '/nano/sensors', 10)
        self.serial = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.1)
        self.timer = self.create_timer(0.05, self.read_sensors)

    def read_sensors(self):
        if self.serial.in_waiting:
            data = self.serial.readline().decode('utf-8').strip()
            msg = String()
            msg.data = data
            self.publisher.publish(msg)
```

## Arduino IDE Setup

1. **Install Arduino IDE** (or use arduino-cli)
2. **Select Board:** Tools → Board → Arduino Nano
3. **Select Processor:** ATmega328P (or "ATmega328P (Old Bootloader)")
4. **Select Port:** /dev/ttyUSB0 (Linux) or COM# (Windows)
5. **Upload:** Click Upload button

### Using arduino-cli (headless)
```bash
# Install
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh

# Configure
arduino-cli config init
arduino-cli core update-index
arduino-cli core install arduino:avr

# Compile and upload
arduino-cli compile --fqbn arduino:avr:nano sketch/
arduino-cli upload -p /dev/ttyUSB0 --fqbn arduino:avr:nano sketch/
```

## Comparison with Other Options

| Feature | Arduino Nano | ESP32 | Direct to Pi GPIO |
|---------|-------------|-------|-------------------|
| Analog Inputs | 8 (10-bit) | 18 (12-bit) | 0 (needs ADC) |
| Real-time | Yes | Yes | No (OS latency) |
| WiFi/BT | No | Yes | No |
| Cost | ~$3-5 | ~$5-8 | N/A |
| Complexity | Low | Medium | Low |

## Notes for ROVAC Integration

1. **Primary Use:** Custom USB sensor modules, real-time I/O processing
2. **Connection:** USB to Pi 5 (via hub if needed)
3. **Benefits:**
   - Offload time-critical tasks from Pi
   - 8 analog inputs (Pi has none)
   - Interrupt-driven encoder counting
   - Simple, reliable, well-documented
4. **Limitations:**
   - No wireless
   - Limited memory for complex code
   - Single-threaded

## Package Contents

- 3x Arduino Nano V3.0 boards
- USB cable(s)

## Resources

- **Arduino Reference:** https://www.arduino.cc/reference/en/
- **ATmega328P Datasheet:** https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf
- **CH340 Driver:** http://www.wch-ic.com/downloads/CH341SER_EXE.html
