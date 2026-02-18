# Using the Nano LIDAR USB Bridge

This document explains how to use the Nano boards programmed as USB-to-Serial bridges for XV11 LIDAR modules.

## Directory Structure

```
nano/
├── README.md                  # Programming guide for Nano boards
├── USAGE.md                   # This file
├── test_lidar.sh              # Automated test script
├── verify_lidar_simple.py     # Simple LIDAR data verification
├── test_lidar_data.py         # Advanced LIDAR data validation
└── examples/
    └── lidar_usb_bridge/
        └── lidar_usb_bridge.ino  # LIDAR USB bridge sketch
```

## Pre-Programming Verification

Before connecting the LIDAR to your Raspberry Pi, verify that the Nano is working correctly:

### 1. Run the Automated Test

```bash
cd ~/robots/rovac/nano
./test_lidar.sh
```

This will:
- Check if the Nano is connected
- Verify serial communication
- Display data flow from the LIDAR

### 2. Manual Verification

You can also manually check the data stream:

```bash
# Method 1: Using screen
screen /dev/cu.wchusbserial2140 115200

# Method 2: Using cat
cat /dev/cu.wchusbserial2140

# Press Ctrl+C to exit
```

You should see streaming hexadecimal data if the LIDAR is working correctly.

## Expected Behavior

### Successful Connection
- Continuous stream of data (hexadecimal characters)
- Data rate of approximately 2000-3000 bytes/second
- Occasional recognizable patterns in the data stream

### No Data
- Empty output or rare random characters
- May indicate wiring issues or power problems

## Troubleshooting

### No Data Received

1. **Check physical connections**:
   - Ensure all four wires are properly connected
   - Red (5V), Black (GND), Orange (TX), Brown (RX)
   - Verify Nano pins D2 and D3 are correctly wired

2. **Check power supply**:
   - Ensure the LIDAR is receiving adequate power
   - The Nano should be powered via USB during testing

3. **Verify sketch upload**:
   - Re-upload the sketch using verbose mode:
     ```bash
     cd ~/robots/rovac/nano/examples/lidar_usb_bridge
     arduino-cli upload -p /dev/cu.wchusbserial2140 --fqbn arduino:avr:nano:cpu=atmega328 -v
     ```

### Garbled or Intermittent Data

1. **Check baud rate**:
   - Ensure both the sketch and test tools use 115200 baud

2. **Check wiring**:
   - Verify TX/RX connections are not swapped
   - Orange wire should go to D2 (Nano receives from LIDAR)
   - Brown wire should go to D3 (Nano sends to LIDAR)

## Connecting to Raspberry Pi

Once verified working on this machine:

1. **Disconnect Nano** from this computer
2. **Connect Nano** to Raspberry Pi via USB
3. **SSH into Raspberry Pi** and check for the device:
   ```bash
   ssh pi@192.168.234.9
   ls /dev/ttyUSB*
   ```
4. **The device should appear** as `/dev/ttyUSB0`
5. **Update the LIDAR service** to use this new device path

## Reusing Nano Boards

To program additional Nano boards:

1. **Connect the new board** via USB
2. **Identify its device path**:
   ```bash
   ls /dev/cu.wchusbserial*
   ```
3. **Upload the sketch**:
   ```bash
   cd ~/robots/rovac/nano/examples/lidar_usb_bridge
   arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328 .
   arduino-cli upload -p /dev/cu.wchusbserialXXXX --fqbn arduino:avr:nano:cpu=atmega328 .
   ```
4. **Verify operation** using the test scripts

## Maintenance Tips

1. **Keep a inventory** of programmed boards and their purposes
2. **Label physical boards** with their function
3. **Document any modifications** to the standard sketch
4. **Regular testing** ensures continued reliability

## Advanced Testing

For detailed validation of LIDAR data integrity:

```bash
cd ~/robots/rovac/nano
python3 test_lidar_data.py
```

This script performs packet-level validation to ensure the data conforms to XV11 LIDAR protocol specifications.