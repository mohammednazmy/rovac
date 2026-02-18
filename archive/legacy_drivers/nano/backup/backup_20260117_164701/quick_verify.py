#!/usr/bin/env python3
"""
Quick verification script for ROVAC LIDAR USB Bridge Professional Enhancement
"""

import serial
import serial.tools.list_ports
import time
import platform


def find_and_test_device():
    """Find ROVAC LIDAR device and test professional features"""
    print("=" * 60)
    print("  ROVAC LIDAR USB Bridge - Quick Verification")
    print("=" * 60)
    print()

    print(f"🖥️  Platform: {platform.system()} {platform.release()}")
    print()

    # Find potential devices
    print("🔍 Searching for ROVAC LIDAR devices...")
    ports = serial.tools.list_ports.comports()

    rovac_devices = []
    for port in ports:
        # Look for CH340 devices (common for LAFVIN Nano)
        if (
            (hasattr(port, "vid") and port.vid == 6790)
            or (hasattr(port, "description") and "CH340" in str(port.description))
            or (hasattr(port, "device") and "wchusbserial" in str(port.device).lower())
        ):
            rovac_devices.append(port)
            print(
                f"   ✅ Found: {getattr(port, 'device', 'Unknown')} - {getattr(port, 'description', 'Unknown')}"
            )

    if not rovac_devices:
        print("   ❌ No ROVAC LIDAR devices found")
        print()
        print("   Troubleshooting tips:")
        print("   1. Check USB connection")
        print("   2. Ensure CH340 drivers are installed")
        print("   3. Try different USB port")
        return False

    print()

    # Test first device
    device_port = getattr(rovac_devices[0], "device", "Unknown")
    print(f"🔌 Testing device: {device_port}")

    try:
        # Connect to device
        ser = serial.Serial(device_port, 115200, timeout=2)
        print("✅ Serial connection established")

        # Test enhanced features
        print()
        print("🧪 Testing professional features...")

        # Test device identification
        print("   Testing device identification...")
        ser.reset_input_buffer()
        ser.write(b"!id\n")
        time.sleep(0.5)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""

        if "!DEVICE_ID" in response or "!ROVAC_LIDAR_BRIDGE" in response:
            print(f"   ✅ Professional firmware detected: {response.strip()}")
            professional = True
        else:
            print("   ℹ️  Basic firmware detected")
            professional = False

        # Test data flow
        print("   Testing data flow...")
        ser.reset_input_buffer()
        time.sleep(2)
        bytes_available = ser.in_waiting

        if bytes_available > 0:
            data = ser.read(min(bytes_available, 100))
            print(f"   ✅ Data flow confirmed: {bytes_available} bytes available")
            data_flow = True
        else:
            print("   ❌ No data flow detected")
            data_flow = False

        ser.close()

        print()
        print("📋 SUMMARY")
        print("===========")
        if professional and data_flow:
            print("🎉 SUCCESS! Professional enhancement is working perfectly!")
            print("   • Enhanced firmware responding")
            print("   • Data flow confirmed")
            print("   • Device ready for professional use")
        elif data_flow:
            print("✅ BASIC SUCCESS! Device is working with data flow")
            print("   • Basic firmware functional")
            print("   • Data flow confirmed")
            print("   • Ready for standard use")
        else:
            print("❌ ISSUE DETECTED!")
            print("   • Device connected but no data flow")
            print("   • Check wiring and LIDAR power")

        return data_flow  # Success if we have data flow

    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


def main():
    """Main function"""
    success = find_and_test_device()

    print()
    print("=" * 60)
    if success:
        print("✅ VERIFICATION COMPLETE - YOUR DEVICE IS READY!")
    else:
        print("❌ VERIFICATION FAILED - PLEASE CHECK CONNECTION!")
    print("=" * 60)


if __name__ == "__main__":
    main()
