# Nano V3.0 Programming Guide

This directory contains documentation and resources for programming LAFVIN Nano V3.0 boards (ATmega328P with CH340 chip) for use with the ROVAC robot project.

## Board Specifications

- **Model**: LAFVIN Nano V3.0
- **Microcontroller**: ATmega328P
- **USB-to-Serial Chip**: CH340G
- **Operating Voltage**: 5V
- **Clock Speed**: 16MHz

## Initial Setup

### 1. Driver Installation

For macOS systems, the CH340 driver should already be installed. If not, install it using Homebrew:

```bash
brew install wch-ch34x-usb-serial-driver
```

After installation, reboot your system for the driver to take effect.

### 2. Arduino CLI Installation

The Arduino CLI is used for command-line programming of the Nano boards:

```bash
brew install arduino-cli
```

### 3. Core Installation

Install the required Arduino cores:

```bash
arduino-cli core update-index
arduino-cli core install arduino:avr
```

## Programming Process

### 1. Identify the Board

Connect the Nano board via USB and identify the serial port:

```bash
ls /dev/cu.wchusbserial*
```

Typical output: `/dev/cu.wchusbserial2140`

### 2. Compile the Sketch

Navigate to your sketch directory and compile:

```bash
cd ~/robots/rovac/nano/examples/lidar_usb_bridge
arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328 .
```

### 3. Upload the Sketch

Upload the compiled sketch to the board:

```bash
arduino-cli upload -p /dev/cu.wchusbserial2140 --fqbn arduino:avr:nano:cpu=atmega328 .
```

### 4. Troubleshooting Upload Issues

If you encounter "not in sync" errors (common with CH340 boards):

1. **Use verbose output** to see detailed information:
   ```bash
   arduino-cli upload -p /dev/cu.wchusbserial2140 --fqbn arduino:avr:nano:cpu=atmega328 -v
   ```

2. **Try different baud rates** if the default fails:
   ```bash
   arduino-cli upload -p /dev/cu.wchusbserial2140 --fqbn arduino:avr:nano:cpu=atmega328 --upload-property baudrate=57600
   ```

3. **Manual reset technique**:
   - Hold down the reset button on the Nano
   - Run the upload command
   - Release the reset button when you see "Connecting..." in the output

## Example Projects

### LIDAR USB Bridge

This sketch converts the Nano into a USB-to-Serial bridge for XV11 LIDAR modules.

Location: `examples/lidar_usb_bridge/lidar_usb_bridge.ino`

Features:
- Bidirectional serial communication
- USB CDC interface for computer connection
- Hardware serial for LIDAR connection
- 115200 baud rate support

## Common Issues and Solutions

### 1. "Programmer is not responding" Errors

**Solution**: 
- Ensure the CH340 driver is properly installed
- Try different USB cables (some charge-only cables don't support data)
- Use the verbose flag to get more information about the error

### 2. "not in sync" Errors

**Solution**:
- Try the manual reset technique described above
- Use a slower baud rate for uploading
- Ensure no other applications are using the serial port

### 3. Device Not Recognized

**Solution**:
- Check `ls /dev/cu.*` to see if the device appears with a different name
- Reinstall the CH340 driver
- Try a different USB port

## Best Practices

1. **Always use the correct FQBN**: `arduino:avr:nano:cpu=atmega328`
2. **Keep sketches in dedicated directories** with the same name as the .ino file
3. **Test communication** after uploading using `screen` or `cat` commands
4. **Document pin assignments** in your sketches for future reference
5. **Use version control** to track changes to your sketches

## Useful Commands

### List connected boards
```bash
arduino-cli board list
```

### Detailed board information
```bash
arduino-cli board details -b arduino:avr:nano
```

### Compile with output directory
```bash
arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328 --output-dir ./build .
```

### Upload with verbose output
```bash
arduino-cli upload -p /dev/cu.wchusbserial2140 --fqbn arduino:avr:nano:cpu=atmega328 -v
```