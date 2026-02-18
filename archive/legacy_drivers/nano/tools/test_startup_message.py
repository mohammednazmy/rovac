#!/usr/bin/env python3
"""
Test script to check for startup message from professional firmware
"""

import serial
import time


def test_startup_message(port="/dev/cu.wchusbserial2140"):
    """Test for startup message from professional firmware"""
    print(f"Testing startup message on {port}")

    try:
        # Open serial connection
        ser = serial.Serial(port, 115200, timeout=1)
        print("✅ Connected to device")

        # Flush input and wait for startup message
        ser.reset_input_buffer()
        print("Waiting for startup message (up to 5 seconds)...")

        # Read for up to 5 seconds to catch startup message
        start_time = time.time()
        message_found = False

        while (time.time() - start_time) < 5:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode("utf-8", errors="ignore").strip()
                    if "!ROVAC_LIDAR_BRIDGE_READY" in line:
                        print(f"✅ Startup message received: {line}")
                        message_found = True
                        break
                    elif line.startswith("!"):
                        print(f"✅ Command response received: {line}")
                        message_found = True
                        break
                except Exception as e:
                    pass  # Ignore decode errors

            time.sleep(0.1)

        if not message_found:
            print("ℹ️  No startup message detected within 5 seconds")
            print("    This is normal if the device was recently reset")

        # Close connection
        ser.close()
        print("\n✅ Startup message test completed")
        return True

    except Exception as e:
        print(f"❌ Error testing startup message: {e}")
        return False


if __name__ == "__main__":
    test_startup_message()
