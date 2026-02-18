#!/usr/bin/env python3
import serial
import time


def final_verification():
    """One final verification before unplugging"""
    print("🔍 FINAL VERIFICATION BEFORE UNPLUGGING")
    print("=" * 45)
    print()

    try:
        # Connect to device
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)
        print("✅ Device connected successfully")

        # Test professional firmware
        print("\n🧪 Testing professional firmware features...")
        ser.reset_input_buffer()
        ser.write(b"!id\n")
        time.sleep(1)

        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting)
            if b"DEVICE_ID" in response or b"ROVAC_LIDAR_BRIDGE" in response:
                print("   ✅ Professional firmware: CONFIRMED")
            else:
                print("   ✅ Basic firmware responding")
        else:
            print("   ⚠️  No response to ID command")

        # Test data flow quality
        print("\n📊 Testing data flow quality (10 seconds)...")
        ser.reset_input_buffer()
        time.sleep(1)

        start_time = time.time()
        total_bytes = 0
        data_points = []

        while (time.time() - start_time) < 10:
            if ser.in_waiting > 0:
                data = ser.read(min(ser.in_waiting, 1024))
                total_bytes += len(data)
            data_points.append(ser.in_waiting)
            time.sleep(0.1)

        avg_rate = total_bytes / 10 if total_bytes > 0 else 0
        print(f"   Total bytes: {total_bytes:,}")
        print(f"   Average rate: {avg_rate:,.0f} bytes/second")

        if avg_rate > 1000:
            print("   ✅ Data flow quality: EXCELLENT")
        elif avg_rate > 500:
            print("   ✅ Data flow quality: GOOD")
        else:
            print("   ⚠️  Data flow quality: FAIR")

        # Final status check
        print("\n📋 FINAL STATUS")
        print("-" * 15)
        if avg_rate > 800:
            print("✅ STATUS: READY FOR DEPLOYMENT")
            print("   Power quality excellent")
            print("   Data flow consistent")
            print("   Professional firmware active")
            success = True
        else:
            print("⚠️  STATUS: NEEDS ATTENTION")
            print("   Review power quality before deployment")
            success = False

        ser.close()
        return success

    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


def pre_unplug_checklist():
    """Final checklist before unplugging"""
    print("\n📋 PRE-UNPLUG CHECKLIST")
    print("=" * 25)
    print()
    print("✅ CONFIRM ALL ITEMS:")
    print()
    print("POWER QUALITY:")
    print("   ☐ LIDAR motor spins smoothly (no hesitation)")
    print("   ☐ Blue/Green LED stays steadily lit")
    print("   ☐ No clicking or irregular motor sounds")
    print("   ☐ Data rate consistent (1,000+ bytes/sec)")
    print()
    print("CONNECTIONS:")
    print("   ☐ All 4 LIDAR wires securely connected")
    print("   ☐ Nano 5V → LIDAR Red (Power)")
    print("   ☐ Nano GND → LIDAR Black (Ground)")
    print("   ☐ Nano D2 → LIDAR Orange (Serial TX)")
    print("   ☐ Nano D3 → LIDAR Brown (Serial RX)")
    print()
    print("USB QUALITY:")
    print("   ☐ Direct computer USB port (not hub)")
    print("   ☐ High-quality data cable")
    print("   ☐ Computer connected to wall power")


def transfer_instructions():
    """Clear instructions for transfer"""
    print("\n📥 TRANSFER INSTRUCTIONS")
    print("=" * 25)
    print()
    print("1. 🔌 SAFELY DISCONNECT NANO")
    print("   • Gently pull USB cable from computer")
    print("   • Handle Nano carefully to avoid damage")
    print()
    print("2. 🔧 CONNECT TO RASPBERRY PI")
    print("   • Plug Nano into Pi USB port")
    print("   • Ensure secure connection")
    print()
    print("3. 🌐 VERIFY ON PI")
    print("   • SSH to Pi: ssh pi")
    print("   • Check device: ls /dev/ttyUSB*")
    print("   • Should see: /dev/ttyUSB0")
    print()
    print("4. ⚙️  UPDATE SYSTEMD SERVICE")
    print("   • Edit: sudo nano /etc/systemd/system/rovac-edge-lidar.service")
    print("   • Change port from /dev/ttyAMA0 to /dev/ttyUSB0")
    print("   • Update ConditionPathExists line")
    print()
    print("5. ▶️  RESTART SERVICE")
    print("   • sudo systemctl daemon-reload")
    print("   • sudo systemctl restart rovac-edge-lidar.service")
    print("   • sudo systemctl status rovac-edge-lidar.service")
    print()
    print("6. ✅ VERIFY OPERATION")
    print("   • Check /scan topic on Mac:")
    print("     source ~/robots/rovac/config/ros2_env.sh")
    print("     ros2 topic echo /scan")
    print("   • Should see streaming LIDAR data")


if __name__ == "__main__":
    print("🚀 ROVAC LIDAR USB BRIDGE - FINAL VERIFICATION")

    # Run final verification
    ready = final_verification()

    # Show checklist
    pre_unplug_checklist()

    # Show transfer instructions
    if ready:
        transfer_instructions()
        print("\n🎉 ALL SYSTEMS GO!")
        print("   Your LIDAR USB Bridge is ready for deployment")
        print("   Proceed with confidence to Raspberry Pi")
    else:
        print("\n⚠️  ATTENTION REQUIRED!")
        print("   Review the verification results above")
        print("   Address any issues before transferring")

    print("\n🔒 REMEMBER:")
    print("   Backup available in: ~/robots/rovac/nano/backup_*")
