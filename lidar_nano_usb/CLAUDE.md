# LIDAR Nano USB Module - AI Agent Instructions

## Overview

This directory contains a custom USB LIDAR module built from:
- **Neato XV11 LIDAR** (salvaged) - 360° scanning laser rangefinder
- **Arduino Nano** - USB-to-serial bridge with CH340 chip

The goal is to create a truly plug-and-play USB LIDAR device for robotics applications.

For the plug-and-play/driver assessment, see `PLUG_AND_PLAY.md`.

## Critical Safety Rules for AI Agents

### BEFORE Accessing the Serial Port

**Always check for stuck processes first.** Previous Claude Code sessions can leave orphaned processes holding the serial port open, which will cause your session to hang/freeze.

```bash
# Pre-flight check - RUN THIS FIRST
./preflight_check.sh
```

If you need a safe “what’s plugged in?” check (no serial reads):
```bash
python3 tools/usb_audit.py
```

If you need a safe “does data flow / is the port free?” check (short, bounded read):
```bash
python3 tools/bridge_probe.py
```

**⚠️ IMPORTANT:** Even if you use "safe" byte-limited reads (like `dd bs=100 count=5`), the session can still freeze if:
1. The session is interrupted while processing binary data during the "thinking" phase
2. The LIDAR motor stalls and stops sending data mid-read
3. The serial buffer has less data than requested

When a freeze occurs, the `dd` or `cat` process continues running in the background, holding the port open for subsequent sessions.

### Safe Serial Port Operations

**NEVER do this** - unbounded reads will hang your session:
```bash
# DANGEROUS - will hang
cat /dev/cu.wchusbserial1140
```

**DO this instead** - always limit bytes and use proper tools:
```bash
# Safer: hard-time-limit the read (this Mac has GNU coreutils `timeout`)
timeout --foreground -k 0.2s 1s dd if=/dev/cu.wchusbserial1140 bs=100 count=5 2>/dev/null | xxd | head -20

# Safe: Configure port without reading
stty -f /dev/cu.wchusbserial1140 115200
```

## Device Detection

The CH340 chip appears as:
- `/dev/cu.wchusbserial*` or `/dev/tty.wchusbserial*` (macOS)
- `/dev/ttyUSB*` or `/dev/ttyACM*` (Linux)
- `/dev/rovac_lidar` (Linux, after installing the udev rule in `udev/99-lidar-nano-usb.rules`)

```bash
# Find the device
ls -la /dev/cu.wch* /dev/tty.wch* /dev/cu.usb* /dev/tty.usb* 2>/dev/null

# Or, prefer the scripts in this folder:
python3 tools/find_lidar_port.py
python3 tools/usb_audit.py
```

## One-Time Install Then Seamless

Use this on a new machine to check prerequisites and (on Linux) set up a stable device name:

```bash
./install_once.sh
```

If you prefer a basic GUI installer (macOS + Linux), run:

```bash
./install_ui.py
```

On macOS, the GUI installer can run offline if `drivers/macos/CH341SER_MAC.ZIP` is present.

## XV11 LIDAR Protocol

| Parameter | Value |
|-----------|-------|
| Baud Rate | 115200 |
| Data Bits | 8 |
| Stop Bits | 1 |
| Parity | None |
| Output | Binary packets (22 bytes each) |

The LIDAR outputs continuous binary data when the motor is spinning. Each packet contains:
- Start byte (0xFA)
- Index byte (0xA0-0xF9 for angles 0-359)
- Speed (2 bytes)
- 4 distance readings (4 bytes each)
- Checksum (2 bytes)

## Recovery Procedures

### If Your Session Hangs

1. Open a new terminal
2. Find and kill stuck processes:
   ```bash
   # Find processes holding serial ports
   lsof /dev/cu.wchusbserial1140 2>/dev/null

   # Kill by PID (replace <PID> with actual number)
   kill -9 <PID>

   # Or kill all processes holding the LIDAR port in one command
   lsof /dev/cu.wchusbserial1140 2>/dev/null | awk 'NR>1 {print $2}' | xargs kill -9 2>/dev/null
   ```
3. Verify the port is free:
   ```bash
   lsof /dev/cu.wchusbserial1140 2>/dev/null || echo "Port is free"
   ```
4. Start a new Claude Code session

### Reset Serial Port State

```bash
stty -f /dev/cu.wchusbserial1140 sane
stty -f /dev/cu.wchusbserial1140 115200 cs8 -cstopb -parenb raw -echo
```

## Hardware Notes

- The Arduino Nano CH340 bridge is not truly driverless on macOS. This Mac is using the WCH DriverKit extension (`cn.wch.CH34xVCPDriver`).
- The XV11 motor needs 3.3V PWM to spin (controlled by Arduino)
- Data is only output when the motor is spinning at sufficient speed

## Project Goals

1. True plug-and-play operation (no driver installation)
2. Cross-platform compatibility (macOS, Linux, Windows)
3. Standard USB CDC device class
4. Self-contained power (USB-powered motor control)
