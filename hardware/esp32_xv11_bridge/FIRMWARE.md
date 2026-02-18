# ESP32 XV11 LIDAR Bridge - Firmware Documentation

Technical documentation for the ESP32 XV11 Bridge firmware.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     ESP32 Firmware                           │
│                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────┐     │
│  │   UART2     │───▶│  Main Loop   │───▶│   UART0     │     │
│  │  (LIDAR)    │    │  (Bridge)    │    │   (USB)     │     │
│  │  GPIO16/17  │    │              │    │   to Host   │     │
│  │  115200bd   │◀───│  Commands    │◀───│  115200bd   │     │
│  └─────────────┘    └──────────────┘    └─────────────┘     │
│                            │                                 │
│                     ┌──────┴──────┐                         │
│                     │ LED Status  │                         │
│                     │   GPIO2     │                         │
│                     └─────────────┘                         │
└──────────────────────────────────────────────────────────────┘
```

## Firmware Details

### Version Information

| Property | Value |
|----------|-------|
| Version | 1.0.0 |
| Device Name | ESP32_XV11_BRIDGE |
| Author | ROVAC Project |
| License | Open Source |

### Pin Assignments

| Pin | Function | Description |
|-----|----------|-------------|
| GPIO16 | UART2 RX | Receives data from LIDAR (connect to LIDAR Orange/RX) |
| GPIO17 | UART2 TX | Transmits to LIDAR (connect to LIDAR Brown/TX) |
| GPIO2 | LED | Status indicator (built-in on most DevKits) |

### Serial Configuration

| Parameter | UART0 (USB) | UART2 (LIDAR) |
|-----------|-------------|---------------|
| Baud Rate | 115200 | 115200 |
| Data Bits | 8 | 8 |
| Stop Bits | 1 | 1 |
| Parity | None | None |
| RX Buffer | Default | 1024 bytes |

## Main Loop Operation

The firmware operates as a transparent bridge with minimal processing:

```cpp
void loop() {
    // 1. Forward LIDAR data to USB (primary function)
    while (LidarSerial.available()) {
        uint8_t byte = LidarSerial.read();
        Serial.write(byte);
        // Track statistics
    }

    // 2. Process debug commands from USB
    while (Serial.available()) {
        // Handle ! commands or forward to LIDAR
    }

    // 3. Update status LED
    // Fast blink = data flowing, slow blink = idle
}
```

### Data Flow

**LIDAR → USB (Primary):**
```
XV11 LIDAR → UART2 RX (GPIO16) → Serial.write() → USB → Host
```

**USB → LIDAR (Optional, for commands):**
```
Host → USB → Serial.read() → UART2 TX (GPIO17) → XV11 LIDAR
```

## Debug Command Interface

Commands are prefixed with `!` and terminated with newline.

### Command Protocol

```
Send: !<command>\n
Receive: !<RESPONSE>\n
```

### Available Commands

#### `!id` - Device Identification

Returns the device name for identification in multi-device setups.

```
Request:  !id
Response: !DEVICE:ESP32_XV11_BRIDGE
```

#### `!version` - Firmware Version

Returns the firmware version string.

```
Request:  !version
Response: !VERSION:1.0.0
```

#### `!status` - Runtime Statistics

Returns operational statistics.

```
Request:  !status
Response: !STATUS: Uptime=3600s, Bytes=41256000, Packets=1875000, Rate=11460.0 B/s, Idle=0s
```

| Field | Description |
|-------|-------------|
| Uptime | Seconds since power on |
| Bytes | Total bytes forwarded |
| Packets | XV11 packets detected (0xFA headers) |
| Rate | Average bytes per second |
| Idle | Seconds since last LIDAR data |

#### `!reset` - Reset Statistics

Clears all counters and resets uptime.

```
Request:  !reset
Response: !STATS_RESET
```

#### `!help` - Command List

Lists available commands.

```
Request:  !help
Response: !COMMANDS: !id, !version, !status, !reset, !help
```

## LED Status Indicators

The onboard LED (GPIO2) provides visual feedback:

| Pattern | Meaning |
|---------|---------|
| 3 quick flashes | Startup complete |
| Fast blink (100ms) | Data actively flowing |
| Slow blink (1000ms) | Idle (no data for 500ms+) |

## XV11 Packet Detection

The firmware monitors for valid XV11 packets to track statistics:

```cpp
// XV11 packet format: 0xFA + index (0xA0-0xF9) + 20 data bytes
if (prevByte == 0xFA && byte >= 0xA0 && byte <= 0xF9) {
    packetsDetected++;
}
```

This provides a count of valid packet headers without affecting data throughput.

## Building and Uploading

### Prerequisites

- Arduino IDE or arduino-cli
- ESP32 board support package

### Arduino IDE Setup

1. Add ESP32 board URL to Preferences:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```

