# ESP32-WROOM-32 Development Board (38-Pin)

## Overview

The ESP32-WROOM-32 is a powerful dual-core microcontroller with integrated WiFi and Bluetooth. It's ideal for creating wireless sensors, remote monitoring devices, and IoT peripherals for robotics projects. The 38-pin development board exposes all GPIO pins for easy prototyping.

**Purchase Link:** [Amazon - B0C8HDDNLV](https://www.amazon.com/dp/B0C8HDDNLV)

## Key Specifications

| Specification | Value |
|---------------|-------|
| SoC | ESP32-D0WDQ6 |
| CPU | Dual-core Tensilica Xtensa LX6 |
| Clock Speed | Up to 240 MHz |
| Flash Memory | 4 MB SPI Flash |
| SRAM | 520 KB |
| WiFi | 802.11 b/g/n (2.4 GHz) |
| Bluetooth | Classic + BLE 4.2 |
| Operating Voltage | 3.3V |
| Input Voltage | 5V (via USB or VIN) |

## Wireless Capabilities

### WiFi
- **Standard:** IEEE 802.11 b/g/n
- **Frequency:** 2.4 GHz
- **Security:** WPA/WPA2/WPA3, WEP
- **Modes:** Station, Access Point, Station+AP
- **Range:** ~100m line of sight

### Bluetooth
- **Classic:** BR/EDR for audio, serial
- **BLE 4.2:** Low energy for sensors
- **Simultaneous:** Up to 7 BLE connections
- **Profiles:** SPP, GATT, GAP, etc.

## Pin Configuration (38-Pin Board)

| Pin Type | Count | Notes |
|----------|-------|-------|
| Total GPIO | 34 | Not all usable |
| Usable GPIO | 25 | Some reserved |
| ADC Channels | 18 | 12-bit resolution |
| DAC Channels | 2 | 8-bit resolution |
| Touch Pins | 10 | Capacitive touch |
| PWM | All GPIO | Software PWM |
| UART | 3 | UART0, 1, 2 |
| I2C | 2 | Any GPIO configurable |
| SPI | 3 | VSPI, HSPI + Flash |

## Pinout Diagram (38-Pin)

```
                    ┌─────────────────┐
                    │    USB Micro    │
                    └────────┬────────┘
        ┌────────────────────┴────────────────────┐
        │              ESP32-WROOM-32             │
        │                                         │
   3V3 ─┤ 1                                   38 ├─ GND
    EN ─┤ 2  (Reset)                          37 ├─ GPIO23 (MOSI)
   VP  ─┤ 3  GPIO36 (ADC1_CH0, input only)    36 ├─ GPIO22 (SCL)
   VN  ─┤ 4  GPIO39 (ADC1_CH3, input only)    35 ├─ GPIO1  (TX0)
  D34 ─┤ 5  GPIO34 (ADC1_CH6, input only)    34 ├─ GPIO3  (RX0)
  D35 ─┤ 6  GPIO35 (ADC1_CH7, input only)    33 ├─ GPIO21 (SDA)
  D32 ─┤ 7  GPIO32 (ADC1_CH4, Touch9)        32 ├─ GND
  D33 ─┤ 8  GPIO33 (ADC1_CH5, Touch8)        31 ├─ GPIO19 (MISO)
  D25 ─┤ 9  GPIO25 (ADC2_CH8, DAC1)          30 ├─ GPIO18 (SCK)
  D26 ─┤ 10 GPIO26 (ADC2_CH9, DAC2)          29 ├─ GPIO5  (SS)
  D27 ─┤ 11 GPIO27 (ADC2_CH7, Touch7)        28 ├─ GPIO17 (TX2)
  D14 ─┤ 12 GPIO14 (ADC2_CH6, Touch6)        27 ├─ GPIO16 (RX2)
  D12 ─┤ 13 GPIO12 (ADC2_CH5, Touch5)        26 ├─ GPIO4  (ADC2_CH0)
  GND ─┤ 14                                   25 ├─ GPIO0  (Boot, Touch1)
  D13 ─┤ 15 GPIO13 (ADC2_CH4, Touch4)        24 ├─ GPIO2  (LED, Touch2)
   D9 ─┤ 16 GPIO9  (Flash - do not use)      23 ├─ GPIO15 (ADC2_CH3, Touch3)
  D10 ─┤ 17 GPIO10 (Flash - do not use)      22 ├─ D8/GPIO8  (Flash)
  D11 ─┤ 18 GPIO11 (Flash - do not use)      21 ├─ D7/GPIO7  (Flash)
  VIN ─┤ 19 (5V input)                        20 ├─ D6/GPIO6  (Flash)
        │                                         │
        └─────────────────────────────────────────┘
```

## GPIO Usage Notes

### Input-Only Pins (No Output)
- GPIO34, GPIO35, GPIO36 (VP), GPIO39 (VN)
- No internal pull-up/pull-down resistors

### Do Not Use (Connected to Flash)
- GPIO6, GPIO7, GPIO8, GPIO9, GPIO10, GPIO11
- Using these will crash the ESP32

### Boot Pins (Use with Caution)
- GPIO0: Must be HIGH during boot (has internal pull-up)
- GPIO2: Should be LOW or floating during boot
- GPIO12: Affects flash voltage (leave floating)
- GPIO15: Should be HIGH during boot

### Safe General-Purpose GPIO
- GPIO4, GPIO5, GPIO13, GPIO14, GPIO16, GPIO17, GPIO18, GPIO19
- GPIO21, GPIO22, GPIO23, GPIO25, GPIO26, GPIO27, GPIO32, GPIO33

## Analog-to-Digital Converter (ADC)

### ADC1 (Always Available)
| Channel | GPIO | Notes |
|---------|------|-------|
| ADC1_CH0 | GPIO36 | Input only |
| ADC1_CH3 | GPIO39 | Input only |
| ADC1_CH4 | GPIO32 | |
| ADC1_CH5 | GPIO33 | |
| ADC1_CH6 | GPIO34 | Input only |
| ADC1_CH7 | GPIO35 | Input only |

### ADC2 (Not available when WiFi active)
| Channel | GPIO |
|---------|------|
| ADC2_CH0 | GPIO4 |
| ADC2_CH3 | GPIO15 |
| ADC2_CH4 | GPIO13 |
| ADC2_CH5 | GPIO12 |
| ADC2_CH6 | GPIO14 |
| ADC2_CH7 | GPIO27 |
| ADC2_CH8 | GPIO25 |
| ADC2_CH9 | GPIO26 |

**Important:** When WiFi is enabled, ADC2 cannot be used. Use ADC1 pins for analog readings in WiFi projects.

## Digital-to-Analog Converter (DAC)

| DAC | GPIO | Resolution |
|-----|------|------------|
| DAC1 | GPIO25 | 8-bit (0-255) |
| DAC2 | GPIO26 | 8-bit (0-255) |

## Touch Pins

Capacitive touch sensing on these pins:

| Touch | GPIO |
|-------|------|
| TOUCH0 | GPIO4 |
| TOUCH1 | GPIO0 |
| TOUCH2 | GPIO2 |
| TOUCH3 | GPIO15 |
| TOUCH4 | GPIO13 |
| TOUCH5 | GPIO12 |
| TOUCH6 | GPIO14 |
| TOUCH7 | GPIO27 |
| TOUCH8 | GPIO33 |
| TOUCH9 | GPIO32 |

## Communication Interfaces

### UART
| UART | TX | RX | Notes |
|------|----|----|-------|
| UART0 | GPIO1 | GPIO3 | USB serial (programming) |
| UART1 | GPIO10 | GPIO9 | Flash pins - remap needed |
| UART2 | GPIO17 | GPIO16 | Free to use |

### I2C (Default Pins)
```
SDA: GPIO21
SCL: GPIO22
```
Note: Any GPIO can be configured for I2C via software.

### SPI
| Interface | MOSI | MISO | SCK | CS |
|-----------|------|------|-----|-----|
| VSPI | GPIO23 | GPIO19 | GPIO18 | GPIO5 |
| HSPI | GPIO13 | GPIO12 | GPIO14 | GPIO15 |

## Use Cases for ROVAC Robotics

### 1. Wireless Sensor Node

Create a remote sensor that sends data to Pi via WiFi:

```cpp
#include <WiFi.h>
#include <HTTPClient.h>

const char* ssid = "ROVAC_NETWORK";
const char* password = "your_password";

void setup() {
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(500);
}

void loop() {
  float distance = readUltrasonic();

  HTTPClient http;
  http.begin("http://192.168.1.104:8080/sensor");
  http.addHeader("Content-Type", "application/json");

  String json = "{\"sensor\":\"ultrasonic\",\"value\":" + String(distance) + "}";
  http.POST(json);
  http.end();

  delay(100);
}
```

### 2. Bluetooth Remote Control

Create a Bluetooth joystick/controller:

```cpp
#include "BluetoothSerial.h"

BluetoothSerial SerialBT;

void setup() {
  SerialBT.begin("ROVAC_Controller");
}

void loop() {
  int joyX = analogRead(34);
  int joyY = analogRead(35);
  int button = digitalRead(4);

  String data = String(joyX) + "," + String(joyY) + "," + String(button);
  SerialBT.println(data);
  delay(50);
}
```

### 3. WiFi Camera Trigger

Trigger camera capture wirelessly:

```cpp
#include <WiFi.h>
#include <WebServer.h>

WebServer server(80);

void handleCapture() {
  digitalWrite(2, HIGH);  // Trigger LED/signal
  delay(100);
  digitalWrite(2, LOW);
  server.send(200, "text/plain", "Captured");
}

void setup() {
  WiFi.begin("ROVAC_NETWORK", "password");
  server.on("/capture", handleCapture);
  server.begin();
}

void loop() {
  server.handleClient();
}
```

### 4. Mesh Network Sensor Array

Deploy multiple ESP32s as a sensor mesh:

```cpp
#include <painlessMesh.h>

painlessMesh mesh;

void receivedCallback(uint32_t from, String &msg) {
  // Process incoming sensor data from other nodes
}

void setup() {
  mesh.init("ROVAC_MESH", "mesh_password", 5555);
  mesh.onReceive(&receivedCallback);
}

void loop() {
  mesh.update();

  // Broadcast sensor reading
  float temp = readTemperature();
  mesh.sendBroadcast(String(temp));
  delay(1000);
}
```

### 5. USB + WiFi Bridge

Connect USB devices wirelessly to Pi:

```cpp
// ESP32 reads USB device, sends to Pi via WiFi
#include <WiFi.h>
#include <AsyncTCP.h>

AsyncClient* client;
HardwareSerial USBSerial(2);  // UART2 for USB device

void setup() {
  USBSerial.begin(115200, SERIAL_8N1, 16, 17);
  WiFi.begin("ROVAC_NETWORK", "password");

  client = new AsyncClient();
  client->connect("192.168.1.200", 8888);
}

void loop() {
  while (USBSerial.available()) {
    char c = USBSerial.read();
    if (client->connected()) {
      client->write(&c, 1);
    }
  }
}
```

### 6. OTA (Over-The-Air) Updates

Update ESP32 firmware wirelessly:

```cpp
#include <WiFi.h>
#include <ArduinoOTA.h>

void setup() {
  WiFi.begin("ROVAC_NETWORK", "password");

  ArduinoOTA.setHostname("rovac-sensor-1");
  ArduinoOTA.begin();
}

void loop() {
  ArduinoOTA.handle();
  // Your sensor code here
}
```

## Connecting to Raspberry Pi

### Option 1: WiFi (Recommended for Wireless)
```
ESP32 ──── WiFi ────► Router ────► Pi 5
                   or
ESP32 ──── WiFi ────► Pi 5 (AP mode)
```

### Option 2: USB Serial
```
ESP32 USB ──► Pi 5 USB Port
              └──► /dev/ttyUSB0
```

### Option 3: Direct Serial (UART)
```
ESP32 TX (GPIO17) ──► Pi RX (GPIO15)
ESP32 RX (GPIO16) ◄── Pi TX (GPIO14)
ESP32 GND ────────── Pi GND

Note: ESP32 is 3.3V - direct connection OK
```

### Option 4: Bluetooth
```python
# Python on Pi - connect via Bluetooth Serial
import serial
bt = serial.Serial('/dev/rfcomm0', 115200)
data = bt.readline()
```

## Development Environment

### Arduino IDE
1. Add ESP32 board URL: `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
2. Install "ESP32 by Espressif" in Board Manager
3. Select "ESP32 Dev Module"

### PlatformIO
```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
```

### ESP-IDF (Advanced)
```bash
# Install ESP-IDF
git clone --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
./install.sh
source export.sh
```

## ROS2 Integration via micro-ROS

The ESP32 can run micro-ROS for direct ROS2 communication:

```cpp
#include <micro_ros_arduino.h>
#include <std_msgs/msg/float32.h>

rcl_publisher_t publisher;
std_msgs__msg__Float32 msg;

void setup() {
  set_microros_wifi_transports("ROVAC_NETWORK", "password",
                                "192.168.1.104", 8888);

  rcl_node_t node;
  rclc_node_init_default(&node, "esp32_sensor", "", &support);
  rclc_publisher_init_default(&publisher, &node,
    ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Float32), "/esp32/sensor");
}

