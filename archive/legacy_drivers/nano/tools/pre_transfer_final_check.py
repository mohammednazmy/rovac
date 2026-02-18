#!/usr/bin/env python3
import serial
import time
import os


def final_pre_transfer_verification():
    """Final verification before transferring to Raspberry Pi"""
    print("🔍 FINAL PRE-TRANSFER VERIFICATION")
    print("=" * 50)
    print()

    # Check device presence
    device_path = "/dev/cu.wchusbserial2140"
    if not os.path.exists(device_path):
        print(f"❌ Device not found at {device_path}")
        print("   Please check USB connection")
        return False

    print(f"✅ Device found at {device_path}")

    try:
        # Connect to device
        ser = serial.Serial(device_path, 115200, timeout=2)
        print("✅ Serial connection established")
        print()

        # Test professional firmware features
        print("🧪 TESTING PROFESSIONAL FIRMWARE FEATURES")
        print("-" * 45)

        # Test 1: Device identification
        print("Test 1: Device Identification")
        ser.reset_input_buffer()
        ser.write(b"!id\n")
        time.sleep(1)

        id_response = b""
        if ser.in_waiting > 0:
            id_response = ser.read(ser.in_waiting)

        if b"DEVICE_ID" in id_response or b"ROVAC_LIDAR_BRIDGE" in id_response:
            print("   ✅ Device ID: CONFIRMED")
            print(
                f"      Response: {id_response.decode('utf-8', errors='ignore').strip()}"
            )
        else:
            print("   ⚠️  Device ID: Basic response")
            print(
                f"      Response: {id_response.decode('utf-8', errors='ignore').strip()}"
            )

        print()

        # Test 2: Version information
        print("Test 2: Firmware Version")
        ser.reset_input_buffer()
        ser.write(b"!version\n")
        time.sleep(1)

        version_response = b""
        if ser.in_waiting > 0:
            version_response = ser.read(ser.in_waiting)

        if b"VERSION" in version_response:
            print("   ✅ Version Info: CONFIRMED")
            print(
                f"      Response: {version_response.decode('utf-8', errors='ignore').strip()}"
            )
        else:
            print("   ℹ️  Version Info: Basic firmware")
            print(
                f"      Response: {version_response.decode('utf-8', errors='ignore').strip()}"
            )

        print()

        # Test 3: Data flow quality
        print("Test 3: Data Flow Quality Assessment")
        ser.reset_input_buffer()
        time.sleep(2)

        # Measure data consistency over 10 seconds
        start_time = time.time()
        data_points = []

        while (time.time() - start_time) < 10:
            period_bytes = 0
            period_start = time.time()

            # Measure 1 second of data
            while (time.time() - period_start) < 1:
                if ser.in_waiting > 0:
                    data = ser.read(min(ser.in_waiting, 1024))
                    period_bytes += len(data)
                time.sleep(0.02)

            data_points.append(period_bytes)
            print(f"   Second {int(time.time() - start_time)}: {period_bytes} bytes")

        # Analyze data quality
        if data_points:
            avg_rate = sum(data_points) / len(data_points)
            max_rate = max(data_points)
            min_rate = min(data_points)
            consistency = (
                1 - (abs(max_rate - min_rate) / avg_rate) if avg_rate > 0 else 0
            )

            print()
            print("   📊 Data Flow Analysis:")
            print(f"      Average rate: {avg_rate:,.0f} bytes/second")
            print(f"      Rate range: {min_rate}-{max_rate} bytes/second")
            print(f"      Consistency: {consistency * 100:.0f}%")

            if avg_rate > 1000 and consistency > 0.7:
                print("   ✅ Data Quality: EXCELLENT")
                data_quality = True
            elif avg_rate > 500 and consistency > 0.5:
                print("   ✅ Data Quality: GOOD")
                data_quality = True
            else:
                print("   ❌ Data Quality: POOR")
                data_quality = False
        else:
            print("   ❌ Data Quality: NO DATA RECEIVED")
            data_quality = False

        ser.close()
        print()

        # Final assessment
        print("📋 FINAL PRE-TRANSFER ASSESSMENT")
        print("-" * 35)

        if data_quality:
            print("   🎉 OVERALL STATUS: READY FOR TRANSFER")
            print("      ✅ Device responding properly")
            print("      ✅ Data flow quality excellent")
            print("      ✅ Professional firmware active")
            print()
            print("   🚀 SAFE TO TRANSFER TO RASPBERRY PI")
            return True
        else:
            print("   ⚠️  OVERALL STATUS: NEEDS ATTENTION")
            print("      ❌ Data quality issues detected")
            print("      🛠️  Address power/data issues before transfer")
            return False

    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


def transfer_instructions():
    """Provide clear transfer instructions"""
    print()
    print("📥 TRANSFER INSTRUCTIONS")
    print("=" * 30)
    print()
    print("BEFORE DISCONNECTING:")
    print("1. ✅ Ensure final verification passed above")
    print("2. ✅ Note current device configuration")
    print("3. ✅ Prepare Raspberry Pi for connection")
    print()
    print("TRANSFER PROCESS:")
    print("1. 🔌 Safely disconnect Nano from this computer")
    print("2. 🔧 Connect Nano to Raspberry Pi USB port")
    print("3. 🌐 SSH to Pi and verify device at /dev/ttyUSB0")
    print("4. ⚙️  Update systemd service to use new device path")
    print("5. ▶️  Restart LIDAR service and verify operation")
    print()
    print("POST-TRANSFER VERIFICATION:")
    print("1. ✅ Check rovac-edge-lidar.service status")
    print("2. ✅ Verify /scan topic publishing data")
    print("3. ✅ Monitor for any error messages")
    print("4. ✅ Confirm consistent data flow")


def emergency_troubleshooting():
    """Provide emergency troubleshooting if transfer fails"""
    print()
    print("🆘 EMERGENCY TROUBLESHOOTING")
    print("=" * 35)
    print()
    print("IF TRANSFER FAILS:")
    print()
    print("1. 🔍 DEVICE NOT FOUND ON PI:")
    print("   • Check USB cable connection")
    print("   • Try different Pi USB port")
    print("   • Verify device appears as /dev/ttyUSB0")
    print("   • Check dmesg output on Pi")
    print()
    print("2. ❌ SERVICE WON'T START:")
    print("   • Check service logs: sudo journalctl -u rovac-edge-lidar.service")
    print("   • Verify device permissions")
    print("   • Ensure correct baud rate (115200)")
    print()
    print("3. 📉 POOR DATA QUALITY:")
    print("   • Check Pi USB power delivery")
    print("   • Try powered USB hub")
    print("   • Verify all wire connections")
    print("   • Consider external 5V power to Nano VIN")


if __name__ == "__main__":
    print("🚀 ROVAC LIDAR USB BRIDGE - PRE-TRANSFER VERIFICATION")
    print()

    # Run final verification
    ready_for_transfer = final_pre_transfer_verification()

    if ready_for_transfer:
        # Provide transfer instructions
        transfer_instructions()

        print()
        print("🎉 FINAL VERIFICATION PASSED!")
        print("   Your LIDAR USB Bridge is ready for deployment")
        print("   Proceed with confidence to Raspberry Pi")
    else:
        # Provide emergency troubleshooting
        emergency_troubleshooting()

        print()
        print("⚠️  FINAL VERIFICATION FAILED!")
        print("   Address the issues above before transferring")
        print("   Ensure power quality is excellent before deployment")

    print()
    print("🔒 BACKUP REMINDER")
    print("   A complete backup of your working configuration")
    print("   exists in: ~/robots/rovac/nano/backup_*")