2. Install ESP32 boards via Board Manager

3. Select Board: **ESP32 Dev Module**

### Compile and Upload

**Using Arduino CLI:**

```bash
# Compile
arduino-cli compile --fqbn esp32:esp32:esp32 esp32_xv11_bridge.ino

# Upload (adjust port as needed)
arduino-cli upload -p /dev/ttyUSB2 --fqbn esp32:esp32:esp32 esp32_xv11_bridge.ino
```

**Using Arduino IDE:**

1. Open `esp32_xv11_bridge.ino`
2. Select Tools → Board → ESP32 Dev Module
3. Select Tools → Port → (your ESP32 port)
4. Click Upload

### Build Output

Typical resource usage:

| Resource | Usage | Available | Percentage |
|----------|-------|-----------|------------|
| Program Storage | ~285 KB | 1,310 KB | 21% |
| Dynamic Memory | ~21 KB | 327 KB | 6% |

## Customization

### Changing Pin Assignments

Edit these defines at the top of the sketch:

```cpp
#define LIDAR_RX_PIN    16    // Change for different RX pin
#define LIDAR_TX_PIN    17    // Change for different TX pin
#define LED_PIN         2     // Change for different LED pin
```

### Adjusting Buffer Size

The RX buffer can be increased for high-latency hosts:

```cpp
LidarSerial.setRxBufferSize(1024);  // Default: 1024, max: 4096
```

### Modifying Baud Rate

Both baud rates are defined as constants:

```cpp
#define USB_BAUD        115200    // Must match host configuration
#define LIDAR_BAUD      115200    // Fixed by XV11 specification
```

> **Warning:** The XV11 LIDAR operates at fixed 115200 baud. Do not change `LIDAR_BAUD`.

## Performance Characteristics

### Throughput

| Metric | Value |
|--------|-------|
| Maximum throughput | ~115,200 bps |
| Actual LIDAR data rate | ~11,000 bytes/sec |
| Latency | < 1ms (hardware UART) |
| Packet loss | 0% (with hardware UART) |

### Reliability

The ESP32's hardware UART provides:
- Dedicated RX/TX hardware with FIFO buffers
- DMA-capable transfers (not used in this simple bridge)
- Interrupt-driven reception
- No bit-banging or timing-critical software

## Memory Map

```
Flash Memory Layout:
┌────────────────────┬──────────┐
│ Bootloader         │ 0x1000   │
├────────────────────┼──────────┤
│ Partition Table    │ 0x8000   │
├────────────────────┼──────────┤
│ NVS                │ 0x9000   │
├────────────────────┼──────────┤
│ Application        │ 0x10000  │
│ (esp32_xv11_bridge)│          │
└────────────────────┴──────────┘
```

## Error Handling

The firmware is designed for simplicity and reliability:

- **No blocking operations** - All serial I/O is non-blocking
- **No dynamic allocation** - Fixed buffers prevent fragmentation
- **Watchdog enabled** - ESP32's default watchdog prevents lockups
- **Graceful degradation** - Continues operating even if LIDAR disconnects

## Future Enhancements

Potential improvements for future versions:

- [ ] Motor PWM control (for LIDARs without external motor power)
- [ ] Automatic baud rate detection
- [ ] Data validation and error statistics
- [ ] WiFi/Bluetooth streaming option
- [ ] OTA (Over-The-Air) firmware updates
