#!/usr/bin/env python3
"""
Quick diagnostic tool for ESP32 XV11 LIDAR Bridge
Tests communication and data flow
"""

import serial
import time
import sys

PORT = '/dev/cu.usbserial-0001'
BAUD = 115200

def test_esp32_commands():
    """Test ESP32 command responses"""
    print("Testing ESP32 commands...")
    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        time.sleep(1)  # Let ESP32 settle
        
        # Test ID command
        ser.write(b'!id\n')
        time.sleep(0.3)
        response = ser.read(100).decode('ascii', errors='ignore')
        if 'ESP32_XV11_BRIDGE' in response:
            print("✅ ESP32 ID: OK")
        else:
            print(f"⚠️  Unexpected ID response: {response}")
        
        # Test RPM command
        ser.flushInput()
        ser.write(b'!rpm\n')
        time.sleep(0.3)
        response = ser.read(200).decode('ascii', errors='ignore')
        print(f"RPM Status: {response.strip()}")
        
        # Test status command
        ser.flushInput()
        ser.write(b'!status\n')
        time.sleep(0.3)
        response = ser.read(300).decode('ascii', errors='ignore')
        print(f"Status: {response.strip()}")
        
        ser.close()
        return True
    except Exception as e:
        print(f"❌ Command test failed: {e}")
        return False

def test_lidar_data():
    """Check for XV11 data packets"""
    print("\nTesting LIDAR data stream...")
    try:
        ser = serial.Serial(PORT, BAUD, timeout=3)
        time.sleep(0.5)
        
        # Read raw data
        data = ser.read(5000)
        ser.close()
        
        # Count 0xFA markers
        fa_count = data.count(b'\xfa')
        print(f"0xFA packet markers found: {fa_count}")
        
        if fa_count > 10:
            print("✅ LIDAR data flowing correctly!")
            
            # Analyze packet structure
            for i in range(min(3, fa_count)):
                idx = data.find(b'\xfa', i * 22)
                if idx >= 0 and idx + 4 < len(data):
                    packet_idx = data[idx + 1]
                    if 0xA0 <= packet_idx <= 0xF9:
                        rpm_raw = data[idx + 2] | (data[idx + 3] << 8)
                        rpm = rpm_raw / 64
                        print(f"  Packet {packet_idx - 0xA0}: RPM = {rpm:.1f}")
            return True
        else:
            print("⚠️  No valid LIDAR packets detected")
            print(f"First 100 bytes (hex): {data[:100].hex()}")
            return False
            
    except Exception as e:
        print(f"❌ Data test failed: {e}")
        return False

def main():
    print("=" * 60)
    print("ESP32 XV11 LIDAR Bridge Diagnostic")
    print("=" * 60)
    print(f"Port: {PORT}")
    print(f"Baud: {BAUD}\n")
    
    # Run tests
    cmd_ok = test_esp32_commands()
    data_ok = test_lidar_data()
    
    print("\n" + "=" * 60)
    if cmd_ok and data_ok:
        print("✅ ALL TESTS PASSED - LIDAR is ready!")
    elif cmd_ok:
        print("⚠️  ESP32 OK, but no LIDAR data - check wiring or motor")
    else:
        print("❌ Communication failed - check connections")
    print("=" * 60)

if __name__ == '__main__':
    main()
