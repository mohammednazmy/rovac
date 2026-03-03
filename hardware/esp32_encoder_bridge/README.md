# ESP32 Encoder Bridge

Hardware quadrature decoder for ROVAC's wheel encoders using the ESP32's PCNT (Pulse Counter) peripheral.

## Why

The Pi 5's RP1 GPIO edge detection is unreliable on Ubuntu 24.04 (kernel 6.8) — all libraries (lgpio, gpiod, gpiozero) miss encoder ticks. The ESP32's PCNT counts in dedicated hardware silicon with zero CPU load and zero missed ticks.

## Architecture

```
Encoders ──► ESP32 (PCNT hardware) ──USB serial──► Pi 5 ──► ROS2 /odom
Motors   ◄── Pi 5 GPIO (gpiozero, unchanged)
```

## Wiring

| Wire | Motor Pin | Color | ESP32 Pin |
|------|-----------|-------|-----------|
| Left Ch A | Pin 4 | Yellow | GPIO32 |
| Left Ch B | Pin 3 | Green | GPIO33 |
| Right Ch A | Pin 4 | Yellow | GPIO25 |
| Right Ch B | Pin 3 | Green | GPIO26 |
| Encoder VCC | Pin 5 | Blue | 3.3V |
| Encoder GND | Pin 2 | Black | GND |

ESP32 pins 25, 26, 32, 33 are safe general-purpose GPIOs (no boot strapping, no flash conflicts).

## Serial Protocol

**ESP32 → Pi (50 Hz default):**
```
E 12345 -6789\n
```
Two space-separated signed integers: cumulative left and right tick counts.

**Pi → ESP32 (commands):**
```
!id        →  !DEVICE:ESP32_ENCODER_BRIDGE
!status    →  !STATUS: Left=12345 Right=-6789 Rate=50Hz Uptime=3600s
!reset     →  !RESET:OK   (resets both counters to 0)
!rate 100  →  !RATE:100   (change streaming rate, 10-200 Hz)
!help      →  (list commands)
```

## Flashing

```bash
# Install ESP32 Arduino core (if not already from LIDAR bridge)
arduino-cli core install esp32:esp32

# Install ESP32Encoder library
arduino-cli lib install "ESP32Encoder"

# Compile
arduino-cli compile --fqbn esp32:esp32:esp32 hardware/esp32_encoder_bridge/

# Flash (replace /dev/ttyUSB0 with actual port)
arduino-cli upload --fqbn esp32:esp32:esp32 -p /dev/ttyUSB0 hardware/esp32_encoder_bridge/
```

## Testing

```bash
# Quick serial monitor test (spin wheels by hand)
screen /dev/ttyUSB0 115200

# Or with minicom
minicom -D /dev/ttyUSB0 -b 115200

# Send commands by typing: !id  then Enter
```

## udev Rule

Add to `/etc/udev/rules.d/99-rovac-usb.rules` on the Pi:

```
# ESP32 Encoder Bridge (Silicon Labs CP2102 or similar)
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", ATTRS{serial}=="XXXX", SYMLINK+="esp32_encoder"
```

Replace vendor/product/serial with actual values from `udevadm info /dev/ttyUSBX`.

After adding: `sudo udevadm control --reload-rules && sudo udevadm trigger`
