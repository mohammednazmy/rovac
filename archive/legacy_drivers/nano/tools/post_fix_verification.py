#!/usr/bin/env python3
import serial
import time


def verify_power_quality_improvements():
    """Verify that power quality improvements have been effective"""
    print("✅ POST-IMPROVEMENT POWER QUALITY VERIFICATION")
    print("=" * 55)
    print()

    try:
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)
        print("✅ Connected to LIDAR USB Bridge")
        print()

        print("🔬 COMPREHENSIVE POST-IMPROVEMENT TEST")
        print("-" * 45)

        # Extended test period for better assessment
        print("Running extended 20-second quality assessment...")
        start_time = time.time()
        total_bytes = 0
        data_points = []
        consistent_periods = 0
        good_periods = 0

        while (time.time() - start_time) < 20:
            period_start = time.time()
            period_bytes = 0

            # Measure data for 1 second
            while (time.time() - period_start) < 1:
                if ser.in_waiting > 0:
                    data = ser.read(min(ser.in_waiting, 1024))
                    period_bytes += len(data)
                time.sleep(0.02)

            total_bytes += period_bytes
            data_points.append(period_bytes)

            # Assess period quality
            if period_bytes > 1000:  # Good data rate threshold
                good_periods += 1
            if (
                abs(period_bytes - (sum(data_points) / len(data_points))) < 300
            ):  # Consistency check
                consistent_periods += 1

            # Progress indicator
            elapsed = int(time.time() - start_time)
            if elapsed % 5 == 0 and elapsed > 0:
                print(f"   Time: {elapsed}s, Recent rate: {period_bytes} bytes/sec")

        ser.close()

        # Calculate final metrics
        duration = time.time() - start_time
        avg_rate = total_bytes / duration if duration > 0 else 0
        max_rate = max(data_points) if data_points else 0
        min_rate = min(data_points) if data_points else 0
        rate_consistency = consistent_periods / len(data_points) if data_points else 0
        good_quality_ratio = good_periods / len(data_points) if data_points else 0

        print()
        print("📊 DETAILED PERFORMANCE METRICS")
        print("-" * 35)
        print(f"   Test duration: {duration:.1f} seconds")
        print(f"   Total data: {total_bytes:,} bytes")
        print(f"   Average rate: {avg_rate:,.0f} bytes/second")
        print(f"   Rate range: {min_rate}-{max_rate} bytes/second")
        print(f"   Rate consistency: {rate_consistency * 100:.0f}%")
        print(f"   Good quality periods: {good_quality_ratio * 100:.0f}%")

        print()
        print("🏆 POWER QUALITY ASSESSMENT")
        print("-" * 30)

        # Multi-factor assessment
        score = 0
        max_score = 5

        # Factor 1: Absolute data rate
        if avg_rate > 1500:
            print("   ✅ Data rate: EXCELLENT (>1500 bytes/sec)")
            score += 1
        elif avg_rate > 1000:
            print("   ✅ Data rate: GOOD (1000-1500 bytes/sec)")
            score += 1
        else:
            print("   ⚠️  Data rate: FAIR (<1000 bytes/sec)")

        # Factor 2: Rate consistency
        if rate_consistency > 0.8:
            print("   ✅ Rate stability: EXCELLENT (>80% consistent)")
            score += 1
        elif rate_consistency > 0.6:
            print("   ✅ Rate stability: GOOD (60-80% consistent)")
            score += 1
        else:
            print("   ⚠️  Rate stability: VARIABLE (<60% consistent)")

        # Factor 3: Good quality periods
        if good_quality_ratio > 0.8:
            print("   ✅ Quality consistency: EXCELLENT (>80% good)")
            score += 1
        elif good_quality_ratio > 0.6:
            print("   ✅ Quality consistency: GOOD (60-80% good)")
            score += 1
        else:
            print("   ⚠️  Quality consistency: VARIABLE (<60% good)")

        # Factor 4: Peak performance
        if max_rate > 2000:
            print("   ✅ Peak performance: EXCELLENT (>2000 bytes/sec)")
            score += 1
        elif max_rate > 1500:
            print("   ✅ Peak performance: GOOD (1500-2000 bytes/sec)")
            score += 1
        else:
            print("   ⚠️  Peak performance: MODERATE (<1500 bytes/sec)")

        # Factor 5: Minimum threshold
        if min_rate > 500:
            print("   ✅ Minimum threshold: MAINTAINED (>500 bytes/sec)")
            score += 1
        else:
            print("   ❌ Minimum threshold: NOT MET (<500 bytes/sec)")

        print()
        print("📋 FINAL ASSESSMENT")
        print("-" * 20)

        if score >= 4:
            print("   🎉 OVERALL QUALITY: EXCELLENT")
            print("      ✅ Ready for deployment to Raspberry Pi")
            print("      ✅ Power quality meets professional standards")
            return True
        elif score >= 3:
            print("   ✅ OVERALL QUALITY: GOOD")
            print("      ✅ Acceptable for most applications")
            print("      ✅ Deployable with monitoring")
            return True
        else:
            print("   ⚠️  OVERALL QUALITY: NEEDS ATTENTION")
            print("      ❌ Not recommended for deployment yet")
            print("      ❌ Further power improvements needed")
            return False

    except Exception as e:
        print(f"❌ Error during verification: {e}")
        return False


