#!/usr/bin/env python3
import serial
import time


def observe_lidar_behavior():
    """Observe LIDAR behavior to assess power quality"""
    print("👀 OBSERVING LIDAR BEHAVIOR")
    print("=" * 40)

    try:
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)
        print("✅ Connected to LIDAR")
        print()

        # Visual observation indicators
        print("LOOK FOR THESE INDICATORS:")
        print("✅ STEADY OPERATION:")
        print("   - LIDAR motor spins smoothly without hesitation")
        print("   - Blue/Green LED stays steadily lit (not blinking)")
        print("   - No clicking, grinding, or irregular sounds")
        print("   - Immediate startup when powered")
        print()
        print("❌ POWER ISSUES:")
        print("   - Motor speeds up/down erratically")
        print("   - LED flickers or dims periodically")
        print("   - Clicking sounds or motor stalls")
        print("   - Slow startup or intermittent operation")
        print()

        # Monitor for 15 seconds
        print("Monitoring LIDAR behavior for 15 seconds...")
        start_time = time.time()

        data_rates = []
        consistent_data = True

        while (time.time() - start_time) < 15:
            elapsed = int(time.time() - start_time)

            if ser.in_waiting > 0:
                bytes_available = ser.in_waiting
                data = ser.read(min(bytes_available, 1024))

                # Track data consistency as indicator of motor stability
                data_rates.append(len(data))

                # Report periodically
                if elapsed % 3 == 0 and elapsed > 0:
                    avg_recent = (
                        sum(data_rates[-10:]) / min(10, len(data_rates))
                        if data_rates
                        else 0
                    )
                    print(
                        f"   Time {elapsed}s: {len(data)} bytes received (avg recent: {avg_recent:.0f})"
                    )

                    # Check for significant drops that might indicate power issues
                    if len(data_rates) > 5:
                        recent_avg = sum(data_rates[-5:]) / 5
                        overall_avg = sum(data_rates) / len(data_rates)
                        if recent_avg < overall_avg * 0.5:
                            print("   ⚠️  Possible power interruption detected")
                            consistent_data = False

            time.sleep(0.1)

        ser.close()

        print()
        print("📊 BEHAVIOR ANALYSIS")
        print("-" * 25)

        if data_rates:
            avg_rate = sum(data_rates) / len(data_rates)
            max_rate = max(data_rates) if data_rates else 0
            min_rate = min(data_rates) if data_rates else 0

            print(f"   Average data rate: {avg_rate:.0f} bytes/period")
            print(f"   Rate range: {min_rate}-{max_rate} bytes/period")

            # Assess consistency
            if max_rate - min_rate < avg_rate * 0.5:
                print("   ✅ Data consistency: STABLE")
                data_stable = True
            else:
                print("   ⚠️  Data consistency: VARIABLE")
                data_stable = False

            # Assess overall quality
            if avg_rate > 500 and data_stable:
                print("   ✅ Overall operation: GOOD")
                print("      LIDAR appears to have adequate stable power")
                return True
            elif avg_rate > 200:
                print("   ⚠️  Overall operation: ACCEPTABLE")
                print("      LIDAR operation is fair but could be better")
                return True
            else:
                print("   ❌ Overall operation: POOR")
                print("      LIDAR likely has power supply issues")
                return False
        else:
            print("   ❌ No data received - check connections")
            return False

    except Exception as e:
        print(f"❌ Error observing LIDAR: {e}")
        return False


def check_power_delivery():
    """Check USB power delivery characteristics"""
    print()
    print("🔌 USB POWER DELIVERY CHECK")
    print("=" * 40)

    try:
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)
        print("✅ USB connection established")

        # Quick power stress test
        print("Performing brief power stress test...")

        # Send rapid commands to increase current draw
        for i in range(5):
            ser.write(b"!id\n")
            ser.write(b"!version\n")
            time.sleep(0.1)

        # Monitor response
        ser.reset_input_buffer()
        time.sleep(2)

        # Check data flow during "stress"
        bytes_before = ser.in_waiting
        time.sleep(3)
        bytes_after = ser.in_waiting

        print(f"   Baseline data availability: {bytes_before} bytes")
        print(f"   Post-stress data availability: {bytes_after} bytes")

        # If data flow stops during stress, power may be inadequate
        if bytes_after > bytes_before + 100:
            print("   ✅ Power delivery: STABLE UNDER LOAD")
            power_stable = True
        elif bytes_after > bytes_before:
            print("   ✅ Power delivery: ADEQUATE")
            power_stable = True
        else:
            print("   ⚠️  Power delivery: MARGINAL")
            power_stable = False

        ser.close()
        return power_stable

    except Exception as e:
        print(f"❌ Error during power check: {e}")
        return False


def final_power_assessment():
    """Final comprehensive power assessment"""
    print()
    print("🔍 FINAL POWER QUALITY ASSESSMENT")
    print("=" * 50)

    # Observe behavior
    behavior_ok = observe_lidar_behavior()

    # Check power delivery
    power_ok = check_power_delivery()

    print()
    print("📋 COMPREHENSIVE ASSESSMENT")
    print("-" * 30)

    if behavior_ok and power_ok:
        print("   ✅ POWER QUALITY: EXCELLENT")
        print("      LIDAR has adequate stable power supply")
        print("      Ready for deployment to Raspberry Pi")
        return True
    elif behavior_ok or power_ok:
        print("   ⚠️  POWER QUALITY: ACCEPTABLE")
        print("      LIDAR operation is functional but marginal")
        print("      Monitor closely after deployment")
        return True
    else:
        print("   ❌ POWER QUALITY: INSUFFICIENT")
        print("      LIDAR power supply inadequate for reliable operation")
        print("      Address power issues before deployment")
        return False


def power_troubleshooting_guide():
    """Provide troubleshooting guide for power issues"""
    print()
    print("🛠️  POWER TROUBLESHOOTING GUIDE")
    print("=" * 40)
    print()
    print("IF POWER QUALITY IS POOR:")
    print()
    print("1. 🔧 CHECK CONNECTIONS:")
    print("   ☐ Ensure all wire connections are secure")
    print("   ☐ Verify Red (5V) and Black (GND) wires properly connected")
    print("   ☐ Check for loose or damaged wires")
    print()
    print("2. 🔌 IMPROVE POWER DELIVERY:")
    print("   ☐ Use direct computer USB port (avoid hubs)")
    print("   ☐ Try shorter, higher-quality USB cable")
    print("   ☐ Connect computer to wall power (not battery)")
    print("   ☐ Try different USB port on computer")
    print()
    print("3. ⚡ ALTERNATIVE POWER OPTIONS:")
    print("   ☐ External 5V/1A power supply to Nano VIN pin")
    print("   ☐ Powered USB hub with external power adapter")
    print("   ☐ USB power bank with sufficient current output")
    print()
    print("4. 🔍 MONITOR RESULTS:")
    print("   ☐ LIDAR motor should spin smoothly")
    print("   ☐ LED should stay steadily lit")
    print("   ☐ Data flow should be consistent")


if __name__ == "__main__":
    print("🔍 STARTING LIDAR POWER QUALITY VERIFICATION")
    print()

    # Run comprehensive assessment
    power_ok = final_power_assessment()

    # Provide troubleshooting if needed
    if not power_ok:
        power_troubleshooting_guide()

    print()
    print("🏁 POWER VERIFICATION COMPLETE")
    print("=" * 50)

    if power_ok:
        print("✅ LIDAR power quality verified")
        print("   Safe to transfer to Raspberry Pi")
    else:
        print("⚠️  LIDAR power quality concerns detected")
        print("   Address issues before deployment")
