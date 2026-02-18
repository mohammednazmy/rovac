# USB LIDAR Module: Plug-and-Play Assessment

This directory tracks a USB LIDAR module built from a Neato XV11 LIDAR plus an Arduino Nano‑class board acting as a USB‑to‑serial bridge.

## Current USB Device (Observed on this Mac)

- Serial port: `/dev/cu.wchusbserial1140`
- USB VID:PID: `0x1A86:0x7523` (QinHeng/WCH CH340 family)
- USB product string: `USB Serial`
- USB serial number: **none** (not reported)
- macOS driver in use: `cn.wch.CH34xVCPDriver` (DriverKit system extension)
- USB device class: `0xFF` (vendor-specific, not USB CDC)

You can reproduce the above safely (no serial reads) with:

```bash
python3 tools/usb_audit.py
```

## Is it “Truly Plug-and-Play” Today?

**Linux:** Usually yes (kernel `ch341` driver is typically present).

**macOS:** Not truly plug-and-play on a clean machine. This device works here because the WCH CH34x DriverKit extension is installed and enabled (`cn.wch.CH34xVCPDriver`). Without that driver, the `/dev/cu.wchusbserial*` device node typically won’t appear.

**Windows:** Often requires a CH340 driver install (sometimes via Windows Update, but not guaranteed). Relying on a driver download/install step is not “plug-and-play”.

## “One-time Install Then Seamless” (Software-Only)

You can’t make a CH340-based device driverless via Arduino firmware alone, but you can make it *practically* plug-and-play after a one-time setup:

1. Run the one-time setup helper:
   ```bash
   ./install_once.sh
   ```
   Or use the basic GUI installer:
   ```bash
   ./install_ui.py
   ```
2. After that, use the discovery/probe tools:
   ```bash
   python3 tools/find_lidar_port.py
   python3 tools/bridge_probe.py
   ```

Notes:
- On Linux, `./install_once.sh` prints (or installs, if run as root) a udev rule from `udev/99-lidar-nano-usb.rules` to create a stable `/dev/rovac_lidar` symlink.
- `tools/bridge_probe.py` is designed to be safe: it uses short serial timeouts and only samples a small window of bytes (no unbounded reads).
- On macOS, `install_ui.py` can use a bundled offline driver zip at `drivers/macos/CH341SER_MAC.ZIP` (contains `CH34xVCPDriver.pkg`).

## What’s Blocking Plug-and-Play

1. **CH340 enumerates as vendor-specific USB (`0xFF`)**, so the OS needs a vendor driver (or an OS-bundled chip-specific driver).
2. **No USB serial number** makes it hard to reliably identify the device when multiple serial devices are connected, and makes COM port stability worse on Windows.
3. **Generic strings (or missing manufacturer/product fields)** reduce user confidence and make automated matching harder.

## Recommended Paths to “Truly Plug-and-Play”

### Path A (Best): Switch to a native-USB MCU and present as USB CDC-ACM

Replace the CH340-based Nano with a microcontroller that can implement USB directly and enumerate as **USB CDC-ACM** (standard “USB Serial” class).

Benefits:
- Driverless on Linux/macOS, and typically driverless on modern Windows when using a standards-compliant CDC configuration.
- You can set **Manufacturer/Product strings** and a **unique serial number**.
- You can keep the host-side interface as “serial port @ 115200”, which works well with existing XV11 tooling.

### Path B (Good): Use a USB-serial bridge that ships with OS drivers

Swap the CH340 bridge for a USB‑serial IC that has OS-bundled drivers across macOS/Windows/Linux.

Notes:
- This can be “practically plug-and-play” for most users.
- You still may not control USB descriptors as cleanly as a native-USB MCU solution.

### Path C (Driverless but different): USB HID interface

Enumerate as USB HID and use a small host library/app to read HID reports.

Benefits:
- HID is driverless everywhere.
Tradeoffs:
- Not a serial port; existing XV11 serial tools won’t work without a bridge layer.

## Host-Side “Plug-and-Play” Improvements (Regardless of Hardware)

- Provide a small tool that discovers the port by VID/PID (and serial number when available): `python3 tools/find_lidar_port.py`.
- Avoid unbounded reads (`cat /dev/cu...`); always use a hard timeout if you must sample bytes.
- On Linux, add a udev rule to create a stable symlink (only applicable if the bridge exposes stable identity like VID/PID/serial).
