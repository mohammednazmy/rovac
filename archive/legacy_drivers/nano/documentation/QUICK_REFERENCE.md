# Nano LIDAR USB Bridge - Quick Reference

## Programming a New Nano Board

```bash
# 1. Connect Nano via USB
# 2. Identify device
ls /dev/cu.wchusbserial*

# 3. Navigate to sketch directory
cd ~/robots/rovac/nano/examples/lidar_usb_bridge

# 4. Compile sketch
arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328 .

# 5. Upload sketch (replace XXXX with actual device number)
arduino-cli upload -p /dev/cu.wchusbserialXXXX --fqbn arduino:avr:nano:cpu=atmega328 .
```

## Verifying Operation

```bash
# Quick test
cd ~/robots/rovac/nano
./test_lidar.sh

# Detailed validation
python3 test_lidar_data.py
```

## Expected LIDAR Wiring

```
LIDAR Wire    Color    Nano Pin    Function
----------    -----    --------    --------
Red           Red      5V          Power (+5V)
Black         Black    GND         Ground
Orange        Orange   D2          Serial TX (LIDAR -> Nano)
Brown         Brown    D3          Serial RX (Nano -> LIDAR)
```

## Troubleshooting

### Upload Issues
- Use verbose flag: `-v`
- Try manual reset technique
- Check USB cable (must be data cable, not charge-only)

### No Data
- Verify all 4 wire connections
- Check LIDAR power LED
- Re-upload sketch if needed

### Invalid Data
- Confirm baud rate is 115200
- Check TX/RX wiring orientation
- Verify LIDAR functionality independently

## Raspberry Pi Integration

After successful local testing:
1. Unplug Nano from this computer
2. Plug Nano into Raspberry Pi USB port
3. SSH to Pi and check for `/dev/ttyUSB0`
4. Update rovac-edge-lidar.service to use new device path
5. Restart service and verify ROS2 topics

## Documentation
- `README.md` - Complete programming guide
- `USAGE.md` - Operational procedures
- `VERIFICATION_REPORT.md` - Test results and validation
- `examples/lidar_usb_bridge/` - Source code