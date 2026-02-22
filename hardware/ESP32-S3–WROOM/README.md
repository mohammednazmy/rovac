# ESP32-S3 WROOM Dev Kit

**Manufacturer:** Lonely Binary
**Model:** 2518V5
**Product Code:** S3
**Quantity:** 3 boards

| Spec | Value |
|------|-------|
| SoC | ESP32-S3 (dual-core Xtensa LX7, 240 MHz) |
| Flash | 16 MB (128 Mbit) |
| PSRAM | OPI PSRAM |
| Flash Mode | QIO 80 MHz |
| Connectivity | Wi-Fi 802.11 b/g/n, Bluetooth 5.0 LE |
| USB | Native USB-OTG (Hardware CDC + JTAG) |
| Backup UART | CH340K USB-to-Serial |
| Built-in LED | WS2812 RGB on GPIO 48 |
| Partition Scheme | 16M Flash (3 MB APP / 9.9 MB FATFS) |

## USB Ports

This board has **two USB-C ports**:

| Port | Label | Side | Chip | Driver |
|------|-------|------|------|--------|
| Main | **USB** | Right | Native USB-CDC | Built-in (Windows/Mac) |
| Backup | **UART** | Left | CH340K | Manual install required |

The **main USB port** is used for programming and serial communication (plug-and-play, no driver needed). The backup UART port requires the CH340K driver.

## Resources

| Resource | Link |
|----------|------|
| Product Page | <https://lonelybinary.com/products/s3> |
| Support | <https://lonelybinary.com> (click Support) |
| ESP32 Guide (book) | <https://tinyurl.com/esp32guide> |
| Arduino-ESP32 Core | <https://github.com/espressif/arduino-esp32> |
| CH340K Driver | <https://www.wch-ic.com/downloads/CH341SER_ZIP.html> |

## Guide Book

The boards ship with "Getting Started with ESP32 Family" by Lonely Binary (copyright 2025). Covers ESP32, C3, S2, and S3 variants — features, setup, and beginner projects.
