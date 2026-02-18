#!/usr/bin/env python3
"""
Super Sensor CLI Application.

Provides a text-based interface for controlling the Super Sensor module
on headless Linux systems (like Raspberry Pi without desktop).
"""

import os
import sys
import time
import json
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from super_sensor_driver import SuperSensor, ScanResult
except ImportError:
    SuperSensor = None
    ScanResult = None


class Colors:
    """ANSI color codes for terminal output."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'

    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_BLUE = '\033[44m'

    @classmethod
    def disable(cls):
        """Disable colors (for non-TTY output)."""
        for attr in dir(cls):
            if not attr.startswith('_') and attr.isupper():
                setattr(cls, attr, '')


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


class SuperSensorCLI:
    """Command-line interface for Super Sensor module."""

    # Sensor display names matching physical orientation
    SENSOR_NAMES = ['Front-Top', 'Left', 'Right', 'Front-Bottom']

    def __init__(self):
        self.sensor: Optional[SuperSensor] = None
        self.port: Optional[str] = None
        self.running = True
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None

        # Calibration data
        self.calibration = {
            'sensor_offsets': [0, 0, 0, 0],
            'servo_min': 0,
            'servo_center': 90,
            'servo_max': 180,
        }

    def clear_screen(self):
        """Clear terminal screen."""
        os.system('clear' if os.name != 'nt' else 'cls')

    def print_header(self, title: str):
        """Print a styled header."""
        width = 60
        print()
        print(f"{Colors.CYAN}{Colors.BOLD}{'=' * width}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}{title.center(width)}{Colors.RESET}")
        print(f"{Colors.CYAN}{Colors.BOLD}{'=' * width}{Colors.RESET}")
        print()

    def print_status(self, label: str, value: str, color: str = Colors.WHITE):
        """Print a status line."""
        print(f"  {Colors.DIM}{label}:{Colors.RESET} {color}{value}{Colors.RESET}")

    def print_menu(self, options: List[tuple], title: str = "Options"):
        """Print a menu with numbered options."""
        print(f"\n{Colors.YELLOW}{title}:{Colors.RESET}")
        for key, label in options:
            print(f"  {Colors.GREEN}[{key}]{Colors.RESET} {label}")
        print()

    def get_input(self, prompt: str = "> ") -> str:
        """Get user input with prompt."""
        try:
            return input(f"{Colors.CYAN}{prompt}{Colors.RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            return 'q'

    def wait_for_key(self, message: str = "Press Enter to continue..."):
        """Wait for user to press Enter."""
        self.get_input(message)

    def print_success(self, message: str):
        """Print success message."""
        print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")

    def print_error(self, message: str):
        """Print error message."""
        print(f"{Colors.RED}✗ {message}{Colors.RESET}")

    def print_warning(self, message: str):
        """Print warning message."""
        print(f"{Colors.YELLOW}⚠ {message}{Colors.RESET}")

    def print_info(self, message: str):
        """Print info message."""
        print(f"{Colors.BLUE}ℹ {message}{Colors.RESET}")

    # ==================== Connection ====================

    def get_available_ports(self) -> List[Dict[str, str]]:
        """Get list of available serial ports."""
        try:
            import serial.tools.list_ports
            ports = []
            for port in serial.tools.list_ports.comports():
                ports.append({
                    'device': port.device,
                    'description': port.description or 'Unknown',
                    'hwid': port.hwid or '',
                })
            return ports
        except Exception:
            return []

    def auto_detect_port(self) -> Optional[str]:
        """Auto-detect Super Sensor port."""
        ports = self.get_available_ports()
        for port in ports:
            # Look for CH340/CH341 (common Arduino Nano clone chip)
            if '1a86:7523' in port['hwid'].lower():
                return port['device']
            # Look for FTDI
            if '0403:6001' in port['hwid'].lower():
                return port['device']
            # Look for Arduino
            if '2341:' in port['hwid'].lower():
                return port['device']
        return None

    def connect(self, port: Optional[str] = None) -> bool:
        """Connect to Super Sensor."""
        if self.sensor and self.sensor._connected:
            self.disconnect()

        if not port:
            port = self.auto_detect_port()
            if not port:
                self.print_error("No Super Sensor detected. Please specify a port.")
                return False

        try:
            self.sensor = SuperSensor(port)
            self.sensor.connect()
            self.port = port
            self.print_success(f"Connected to Super Sensor at {port}")
            return True
        except Exception as e:
            self.print_error(f"Connection failed: {e}")
            self.sensor = None
            return False

    def disconnect(self):
        """Disconnect from Super Sensor."""
        if self._polling:
            self.stop_polling()
        if self.sensor:
            try:
                self.sensor.disconnect()
            except Exception:
                pass
            self.sensor = None
            self.port = None
            self.print_info("Disconnected")

    @property
    def is_connected(self) -> bool:
        """Check if connected to sensor."""
        return self.sensor is not None and self.sensor._connected

    # ==================== Sensor Operations ====================

    def scan(self) -> Optional[ScanResult]:
        """Perform a single scan."""
        if not self.is_connected:
            self.print_error("Not connected")
            return None
        try:
            return self.sensor.scan()
        except Exception as e:
            self.print_error(f"Scan failed: {e}")
            return None

    def get_status(self) -> Optional[Dict[str, Any]]:
        """Get full sensor status."""
        if not self.is_connected:
            self.print_error("Not connected")
            return None
        try:
            return self.sensor.status()
        except Exception as e:
            self.print_error(f"Status failed: {e}")
            return None

    def set_led(self, r: int, g: int, b: int):
        """Set LED color."""
        if not self.is_connected:
            self.print_error("Not connected")
            return
        try:
            self.sensor.set_led(r, g, b)
            self.print_success(f"LED set to RGB({r}, {g}, {b})")
        except Exception as e:
            self.print_error(f"LED command failed: {e}")

    def set_servo(self, angle: int):
        """Set servo angle."""
        if not self.is_connected:
            self.print_error("Not connected")
            return
        try:
            angle = max(0, min(180, angle))
            self.sensor.set_servo(angle)
            self.print_success(f"Servo set to {angle}°")
        except Exception as e:
            self.print_error(f"Servo command failed: {e}")

    def sweep(self, start: int = 0, end: int = 180) -> Optional[List[Dict]]:
        """Perform servo sweep with scanning."""
        if not self.is_connected:
            self.print_error("Not connected")
            return None
        try:
            print(f"Sweeping from {start}° to {end}°...")
            result = self.sensor.sweep(start, end)
            self.print_success(f"Sweep complete: {len(result)} readings")
            return result
        except Exception as e:
            self.print_error(f"Sweep failed: {e}")
            return None

    # ==================== Polling ====================

    def start_polling(self, interval_ms: int = 100, callback=None):
        """Start continuous polling."""
        if self._polling:
            return

        self._polling = True

        def poll_loop():
            while self._polling and self.is_connected:
                try:
                    result = self.sensor.scan()
                    if callback:
                        callback(result)
                except Exception:
                    pass
                time.sleep(interval_ms / 1000.0)

        self._poll_thread = threading.Thread(target=poll_loop, daemon=True)
        self._poll_thread.start()

    def stop_polling(self):
        """Stop continuous polling."""
        self._polling = False
        if self._poll_thread:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None

    # ==================== Display Helpers ====================

    def format_distance(self, cm: int) -> str:
        """Format distance with color coding."""
        if cm <= 0:
            return f"{Colors.DIM}--{Colors.RESET}"
        elif cm < 30:
            return f"{Colors.RED}{cm} cm{Colors.RESET}"
        elif cm < 60:
            return f"{Colors.YELLOW}{cm} cm{Colors.RESET}"
        else:
            return f"{Colors.GREEN}{cm} cm{Colors.RESET}"

    def display_scan_result(self, result: ScanResult):
        """Display scan result in a formatted way."""
        # Map ScanResult properties to physical sensor positions
        readings = [
            result.front_left,   # Front-Top (us[0])
            result.front_right,  # Left (us[1])
            result.left,         # Right (us[2])
            result.right,        # Front-Bottom (us[3])
        ]

        print(f"\n{Colors.BOLD}Ultrasonic Sensors:{Colors.RESET}")
        for i, name in enumerate(self.SENSOR_NAMES):
            dist = self.format_distance(readings[i])
            print(f"  {name:15} {dist}")

        # Show min distance warning
        valid = [r for r in readings if r > 0]
        if valid:
            min_dist = min(valid)
            if min_dist < 30:
                print(f"\n{Colors.RED}{Colors.BOLD}⚠ OBSTACLE DETECTED ({min_dist} cm){Colors.RESET}")
            elif min_dist < 60:
                print(f"\n{Colors.YELLOW}CAUTION ({min_dist} cm){Colors.RESET}")
            else:
                print(f"\n{Colors.GREEN}CLEAR (min: {min_dist} cm){Colors.RESET}")

    def display_status(self, status: Dict[str, Any]):
        """Display full status."""
        us = status.get('us', [-1, -1, -1, -1])
        led = status.get('led', [0, 0, 0])
        servo = status.get('servo', 90)

        print(f"\n{Colors.BOLD}Ultrasonic Sensors:{Colors.RESET}")
        # Map us[] array to physical positions
        sensor_values = [us[0], us[1], us[2], us[3]]  # Front-Top, Left, Right, Front-Bottom
        for i, name in enumerate(self.SENSOR_NAMES):
            if i < len(sensor_values):
                dist = self.format_distance(sensor_values[i])
                print(f"  {name:15} {dist}")

        print(f"\n{Colors.BOLD}LED:{Colors.RESET}")
        print(f"  RGB({led[0]}, {led[1]}, {led[2]})")

        print(f"\n{Colors.BOLD}Servo:{Colors.RESET}")
        print(f"  Angle: {servo}°")

    # ==================== Main Menu ====================

    def main_menu(self):
        """Show main menu."""
        while self.running:
            self.clear_screen()
            self.print_header("SUPER SENSOR CLI")

            # Connection status
            if self.is_connected:
                self.print_status("Status", "Connected", Colors.GREEN)
                self.print_status("Port", self.port, Colors.CYAN)
            else:
                self.print_status("Status", "Disconnected", Colors.RED)

            options = [
                ('1', 'Control & Test'),
                ('2', 'Setup & Install'),
                ('3', 'Calibration'),
                ('4', 'Connect' if not self.is_connected else 'Disconnect'),
                ('s', 'Quick Scan' if self.is_connected else 'Scan Ports'),
                ('q', 'Quit'),
            ]

            self.print_menu(options, "Main Menu")

            choice = self.get_input().lower()

            if choice == '1':
                self.control_menu()
            elif choice == '2':
                self.setup_menu()
            elif choice == '3':
                self.calibration_menu()
            elif choice == '4':
                if self.is_connected:
                    self.disconnect()
                else:
                    self.connection_menu()
            elif choice == 's':
                if self.is_connected:
                    result = self.scan()
                    if result:
                        self.display_scan_result(result)
                    self.wait_for_key()
                else:
                    self.show_ports()
            elif choice == 'q':
                self.running = False
                self.disconnect()
                print("\nGoodbye!")

    def show_ports(self):
        """Show available serial ports."""
        ports = self.get_available_ports()
        print(f"\n{Colors.BOLD}Available Serial Ports:{Colors.RESET}")
        if not ports:
            print("  No serial ports found")
        else:
            for port in ports:
                print(f"  {Colors.CYAN}{port['device']}{Colors.RESET}")
                print(f"    {Colors.DIM}{port['description']}{Colors.RESET}")
        self.wait_for_key()

    def connection_menu(self):
        """Show connection menu."""
        self.clear_screen()
        self.print_header("CONNECT TO SENSOR")

        ports = self.get_available_ports()
        auto_port = self.auto_detect_port()

        print(f"{Colors.BOLD}Available Ports:{Colors.RESET}")
        for i, port in enumerate(ports):
            marker = " (auto-detected)" if port['device'] == auto_port else ""
            print(f"  {Colors.GREEN}[{i+1}]{Colors.RESET} {port['device']}{Colors.CYAN}{marker}{Colors.RESET}")
            print(f"      {Colors.DIM}{port['description']}{Colors.RESET}")

        options = [
            ('a', 'Auto-connect' + (f" ({auto_port})" if auto_port else " (no device found)")),
            ('m', 'Manual entry'),
            ('b', 'Back'),
        ]
        self.print_menu(options)

        choice = self.get_input().lower()

        if choice == 'a':
            self.connect()
            self.wait_for_key()
        elif choice == 'm':
            port = self.get_input("Enter port path: ")
            if port:
                self.connect(port)
                self.wait_for_key()
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                self.connect(ports[idx]['device'])
                self.wait_for_key()

    # ==================== Control Menu ====================

    def control_menu(self):
        """Show control/test menu."""
        while True:
            self.clear_screen()
            self.print_header("CONTROL & TEST")

            if not self.is_connected:
                self.print_warning("Not connected to sensor")

            options = [
                ('1', 'Scan Once'),
                ('2', 'Get Full Status'),
                ('3', 'Continuous Scan'),
                ('4', 'LED Control'),
                ('5', 'Servo Control'),
                ('6', 'Sweep Scan'),
                ('b', 'Back'),
            ]

            self.print_menu(options)
            choice = self.get_input().lower()

            if choice == '1':
                result = self.scan()
                if result:
                    self.display_scan_result(result)
                self.wait_for_key()
            elif choice == '2':
                status = self.get_status()
                if status:
                    self.display_status(status)
                self.wait_for_key()
            elif choice == '3':
                self.continuous_scan_menu()
            elif choice == '4':
                self.led_control_menu()
            elif choice == '5':
                self.servo_control_menu()
            elif choice == '6':
                self.sweep_menu()
            elif choice == 'b':
                break

    def continuous_scan_menu(self):
        """Continuous scanning mode."""
        if not self.is_connected:
            self.print_error("Not connected")
            self.wait_for_key()
            return

        self.clear_screen()
        self.print_header("CONTINUOUS SCAN")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                result = self.scan()
                if result:
                    # Clear and redraw
                    print("\033[H\033[J", end="")  # Clear screen
                    self.print_header("CONTINUOUS SCAN")
                    print("Press Ctrl+C to stop\n")
                    self.display_scan_result(result)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\nStopped")
            self.wait_for_key()

    def led_control_menu(self):
        """LED control menu."""
        while True:
            self.clear_screen()
            self.print_header("LED CONTROL")

            options = [
                ('1', 'Red'),
                ('2', 'Green'),
                ('3', 'Blue'),
                ('4', 'White'),
                ('5', 'Cyan'),
                ('6', 'Magenta'),
                ('7', 'Yellow'),
                ('8', 'Custom RGB'),
                ('0', 'Off'),
                ('b', 'Back'),
            ]

            self.print_menu(options)
            choice = self.get_input().lower()

            colors = {
                '1': (255, 0, 0),
                '2': (0, 255, 0),
                '3': (0, 0, 255),
                '4': (255, 255, 255),
                '5': (0, 255, 255),
                '6': (255, 0, 255),
                '7': (255, 255, 0),
                '0': (0, 0, 0),
            }

            if choice in colors:
                r, g, b = colors[choice]
                self.set_led(r, g, b)
                time.sleep(0.3)
            elif choice == '8':
                try:
                    r = int(self.get_input("Red (0-255): "))
                    g = int(self.get_input("Green (0-255): "))
                    b = int(self.get_input("Blue (0-255): "))
                    self.set_led(r, g, b)
                except ValueError:
                    self.print_error("Invalid input")
                self.wait_for_key()
            elif choice == 'b':
                break

    def servo_control_menu(self):
        """Servo control menu."""
        while True:
            self.clear_screen()
            self.print_header("SERVO CONTROL")

            options = [
                ('1', '0° (Left)'),
                ('2', '45°'),
                ('3', '90° (Center)'),
                ('4', '135°'),
                ('5', '180° (Right)'),
                ('c', 'Custom angle'),
                ('b', 'Back'),
            ]

            self.print_menu(options)
            choice = self.get_input().lower()

            angles = {'1': 0, '2': 45, '3': 90, '4': 135, '5': 180}

            if choice in angles:
                self.set_servo(angles[choice])
                time.sleep(0.3)
            elif choice == 'c':
                try:
                    angle = int(self.get_input("Angle (0-180): "))
                    self.set_servo(angle)
                except ValueError:
                    self.print_error("Invalid input")
                self.wait_for_key()
            elif choice == 'b':
                break

    def sweep_menu(self):
        """Sweep scan menu."""
        self.clear_screen()
        self.print_header("SWEEP SCAN")

        try:
            start = int(self.get_input("Start angle (0-180) [0]: ") or "0")
            end = int(self.get_input("End angle (0-180) [180]: ") or "180")
        except ValueError:
            self.print_error("Invalid input")
            self.wait_for_key()
            return

        result = self.sweep(start, end)
        if result:
            print(f"\n{Colors.BOLD}Sweep Results:{Colors.RESET}")
            for reading in result:
                angle = reading.get('angle', 0)
                us = reading.get('us', [-1, -1, -1, -1])
                print(f"  {angle:3}°: {us}")

        self.wait_for_key()

    # ==================== Setup Menu ====================

    def setup_menu(self):
        """Show setup/installation menu."""
        from .linux_setup import LinuxSetup
        setup = LinuxSetup(self)
        setup.menu()

    # ==================== Calibration Menu ====================

    def calibration_menu(self):
        """Show calibration menu."""
        while True:
            self.clear_screen()
            self.print_header("CALIBRATION")

            options = [
                ('1', 'Test All Sensors'),
                ('2', 'Test Individual Sensor'),
                ('3', 'Test LED Channels'),
                ('4', 'Servo Calibration'),
                ('5', 'Save Calibration Profile'),
                ('6', 'Load Calibration Profile'),
                ('b', 'Back'),
            ]

            self.print_menu(options)
            choice = self.get_input().lower()

            if choice == '1':
                self.test_all_sensors()
            elif choice == '2':
                self.test_individual_sensor()
            elif choice == '3':
                self.test_led_channels()
            elif choice == '4':
                self.servo_calibration()
            elif choice == '5':
                self.save_calibration()
            elif choice == '6':
                self.load_calibration()
            elif choice == 'b':
                break

    def test_all_sensors(self):
        """Test all ultrasonic sensors."""
        if not self.is_connected:
            self.print_error("Not connected")
            self.wait_for_key()
            return

        self.clear_screen()
        self.print_header("SENSOR TEST")

        result = self.scan()
        if not result:
            self.wait_for_key()
            return

        # Map to physical positions
        readings = [
            result.front_left,   # Front-Top
            result.front_right,  # Left
            result.left,         # Right
            result.right,        # Front-Bottom
        ]

        print(f"{'Sensor':<15} {'Reading':<12} {'Status':<10}")
        print("-" * 40)

        for i, name in enumerate(self.SENSOR_NAMES):
            reading = readings[i]
            offset = self.calibration['sensor_offsets'][i]
            corrected = reading + offset if reading > 0 else -1

            if reading <= 0:
                status = f"{Colors.RED}FAIL{Colors.RESET}"
                reading_str = "--"
            elif reading < 5 or reading > 350:
                status = f"{Colors.YELLOW}WARN{Colors.RESET}"
                reading_str = f"{reading} cm"
            else:
                status = f"{Colors.GREEN}OK{Colors.RESET}"
                reading_str = f"{reading} cm"

            print(f"{name:<15} {reading_str:<12} {status}")

        self.wait_for_key()

    def test_individual_sensor(self):
        """Test a single sensor."""
        self.clear_screen()
        self.print_header("TEST INDIVIDUAL SENSOR")

        for i, name in enumerate(self.SENSOR_NAMES):
            print(f"  {Colors.GREEN}[{i+1}]{Colors.RESET} {name}")

        choice = self.get_input("\nSelect sensor (1-4): ")

        try:
            idx = int(choice) - 1
            if 0 <= idx < 4:
                result = self.scan()
                if result:
                    readings = [result.front_left, result.front_right, result.left, result.right]
                    reading = readings[idx]
                    print(f"\n{self.SENSOR_NAMES[idx]}: {self.format_distance(reading)}")
        except ValueError:
            self.print_error("Invalid selection")

        self.wait_for_key()

    def test_led_channels(self):
        """Test LED R/G/B channels."""
        if not self.is_connected:
            self.print_error("Not connected")
            self.wait_for_key()
            return

        self.clear_screen()
        self.print_header("LED CHANNEL TEST")

        channels = [
            ("Red", (255, 0, 0)),
            ("Green", (0, 255, 0)),
            ("Blue", (0, 0, 255)),
            ("White", (255, 255, 255)),
        ]

        for name, (r, g, b) in channels:
            print(f"Testing {name}...")
            self.sensor.set_led(r, g, b)
            time.sleep(0.5)

        self.sensor.set_led(0, 0, 0)
        self.print_success("LED test complete")
        self.wait_for_key()

    def servo_calibration(self):
        """Calibrate servo positions."""
        while True:
            self.clear_screen()
            self.print_header("SERVO CALIBRATION")

            print(f"Current values:")
            print(f"  Min angle:    {self.calibration['servo_min']}°")
            print(f"  Center angle: {self.calibration['servo_center']}°")
            print(f"  Max angle:    {self.calibration['servo_max']}°")

            options = [
                ('1', 'Set/Test Min'),
                ('2', 'Set/Test Center'),
                ('3', 'Set/Test Max'),
                ('4', 'Full Sweep Test'),
                ('r', 'Reset to Defaults'),
                ('b', 'Back'),
            ]

            self.print_menu(options)
            choice = self.get_input().lower()

            if choice == '1':
                try:
                    angle = int(self.get_input(f"Min angle [{self.calibration['servo_min']}]: ")
                               or str(self.calibration['servo_min']))
                    self.calibration['servo_min'] = angle
                    self.set_servo(angle)
                except ValueError:
                    self.print_error("Invalid input")
            elif choice == '2':
                try:
                    angle = int(self.get_input(f"Center angle [{self.calibration['servo_center']}]: ")
                               or str(self.calibration['servo_center']))
                    self.calibration['servo_center'] = angle
                    self.set_servo(angle)
                except ValueError:
                    self.print_error("Invalid input")
            elif choice == '3':
                try:
                    angle = int(self.get_input(f"Max angle [{self.calibration['servo_max']}]: ")
                               or str(self.calibration['servo_max']))
                    self.calibration['servo_max'] = angle
                    self.set_servo(angle)
                except ValueError:
                    self.print_error("Invalid input")
            elif choice == '4':
                print("Testing full sweep...")
                self.set_servo(self.calibration['servo_min'])
                time.sleep(0.5)
                for angle in range(self.calibration['servo_min'],
                                  self.calibration['servo_max'] + 1, 5):
                    self.sensor.set_servo(angle)
                    time.sleep(0.05)
                time.sleep(0.3)
                self.set_servo(self.calibration['servo_center'])
                self.print_success("Sweep complete")
                self.wait_for_key()
            elif choice == 'r':
                self.calibration['servo_min'] = 0
                self.calibration['servo_center'] = 90
                self.calibration['servo_max'] = 180
                self.print_success("Reset to defaults")
            elif choice == 'b':
                break

    def save_calibration(self):
        """Save calibration profile."""
        config_dir = Path.home() / '.config' / 'super_sensor'
        config_dir.mkdir(parents=True, exist_ok=True)

        name = self.get_input("Profile name [default]: ") or "default"
        filepath = config_dir / f"{name}.json"

        try:
            with open(filepath, 'w') as f:
                json.dump(self.calibration, f, indent=2)
            self.print_success(f"Saved to {filepath}")
        except Exception as e:
            self.print_error(f"Save failed: {e}")

        self.wait_for_key()

    def load_calibration(self):
        """Load calibration profile."""
        config_dir = Path.home() / '.config' / 'super_sensor'

        if not config_dir.exists():
            self.print_warning("No calibration profiles found")
            self.wait_for_key()
            return

        profiles = list(config_dir.glob("*.json"))
        if not profiles:
            self.print_warning("No calibration profiles found")
            self.wait_for_key()
            return

        print(f"\n{Colors.BOLD}Available Profiles:{Colors.RESET}")
        for i, p in enumerate(profiles):
            print(f"  {Colors.GREEN}[{i+1}]{Colors.RESET} {p.stem}")

        choice = self.get_input("\nSelect profile: ")

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(profiles):
                with open(profiles[idx], 'r') as f:
                    self.calibration = json.load(f)
                self.print_success(f"Loaded {profiles[idx].stem}")
        except (ValueError, json.JSONDecodeError) as e:
            self.print_error(f"Load failed: {e}")

        self.wait_for_key()

    def run(self):
        """Run the CLI application."""
        try:
            self.main_menu()
        except KeyboardInterrupt:
            print("\n\nInterrupted")
        finally:
            self.disconnect()


def main():
    """Entry point."""
    app = SuperSensorCLI()
    app.run()


if __name__ == '__main__':
    main()
