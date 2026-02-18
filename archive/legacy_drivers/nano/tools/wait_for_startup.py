#!/usr/bin/env python3
import serial
import time


def wait_for_startup():
    print("Waiting for device startup message...")

    try:
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)

        # Flush and wait for startup
        ser.reset_input_buffer()
        print("Waiting for startup message (up to 5 seconds)...")

        start_time = time.time()
        found_startup = False

        while (time.time() - start_time) < 5:
            if ser.in_waiting > 0:
                line = ser.readline().decode("utf-8", errors="ignore")
                print(f"Received: {repr(line)}")
                if "!ROVAC_LIDAR_BRIDGE_READY" in line or "ROVAC_LIDAR_BRIDGE" in line:
                    print("✅ Startup message detected!")
                    found_startup = True
                    break
            time.sleep(0.1)

        if not found_startup:
            print("ℹ️  No startup message found, continuing anyway...")

        ser.close()

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    wait_for_startup()
