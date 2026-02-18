#!/usr/bin/env python3
"""
Simple script to verify LIDAR data is flowing from the Nano USB bridge.
"""

import serial
import time
import sys


def simple_lidar_test(port="/dev/cu.wchusbserial2140", baudrate=115200, duration=5):
    """
    Simple test to verify data is coming from LIDAR.
    """
    print(f"Testing LIDAR on {port} at {baudrate} baud for {duration} seconds...")

    try:
        # Open serial connection
        ser = serial.Serial(port, baudrate, timeout=1)
        print("✅ Serial connection established")

        # Flush input buffer
        ser.reset_input_buffer()

        start_time = time.time()
        total_bytes = 0

        print("Listening for data...")

        while (time.time() - start_time) < duration:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                total_bytes += len(data)
                # Print a dot for every 100 bytes received
                if len(data) > 0:
                    print(".", end="", flush=True)

            time.sleep(0.1)

        ser.close()

        print(f"\n\n--- Results ---")
        print(f"Total bytes received: {total_bytes}")
        print(f"Average data rate: {total_bytes / duration:.1f} bytes/second")

        if total_bytes > 0:
            print("✅ SUCCESS: Data is flowing from LIDAR!")
            return True
        else:
            print("❌ WARNING: No data received")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False


if __name__ == "__main__":
    port = "/dev/cu.wchusbserial2140"
    if len(sys.argv) > 1:
        port = sys.argv[1]

    simple_lidar_test(port)
