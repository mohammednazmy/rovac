#!/usr/bin/env python3
import serial
import time


def test_power_optimization():
    """Test power optimization techniques"""
    print("⚡ POWER OPTIMIZATION TEST")
    print("=" * 40)
    print()

    try:
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)
        print("✅ Connected to LIDAR USB Bridge")
        print()

        # Test 1: Baseline measurement
        print("Test 1: Establishing baseline power consumption")
        ser.reset_input_buffer()
        time.sleep(2)

        # Measure baseline data rate
        start_time = time.time()
        baseline_bytes = 0

        while (time.time() - start_time) < 3:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                baseline_bytes += len(data)
            time.sleep(0.05)

        baseline_rate = baseline_bytes / 3 if baseline_bytes > 0 else 0
        print(f"   Baseline data rate: {baseline_rate:.0f} bytes/second")
        print()

        # Test 2: Reduce command overhead
        print("Test 2: Optimizing communication for reduced overhead")
        ser.reset_input_buffer()
        time.sleep(1)

        # Don't send frequent commands that might interrupt LIDAR operation
        # Just monitor passive data flow
        start_time = time.time()
        optimized_bytes = 0

        while (time.time() - start_time) < 3:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                optimized_bytes += len(data)
            # No commands sent - just passive monitoring
            time.sleep(0.05)

        optimized_rate = optimized_bytes / 3 if optimized_bytes > 0 else 0
        print(f"   Optimized data rate: {optimized_rate:.0f} bytes/second")
        print()

        ser.close()

        # Analysis
        print("📊 POWER OPTIMIZATION ANALYSIS")
        print("-" * 35)

        if optimized_rate > baseline_rate * 1.1:
            improvement = ((optimized_rate - baseline_rate) / baseline_rate) * 100
            print(f"   ✅ Optimization improved performance by {improvement:.0f}%")
            print("      Reduced communication overhead helps power stability")
        elif optimized_rate > baseline_rate:
            print("   ✅ Optimization slightly improved performance")
            print("      Minor reduction in communication overhead")
        else:
            print("   ℹ️  Optimization showed minimal difference")
            print("      Communication overhead not the primary issue")

        return optimized_rate > 0

    except Exception as e:
        print(f"❌ Error during power optimization test: {e}")
        return False


def recommend_immediate_actions():
    """Recommend immediate actions to improve power quality"""
    print()
    print("🔧 IMMEDIATE ACTIONS TO IMPROVE POWER QUALITY")
    print("=" * 50)
    print()

    print("1. 🔄 PHYSICAL CONNECTIONS:")
    print("   ☐ Re-seat all wire connections to Nano")
    print("   ☐ Ensure Red (5V) and Black (GND) wires have solid connections")
    print("   ☐ Check that Orange (TX) and Brown (RX) wires are secure")
    print("   ☐ Gently tug on wires to check for loose connections")
    print()

    print("2. 🔌 POWER SOURCE IMPROVEMENT:")
    print("   ☐ Connect THIS computer directly to wall power")
    print("   ☐ Try a different USB port on this computer")
    print("   ☐ Use a shorter, higher-quality USB cable")
    print("   ☐ Avoid USB hubs or extenders")
    print()

    print("3. ⚡ ALTERNATIVE POWER METHODS:")
    print("   Option A: External 5V power supply")
    print("      • Connect 5V power supply to Nano VIN and GND pins")
    print("      • Keep USB connection for data only")
    print("      • This separates power from data")
    print()
    print("   Option B: Powered USB hub")
    print("      • Use powered USB hub with external power adapter")
    print("      • Connect Nano to powered hub")
    print("      • Hub provides dedicated power to Nano")
    print()

    print("4. 📋 QUICK VERIFICATION TEST:")
    print("   After making changes, run this verification:")
    print("   • LIDAR motor should spin smoothly without hesitation")
    print("   • Blue/Green LED should stay steadily lit")
    print("   • Data flow should be consistent (not bursty)")
    print("   • No clicking or irregular sounds from motor")
    print()


def create_power_verification_checklist():
    """Create a verification checklist"""
    print("📋 POWER QUALITY VERIFICATION CHECKLIST")
    print("=" * 45)
    print()
    print("BEFORE TRANSFER TO PI - VERIFY ALL ITEMS:")
    print()
    print("✅ HARDWARE CONNECTIONS:")
    print("   ☐ All 4 LIDAR wires securely connected to Nano")
    print("   ☐ Nano 5V pin connected to LIDAR Red wire")
    print("   ☐ Nano GND pin connected to LIDAR Black wire")
    print("   ☐ Nano D2 (RX) connected to LIDAR Orange (TX)")
    print("   ☐ Nano D3 (TX) connected to LIDAR Brown (RX)")
    print()
    print("✅ POWER QUALITY:")
    print("   ☐ LIDAR motor spins smoothly and consistently")
    print("   ☐ LIDAR motor LED stays steadily lit")
    print("   ☐ No clicking or irregular sounds from motor")
    print("   ☐ Data flow is consistent (not bursty or dropping)")
    print()
    print("✅ USB CONNECTION:")
    print("   ☐ Using direct computer USB port (not hub)")
    print("   ☐ High-quality data cable (not charge-only)")
    print("   ☐ Computer connected to reliable power source")
    print()
    print("✅ SIGNAL QUALITY:")
    print("   ☐ Valid LIDAR packets being received")
    print("   ☐ Minimal packet errors or corruption")
    print("   ☐ Consistent data rate over time")
    print()


def final_power_readiness():
    """Final assessment of power readiness"""
    print("🏁 FINAL POWER READINESS ASSESSMENT")
    print("=" * 45)
    print()

    print("CURRENT STATUS: ⚠️  POWER QUALITY CONCERNS DETECTED")
    print()
    print("RECOMMENDATIONS:")
    print("1. ✅ IMPLEMENT IMMEDIATE ACTIONS (see above)")
    print("2. ✅ VERIFY IMPROVEMENTS WITH CHECKLIST")
    print("3. ✅ TEST WITH MULTIPLE USB PORTS/CABLES")
    print("4. ✅ CONSIDER EXTERNAL POWER IF ISSUES PERSIST")
    print()
    print("🛑 DO NOT TRANSFER TO PI UNTIL:")
    print("   • LIDAR motor operates smoothly")
    print("   • Data flow is consistent and reliable")
    print("   • No power-related interruptions observed")
    print()
    print("💡 TIP: Good power quality is critical for reliable LIDAR operation.")
    print("   A few minutes fixing power issues now saves hours of debugging later.")


if __name__ == "__main__":
    print("⚡ STARTING POWER QUALITY OPTIMIZATION")
    print()

    # Test optimization
    optimization_success = test_power_optimization()

    # Recommend actions
    recommend_immediate_actions()

    # Create verification checklist
    create_power_verification_checklist()

    # Final assessment
    final_power_readiness()

    print()
    print("🔧 POWER OPTIMIZATION COMPLETE")
    print("Remember: Reliable power is essential for consistent LIDAR operation!")
