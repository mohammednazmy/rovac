#!/usr/bin/env python3
"""
Quick test script for SensorServer WebSocket connection.
Run this after starting the SensorServer app on your phone.
"""

import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. Run: pip install websockets")
    sys.exit(1)


SENSORS = {
    'accelerometer': 'android.sensor.accelerometer',
    'gyroscope': 'android.sensor.gyroscope',
    'magnetometer': 'android.sensor.magnetic_field',
    'light': 'android.sensor.light',
    'proximity': 'android.sensor.proximity',
}


async def test_sensor(name: str, sensor_type: str, host: str, port: int):
    """Test connection to a single sensor"""
    url = f'ws://{host}:{port}/sensor/connect?type={sensor_type}'
    try:
        async with websockets.connect(url, close_timeout=2) as ws:
            # Read a few messages
            for i in range(3):
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(msg)
                values = data.get('values', [])
                print(f"  {name}: {values}")
            return True
    except asyncio.TimeoutError:
        print(f"  {name}: TIMEOUT (no data)")
        return False
    except Exception as e:
        print(f"  {name}: ERROR - {e}")
        return False


async def main():
    host = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080

    print(f"\n=== Testing SensorServer at ws://{host}:{port} ===\n")

    # First test basic connection
    print("Testing connection...")
    try:
        ws = await asyncio.wait_for(
            websockets.connect(f'ws://{host}:{port}/sensor/connect?type=android.sensor.accelerometer'),
            timeout=3.0
        )
        await ws.close()
        print("✓ Connection successful!\n")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("\nMake sure:")
        print("  1. SensorServer app is running on your phone")
        print("  2. You tapped START in the app")
        print("  3. ADB port forwarding is set up: adb forward tcp:8080 tcp:8080")
        return

    # Test each sensor
    print("Testing sensors:")
    results = {}
    for name, sensor_type in SENSORS.items():
        results[name] = await test_sensor(name, sensor_type, host, port)

    # Summary
    print("\n=== Summary ===")
    working = sum(1 for v in results.values() if v)
    print(f"Working sensors: {working}/{len(results)}")
    for name, ok in results.items():
        status = "✓" if ok else "✗"
        print(f"  {status} {name}")


if __name__ == '__main__':
    asyncio.run(main())
