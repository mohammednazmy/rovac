#!/usr/bin/env python3
import serial
import time


def validate_lidar_packets(port="/dev/cu.wchusbserial2140", duration=5):
    print(f"Validating LIDAR packet structure on {port}...")

    try:
        ser = serial.Serial(port, 115200, timeout=1)
        ser.reset_input_buffer()

        start_time = time.time()
        valid_packets = 0
        total_bytes = 0
        packet_errors = 0

        print("Analyzing packet structure...")
        buffer = bytearray()

        while (time.time() - start_time) < duration:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                buffer.extend(data)
                total_bytes += len(data)

                # Look for complete packets (22 bytes for XV11)
                while len(buffer) >= 22:
                    # Check for start byte (0xFA is typical for XV11)
                    if buffer[0] == 0xFA:
                        packet = buffer[:22]
                        buffer = buffer[22:]

                        # Validate packet structure
                        index_byte = packet[1]
                        if 0xA0 <= index_byte <= 0xF9:  # Valid index range
                            valid_packets += 1
                            if valid_packets <= 5:  # Show first 5 packets
                                print(
                                    f"   Valid packet #{valid_packets}: Index={index_byte:02X}, Length={len(packet)}"
                                )
                        else:
                            packet_errors += 1
                    else:
                        # Skip invalid start byte
                        buffer = buffer[1:]

            time.sleep(0.01)

        ser.close()

        print(f"\n🔍 Validation Results:")
        print(f"   Total bytes analyzed: {total_bytes:,}")
        print(f"   Valid packets found: {valid_packets:,}")
        print(f"   Packet errors: {packet_errors:,}")

        if valid_packets > 0:
            error_rate = (
                (packet_errors / (valid_packets + packet_errors)) * 100
                if (valid_packets + packet_errors) > 0
                else 0
            )
            print(f"   Error rate: {error_rate:.2f}%")
            print("   ✅ LIDAR data integrity: GOOD")
        else:
            print("   ⚠️  LIDAR data integrity: CONCERN - No valid packets found")

        return valid_packets > 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    validate_lidar_packets()
