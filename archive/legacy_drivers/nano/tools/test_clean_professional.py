#!/usr/bin/env python3
import serial
import time


def test_professional_features():
    print("Testing clean professional features...")

    try:
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=2)
        print("✅ Connected to device")

        # Wait for any startup messages and flush
        time.sleep(2)
        ser.reset_input_buffer()
        time.sleep(0.5)

        # Test device ID
        print("\n--- Testing Device ID ---")
        ser.write(b"!id\n")
        time.sleep(1)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        print(f"Response: {repr(response)}")

        # Look for our specific response
        if "!DEVICE_ID:ROVAC_LIDAR_BRIDGE" in response:
            print("✅ Device ID confirmed!")
        elif "!ROVAC_LIDAR_BRIDGE" in response:
            print("✅ Device startup message detected!")

        # Flush and test version
        ser.reset_input_buffer()
        print("\n--- Testing Version ---")
        ser.write(b"!version\n")
        time.sleep(1)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        print(f"Response: {repr(response)}")

        # Flush and test help
        ser.reset_input_buffer()
        print("\n--- Testing Help ---")
        ser.write(b"!help\n")
        time.sleep(1)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        print(f"Response: {repr(response)}")

        # Test data flow
        ser.reset_input_buffer()
        print("\n--- Testing Data Flow ---")
        time.sleep(2)
        bytes_avail = ser.in_waiting
        if bytes_avail > 0:
            data = ser.read(min(bytes_avail, 100))
            print(f"✅ Data flow confirmed: {bytes_avail} bytes available")
        else:
            print("❌ No data flow detected")

        ser.close()
        print("\n✅ Professional feature testing completed")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    test_professional_features()
