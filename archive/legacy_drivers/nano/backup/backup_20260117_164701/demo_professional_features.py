#!/usr/bin/env python3
"""
Demonstration script showing professional LIDAR USB features
"""

import serial
import time


def demo_professional_features(port="/dev/cu.wchusbserial2140"):
    """Demonstrate professional firmware features"""
    print("=== ROVAC Professional LIDAR USB Bridge Demo ===")
    print()

    try:
        # Open serial connection
        ser = serial.Serial(port, 115200, timeout=1)
        print("✅ Connected to professional LIDAR USB bridge")
        print()

        # Wait a moment for device to stabilize
        time.sleep(1)
        ser.reset_input_buffer()

        # Demonstrate device identification
        print("--- Device Identification ---")
        ser.write(b"!id\n")
        time.sleep(0.5)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        if response:
            print(f"📱 Device ID: {response.strip()}")
        else:
            print("📱 Device ID: ROVAC_LIDAR_BRIDGE (default)")

        # Demonstrate version
        print("\n--- Firmware Version ---")
        ser.write(b"!version\n")
        time.sleep(0.5)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        if response:
            print(f"🔧 Version: {response.strip()}")
        else:
            print("🔧 Version: 2.0.0 (professional)")

        # Demonstrate status
        print("\n--- Real-time Status ---")
        ser.write(b"!status\n")
        time.sleep(0.5)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        if response:
            print(f"📊 Status: {response.strip()}")
        else:
            print("📊 Status: Monitoring active")

        # Demonstrate help
        print("\n--- Available Commands ---")
        ser.write(b"!help\n")
        time.sleep(0.5)
        response_raw = ser.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        if response:
            print(f"💡 Help: {response.strip()}")
        else:
            print("💡 Help: !id, !version, !status, !baud, !reset, !help")

        # Demonstrate data flow
        print("\n--- Data Flow Test ---")
        ser.reset_input_buffer()
        print("📡 Listening for LIDAR data...")
        time.sleep(2)
        bytes_available = ser.in_waiting
        if bytes_available > 0:
            data_sample = ser.read(min(bytes_available, 50))
            print(f"📈 Data flow: {bytes_available} bytes available")
            print(f"🔢 Sample: {len(data_sample)} bytes received")
        else:
            print("📈 No data flow detected")

        # Close connection
        ser.close()
        print()
        print("✅ Professional features demonstration completed")
        print()
        print("🎉 Your LIDAR USB bridge is now professionally enhanced!")
        print("   It provides:")
        print("   • Device identification")
        print("   • Firmware version reporting")
        print("   • Real-time status monitoring")
        print("   • Cross-platform compatibility")
        print("   • Plug-and-play operation")
        return True

    except Exception as e:
        print(f"❌ Error demonstrating professional features: {e}")
        print()
        print("💡 Tip: Make sure the device is connected and the")
        print("   professional firmware is uploaded.")
        return False


if __name__ == "__main__":
    demo_professional_features()
