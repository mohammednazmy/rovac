# ESP32 XV11 LIDAR Bridge - Troubleshooting Guide

Solutions for common issues with the ESP32 XV11 LIDAR Bridge.

## Quick Diagnostics

### Step 1: Check Hardware

```bash
# List USB devices
lsusb | grep -i "silicon\|cp210\|esp"

# Check serial ports
ls -la /dev/ttyUSB* /dev/ttyACM*
```

### Step 2: Test ESP32 Communication

```bash
# Configure port
stty -F /dev/ttyUSB2 115200 raw -echo

# Send ID command
echo '!id' > /dev/ttyUSB2

# Read response (in another terminal or before command)
cat /dev/ttyUSB2
```

### Step 3: Check LIDAR Data

```bash
# Capture raw data
timeout 2 cat /dev/ttyUSB2 | xxd | head -20

# Look for 0xFA bytes (XV11 packet markers)
timeout 2 cat /dev/ttyUSB2 | xxd | grep "fa"
```

---

## Common Issues and Solutions

### Issue: ESP32 Not Detected on USB

**Symptoms:**
- No `/dev/ttyUSB*` device appears
- `lsusb` doesn't show Silicon Labs CP2102

**Solutions:**

1. **Try a different USB cable**
   - Some cables are charge-only and don't support data
   - Use a known-good data cable

2. **Try a different USB port**
   - Front panel ports may have power issues
   - Use a rear motherboard port or USB 3.0 port

3. **Check driver installation (Linux)**
   ```bash
   # CP2102 driver should be built into kernel
   lsmod | grep cp210x

   # If not loaded:
   sudo modprobe cp210x
   ```

4. **Check permissions**
   ```bash
   # Add user to dialout group
   sudo usermod -a -G dialout $USER
   # Log out and back in
   ```

---

### Issue: No LIDAR Data (Motor Spinning)

**Symptoms:**
- Motor spins normally
- ESP32 LED blinks slowly (idle pattern)
- No data on serial port

**Solutions:**

1. **Check data wire connections**
   - Verify Orange wire is connected to GPIO16
   - Verify Brown wire is connected to GPIO17

2. **Check for loose connections**
   - Wiggle wires gently while monitoring data
   - Re-seat all connections

3. **Verify LIDAR is outputting data**
   ```bash
   # If you have another serial adapter, connect directly to LIDAR
   # and verify it outputs data at 115200 baud
   ```

4. **Check ESP32 firmware**
   ```bash
   # Re-upload firmware
   arduino-cli upload -p /dev/ttyUSB2 --fqbn esp32:esp32:esp32 .
   ```

---

### Issue: Motor Not Spinning

**Symptoms:**
- No motor movement when powered
- LIDAR is silent

**Solutions:**

1. **Check motor power connections**
   - Motor Red wire must be connected to 5V
   - Motor Black wire must be connected to GND

2. **Check power supply capacity**
   - Motor needs ~300-400mA
   - Total system needs ~500-680mA
   - Try a USB 3.0 port or powered hub

3. **Test motor directly**
   - Apply 5V directly to motor wires
   - If motor doesn't spin, it may be damaged

4. **Check for mechanical binding**
   - Rotate LIDAR head manually
   - Should spin freely with minimal resistance

---

### Issue: Corrupted Data (Not 0xFA Packets)

**Symptoms:**
- Data stream doesn't contain 0xFA bytes
- Random-looking data
- Checksum errors in ROS2 driver

**Solutions:**

1. **Verify baud rate**
   ```bash
   # Must be 115200
   stty -F /dev/ttyUSB2 115200
   ```

2. **Check for electrical noise**
   - Keep data wires away from motor wires
   - Use shorter wires if possible
   - Add 100nF capacitor across 5V/GND near LIDAR

3. **Re-upload firmware**
   - Firmware may have been corrupted
   ```bash
   arduino-cli upload -p /dev/ttyUSB2 --fqbn esp32:esp32:esp32 .
   ```

---

### Issue: Intermittent Data / Dropouts

**Symptoms:**
- Data flows, then stops
- ESP32 resets randomly
- Motor speed varies

**Solutions:**

1. **Power supply issues (most common)**
   - Use USB 3.0 port (900mA vs 500mA)
   - Use powered USB hub
   - Add capacitor (470µF) across 5V/GND

2. **Check connections**
   - Loose connections cause intermittent issues
   - Solder connections instead of using jumpers

3. **Reduce cable length**
   - Long USB cables cause voltage drop
   - Use shortest cable possible

---