void loop() {
  msg.data = analogRead(34) * 3.3 / 4095.0;
  rcl_publish(&publisher, &msg, NULL);
  delay(100);
}
```

## Power Consumption

| Mode | Current |
|------|---------|
| Active (WiFi TX) | ~240 mA |
| Active (WiFi RX) | ~100 mA |
| Active (no radio) | ~50 mA |
| Light Sleep | ~0.8 mA |
| Deep Sleep | ~10 µA |

**Tip:** Use deep sleep for battery-powered sensors:
```cpp
esp_deep_sleep_start();  // Wake via timer, touch, or GPIO
```

## Comparison with Arduino Nano

| Feature | Arduino Nano | ESP32 |
|---------|-------------|-------|
| CPU Cores | 1 | 2 |
| Clock Speed | 16 MHz | 240 MHz |
| RAM | 2 KB | 520 KB |
| Flash | 32 KB | 4 MB |
| WiFi | No | Yes |
| Bluetooth | No | Yes |
| ADC Resolution | 10-bit | 12-bit |
| ADC Channels | 8 | 18 |
| Price | ~$3-5 | ~$5-8 |

## Package Contents

- 3x ESP32 Development Boards (38-pin)
- 3x GPIO Breakout/Terminal Boards

## Resources

- **ESP32 Pinout:** https://lastminuteengineers.com/esp32-wroom-32-pinout-reference/
- **Random Nerd Tutorials:** https://randomnerdtutorials.com/esp32-pinout-reference-gpios/
- **Espressif Documentation:** https://docs.espressif.com/projects/esp-idf/en/latest/esp32/
- **ESP32 Datasheet:** https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32_datasheet_en.pdf
- **micro-ROS for ESP32:** https://micro.ros.org/docs/tutorials/core/first_application_rtos/freertos/

## Notes for ROVAC Integration

1. **Primary Use:** Wireless sensors, remote monitoring, Bluetooth peripherals
2. **Connection Options:**
   - WiFi to Pi (most flexible)
   - USB serial (simple, reliable)
   - Bluetooth (for handheld controllers)
3. **Benefits:**
   - Wireless communication built-in
   - Powerful dual-core processor
   - Low power modes for battery operation
   - micro-ROS support for ROS2 integration
4. **Considerations:**
   - ADC2 unavailable when WiFi active
   - Some boot-sensitive pins
   - 3.3V logic (compatible with Pi)
