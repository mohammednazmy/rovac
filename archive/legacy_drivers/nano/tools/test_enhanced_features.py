#!/usr/bin/env python3
"""
Test script for enhanced firmware features
"""

import serial
import time


def test_enhanced_commands(port="/dev/cu.wchusbserial2140"):
    """Test enhanced firmware commands"""
    print(f"Testing enhanced firmware on {port}")

    try:
        # Open serial connection
        ser = serial.Serial(port, 115200, timeout=2)
        print("✅ Connected to device")

        # Flush input
        ser.reset_input_buffer()
        time.sleep(1)

        # Test device identification
        print("\n--- Testing Device Identification ---")
        ser.write(b"!id\n")
        time.sleep(0.5)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        print(f"ID Response: {repr(response)}")

        # Test version
        print("\n--- Testing Version ---")
        ser.write(b"!version\n")
        time.sleep(0.5)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        print(f"Version Response: {repr(response)}")

        # Test status
        print("\n--- Testing Status ---")
        ser.write(b"!status\n")
        time.sleep(0.5)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        print(f"Status Response: {repr(response)}")

        # Test help
        print("\n--- Testing Help ---")
        ser.write(b"!help\n")
        time.sleep(0.5)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        print(f"Help Response: {repr(response)}")

        # Test data flow
        print("\n--- Testing Data Flow ---")
        ser.reset_input_buffer()
        time.sleep(2)
        bytes_received = ser.in_waiting
        if bytes_received > 0:
            data = ser.read(min(bytes_received, 100))
            print(f"Data flow confirmed: {bytes_received} bytes available")
            print(f"Sample data: {str(data[:20])}...")
        else:
            print("No data received during test period")

        ser.close()
        print("\n✅ Enhanced firmware testing completed")
        return True

    except Exception as e:
        print(f"❌ Error testing enhanced firmware: {e}")
        return False


if __name__ == "__main__":
    test_enhanced_commands()
