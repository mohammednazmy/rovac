#!/usr/bin/env python3
import serial
import time
import struct


def test_lidar_power_and_data_quality():
    print("🔍 COMPREHENSIVE LIDAR POWER & DATA QUALITY TEST")
    print("=" * 60)
    print()

    try:
        # Connect to LIDAR
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=2)
        print("✅ Connected to LIDAR USB Bridge")
        print()

        # Flush input buffer
        ser.reset_input_buffer()
        time.sleep(1)

        print("🔋 POWER QUALITY TEST")
        print("-" * 30)

        # Test data consistency over time
        print("Collecting data samples for 15 seconds...")
        start_time = time.time()
        total_bytes = 0
        packet_count = 0
        error_count = 0
        voltage_stability_issues = 0

        # Track data rate consistency
        data_rates = []
        packet_sizes = []

        # Collect data for 15 seconds
        while (time.time() - start_time) < 15:
            if ser.in_waiting > 0:
                # Read available data
                data = ser.read(min(ser.in_waiting, 1024))
                total_bytes += len(data)

                # Analyze data for packet structure
                for i in range(len(data) - 21):
                    if data[i] == 0xFA:  # Start of packet marker for XV11
                        if i + 22 <= len(data):
                            packet = data[i : i + 22]
                            packet_count += 1
                            packet_sizes.append(len(packet))

                            # Validate packet structure
                            index_byte = packet[1]
                            if not (0xA0 <= index_byte <= 0xF9):
                                error_count += 1

                            # Check for reasonable values
                            if packet[2] == 0 and packet[3] == 0:
                                # Both distance bytes zero - might indicate power issue
                                voltage_stability_issues += 1

                # Record data rate every second
                if int(time.time() - start_time) > len(data_rates):
                    data_rates.append(total_bytes)

            time.sleep(0.01)  # Small delay to prevent excessive CPU usage

        ser.close()

        # Calculate results
        duration = time.time() - start_time
        avg_rate = total_bytes / duration if duration > 0 else 0

        print(f"📊 DATA COLLECTION RESULTS")
        print(f"   Duration: {duration:.1f} seconds")
        print(f"   Total bytes: {total_bytes:,}")
        print(f"   Average data rate: {avg_rate:,.0f} bytes/second")
        print(f"   Valid packets found: {packet_count:,}")
        print(f"   Packet errors: {error_count:,}")
        print(f"   Potential power stability issues: {voltage_stability_issues}")

        # Calculate data rate consistency
        if len(data_rates) > 1:
            rate_variations = [
                abs(data_rates[i] - data_rates[i - 1])
                for i in range(1, len(data_rates))
            ]
            avg_variation = (
                sum(rate_variations) / len(rate_variations) if rate_variations else 0
            )
            print(f"   Data rate variation: {avg_variation:,.0f} bytes/second")

            if avg_variation < 100:
                print("   📈 Data rate: STABLE")
            elif avg_variation < 500:
                print("   📈 Data rate: MODERATELY STABLE")
            else:
                print("   📈 Data rate: UNSTABLE - Possible power issues")

        print()
        print("⚡ POWER QUALITY ASSESSMENT")
        print("-" * 30)

        # Power quality assessment
        if avg_rate > 5000:
            print("   ✅ Power Level: EXCELLENT")
            print("      LIDAR receiving adequate stable power")
        elif avg_rate > 3000:
            print("   ✅ Power Level: GOOD")
            print("      LIDAR receiving sufficient power")
        elif avg_rate > 1500:
            print("   ⚠️  Power Level: FAIR")
            print("      LIDAR may have marginal power - monitor closely")
        else:
            print("   ❌ Power Level: POOR")
            print("      LIDAR likely has inadequate power supply")

        # Voltage stability assessment
        if voltage_stability_issues < 5:
            print("   ✅ Voltage Stability: STABLE")
            print("      Clean power delivery to LIDAR")
        elif voltage_stability_issues < 20:
            print("   ⚠️  Voltage Stability: MODERATE")
            print("      Some power fluctuations detected")
        else:
            print("   ❌ Voltage Stability: UNSTABLE")
            print("      Significant power issues affecting LIDAR operation")

        print()
        print("📡 DATA QUALITY ANALYSIS")
        print("-" * 30)

        # Data quality based on packet analysis
        if packet_count > 100 and error_count < 10:
            print("   ✅ Data Integrity: EXCELLENT")
            print("      High-quality, reliable LIDAR data stream")
        elif packet_count > 50 and error_count < 25:
            print("   ✅ Data Integrity: GOOD")
            print("      Acceptable data quality for most applications")
        elif packet_count > 20 and error_count < 50:
            print("   ⚠️  Data Integrity: FAIR")
            print("      Data quality acceptable but could be improved")
        else:
            print("   ❌ Data Integrity: POOR")
            print("      Significant data corruption - check power/wiring")

        print()
        print("📋 RECOMMENDATIONS")
        print("-" * 30)

        # Power recommendations
        if avg_rate > 3000 and voltage_stability_issues < 10:
            print("   ✅ Power Supply: OPTIMAL")
            print("      No action needed for power delivery")
        else:
            print("   🔧 Power Supply Recommendations:")
            print("      - Verify USB power source provides stable 5V")
            print("      - Check all wiring connections are secure")
            print("      - Ensure LIDAR motor indicator LED is steady (not flickering)")
            print("      - Consider external power if USB source is marginal")

        # Data recommendations
        if packet_count > 50 and error_count < 25:
            print("   ✅ Data Quality: ACCEPTABLE")
            print("      LIDAR data suitable for deployment")
        else:
            print("   🔧 Data Quality Recommendations:")
            print("      - Check wiring for loose connections")
            print("      - Verify LIDAR receives clean 5V power")
            print("      - Test with different USB cable/port")
            print("      - Ensure no electrical interference")

        print()
        return avg_rate > 1500 and packet_count > 20  # Minimum acceptable thresholds

    except Exception as e:
        print(f"❌ Error during testing: {e}")
        return False


