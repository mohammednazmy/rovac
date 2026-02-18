#!/usr/bin/env python3
"""
Test script to verify LIDAR data from the Nano USB bridge.
This script connects to the Nano board and verifies that valid LIDAR data is being received.
"""

import serial
import time
import sys


def validate_lidar_packet(data):
    """
    Validate a LIDAR packet to ensure we're getting real data.
    Basic validation for XV11 LIDAR packets.
    """
    if len(data) < 22:  # Minimum packet size
        return False

    # Check for start byte (0xFA is typical for XV11)
    if data[0] != 0xFA:
        return False

    # Check index byte range (should be between 0xA0 and 0xF9 for XV11)
    if data[1] < 0xA0 or data[1] > 0xF9:
        return False

    # Basic checksum validation could be added here
    return True


def test_lidar_connection(
    port="/dev/cu.wchusbserial2140", baudrate=115200, duration=10
):
    """
    Test the LIDAR connection and verify data integrity.
    """
    print(f"Testing LIDAR connection on {port} at {baudrate} baud...")
    print(f"Will run for {duration} seconds. Press Ctrl+C to stop early.\n")

    ser = None
    start_time = time.time()
    bytes_received = 0
    packets_received = 0
    valid_packets = 0

    try:
        # Open serial connection
        ser = serial.Serial(port, baudrate, timeout=1)
        print("Serial connection established.")

        # Flush input buffer
        ser.reset_input_buffer()

        start_time = time.time()
        bytes_received = 0
        packets_received = 0
        valid_packets = 0

        print("Listening for LIDAR data...\n")

        while (time.time() - start_time) < duration:
            # Read available data
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                bytes_received += len(data)

                # Look for complete packets (22 bytes for XV11)
                if len(data) >= 22:
                    # Try to find packet boundaries
                    for i in range(len(data) - 21):
                        if data[i] == 0xFA:  # Start byte
                            packet = data[i : i + 22]
                            if len(packet) == 22:
                                packets_received += 1
                                if validate_lidar_packet(packet):
                                    valid_packets += 1

                                    # Print first few valid packets for verification
                                    if valid_packets <= 5:
                                        print(
                                            f"Valid packet #{valid_packets}: {[hex(b) for b in packet[:10]]}..."
                                        )

                                # Skip ahead to avoid counting the same packet multiple times
                                break

                # Print status every 2 seconds
                if (
                    int(time.time() - start_time) % 2 == 0
                    and int(time.time() - start_time) > 0
                ):
                    print(
                        f"Status: {bytes_received} bytes, {packets_received} packets, {valid_packets} valid packets"
                    )

            time.sleep(0.01)  # Small delay to prevent excessive CPU usage

    except serial.SerialException as e:
        print(f"Serial error: {e}")
        return False
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False
    finally:
        if ser and ser.is_open:
            ser.close()
            print("Serial connection closed.")

    # Summary
    elapsed_time = time.time() - start_time
    print(f"\n--- Test Summary ---")
    print(f"Duration: {elapsed_time:.1f} seconds")
    print(f"Bytes received: {bytes_received}")
    print(f"Packets received: {packets_received}")
    print(f"Valid packets: {valid_packets}")
    print(f"Data rate: {bytes_received / elapsed_time:.1f} bytes/second")

    if valid_packets > 0:
        print("\n✅ SUCCESS: Valid LIDAR data detected!")
        print("The LIDAR is working correctly through the Nano USB bridge.")
        return True
    else:
        print("\n❌ WARNING: No valid LIDAR data detected.")
        print("Check connections and power supply.")
        return False


if __name__ == "__main__":
    # Default port - change if needed
    port = "/dev/cu.wchusbserial2140"

    # Allow port to be specified as command line argument
    if len(sys.argv) > 1:
        port = sys.argv[1]

    test_lidar_connection(port)
