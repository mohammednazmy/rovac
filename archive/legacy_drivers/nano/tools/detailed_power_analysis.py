#!/usr/bin/env python3
import serial
import time


def detailed_power_analysis():
    print("🔬 DETAILED POWER AND SIGNAL QUALITY ANALYSIS")
    print("=" * 60)
    print()

    try:
        # Connect with detailed analysis
        ser = serial.Serial("/dev/cu.wchusbserial2140", 115200, timeout=1)
        print("✅ Connected to LIDAR USB Bridge")
        print()

        # Physical inspection checklist
        print("📋 PHYSICAL SETUP INSPECTION")
        print("-" * 40)
        print("Please verify the following:")
        print()
        print("1. 🔌 POWER CONNECTIONS:")
        print("   ☐ Nano 5V pin connected to LIDAR Red wire")
        print("   ☐ Nano GND pin connected to LIDAR Black wire")
        print("   ☐ Connections are secure (no loose wires)")
        print("   ☐ No solder joints are cracked or loose")
        print()
        print("2. 📡 SERIAL CONNECTIONS:")
        print("   ☐ Nano D2 (RX) connected to LIDAR Orange (TX)")
        print("   ☐ Nano D3 (TX) connected to LIDAR Brown (RX)")
        print("   ☐ Wires are not crossed or reversed")
        print()
        print("3. ⚡ POWER SOURCE:")
        print("   ☐ USB cable is high-quality data cable (not charge-only)")
        print("   ☐ Computer USB port provides adequate power (>500mA)")
        print("   ☐ No USB hubs or extenders in the chain")
        print()

        input("Press Enter after verifying physical connections...")
        print()

        # Flush buffers
        ser.reset_input_buffer()
        time.sleep(2)

        print("📊 SIGNAL QUALITY ANALYSIS")
        print("-" * 40)

        # Test signal integrity with different approaches
        print("Testing signal stability over time...")

        # Test 1: Short burst analysis
        print("Test 1: Signal burst analysis (5 seconds)")
        start_time = time.time()
        burst_data = []

        while (time.time() - start_time) < 5:
            if ser.in_waiting > 0:
                data_chunk = ser.read(min(ser.in_waiting, 100))
                burst_data.append((time.time(), len(data_chunk), data_chunk))
            time.sleep(0.05)

        print(f"   Collected {len(burst_data)} data bursts")

        # Analyze burst consistency
        if burst_data:
            burst_sizes = [size for _, size, _ in burst_data]
            avg_size = sum(burst_sizes) / len(burst_sizes) if burst_sizes else 0
            max_size = max(burst_sizes) if burst_sizes else 0
            min_size = min(burst_sizes) if burst_sizes else 0

            print(f"   Average burst size: {avg_size:.1f} bytes")
            print(f"   Size range: {min_size}-{max_size} bytes")

            if max_size - min_size < 50:
                print("   ✅ Burst consistency: GOOD")
            else:
                print("   ⚠️  Burst consistency: VARIABLE")

        print()

        # Test 2: Long-term stability
        print("Test 2: Long-term signal stability (10 seconds)")
        ser.reset_input_buffer()
        time.sleep(1)

        start_time = time.time()
        byte_counts = []

        while (time.time() - start_time) < 10:
            time.sleep(1)
            bytes_per_second = ser.in_waiting
            byte_counts.append(bytes_per_second)
            print(
                f"   Second {int(time.time() - start_time)}: {bytes_per_second} bytes"
            )

        print()

        # Analyze stability
        if byte_counts:
            avg_rate = sum(byte_counts) / len(byte_counts)
            max_rate = max(byte_counts)
            min_rate = min(byte_counts)
            rate_variation = max_rate - min_rate

            print(f"   Average rate: {avg_rate:.0f} bytes/second")
            print(f"   Rate variation: {rate_variation} bytes/second")

            if rate_variation < 100:
                print("   ✅ Rate stability: EXCELLENT")
            elif rate_variation < 300:
                print("   ✅ Rate stability: GOOD")
            else:
                print("   ⚠️  Rate stability: VARIABLE")

        print()

        # Test 3: Packet structure analysis
        print("Test 3: Packet structure integrity")
        ser.reset_input_buffer()
        time.sleep(2)

        # Collect packets for analysis
        packets = []
        raw_data = bytearray()

        # Read for 5 seconds
        collect_start = time.time()
        while (time.time() - collect_start) < 5:
            if ser.in_waiting > 0:
                chunk = ser.read(min(ser.in_waiting, 1024))
                raw_data.extend(chunk)
            time.sleep(0.01)

        # Extract packets (XV11 packets are 22 bytes, start with 0xFA)
        i = 0
        while i < len(raw_data) - 21:
            if raw_data[i] == 0xFA:
                if i + 22 <= len(raw_data):
                    packet = raw_data[i : i + 22]
                    packets.append(packet)
                    i += 22
                else:
                    i += 1
            else:
                i += 1

        print(f"   Found {len(packets)} complete packets")

        # Analyze packet quality
        valid_packets = 0
        checksum_pass = 0

        for packet in packets:
            # Check index byte (should be 0xA0-0xF9)
            index_byte = packet[1]
            if 0xA0 <= index_byte <= 0xF9:
                valid_packets += 1

            # Simple checksum validation (sum of bytes should be consistent)
            # This is a rough check - actual XV11 checksum is more complex
            checksum_field = packet[20] | (packet[21] << 8)
            data_sum = sum(packet[2:20]) & 0xFFFF

            # Rough checksum check
            if abs(checksum_field - data_sum) < 1000:  # Allow some tolerance
                checksum_pass += 1

        print(f"   Valid packet headers: {valid_packets}/{len(packets)}")
        if packets:
            validity_percent = (valid_packets / len(packets)) * 100
            print(f"   Packet header validity: {validity_percent:.1f}%")

            if validity_percent > 90:
                print("   ✅ Packet structure integrity: EXCELLENT")
            elif validity_percent > 75:
                print("   ✅ Packet structure integrity: GOOD")
            else:
                print("   ⚠️  Packet structure integrity: FAIR")

        print()

        # Test 4: Noise analysis
        print("Test 4: Signal noise analysis")
        ser.reset_input_buffer()
        time.sleep(1)

        # Look for unusual patterns in the data stream
        noise_samples = []
        start_collect = time.time()

        while (time.time() - start_collect) < 3:
            if ser.in_waiting > 0:
                data = ser.read(min(ser.in_waiting, 1024))
                # Look for null bytes, repeated patterns, or unusual values
                null_bytes = data.count(0x00)
                ff_bytes = data.count(0xFF)
                noise_level = (null_bytes + ff_bytes) / len(data) if data else 0
                noise_samples.append(noise_level)
            time.sleep(0.05)

        if noise_samples:
            avg_noise = sum(noise_samples) / len(noise_samples)
            print(f"   Average noise level: {avg_noise * 100:.1f}%")

            if avg_noise < 0.05:
                print("   ✅ Signal noise: LOW")
            elif avg_noise < 0.15:
                print("   ⚠️  Signal noise: MODERATE")
            else:
                print("   ❌ Signal noise: HIGH")

        ser.close()

        print()
        print("📋 POWER QUALITY RECOMMENDATIONS")
        print("-" * 40)

        # Based on all tests, provide specific recommendations
        overall_score = 0
        if avg_rate > 1000:
            overall_score += 1
        if rate_variation < 300:
            overall_score += 1
        if len(packets) > 10:
            overall_score += 1
        if valid_packets / max(len(packets), 1) > 0.7:
            overall_score += 1
        if avg_noise < 0.15 if "avg_noise" in locals() else True:
            overall_score += 1

        if overall_score >= 4:
            print("   ✅ Overall signal quality: EXCELLENT")
            print("   ✅ Ready for deployment")
        elif overall_score >= 3:
            print("   ✅ Overall signal quality: GOOD")
            print("   ✅ Acceptable for most applications")
        else:
            print("   ⚠️  Overall signal quality: NEEDS IMPROVEMENT")
            print("   🔧 Recommendations:")
            print("      1. Check all physical connections")
            print("      2. Try a different USB cable")
            print("      3. Verify computer USB port power delivery")
            print("      4. Consider external 5V power supply")
            print("      5. Check for electromagnetic interference")

        return overall_score >= 3

    except Exception as e:
        print(f"❌ Error during detailed analysis: {e}")
        return False


