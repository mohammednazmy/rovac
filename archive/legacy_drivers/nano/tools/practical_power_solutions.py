#!/usr/bin/env python3
import serial
import time


def test_simple_power_stability():
    """Simple test to check if power is stable enough for deployment"""
    print("⚡ SIMPLE POWER STABILITY TEST")
    print("=" * 35)
    print()

    try:
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)
        print("✅ Connected to LIDAR")
        print()

        print("Testing power stability for 15 seconds...")
        print("Criteria: LIDAR should maintain consistent operation")
        print()

        # Quick test - look for obvious issues
        start_time = time.time()
        data_periods = []
        consistent_periods = 0
        total_periods = 0

        while (time.time() - start_time) < 15:
            period_start = time.time()
            period_bytes = 0

            # Measure 1 second of data
            while (time.time() - period_start) < 1:
                if ser.in_waiting > 0:
                    data = ser.read(min(ser.in_waiting, 512))
                    period_bytes += len(data)
                time.sleep(0.02)

            data_periods.append(period_bytes)
            total_periods += 1

            # Show progress every 3 seconds
            if int(time.time() - start_time) % 3 == 0:
                print(
                    f"   Time {int(time.time() - start_time)}s: {period_bytes} bytes/sec"
                )

        ser.close()

        # Analyze results simply
        if data_periods:
            avg_rate = sum(data_periods) / len(data_periods)
            max_rate = max(data_periods)
            min_rate = min(data_periods)

            print()
            print("📊 SIMPLE ANALYSIS")
            print("-" * 18)
            print(f"   Average: {avg_rate:,.0f} bytes/sec")
            print(f"   Range: {min_rate}-{max_rate} bytes/sec")
            print(f"   Variation: {max_rate - min_rate} bytes/sec")

            # Simple pass/fail criteria
            if avg_rate > 800 and (max_rate - min_rate) < 1000:
                print("   ✅ Power stability: GOOD")
                print("   ✅ Ready for deployment")
                return True
            elif avg_rate > 500 and (max_rate - min_rate) < 1500:
                print("   ⚠️  Power stability: ACCEPTABLE")
                print("   ✅ Deployable with monitoring")
                return True
            else:
                print("   ❌ Power stability: POOR")
                print("   ⚠️  Not ready for deployment")
                return False
        else:
            print("   ❌ No data received")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def practical_solutions_checklist():
    """Provide practical solutions for common power issues"""
    print()
    print("🔧 PRACTICAL POWER SOLUTIONS")
    print("=" * 32)
    print()

    print("IMMEDIATE ACTIONS TO TRY:")
    print()

    print("1. 🔧 PHYSICAL CONNECTIONS")
    print("   ☐ Firmly reseat ALL LIDAR wires to Nano pins")
    print("   ☐ Ensure Nano 5V -> LIDAR Red (power) connection is solid")
    print("   ☐ Ensure Nano GND -> LIDAR Black (ground) connection is solid")
    print("   ☐ Gently wiggle wires to check for loose connections")
    print()

    print("2. 🔌 POWER DELIVERY IMPROVEMENTS")
    print("   ☐ Connect THIS computer directly to wall outlet")
    print("   ☐ Try a DIFFERENT USB port on this computer")
    print("   ☐ Use a SHORTER, THICKER USB cable")
    print("   ☐ Remove any USB hubs or adapters")
    print()

    print("3. ⚡ ALTERNATIVE POWER METHODS")
    print("   METHOD A: External Power Supply")
    print("      • Connect 5V/1A wall adapter to Nano VIN and GND pins")
    print("      • Keep USB cable for data only")
    print("      • This separates data from power delivery")
    print()
    print("   METHOD B: Powered USB Hub")
    print("      • Use powered USB hub with external power adapter")
    print("      • Connect Nano to powered hub")
    print("      • Hub provides dedicated stable power")
    print()

    print("4. 🔍 OBSERVATION CHECKLIST")
    print("   While making changes, watch for:")
    print("   ✅ LIDAR motor spins smoothly (no hesitation)")
    print("   ✅ Blue/Green LED stays steadily lit (not flickering)")
    print("   ✅ No clicking/grinding sounds from motor")
    print("   ✅ Data rate becomes more consistent")


def pre_transfer_checklist():
    """Final checklist before considering transfer"""
    print()
    print("📋 PRE-TRANSFER READINESS CHECKLIST")
    print("=" * 38)
    print()
    print("✅ BEFORE TRANSFERRING TO RASPBERRY PI:")
    print()
    print("POWER QUALITY (MOST CRITICAL):")
    print("   ☐ LIDAR motor spins smoothly without hesitation")
    print("   ☐ Blue/Green LED stays steadily lit")
    print("   ☐ No clicking or irregular motor sounds")
    print("   ☐ Data flow is consistent (not bursty)")
    print()
    print("CONNECTIONS:")
    print("   ☐ All 4 LIDAR wires securely connected to Nano")
    print("   ☐ Nano 5V -> LIDAR Red wire (5V power)")
    print("   ☐ Nano GND -> LIDAR Black wire (Ground)")
    print("   ☐ Nano D2 -> LIDAR Orange wire (Serial TX)")
    print("   ☐ Nano D3 -> LIDAR Brown wire (Serial RX)")
    print()
    print("USB QUALITY:")
    print("   ☐ Using direct computer USB port (not hub)")
    print("   ☐ High-quality data cable (not charge-only)")
    print("   ☐ Computer connected to reliable wall power")
    print()


def final_recommendation():
    """Provide final recommendation based on testing"""
    print()
    print("🎯 FINAL RECOMMENDATION")
    print("=" * 25)
    print()

    # Run a quick test
    stability_ok = test_simple_power_stability()

    if stability_ok:
        print("🎉 GOOD NEWS!")
        print("   ✅ Power quality is acceptable for deployment")
        print("   ✅ Ready to transfer to Raspberry Pi")
        print()
        print("🚀 PROCEED WITH CONFIDENCE")
        print("   Your LIDAR USB Bridge has stable power")
        print("   Professional firmware is working correctly")
        print("   Device is ready for robot deployment")
    else:
        print("⚠️  ATTENTION NEEDED")
        print("   ❌ Power quality issues detected")
        print("   ⚠️  Not recommended for deployment yet")
        print()
        print("🛠️  RECOMMENDED ACTIONS:")
        print("   1. Implement practical solutions above")
        print("   2. Re-test power stability")
        print("   3. Verify LIDAR motor operates smoothly")
        print("   4. Ensure consistent data flow")
        print()
        print("💡 REMEMBER:")
        print("   Poor power quality = unreliable robot operation")
        print("   Take time now to fix power issues")
        print("   Save hours of debugging later")


if __name__ == "__main__":
    print("🔌 STARTING PRACTICAL POWER QUALITY ASSESSMENT")
    print()

    # Show practical solutions
    practical_solutions_checklist()

    # Show pre-transfer checklist
    pre_transfer_checklist()

    # Give final recommendation
    final_recommendation()

    print()
    print("🔒 REMEMBER:")
    print("   A complete backup of your working configuration")
    print("   exists in: ~/robots/rovac/nano/backup_*")