### Issue: Low Scan Rate in ROS2

**Symptoms:**
- `/scan` topic publishes at < 5 Hz
- Many invalid readings

**Solutions:**

1. **Check motor speed**
   - Motor should spin at ~250-300 RPM
   - Low voltage causes slow rotation
   - Increase power supply capacity

2. **Verify full 360° coverage**
   ```bash
   # Should see all 90 angle indices (0-89)
   python3 << 'EOF'
   import serial
   ser = serial.Serial('/dev/ttyUSB2', 115200, timeout=2)
   data = ser.read(10000)
   indices = set()
   for i in range(len(data)-1):
       if data[i] == 0xFA and 0xA0 <= data[i+1] <= 0xF9:
           indices.add(data[i+1] - 0xA0)
   print(f"Unique indices: {len(indices)}/90")
   ser.close()
   EOF
   ```

3. **Check XV11 optics**
   - Clean the LIDAR lens with soft cloth
   - Dust on lens reduces valid readings

---

### Issue: ESP32 Commands Not Working

**Symptoms:**
- `!id` returns no response
- Commands seem to be ignored

**Solutions:**

1. **Check command format**
   - Commands must start with `!`
   - Commands must end with newline (`\n`)
   ```bash
   echo -e '!id\n' > /dev/ttyUSB2
   ```

2. **Read response immediately**
   ```bash
   # Start reading before sending command
   (sleep 0.5; echo '!id') > /dev/ttyUSB2 &
   timeout 2 cat /dev/ttyUSB2
   ```

3. **Use proper serial terminal**
   ```bash
   # Interactive test with screen
   screen /dev/ttyUSB2 115200
   # Type: !id<Enter>
   # Exit: Ctrl-A, then K, then Y
   ```

---

### Issue: ROS2 Service Fails to Start

**Symptoms:**
- `rovac-edge-lidar.service` fails
- "Port not found" errors

**Solutions:**

1. **Verify port exists**
   ```bash
   ls -la /dev/ttyUSB2
   ```

2. **Check service configuration**
   ```bash
   cat /etc/systemd/system/rovac-edge-lidar.service | grep port
   ```

3. **Update port in service file**
   ```bash
   sudo nano /etc/systemd/system/rovac-edge-lidar.service
   # Change port:=/dev/ttyUSBX to correct port
   sudo systemctl daemon-reload
   sudo systemctl restart rovac-edge-lidar
   ```

4. **Create udev rule for persistent naming**
   ```bash
   # Create rule for ESP32
   echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="esp32_lidar"' | \
     sudo tee /etc/udev/rules.d/99-esp32-lidar.rules
   sudo udevadm control --reload-rules
   sudo udevadm trigger

   # Now use /dev/esp32_lidar in service file
   ```

---

## Diagnostic Commands Reference

### ESP32 Status

```bash
# Device identification
echo '!id' > /dev/ttyUSB2 && sleep 0.2 && timeout 1 cat /dev/ttyUSB2

# Firmware version
echo '!version' > /dev/ttyUSB2 && sleep 0.2 && timeout 1 cat /dev/ttyUSB2

# Runtime statistics
echo '!status' > /dev/ttyUSB2 && sleep 0.2 && timeout 1 cat /dev/ttyUSB2
```

### Data Quality

```bash
# Count XV11 packets in 2 seconds
timeout 2 cat /dev/ttyUSB2 | grep -o $'\xfa' | wc -c

# Visualize data stream
timeout 2 cat /dev/ttyUSB2 | xxd | head -50
```

### ROS2 Topic

```bash
# Check topic rate
ros2 topic hz /scan

# View single scan
ros2 topic echo /scan --once

# Check for valid readings
ros2 topic echo /scan --field ranges | head -20
```

---

## Getting Help

If you're still having issues:

1. **Collect diagnostic information:**
   ```bash
   echo "=== USB Devices ===" && lsusb
   echo "=== Serial Ports ===" && ls -la /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
   echo "=== ESP32 Status ===" && (echo '!status' > /dev/ttyUSB2; sleep 0.5; timeout 1 cat /dev/ttyUSB2)
   echo "=== Data Sample ===" && timeout 1 cat /dev/ttyUSB2 | xxd | head -10
   ```

2. **Check the project documentation:**
   - [README.md](README.md) - Overview and quick start
   - [WIRING_GUIDE.md](WIRING_GUIDE.md) - Detailed wiring
   - [FIRMWARE.md](FIRMWARE.md) - Firmware details

3. **Report issues** with the diagnostic output to help debug the problem.
