#!/usr/bin/env python3
"""
Cross-platform device testing script for ROVAC LIDAR USB Bridge
"""

import serial
import serial.tools.list_ports
import time
import sys
import platform


def find_rovac_devices():
    """Find all ROVAC LIDAR devices connected to the system"""
    devices = []

    # List all available serial ports
    ports = serial.tools.list_ports.comports()

    for port in ports:
        # Check for CH340 devices (common VID/PID for LAFVIN Nano)
        try:
            if (
                (port.vid and str(port.vid) == "6790")
                or ("CH340" in port.description)
                or ("wchusbserial" in port.device.lower())
            ):
                devices.append(
                    {
                        "device": port.device,
                        "description": port.description,
                        "vid": port.vid,
                        "pid": port.pid,
                    }
                )
        except:
            # Fallback for any attribute errors
            if ("CH340" in str(port.description) if port.description else "") or (
                "wchusbserial" in str(port.device).lower() if port.device else ""
            ):
                devices.append(
                    {
                        "device": getattr(port, "device", "Unknown"),
                        "description": getattr(port, "description", "Unknown"),
                        "vid": getattr(port, "vid", None),
                        "pid": getattr(port, "pid", None),
                    }
                )

    return devices


def test_device_communication(device_path, baudrate=115200):
    """Test communication with the device"""
    print(f"Testing device: {device_path}")

    try:
        # Open serial connection
        ser = serial.Serial(device_path, baudrate, timeout=2)
        print("✅ Serial connection established")

        # Flush input
        ser.reset_input_buffer()

        # Try to get device ID (enhanced firmware)
        print("Checking for enhanced firmware...")
        ser.write(b"!id\n")
        time.sleep(0.1)

        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        if "!DEVICE_ID" in response:
            print("✅ Enhanced firmware detected")
            print(f"   Response: {response.strip()}")

            # Get version
            ser.write(b"!version\n")
            time.sleep(0.1)
            version_response_raw = ser.read_all()
            version_response = (
                version_response_raw.decode("utf-8", errors="ignore")
                if version_response_raw
                else ""
            )
            print(f"   {version_response.strip()}")

            # Get status
            ser.write(b"!status\n")
            time.sleep(0.1)
            status_response_raw = ser.read_all()
            status_response = (
                status_response_raw.decode("utf-8", errors="ignore")
                if status_response_raw
                else ""
            )
            print(f"   {status_response.strip()}")
        else:
            print("ℹ️  Basic firmware detected (no enhanced features)")

        # Test data flow
        print("Testing data flow for 3 seconds...")
        ser.reset_input_buffer()

        start_time = time.time()
        total_bytes = 0

        while (time.time() - start_time) < 3:
            if ser.in_waiting > 0:
                data = ser.read(min(ser.in_waiting, 1024))
                total_bytes += len(data)

        ser.close()

        print(f"   Bytes received: {total_bytes}")
        if total_bytes > 0:
            print("✅ Data flow confirmed")
            return True
        else:
            print("❌ No data received")
            return False

    except Exception as e:
        print(f"❌ Communication error: {e}")
        return False


def main():
    print("=== ROVAC LIDAR USB Bridge Tester ===")
    print(f"Platform: {platform.system()} {platform.release()}")
    print()

    # Find devices
    devices = find_rovac_devices()

    if not devices:
        print("❌ No ROVAC LIDAR devices found")
        print()
        print("Troubleshooting tips:")
        print("1. Check USB connection")
        print("2. Ensure CH340 drivers are installed")
        print("3. Try different USB port")
        print("4. Run installation script:")
        print("   ~/robots/rovac/nano/cross_platform_support/install_rules.sh")
        return 1

    print(f"Found {len(devices)} potential device(s):")
    for i, device in enumerate(devices):
        print(f"  {i + 1}. {device['device']} - {device['description']}")
        if device["vid"]:
            print(f"      VID: {device['vid']}, PID: {device['pid']}")
    print()

    # Test each device
    success_count = 0
    for device in devices:
        if test_device_communication(device["device"]):
            success_count += 1
        print()

    if success_count > 0:
        print(f"✅ {success_count}/{len(devices)} devices working correctly")
        return 0
    else:
        print(f"❌ All devices failed testing")
        return 1


if __name__ == "__main__":
    sys.exit(main())