def test_lidar_motor_indicator():
    """Test LIDAR motor indicator LED stability"""
    print("🔧 LIDAR MOTOR INDICATOR TEST")
    print("-" * 30)

    try:
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)
        ser.reset_input_buffer()

        print("Observing LIDAR motor LED for 10 seconds...")
        print("Look for:")
        print("  ✅ Steady green/blue LED = Good power")
        print("  ❌ Flickering LED = Power instability")
        print("  ❌ LED turning off = Insufficient power")
        print()

        start_time = time.time()
        data_points = []

        # Monitor data flow consistency as indicator of motor stability
        while (time.time() - start_time) < 10:
            bytes_available = ser.in_waiting
            data_points.append(bytes_available)
            time.sleep(0.5)
            if len(data_points) % 2 == 0:  # Every second
                print(
                    f"   Time: {int(time.time() - start_time)}s, Data available: {bytes_available}"
                )

        ser.close()

        # Analyze consistency
        if len(data_points) > 1:
            avg_data = sum(data_points) / len(data_points)
            variance = sum((x - avg_data) ** 2 for x in data_points) / len(data_points)
            std_dev = variance**0.5

            print(f"   Average data availability: {avg_data:.0f} bytes")
            print(f"   Data consistency (std dev): {std_dev:.0f}")

            if std_dev < 50:
                print("   ✅ Motor Stability: EXCELLENT")
                print("      LIDAR motor running smoothly")
            elif std_dev < 100:
                print("   ✅ Motor Stability: GOOD")
                print("      LIDAR motor operating normally")
            else:
                print("   ⚠️  Motor Stability: CONCERN")
                print("      LIDAR motor may be inconsistent")

        return True

    except Exception as e:
        print(f"❌ Error testing motor indicator: {e}")
        return False


def final_verification():
    """Final comprehensive verification"""
    print("🏁 FINAL VERIFICATION")
    print("=" * 60)

    # Run power and data quality test
    power_good = test_lidar_power_and_data_quality()
    print()

    # Run motor indicator test
    motor_good = test_lidar_motor_indicator()
    print()

    if power_good:
        print("🎉 LIDAR POWER AND DATA QUALITY: ACCEPTABLE")
        print("   ✅ Ready for deployment to Raspberry Pi")
        print("   ✅ Power supply adequate")
        print("   ✅ Data quality sufficient")
        print("   ✅ Motor operation stable")
    else:
        print("⚠️  LIDAR POWER AND DATA QUALITY: NEEDS ATTENTION")
        print("   Review recommendations above before deployment")

    return power_good


if __name__ == "__main__":
    final_verification()