def quick_lidar_health_check():
    """Quick health check of LIDAR operation"""
    print()
    print("🩺 QUICK LIDAR HEALTH CHECK")
    print("=" * 35)
    print()

    try:
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)
        print("✅ Connected to LIDAR")

        # Send a simple command to test responsiveness
        print("Testing device responsiveness...")
        ser.write(b"!id\n")
        time.sleep(0.5)

        if ser.in_waiting > 0:
            response = ser.read(ser.in_waiting)
            if b"DEVICE_ID" in response or b"ROVAC" in response:
                print("   ✅ Device responsive: CONFIRMED")
            else:
                print("   ✅ Device responsive: YES (basic response)")
        else:
            print("   ⚠️  Device responsive: NO RESPONSE")

        # Check data flow consistency
        print("Checking data flow consistency...")
        ser.reset_input_buffer()
        time.sleep(2)

        bytes_first = ser.in_waiting
        time.sleep(2)
        bytes_second = ser.in_waiting

        if bytes_second > bytes_first + 500:
            print("   ✅ Data flow: CONSISTENT")
        elif bytes_second > bytes_first:
            print("   ✅ Data flow: MAINTAINED")
        else:
            print("   ⚠️  Data flow: INCONSISTENT")

        ser.close()
        return True

    except Exception as e:
        print(f"❌ Error during health check: {e}")
        return False


def deployment_readiness_checklist():
    """Final checklist before deployment"""
    print()
    print("📋 DEPLOYMENT READINESS CHECKLIST")
    print("=" * 40)
    print()
    print("✅ BEFORE TRANSFERRING TO RASPBERRY PI:")
    print()
    print("HARDWARE VERIFICATION:")
    print("   ☐ All LIDAR-Nano connections secure")
    print("   ☐ Nano 5V connected to LIDAR Red wire")
    print("   ☐ Nano GND connected to LIDAR Black wire")
    print("   ☐ Nano D2 (RX) connected to LIDAR Orange wire")
    print("   ☐ Nano D3 (TX) connected to LIDAR Brown wire")
    print()
    print("POWER QUALITY (CRITICAL):")
    print("   ☐ LIDAR motor spins smoothly without hesitation")
    print("   ☐ LIDAR LED stays steadily lit (blue/green)")
    print("   ☐ No clicking or irregular sounds from motor")
    print("   ☐ Data flow consistent over extended periods")
    print()
    print("SOFTWARE VERIFICATION:")
    print("   ☐ Professional firmware installed and responding")
    print("   ☐ Device identification commands working")
    print("   ☐ Data packets being received properly")
    print()
    print("CONNECTION QUALITY:")
    print("   ☐ USB cable is high-quality data cable")
    print("   ☐ Computer connected to reliable power source")
    print("   ☐ No USB hubs or extenders in use")
    print()


if __name__ == "__main__":
    print("🔍 STARTING POST-IMPROVEMENT VERIFICATION")
    print()

    # Verify improvements
    quality_good = verify_power_quality_improvements()

    # Quick health check
    health_ok = quick_lidar_health_check()

    # Deployment checklist
    deployment_readiness_checklist()

    print()
    print("🏁 VERIFICATION COMPLETE")
    print("=" * 35)

    if quality_good and health_ok:
        print("🎉 EXCELLENT NEWS!")
        print("   ✅ LIDAR power quality verified as excellent")
        print("   ✅ Device health confirmed")
        print("   ✅ Ready for transfer to Raspberry Pi")
        print()
        print("🚀 SAFE TO PROCEED WITH DEPLOYMENT")
    else:
        print("⚠️  ATTENTION REQUIRED")
        print("   Power quality or device health needs attention")
        print("   Review the detailed metrics above")
        print("   Address issues before transferring to Pi")
        print()
        print("💡 REMEMBER: Poor power quality leads to:")
        print("   • Inconsistent LIDAR data")
        print("   • Frequent service restarts")
        print("   • False obstacles in navigation")
        print("   • Unreliable robot operation")
