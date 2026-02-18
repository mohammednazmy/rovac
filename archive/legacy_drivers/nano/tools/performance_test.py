#!/usr/bin/env python3
import serial
import time


def benchmark_lidar_performance(port="/dev/cu.wchusbserial2140", duration=10):
    print(f"Benchmarking LIDAR performance on {port} for {duration} seconds...")

    try:
        ser = serial.Serial(port, 115200, timeout=1)
        ser.reset_input_buffer()

        start_time = time.time()
        total_bytes = 0
        measurements = []

        print("Measuring data rate...")
        while (time.time() - start_time) < duration:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                total_bytes += len(data)

            # Record measurement every second
            if int(time.time() - start_time) > len(measurements):
                measurements.append(total_bytes)

            time.sleep(0.01)

        ser.close()

        # Calculate statistics
        avg_rate = total_bytes / duration
        max_rate = (
            max(
                [
                    measurements[i] - (measurements[i - 1] if i > 0 else 0)
                    for i in range(1, len(measurements))
                ]
            )
            if len(measurements) > 1
            else avg_rate
        )

        print(f"\n📊 Performance Results:")
        print(f"   Total bytes: {total_bytes:,}")
        print(f"   Average rate: {avg_rate:,.0f} bytes/second")
        print(f"   Peak rate: {max_rate:,.0f} bytes/second")
        print(f"   Duration: {duration} seconds")

        # LIDAR quality assessment
        if avg_rate > 5000:
            print("   🎯 Quality: Excellent - Perfect for robotics applications")
        elif avg_rate > 3000:
            print("   🎯 Quality: Good - Suitable for most applications")
        else:
            print("   ⚠️  Quality: Fair - May need investigation")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    benchmark_lidar_performance()
