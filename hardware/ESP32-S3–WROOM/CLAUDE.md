# ESP32-S3 WROOM Dev Kit — AI Agent Briefing

## Board Identity

| Field | Value |
|-------|-------|
| Manufacturer | Lonely Binary |
| Model / SKU | 2518V5 |
| Product Code | S3 |
| SoC | ESP32-S3 (Xtensa LX7 dual-core, 240 MHz) |
| Flash | 16 MB, QIO 80 MHz |
| PSRAM | OPI (Octal SPI) |
| Onboard LED | WS2812 RGB on **GPIO 48** |
| USB (main) | Native USB-CDC + JTAG (right side, labeled "USB") |
| USB (backup) | CH340K UART (left side, labeled "UART") |
| Quantity | 3 boards |
| Datasheet | `esp32-s3_datasheet_en.pdf` in this folder (Espressif v2.1) |

## Arduino IDE Settings (EXACT)

```
Board:             ESP32S3 Dev Module
USB CDC On Boot:   Enabled
PSRAM:             OPI PSRAM
Flash Size:        16MB (128Mb)
Flash Mode:        QIO 80MHz
Partition Scheme:  16M Flash (3MB APP / 9.9MB FATFS)
Upload Mode:       UART0 / Hardware CDC
USB Mode:          Hardware CDC and JTAG
```

Board support: <https://github.com/espressif/arduino-esp32>

## Pin Classification

### SAFE General-Purpose Pins (Priority 2 — no restrictions)

These pins are freely available for digital I/O, PWM, interrupts, etc:

```
GPIO1, GPIO2, GPIO4, GPIO5, GPIO6, GPIO7, GPIO8, GPIO9, GPIO10,
GPIO11, GPIO12, GPIO13, GPIO14, GPIO15, GPIO16, GPIO17, GPIO18,
GPIO21, GPIO47, GPIO48
```

Total: ~21 safe GPIOs.

### DO NOT USE — SPI Flash/PSRAM Bus

These pins connect to in-package flash and OPI PSRAM. Using them WILL crash the board:

```
GPIO26, GPIO27, GPIO28, GPIO29, GPIO30, GPIO31, GPIO32  (SPI0/1 core)
GPIO33, GPIO34, GPIO35, GPIO36, GPIO37                  (Octal SPI data lines — used because this board has OPI PSRAM)
```

### USE WITH CAUTION — Strapping Pins

Read at boot to configure chip behavior. Avoid external pulls that conflict:

| Pin | Default | Function |
|-----|---------|----------|
| GPIO0 | Weak pull-up (1) | Boot mode (1 = SPI boot, 0 = download) |
| GPIO3 | Floating | JTAG signal source |
| GPIO45 | Weak pull-down (0) | VDD_SPI voltage select (0 = 3.3V) |
| GPIO46 | Weak pull-down (0) | Boot mode (with GPIO0) — **input only** |

Strapping pins are sampled at reset then freed for normal I/O. Safe to use AFTER boot if no external pull conflicts.

### USE WITH CAUTION — Special Function Pins

| Pins | Default Function | Notes |
|------|-----------------|-------|
| GPIO19, GPIO20 | USB D-, USB D+ | Used by native USB-CDC. Avoid unless USB disabled via eFuse. 40 mA drive. |
| GPIO43, GPIO44 | UART0 TX, RX | Used by `Serial` output. Don't use if you need Serial monitor. |
| GPIO39, GPIO40, GPIO41, GPIO42 | JTAG (MTCK, MTDO, MTDI, MTMS) | Usable as GPIO if JTAG is disabled. |

### ADC Pins

Two 12-bit SAR ADCs, 20 channels total. **ADC2 cannot be used while WiFi is active.**

| ADC Unit | Channels | GPIO Pins |
|----------|----------|-----------|
| ADC1 | CH0–CH9 | GPIO1–GPIO10 |
| ADC2 | CH0–CH9 | GPIO11–GPIO20 |

Attenuation settings control input voltage range:
- `ADC_0db`: 0–750 mV (most accurate)
- `ADC_2_5db`: 0–1050 mV
- `ADC_6db`: 0–1300 mV
- `ADC_11db`: 0–2500 mV (default, widest range)

### Touch Sensor Pins

14 capacitive touch channels:

| Touch Channel | GPIO |
|--------------|------|
| TOUCH1–TOUCH14 | GPIO1–GPIO14 |

**ESP32-S3 touch behavior is inverted from ESP32**: value RISES when touched (threshold triggers on rise, not fall).

## Power & Electrical Limits

| Parameter | Value |
|-----------|-------|
| Operating voltage (VDD3P3) | 3.0–3.6V (typ 3.3V) |
| Max cumulative IO current | 1200 mA |
| GPIO drive (most pins) | 20 mA |
| GPIO17, GPIO18 drive | 10 mA |
| GPIO19, GPIO20 drive | 40 mA |
| Deep-sleep current | 7 µA |
| Light-sleep current | 240 µA |
| WiFi TX peak (802.11n) | ~286 mA |
| BLE TX peak (0 dBm) | 176 mA |
| Internal pull-up/down | ~45 kΩ |

