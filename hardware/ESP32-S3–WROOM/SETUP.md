# Arduino IDE Setup for ESP32-S3

## 1. Install ESP32 Board Support

Follow the official guide to add ESP32-S3 support to Arduino IDE:

<https://github.com/espressif/arduino-esp32>

## 2. Board Configuration

Once installed, select the following settings in **Tools** menu:

| Setting | Value |
|---------|-------|
| Board | ESP32S3 Dev Module |
| USB CDC On Boot | **Enabled** |
| PSRAM | OPI PSRAM |
| Flash Size | 16MB (128Mb) |
| Flash Mode | QIO 80MHz |
| Partition Scheme | 16M Flash (3MB APP / 9.9MB FATFS) |
| Upload Mode | UART0 / Hardware CDC |
| USB Mode | Hardware CDC and JTAG |

## 3. Connecting the Board

**Use the port labeled "USB"** (right side of the board) for programming and serial output. This is the native USB-CDC port — no driver installation needed on Windows or macOS.

The port labeled "UART" (left side) is a backup that uses a CH340K USB-to-Serial converter and requires a separate driver.

## Troubleshooting

### No serial port detected

1. **Check your cable.** Many USB cables are charge-only (2-wire) and do not support data transfer. Use a cable that supports data (4-wire). If unsure, try a cable you know works for file transfer.

2. **Try a different USB port** on your computer.

3. **Try the board on a different computer** to rule out a host-side issue.

4. **macOS note:** The native USB-CDC port should appear automatically. If using the UART port instead, install the CH340K driver from <https://www.wch-ic.com/downloads/CH341SER_ZIP.html>.

### Using the backup UART port

If the main USB port isn't working, you can use the left-side **UART** port:

1. Download and install the CH340K driver: <https://www.wch-ic.com/downloads/CH341SER_ZIP.html>
2. Plug into the port labeled "UART"
3. The board should appear as a new serial device

### Upload fails or times out

- Ensure **USB CDC On Boot** is set to **Enabled**
- Ensure **Upload Mode** is set to **UART0 / Hardware CDC**
- Hold the **BOOT** button while clicking Upload, then release after "Connecting..." appears
