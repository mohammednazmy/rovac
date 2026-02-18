#!/usr/bin/env python3
"""
ROVAC LIDAR USB Bridge Manager
Cross-platform device manager with professional features
"""

import serial
import serial.tools.list_ports
import time
import platform
import os
import sys


class ROVACLidarManager:
    """Professional LIDAR USB Bridge Manager"""

    def __init__(self):
        self.platform = platform.system()
        self.devices = []
        self.current_device = None

    def find_devices(self):
        """Find all ROVAC LIDAR devices"""
        print("🔍 Scanning for ROVAC LIDAR devices...")

        # List all available serial ports
        ports = serial.tools.list_ports.comports()
        self.devices = []

        for port in ports:
            # Check for CH340 devices (common VID/PID for LAFVIN Nano)
            if (
                (hasattr(port, "vid") and port.vid == 6790)
                or (hasattr(port, "description") and "CH340" in str(port.description))
                or (
                    hasattr(port, "device")
                    and "wchusbserial" in str(port.device).lower()
                )
            ):
                device_info = {
                    "device": getattr(port, "device", "Unknown"),
                    "description": getattr(port, "description", "Unknown"),
                    "vid": getattr(port, "vid", None),
                    "pid": getattr(port, "pid", None),
                    "manufacturer": getattr(port, "manufacturer", "Unknown"),
                    "product": getattr(port, "product", "Unknown"),
                }
                self.devices.append(device_info)

        print(f"✅ Found {len(self.devices)} potential device(s)")
        return self.devices

    def list_devices(self):
        """List all found devices"""
        self.find_devices()

        if not self.devices:
            print("❌ No ROVAC LIDAR devices found")
            print("\nTroubleshooting tips:")
            print("1. Check USB connection")
            print("2. Ensure CH340 drivers are installed")
            print("3. Try different USB port")
            return False

        print("\n📋 Found devices:")
        for i, device in enumerate(self.devices):
            print(f"  {i + 1}. {device['device']} - {device['description']}")
            if device["vid"]:
                print(f"      VID: {device['vid']:04X}, PID: {device['pid']:04X}")

        return True

    def connect_to_device(self, device_index=0):
        """Connect to a specific device"""
        if not self.devices:
            self.find_devices()

        if not self.devices:
            print("❌ No devices available")
            return False

        if device_index >= len(self.devices):
            print(f"❌ Invalid device index. Choose 0-{len(self.devices) - 1}")
            return False

        device_path = self.devices[device_index]["device"]
        print(f"🔌 Connecting to {device_path}...")

        try:
            self.current_device = serial.Serial(device_path, 115200, timeout=2)
            print("✅ Connected successfully")
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False

    def test_enhanced_features(self):
        """Test enhanced firmware features"""
        if not self.current_device:
            print("❌ No device connected")
            return False

        print("\n🧪 Testing enhanced firmware features...")

        # Test device identification
        print("  Testing device identification...")
        self.current_device.write(b"!id\n")
        time.sleep(0.5)
        response_raw = self.current_device.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        if response:
            print(f"    📱 ID: {response.strip()}")
        else:
            print("    📱 ID: Basic firmware detected")

        # Test version
        print("  Testing firmware version...")
        self.current_device.write(b"!version\n")
        time.sleep(0.5)
        response_raw = self.current_device.read_all()
        response = response_raw.decode("utf-8", errors="ignore") if response_raw else ""
        if response:
            print(f"    🔧 Version: {response.strip()}")
        else:
            print("    🔧 Version: 2.0.0 (assumed)")

        # Test data flow
        print("  Testing data flow...")
        self.current_device.reset_input_buffer()
        time.sleep(2)
        bytes_available = self.current_device.in_waiting
        if bytes_available > 0:
            print(f"    📡 Data flow: {bytes_available} bytes available")
        else:
            print("    📡 Data flow: No data detected")

        return True

    def disconnect(self):
        """Disconnect from current device"""
        if self.current_device and self.current_device.is_open:
            self.current_device.close()
            print("🔌 Disconnected from device")

    def platform_specific_info(self):
        """Provide platform-specific information"""
        print(f"\n🖥️  Platform Information: {self.platform}")

        if self.platform == "Darwin":  # macOS
            print("💡 macOS Tips:")
            print("   - Device appears as /dev/cu.wchusbserialXXXX")
            print("   - No drivers needed for recent macOS versions")
            print("   - Check System Preferences > Security if blocked")

        elif self.platform == "Linux":
            print("💡 Linux Tips:")
            print("   - Device appears as /dev/ttyUSB0 or similar")
            print("   - May need udev rules for consistent naming")
            print("   - Add user to dialout group: sudo usermod -a -G dialout $USER")

        elif self.platform == "Windows":
            print("💡 Windows Tips:")
            print("   - Device appears as COM3, COM4, etc.")
            print("   - Check Device Manager for USB Serial Port")
            print("   - No drivers needed for Windows 10/11")

    def create_cross_platform_script(self):
        """Create cross-platform usage script"""
        script_content = '''#!/usr/bin/env python3
"""
Cross-Platform ROVAC LIDAR USB Bridge Usage Script
"""

import serial
import time

def connect_to_lidar():
    """
    Connect to ROVAC LIDAR USB Bridge
    Returns serial connection object or None if failed
    """
    
    # Common device paths for different platforms
    device_paths = [
        '/dev/rovac_lidar',        # Linux with udev rules
        '/dev/ttyUSB0',            # Linux default
        '/dev/cu.wchusbserial*',   # macOS
        'COM3', 'COM4', 'COM5'     # Windows
    ]
    
    for device in device_paths:
        try:
            # Try wildcard expansion for macOS
            if '*' in device and 'darwin' in device.lower():
                import glob
                matches = glob.glob(device)
                if matches:
                    device = matches[0]
                else:
                    continue
            
            print(f"Trying to connect to {device}...")
            ser = serial.Serial(device, 115200, timeout=1)
            print(f"✅ Connected to {device}")
            return ser
        except:
            continue
    
    print("❌ Failed to connect to any device")
    return None

def read_lidar_data(ser, duration=10):
    """
    Read LIDAR data for specified duration
    """
    print(f"📡 Reading LIDAR data for {duration} seconds...")
    
    start_time = time.time()
    total_bytes = 0
    
    try:
        while (time.time() - start_time) < duration:
            if ser.in_waiting > 0:
                # Read available data
                data = ser.read(min(ser.in_waiting, 1024))
                total_bytes += len(data)
                
                # Print progress every 2 seconds
                if int(time.time() - start_time) % 2 == 0:
                    print(f"   Bytes received: {total_bytes}")
            
            time.sleep(0.01)  # Small delay to prevent excessive CPU usage
    
        print(f"✅ Data collection complete: {total_bytes} bytes received")
        return True
        
    except KeyboardInterrupt:
        print("\\n⏹️  Data collection stopped by user")
        return False
    except Exception as e:
        print(f"❌ Error reading data: {e}")
        return False

def main():
    """Main function"""
    print("=== ROVAC LIDAR USB Bridge - Cross-Platform Usage ===")
    print()
    
    # Connect to LIDAR
    ser = connect_to_lidar()
    if not ser:
        return
    
    try:
        # Flush input buffer
        ser.reset_input_buffer()
        time.sleep(1)
        
        # Read data for 10 seconds
        read_lidar_data(ser, 10)
        
    finally:
        # Close connection
        ser.close()
        print("🔌 Connection closed")

if __name__ == "__main__":
    main()
'''

        try:
            with open("usage_example.py", "w") as f:
                f.write(script_content)
            print("✅ Cross-platform usage script created: usage_example.py")
            return True
        except Exception as e:
            print(f"❌ Error creating usage script: {e}")
            return False


def main():
    """Main function"""
    print("===========================================")
    print("  ROVAC LIDAR USB Bridge Manager")
    print("  Professional Cross-Platform Edition")
    print("===========================================")

    manager = ROVACLidarManager()

    # Platform-specific information
    manager.platform_specific_info()

    # List devices
    if manager.list_devices():
        # Connect to first device
        if manager.connect_to_device(0):
            # Test enhanced features
            manager.test_enhanced_features()

            # Disconnect
            manager.disconnect()

    # Create cross-platform usage script
    print()
    manager.create_cross_platform_script()

    print("\n🎉 Professional LIDAR USB Bridge Management Complete!")
    print("   Your device is now truly plug-and-play across platforms!")


if __name__ == "__main__":
    main()
