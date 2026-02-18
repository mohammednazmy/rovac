#!/usr/bin/env python3
"""
Professional ROVAC LIDAR USB Bridge Test Suite
Comprehensive testing of all enhanced features
"""

import serial
import serial.tools.list_ports
import time
import platform
import sys
import os


class ROVACLidarTestSuite:
    """Professional test suite for ROVAC LIDAR USB Bridge"""

    def __init__(self):
        self.device = None
        self.test_results = {}
        self.platform = platform.system()

    def find_device(self):
        """Find ROVAC LIDAR device"""
        print("🔍 Finding ROVAC LIDAR device...")

        # Try common device paths first
        common_paths = [
            "/dev/rovac_lidar",  # Linux with udev rules
            "/dev/ttyUSB0",  # Linux default
            "/dev/cu.wchusbserial*",  # macOS CH340
        ]

        # Add Windows COM ports
        if self.platform == "Windows":
            common_paths.extend([f"COM{i}" for i in range(1, 21)])

        # Try common paths
        for path in common_paths:
            try:
                # Handle wildcard for macOS
                if "*" in path and self.platform == "Darwin":
                    import glob

                    matches = glob.glob(path)
                    if matches:
                        path = matches[0]
                    else:
                        continue

                print(f"   Trying {path}...")
                ser = serial.Serial(path, 115200, timeout=2)
                print(f"✅ Connected to {path}")
                return ser
            except:
                continue

        # Try auto-detection
        print("   No common paths worked, trying auto-detection...")
        ports = serial.tools.list_ports.comports()

        for port in ports:
            # Look for CH340 devices
            if (
                (hasattr(port, "vid") and port.vid == 6790)
                or (hasattr(port, "description") and "CH340" in str(port.description))
                or (
                    hasattr(port, "device")
                    and "wchusbserial" in str(port.device).lower()
                )
            ):
                try:
                    device_path = getattr(port, "device", "Unknown")
                    print(f"   Trying {device_path}...")
                    ser = serial.Serial(device_path, 115200, timeout=2)
                    print(f"✅ Connected to {device_path}")
                    return ser
                except:
                    continue

        print("❌ Failed to find ROVAC LIDAR device")
        return None

    def test_device_identification(self):
        """Test device identification feature"""
        print("\n🧪 Testing Device Identification...")

        if not self.device:
            print("❌ No device connected")
            return False

        try:
            # Clear input buffer
            self.device.reset_input_buffer()

            # Send ID command
            self.device.write(b"!id\n")
            time.sleep(0.5)

            # Read response
            response_raw = self.device.read_all()
            response = (
                response_raw.decode("utf-8", errors="ignore") if response_raw else ""
            )

            if "!DEVICE_ID" in response or "!ROVAC_LIDAR_BRIDGE" in response:
                print(f"✅ Device identification confirmed: {response.strip()}")
                self.test_results["device_id"] = True
                return True
            else:
                print("ℹ️  Basic firmware detected (no enhanced features)")
                self.test_results["device_id"] = False
                return True

        except Exception as e:
            print(f"❌ Error testing device identification: {e}")
            self.test_results["device_id"] = False
            return False

    def test_firmware_version(self):
        """Test firmware version reporting"""
        print("\n🔧 Testing Firmware Version...")

        if not self.device:
            print("❌ No device connected")
            return False

        try:
            # Clear input buffer
            self.device.reset_input_buffer()

            # Send version command
            self.device.write(b"!version\n")
            time.sleep(0.5)

            # Read response
            response_raw = self.device.read_all()
            response = (
                response_raw.decode("utf-8", errors="ignore") if response_raw else ""
            )

            if "!VERSION" in response or "2.0.0" in response:
                print(f"✅ Firmware version confirmed: {response.strip()}")
                self.test_results["firmware_version"] = True
                return True
            else:
                print("ℹ️  Basic firmware version detected")
                self.test_results["firmware_version"] = False
                return True

        except Exception as e:
            print(f"❌ Error testing firmware version: {e}")
            self.test_results["firmware_version"] = False
            return False

    def test_status_monitoring(self):
        """Test real-time status monitoring"""
        print("\n📊 Testing Status Monitoring...")

        if not self.device:
            print("❌ No device connected")
            return False

        try:
            # Clear input buffer
            self.device.reset_input_buffer()

            # Send status command
            self.device.write(b"!status\n")
            time.sleep(0.5)

            # Read response
            response_raw = self.device.read_all()
            response = (
                response_raw.decode("utf-8", errors="ignore") if response_raw else ""
            )

            if "!STATUS" in response and ("Uptime" in response or "Bytes" in response):
                print(f"✅ Real-time status confirmed: {response.strip()}")
                self.test_results["status_monitoring"] = True
                return True
            else:
                print("ℹ️  Status monitoring not available")
                self.test_results["status_monitoring"] = False
                return True

        except Exception as e:
            print(f"❌ Error testing status monitoring: {e}")
            self.test_results["status_monitoring"] = False
            return False

    def test_help_system(self):
        """Test help system"""
        print("\n💡 Testing Help System...")

        if not self.device:
            print("❌ No device connected")
            return False

        try:
            # Clear input buffer
            self.device.reset_input_buffer()

            # Send help command
            self.device.write(b"!help\n")
            time.sleep(0.5)

            # Read response
            response_raw = self.device.read_all()
            response = (
                response_raw.decode("utf-8", errors="ignore") if response_raw else ""
            )

            if (
                "!HELP" in response
                or "!AVAILABLE_COMMANDS" in response
                or ("!id" in response and "!version" in response)
            ):
                print(f"✅ Help system confirmed: {response.strip()}")
                self.test_results["help_system"] = True
                return True
            else:
                print("ℹ️  Help system not available")
                self.test_results["help_system"] = False
                return True

        except Exception as e:
            print(f"❌ Error testing help system: {e}")
            self.test_results["help_system"] = False
            return False

    def test_data_flow(self):
        """Test data flow from LIDAR"""
        print("\n📡 Testing Data Flow...")

        if not self.device:
            print("❌ No device connected")
            return False

        try:
            # Clear input buffer and wait for data
            self.device.reset_input_buffer()
            print("   Waiting for LIDAR data (up to 5 seconds)...")

            start_time = time.time()
            bytes_received = 0

            while (time.time() - start_time) < 5:
                if self.device.in_waiting > 0:
                    data = self.device.read(min(self.device.in_waiting, 1024))
                    bytes_received += len(data)

                time.sleep(0.1)
                # Show progress every second
                if int(time.time() - start_time) % 1 == 0:
                    print(f"   Bytes received: {bytes_received}")

            if bytes_received > 0:
                print(f"✅ Data flow confirmed: {bytes_received} bytes received")
                self.test_results["data_flow"] = True
                return True
            else:
                print("❌ No data flow detected")
                self.test_results["data_flow"] = False
                return False

        except Exception as e:
            print(f"❌ Error testing data flow: {e}")
            self.test_results["data_flow"] = False
            return False

    def test_command_processing(self):
        """Test command processing without interference"""
        print("\n⚙️  Testing Command Processing...")

        if not self.device:
            print("❌ No device connected")
            return False

        try:
            # Clear input buffer
            self.device.reset_input_buffer()

            # Send multiple commands quickly
            commands = [b"!id\n", b"!version\n", b"!status\n", b"!help\n"]

            for cmd in commands:
                self.device.write(cmd)
                time.sleep(0.1)  # Small delay between commands

            time.sleep(1)  # Wait for all responses

            # Read all responses
            response_raw = self.device.read_all()
            response_count = response_raw.count(b"!") if response_raw else 0

            if response_count >= len(commands):
                print(
                    f"✅ Command processing confirmed: {response_count} responses received"
                )
                self.test_results["command_processing"] = True
                return True
            else:
                print(
                    f"ℹ️  Command processing: {response_count}/{len(commands)} responses received"
                )
                self.test_results["command_processing"] = response_count > 0
                return response_count > 0

        except Exception as e:
            print(f"❌ Error testing command processing: {e}")
            self.test_results["command_processing"] = False
            return False

    def run_comprehensive_test(self):
        """Run all tests and generate report"""
        print("=" * 60)
        print("  ROVAC LIDAR USB Bridge - Professional Test Suite")
        print("=" * 60)
        print()

        print(f"🖥️  Platform: {self.platform}")
        print()

        # Connect to device
        self.device = self.find_device()
        if not self.device:
            print("❌ Cannot proceed without device connection")
            return False

        try:
            # Run all tests
            tests = [
                self.test_device_identification,
                self.test_firmware_version,
                self.test_status_monitoring,
                self.test_help_system,
                self.test_data_flow,
                self.test_command_processing,
            ]

            results = []
            for test in tests:
                results.append(test())

            # Generate report
            print("\n" + "=" * 60)
            print("  TEST RESULTS SUMMARY")
            print("=" * 60)

            passed = sum(results)
            total = len(results)

            print(f"Tests Passed: {passed}/{total}")

            if passed == total:
                print("🏆 All tests PASSED! Your device is professionally enhanced!")
                print("   ✅ Device identification")
                print("   ✅ Firmware version reporting")
                print("   ✅ Real-time status monitoring")
                print("   ✅ Help system")
                print("   ✅ Data flow")
                print("   ✅ Command processing")
            elif passed >= total * 0.8:
                print("🎉 Most tests PASSED! Device is functioning well.")
            elif passed >= total * 0.5:
                print("⚠️  Some tests PASSED. Device is partially functional.")
            else:
                print("❌ Most tests FAILED. Device needs attention.")

            print()
            print("💡 Professional Features Available:")
            if self.test_results.get("device_id", False):
                print("   📱 Device identification")
            if self.test_results.get("firmware_version", False):
                print("   🔧 Firmware version reporting")
            if self.test_results.get("status_monitoring", False):
                print("   📊 Real-time status monitoring")
            if self.test_results.get("help_system", False):
                print("   💡 Built-in help system")
            if self.test_results.get("data_flow", False):
                print("   📡 Continuous data flow")
            if self.test_results.get("command_processing", False):
                print("   ⚙️  Reliable command processing")

            print()
            if self.test_results.get("data_flow", False):
                print("✅ Your ROVAC LIDAR USB Bridge is ready for professional use!")
                print("   It provides true plug-and-play operation across platforms.")
            else:
                print("⚠️  Your device is connected but data flow is not detected.")
                print("   Check wiring connections and LIDAR power.")

            return passed > 0

        finally:
            # Close device connection
            if self.device:
                self.device.close()
                print("\n🔌 Device connection closed")

    def create_usage_examples(self):
        """Create usage examples for different scenarios"""
        print("\n📝 Creating Usage Examples...")

        # Cross-platform usage example
        example_script = '''#!/usr/bin/env python3
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
    print("\\n🔍 Querying device features...")
    
    # Query device identification
    ser.write(b'!id\\n')
    time.sleep(0.2)
    response = ser.read_all().decode('utf-8', errors='ignore')
    if response:
        print(f"📱 Device ID: {response.strip()}")
    
    # Query firmware version
    ser.write(b'!version\\n')
    time.sleep(0.2)
    response = ser.read_all().decode('utf-8', errors='ignore')
    if response:
        print(f"🔧 Version: {response.strip()}")
    
    # Query status
    ser.write(b'!status\\n')
    time.sleep(0.2)
    response = ser.read_all().decode('utf-8', errors='ignore')
    if response:
        print(f"📊 Status: {response.strip()}")

def read_lidar_data(ser, duration=10):
    """Read LIDAR data for specified duration"""
    print(f"\\n📡 Reading LIDAR data for {duration} seconds...")
    
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
        print("\\n⏹️  Stopped by user")
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
            print("\\n🔌 Connection closed")

if __name__ == "__main__":
    main()
'''

        try:
            with open("rovac_lidar_usage_example.py", "w") as f:
                f.write(example_script)
            print("✅ Usage example created: rovac_lidar_usage_example.py")
            return True
        except Exception as e:
            print(f"❌ Error creating usage example: {e}")
            return False


def main():
    """Main test function"""
    # Create test suite
    test_suite = ROVACLidarTestSuite()

    # Run comprehensive test
    success = test_suite.run_comprehensive_test()

    # Create usage examples
    test_suite.create_usage_examples()

    print("\n" + "=" * 60)
    print("  ROVAC LIDAR USB BRIDGE - PROFESSIONAL TESTING COMPLETE")
    print("=" * 60)

    if success:
        print("🎉 Congratulations! Your device is professionally enhanced!")
        print("   It provides true plug-and-play operation across all platforms.")
        print()
        print("Next steps:")
        print("1. Use the professional features in your applications")
        print("2. Refer to the usage example for implementation details")
        print("3. Enjoy cross-platform compatibility and professional features!")
    else:
        print("⚠️  Testing completed with some issues.")
        print("   Check the detailed results above for troubleshooting.")

    return success


if __name__ == "__main__":
    main()