def power_supply_verification():
    """Verify actual power supply characteristics"""
    print()
    print("🔌 POWER SUPPLY VERIFICATION")
    print("-" * 40)

    print("To verify adequate power supply:")
    print()
    print("1. 📋 OBSERVE LIDAR BEHAVIOR:")
    print("   ✅ LIDAR motor spins smoothly and consistently")
    print("   ✅ LIDAR motor LED stays steadily lit (blue/green)")
    print("   ✅ No clicking or stuttering sounds from motor")
    print("   ✅ LIDAR starts spinning immediately when powered")
    print()
    print("2. 🔋 POWER SOURCE CHECK:")
    print("   ✅ Use direct computer USB port (avoid hubs)")
    print("   ✅ USB cable is high-quality data cable")
    print("   ✅ Computer is plugged into wall power (not battery)")
    print()
    print("3. ⚡ VOLTAGE MONITORING (if available):")
    print("   ✅ Measure voltage at LIDAR connector: 4.75-5.25V")
    print("   ✅ Measure current draw: 400-500mA typical")
    print("   ✅ Voltage should stay steady under load")
    print()

    input("Press Enter after visually inspecting LIDAR operation...")

    print()
    print("💡 TROUBLESHOOTING TIPS:")
    print("If power issues persist:")
    print("   1. Try different USB port on computer")
    print("   2. Use shorter USB cable")
    print("   3. Connect computer to wall power")
    print("   4. Try powered USB hub (if direct ports don't work)")
    print("   5. Consider external 5V/1A power supply to Nano VIN pin")


if __name__ == "__main__":
    print("🔍 STARTING DETAILED POWER AND SIGNAL ANALYSIS")
    print()

    # Run detailed analysis
    quality_ok = detailed_power_analysis()

    # Run power supply verification
    power_supply_verification()

    print()
    print("🏁 ANALYSIS COMPLETE")
    print("=" * 60)

    if quality_ok:
        print("✅ LIDAR signal quality is acceptable for deployment")
        print("   Proceed with transferring to Raspberry Pi")
    else:
        print("⚠️  LIDAR signal quality needs attention")
        print("   Review recommendations and address issues before deployment")
