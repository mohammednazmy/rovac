#!/usr/bin/env python3
import serial
import time
import matplotlib.pyplot as plt
import numpy as np


def debug_power_fluctuations():
    """Debug and identify power fluctuation issues"""
    print("🔍 DEBUGGING POWER FLUCTUATIONS")
    print("=" * 40)
    print()

    try:
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)
        print("✅ Connected to LIDAR")
        print()

        print("Monitoring power stability for 30 seconds...")
        print("Look for:")
        print("- Large spikes in data rate (indicate power surges)")
        print("- Drops to near-zero data (indicate power loss)")
        print("- Consistent rate = stable power")
        print()

        start_time = time.time()
        data_rates = []
        timestamps = []

        # Monitor for 30 seconds with fine granularity
        while (time.time() - start_time) < 30:
            period_start = time.time()
            bytes_count = 0

            # Measure exactly 0.5 seconds of data
            while (time.time() - period_start) < 0.5:
                if ser.in_waiting > 0:
                    data = ser.read(min(ser.in_waiting, 512))
                    bytes_count += len(data)
                time.sleep(0.01)  # Small delay to prevent CPU overload

            # Record the rate (bytes per 0.5 second = 2x bytes/second rate)
            current_rate = bytes_count * 2  # Convert to bytes/second
            current_time = time.time() - start_time

            data_rates.append(current_rate)
            timestamps.append(current_time)

            # Print every 5 seconds
            if int(current_time) % 5 == 0 and int(current_time) > 0:
                recent_avg = (
                    sum(data_rates[-10:]) / len(data_rates[-10:])
                    if len(data_rates) >= 10
                    else 0
                )
                print(
                    f"   Time {int(current_time)}s: {current_rate} bytes/sec (recent avg: {recent_avg:.0f})"
                )

        ser.close()

        # Analyze the results
        if data_rates:
            avg_rate = sum(data_rates) / len(data_rates)
            max_rate = max(data_rates)
            min_rate = min(data_rates)
            std_dev = (
                sum((x - avg_rate) ** 2 for x in data_rates) / len(data_rates)
            ) ** 0.5

            print()
            print("📊 POWER STABILITY ANALYSIS")
            print("-" * 30)
            print(f"   Average rate: {avg_rate:,.0f} bytes/second")
            print(f"   Peak rate: {max_rate:,.0f} bytes/second")
            print(f"   Minimum rate: {min_rate:,.0f} bytes/second")
            print(f"   Rate variation: {max_rate - min_rate:,.0f} bytes/second")
            print(f"   Standard deviation: {std_dev:,.0f} bytes/second")

            # Identify problematic fluctuations
            spike_threshold = avg_rate + (
                std_dev * 2
            )  # 2 standard deviations above average
            drop_threshold = avg_rate - (
                std_dev * 2
            )  # 2 standard deviations below average

            spikes = [i for i, rate in enumerate(data_rates) if rate > spike_threshold]
            drops = [
                i
                for i, rate in enumerate(data_rates)
                if rate < drop_threshold and rate > 100
            ]  # Ignore complete dropouts

            print()
            print("⚠️  POWER FLUCTUATION DETECTED")
            print("-" * 35)

            if spikes:
                print(f"   Power Spikes ({len(spikes)} events):")
                for idx in spikes[:5]:  # Show first 5 spikes
                    timestamp = timestamps[idx]
                    rate = data_rates[idx]
                    print(f"      Time {timestamp:.1f}s: {rate:,.0f} bytes/sec")
                if len(spikes) > 5:
                    print(f"      ... and {len(spikes) - 5} more")
            else:
                print("   Power Spikes: NONE DETECTED")

            if drops:
                print(f"   Power Drops ({len(drops)} events):")
                for idx in drops[:5]:  # Show first 5 drops
                    timestamp = timestamps[idx]
                    rate = data_rates[idx]
                    print(f"      Time {timestamp:.1f}s: {rate:,.0f} bytes/sec")
                if len(drops) > 5:
                    print(f"      ... and {len(drops) - 5} more")
            else:
                print("   Power Drops: NONE DETECTED")

            # Power quality assessment
            print()
            print("📋 POWER QUALITY ASSESSMENT")
            print("-" * 25)

            if len(spikes) + len(drops) == 0:
                print("   ✅ Power Quality: EXCELLENT")
                print("      No significant fluctuations detected")
                power_quality = "excellent"
            elif len(spikes) + len(drops) < 5:
                print("   ✅ Power Quality: GOOD")
                print("      Minor fluctuations within acceptable range")
                power_quality = "good"
            elif len(spikes) + len(drops) < 15:
                print("   ⚠️  Power Quality: FAIR")
                print("      Noticeable fluctuations - monitor closely")
                power_quality = "fair"
            else:
                print("   ❌ Power Quality: POOR")
                print("      Significant fluctuations detected")
                power_quality = "poor"

            # Root cause analysis
            print()
            print("🔍 ROOT CAUSE ANALYSIS")
            print("-" * 22)

            if max_rate > avg_rate * 3:
                print("   📈 Large Spike Detected")
                print("      Likely cause: Power surge or buffer flush")
                print("      Check: USB power delivery stability")
            elif min_rate < avg_rate * 0.3:
                print("   📉 Significant Drop Detected")
                print("      Likely cause: Power interruption or motor stall")
                print("      Check: LIDAR motor power stability")
            else:
                print("   📊 Data Rate Variations")
                print("      Normal variations in LIDAR data")
                print("      Power delivery appears stable")

            return power_quality != "poor"

    except Exception as e:
        print(f"❌ Error during debugging: {e}")
        return False


