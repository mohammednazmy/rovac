#!/usr/bin/env python3
"""
ROVAC LIDAR USB Bridge - Cross-Platform Usage Example
"""

import serial
import time

def connect_to_lidar():
    """Connect to ROVAC LIDAR USB Bridge with auto-detection"""
    import serial.tools.list_ports
    import platform
    
    # Try common device paths
    common_paths = [
        '/dev/rovac_lidar',           # Linux with udev rules
        '/dev/ttyUSB0',              # Linux default
        '/dev/cu.wchusbserial*',     # macOS CH340
    ]
    
    # Add Windows COM ports
    if platform.system() == "Windows":
        common_paths.extend([f'COM{i}' for i in range(1, 21)])
    
    # Try common paths
    for path in common_paths:
        try:
            # Handle wildcard for macOS
            if '*' in path and platform.system() == "Darwin":
                import glob
                matches = glob.glob(path)
                if matches:
                    path = matches[0]
                else:
                    continue
            
            print(f"Trying to connect to {path}...")
            ser = serial.Serial(path, 115200, timeout=1)
            print(f"✅ Connected to {path}")
            return ser
        except:
            continue
    
    # Try auto-detection if no common paths work
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if ('CH340' in str(getattr(port, 'description', '')) or 
            'wchusbserial' in str(getattr(port, 'device', '')).lower()):
            try:
                device_path = getattr(port, 'device', 'Unknown')
                ser = serial.Serial(device_path, 115200, timeout=1)
                print(f"✅ Connected to {device_path}")
                return ser
            except:
                continue
    
    raise Exception("Failed to connect to ROVAC LIDAR device")

def query_device_features(ser):
    """Query enhanced firmware features"""
    print("\n🔍 Querying device features...")
    
    # Query device identification
    ser.write(b'!id\n')
    time.sleep(0.2)
    response = ser.read_all().decode('utf-8', errors='ignore')
    if response:
        print(f"📱 Device ID: {response.strip()}")
    
    # Query firmware version
    ser.write(b'!version\n')
    time.sleep(0.2)
    response = ser.read_all().decode('utf-8', errors='ignore')
    if response:
        print(f"🔧 Version: {response.strip()}")
    
    # Query status
    ser.write(b'!status\n')
    time.sleep(0.2)
    response = ser.read_all().decode('utf-8', errors='ignore')
    if response:
        print(f"📊 Status: {response.strip()}")

def read_lidar_data(ser, duration=10):
    """Read LIDAR data for specified duration"""
    print(f"\n📡 Reading LIDAR data for {duration} seconds...")
    
    start_time = time.time()
    total_bytes = 0
    
    try:
        while (time.time() - start_time) < duration:
            if ser.in_waiting > 0:
                data = ser.read(min(ser.in_waiting, 1024))
                total_bytes += len(data)
                
                # Print progress occasionally
                if int(time.time() - start_time) % 2 == 0:
                    print(f"   Bytes received: {total_bytes}")
            
            time.sleep(0.01)
        
        print(f"✅ Data collection complete: {total_bytes} bytes")
        return True
        
    except KeyboardInterrupt:
        print("\n⏹️  Stopped by user")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    """Main function"""
    print("=== ROVAC LIDAR USB Bridge - Usage Example ===")
    
    try:
        # Connect to LIDAR
        ser = connect_to_lidar()
        
        # Query device features
        query_device_features(ser)
        
        # Flush input buffer
        ser.reset_input_buffer()
        time.sleep(1)
        
        # Read data for 10 seconds
        read_lidar_data(ser, 10)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    finally:
        # Close connection
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("\n🔌 Connection closed")

if __name__ == "__main__":
    main()
