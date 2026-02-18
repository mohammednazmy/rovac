# PIC16F917 Programmer Documentation

## Overview

This document describes how to use the BQLZR K150 PIC programmer (clone of Kitsrus K150) with the ROVAC robot project. This programmer can be used for programming PIC microcontrollers that may be used in custom robot components or sensors.

## Hardware Information

- **Programmer Model**: BQLZR K150 (Chinese clone of Kitsrus K150)
- **Microcontroller Supported**: PIC16F917 and other compatible PIC microcontrollers
- **Connection Interface**: USB-to-Serial (FTDI-based)
- **Device Path**: `/dev/tty.usbserial-1140`
- **Communication Baud Rate**: 19200

## Prerequisites

The following tools must be installed on your system:

1. **Python 3** - For running the picpro tool
2. **picpro** - Python-based programmer tool for K150 programmers
3. **pyserial** - Python serial communication library

### Installation

```bash
# Install picpro tool
pip3 install picpro

# pyserial should be automatically installed as a dependency
```

## Basic Operations

### 1. Check Programmer Connection

To verify the programmer is properly connected:

```bash
# Test basic communication
python3 -c "
import serial
s = serial.Serial(port='/dev/tty.usbserial-1140', baudrate=19200,
                  bytesize=8, parity='N', stopbits=1,
                  timeout=10, xonxoff=0, rtscts=0)
print('Serial port opened successfully')
s.close()
"
```

### 2. Erase Chip

To erase the entire contents of the PIC16F917:

```bash
picpro erase -p /dev/tty.usbserial-1140 -t 16f917
```

### 3. Program Chip

To program a hex file to the PIC16F917:

```bash
picpro program -p /dev/tty.usbserial-1140 -i YOUR_FILE.hex -t 16f917
```

### 4. Verify Programming

To verify that the hex file was programmed correctly:

```bash
picpro verify -p /dev/tty.usbserial-1140 -i YOUR_FILE.hex -t 16f917
```

### 5. Get Chip Information

To get detailed information about the PIC16F917:

```bash
picpro chipinfo 16f917
```

## Example Usage

### Simple LED Blink Program

Create a simple hex file for testing:

```bash
# Create a simple test hex file
cat > test_led_blink.hex << 'EOF'
:020000040000FA
:1000000000000000000000000000000000000000EF
:00000001FF
EOF

# Program the test file
picpro program -p /dev/tty.usbserial-1140 -i test_led_blink.hex -t 16f917
```

## Troubleshooting

### Common Issues

1. **Permission Denied Error**
   ```bash
   # Add user to dialout group (Linux) or admin group (macOS)
   sudo usermod -a -G dialout $USER
   # On macOS, you might need to use:
   sudo dseditgroup -o edit -a $USER -t user admin
   ```

2. **Device Not Found**
   - Check that the programmer is properly connected via USB
   - Verify the device path with: `ls /dev/tty.usbserial*`
   - Ensure no other application is using the serial port

3. **Communication Timeout**
   - Confirm the baud rate is set to 19200
   - Check cable connections
   - Try unplugging and reconnecting the programmer

4. **Programming Errors**
   - Ensure the PIC is properly seated in the programmer socket
   - Check that the correct chip type is specified (16f917)
   - Verify the hex file is valid and compatible with the target chip

### Diagnostic Script

To run a comprehensive diagnostic of the programmer connection:

```bash
python3 -c "
import serial
from picpro.ProtocolInterface import ProtocolInterface

s = serial.Serial(port='/dev/tty.usbserial-1140', baudrate=19200,
                  bytesize=8, parity='N', stopbits=1,
                  timeout=10, xonxoff=0, rtscts=0)
protocol_interface = ProtocolInterface(s)
result = protocol_interface.reset()
print(f'Programmer reset: {result}')
if result:
    print(f'Firmware version: {protocol_interface.programmer_firmware_version()}')
s.close()
"
```

## Technical Details

### Communication Protocol

The K150 programmer uses a proprietary serial protocol:
- **Baud Rate**: 19200
- **Data Bits**: 8
- **Parity**: None
- **Stop Bits**: 1
- **Flow Control**: None

### Supported Operations

1. Chip erasure
2. ROM programming
3. EEPROM programming
4. Fuse programming
5. Chip verification
6. Chip identification

## Integration with ROVAC Project

This programmer can be used for:
1. Programming custom sensor interfaces
2. Creating specialized motor controllers
3. Developing auxiliary microcontroller-based components
4. Repairing or reflashing existing PIC-based components

## References

- [picpro GitHub Repository](https://github.com/Salamek/picpro)
- [Kitsrus K150 Programmer Documentation](https://www.kitsrus.com/pic.html)
- PIC16F917 datasheet from Microchip

## Notes

- Always disconnect power from the robot when programming PIC microcontrollers
- Ensure proper ESD precautions when handling microcontrollers
- Keep backup copies of working firmware hex files