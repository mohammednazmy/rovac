#!/usr/bin/env python3
import serial
import time


def simple_test():
    print("Simple test of professional firmware...")

    try:
        # Open serial connection
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)
        print("✅ Connected to device")

        # Wait and flush
        time.sleep(2)
        ser.reset_input_buffer()
        print("Flushed input buffer, waiting for startup message...")

        # Try to read any startup messages
        for i in range(10):  # Try 10 times
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                text = data.decode("utf-8", errors="ignore")
                print(f"Data received: {repr(text)}")
                if "ROVAC_LIDAR_BRIDGE" in text:
                    print("✅ Found startup message!")
                    break
            time.sleep(0.5)

        # Send a simple command
        print("\nSending !id command...")
        ser.write(b"!id\n")
        time.sleep(1)

        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting)
            text = response.decode("utf-8", errors="ignore")
            print(f"Response: {repr(text)}")
            if "DEVICE_ID" in text or "ROVAC" in text:
                print("✅ Professional firmware responding!")
            else:
                print("ℹ️  Got response but not clearly professional")
        else:
            print("❌ No response to command")

        ser.close()

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    simple_test()