## Power-Up Pin Glitches

GPIO1–14, GPIO17–18 have **60 µs low-level glitches** at power-up. GPIO19 and GPIO20 have **high-level glitches** lasting ~3.2 ms and ~2 ms respectively. Do not connect relays, motors, or other actuators directly to these pins without accounting for startup transients.

## Peripherals Available

| Peripheral | Count / Details |
|------------|----------------|
| UART | 3 (UART0 used by Serial) |
| I2C | 2 |
| SPI | 2 general-purpose (SPI2, SPI3) + 2 for flash/PSRAM |
| I2S | 2 |
| LED PWM (LEDC) | 8 channels |
| MCPWM | 2 modules (motor control) |
| RMT | TX/RX (remote control, WS2812 driver) |
| PCNT | Pulse counter |
| USB OTG | Full-speed |
| USB Serial/JTAG | Built-in |
| SD/MMC | 2 slots |
| TWAI (CAN) | 1 (ISO 11898-1 / CAN 2.0) |
| ADC | 2x 12-bit SAR, 20 channels |
| Touch | 14 capacitive channels |
| Camera | 8–16 bit DVP interface |
| LCD | Interface available |
| Timers | 4x 54-bit general-purpose |
| Temperature sensor | Internal |
| RNG | Hardware random number generator |
| Crypto | AES-128/256, SHA, RSA, HMAC |

## Boot Mode Control

| GPIO0 | GPIO46 | Boot Mode |
|-------|--------|-----------|
| 1 (default) | Any | SPI Boot (normal operation) |
| 0 | 0 | Joint Download (USB/UART flashing) |

To force download mode: hold BOOT button (pulls GPIO0 low) → press/release RESET → release BOOT.

## Deep Sleep Wakeup Sources (ESP32-S3)

- **Timer** — `esp_sleep_enable_timer_wakeup(us)`
- **EXT1** — multiple RTC GPIO bitmask — `esp_sleep_enable_ext1_wakeup(mask, mode)`
- **Touch** — `touchSleepWakeUpEnable(pin, threshold)`
- **ULP** — ULP coprocessor (RISC-V or FSM)
- **GPIO** — `esp_deep_sleep_enable_gpio_wakeup(mask, mode)`

**Note: ESP32-S3 does NOT support ext0 wakeup (single-pin). Use ext1 instead.**

## Common Gotchas

1. **OPI PSRAM steals GPIO26-37.** This board has Octal SPI PSRAM, so 12 GPIOs are unavailable. Many online tutorials for "ESP32-S3" assume no PSRAM or Quad PSRAM and freely use GPIO33+. They will NOT work on this board.

2. **ADC2 + WiFi conflict.** ADC2 (GPIO11-20) cannot be used while WiFi is active. Use ADC1 (GPIO1-10) for analog reads in WiFi projects.

3. **USB CDC must be enabled.** `USB CDC On Boot: Enabled` is required in Arduino IDE for Serial output on the main USB port. Without it, `Serial.println()` produces no output.

4. **GPIO46 is input-only.** It has no output driver. Cannot be used for output, PWM, etc.

5. **WS2812 LED uses RMT peripheral.** The FastLED library uses the RMT (Remote Control Transceiver) peripheral internally to drive the WS2812 protocol on GPIO48. This consumes one RMT channel.

6. **Charge-only USB cables.** 2-wire USB cables (power only) cannot program or communicate with the board. Use a 4-wire data cable.

7. **Touch sensor polarity.** On ESP32-S3, touched = higher value (opposite of original ESP32). Threshold triggers on rise.

8. **Flash partition: 3 MB APP.** The default partition scheme allocates only 3 MB for application code. Large projects (with WiFi + BLE + OTA) may need a different partition scheme.

## Curated Examples

See `examples/` directory for 8 tested Arduino sketches covering the most common peripherals and patterns. Each sketch uses only safe (Priority 2) GPIO pins and is verified against this board's specific configuration.

## File Inventory

```
ESP32-S3–WROOM/
├── CLAUDE.md                    ← This file (AI agent briefing)
├── README.md                    ← Human-readable overview
├── SETUP.md                     ← Arduino IDE setup + troubleshooting
├── EXAMPLES.md                  ← Quick-start WS2812 example
├── esp32-s3_datasheet_en.pdf    ← Espressif official datasheet v2.1
├── CH341SER.ZIP                 ← CH340K driver (for backup UART port)
├── IMG_7087–7090.jpg            ← Original documentation card photos
└── examples/                    ← Curated Arduino sketches
    ├── 01_blink_ws2812/
    ├── 02_wifi_station/
    ├── 03_ble_uart_server/
    ├── 04_pwm_led_fade/
    ├── 05_i2c_scanner/
    ├── 06_adc_multiread/
    ├── 07_deep_sleep_wakeup/
    └── 08_touch_sensor/
```