def power_troubleshooting_guide():
    """Provide specific troubleshooting for power issues"""
    print()
    print("🛠️  POWER TROUBLESHOOTING GUIDE")
    print("=" * 35)
    print()

    print("IMMEDIATE ACTIONS:")
    print("1. 🔧 CHECK PHYSICAL CONNECTIONS")
    print("   ☐ Re-seat all LIDAR-to-Nano connections")
    print("   ☐ Ensure Nano 5V pin connected to LIDAR Red wire")
    print("   ☐ Ensure Nano GND pin connected to LIDAR Black wire")
    print("   ☐ Verify no loose or intermittent connections")
    print()

    print("2. 🔌 IMPROVE POWER DELIVERY")
    print("   ☐ Connect THIS computer directly to wall power")
    print("   ☐ Try a different USB port on this computer")
    print("   ☐ Use the SHORTEST, THICKEST USB cable available")
    print("   ☐ Avoid USB hubs or extenders completely")
    print()

    print("3. ⚡ ALTERNATIVE POWER SOLUTIONS")
    print("   Option A: External 5V power supply")
    print("      • Connect 5V/1A power supply to Nano VIN and GND")
    print("      • Keep USB for data only (separates power from data)")
    print("      • This often resolves power fluctuation issues")
    print()
    print("   Option B: Powered USB hub with external adapter")
    print("      • Use powered USB hub with separate power supply")
    print("      • Connect Nano to powered hub")
    print("      • Hub provides dedicated stable power")
    print()

    print("4. 🔍 OBSERVATION CHECKLIST")
    print("   While making changes, observe for:")
    print("   ✅ LIDAR motor spins smoothly without hesitation")
    print("   ✅ Blue/Green LED stays steadily lit (not blinking)")
    print("   ✅ No clicking or irregular sounds from motor")
    print("   ✅ Data flow becomes consistent and stable")
    print()


def verification_plan():
    """Create a plan for verifying fixes"""
    print()
    print("📋 VERIFICATION PLAN")
    print("=" * 22)
    print()

    print("AFTER MAKING CHANGES:")
    print("1. Run this debug script again")
    print("2. Verify power fluctuations are reduced")
    print("3. Confirm data rate stabilizes")
    print("4. Check LIDAR motor operation is smooth")
    print()

    print("SUCCESS CRITERIA:")
    print("✅ Average data rate: 1,000+ bytes/second")
    print("✅ Rate variation: < 500 bytes/second")
    print("✅ No significant spikes or drops")
    print("✅ LIDAR motor operates smoothly")
    print("✅ LED stays steadily lit")


if __name__ == "__main__":
    print("⚡ STARTING POWER FLUCTUATION DEBUGGING")
    print()

    # Debug power issues
    stable_power = debug_power_fluctuations()

    # Provide troubleshooting guide
    power_troubleshooting_guide()

    # Create verification plan
    verification_plan()

    print()
    print("🏁 DEBUGGING COMPLETE")
    print("=" * 25)

    if stable_power:
        print("✅ Power quality is acceptable")
        print("   Continue with deployment preparation")
    else:
        print("⚠️  Power quality issues detected")
        print("   Implement troubleshooting steps above")
        print("   Re-run this script after making changes")
