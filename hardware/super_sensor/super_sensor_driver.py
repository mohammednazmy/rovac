#!/usr/bin/env python3
"""
Super Sensor Module Python Driver

Provides a clean interface to communicate with the Super Sensor Arduino
over USB serial. Designed for robotics applications.

Usage:
    from super_sensor_driver import SuperSensor

    sensor = SuperSensor('/dev/ttyUSB0')  # or 'COM3' on Windows
    sensor.connect()

    # Read all ultrasonic sensors
    distances = sensor.scan()
    print(f"Front-Left: {distances['front_left']} cm")

    # Control RGB LED
    sensor.set_led(255, 0, 0)  # Red

    # Control servo
    sensor.set_servo(90)

    # Get full status
    status = sensor.status()

    # Sweep scan
    sweep_data = sensor.sweep(0, 180)

    sensor.disconnect()

Author: ROVAC Project
License: MIT
"""

import json
import time
import serial
import serial.tools.list_ports
from typing import Optional, Dict, List, Any
from dataclasses import dataclass


@dataclass
class ScanResult:
    """
    Result from ultrasonic scan.

    Physical sensor orientation:
    - front_left (front_top): Forward-facing sensor at TOP of module
    - front_right (front_bottom): Forward-facing sensor at BOTTOM of module
    - left: Side-facing sensor pointing LEFT
    - right: Side-facing sensor pointing RIGHT

    Note: The 'front_left' and 'front_right' names are legacy from the firmware.
    Use the alias properties 'front_top' and 'front_bottom' for clarity.
    """
    front_left: int    # Forward-facing, top of module (legacy name)
    front_right: int   # Forward-facing, bottom of module (legacy name)
    left: int          # Side-facing, pointing left
    right: int         # Side-facing, pointing right
    timestamp: float

    # Alias properties for clearer naming
    @property
    def front_top(self) -> int:
        """Forward-facing sensor at top of module."""
        return self.front_left

    @property
    def front_bottom(self) -> int:
        """Forward-facing sensor at bottom of module."""
        return self.front_right

    def to_dict(self) -> Dict[str, int]:
        return {
            'front_top': self.front_left,
            'front_bottom': self.front_right,
            'left': self.left,
            'right': self.right,
        }

    @property
    def min_distance(self) -> int:
        """Return minimum valid distance from all sensors."""
        valid = [d for d in [self.front_left, self.front_right, self.left, self.right] if d > 0]
        return min(valid) if valid else -1

    @property
    def has_obstacle(self) -> bool:
        """Check if any sensor detects an obstacle within 30cm."""
        return self.min_distance > 0 and self.min_distance < 30


class SuperSensor:
    """
    Driver for the Super Sensor Module.

    Communicates with an Arduino Nano running the super_sensor firmware
    over USB serial.
    """

    BAUD_RATE = 115200
    TIMEOUT = 2.0  # seconds

    def __init__(self, port: Optional[str] = None):
        """
        Initialize the Super Sensor driver.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0', 'COM3').
                  If None, will attempt auto-detection.
        """
        self.port = port
        self.serial: Optional[serial.Serial] = None
        self._connected = False

    @staticmethod
    def find_ports() -> List[str]:
        """
        Find available serial ports that might be Arduino devices.

        Returns:
            List of port paths that could be Arduino devices.
        """
        arduino_identifiers = ['arduino', 'ch340', 'cp210', 'ftdi', 'usb serial']
        ports = []

        for port in serial.tools.list_ports.comports():
            desc = (port.description or '').lower()
            manufacturer = (port.manufacturer or '').lower()

            if any(ident in desc or ident in manufacturer for ident in arduino_identifiers):
                ports.append(port.device)

        # Also include common Arduino port patterns
        common_patterns = ['/dev/ttyUSB', '/dev/ttyACM', '/dev/cu.usbserial', '/dev/cu.usbmodem', '/dev/cu.wchusbserial']
        for port in serial.tools.list_ports.comports():
            if any(port.device.startswith(p) for p in common_patterns):
                if port.device not in ports:
                    ports.append(port.device)

        return sorted(ports)

    def connect(self) -> bool:
        """
        Connect to the Super Sensor.

        Returns:
            True if connection successful, False otherwise.
        """
        if self._connected:
            return True

        # Auto-detect port if not specified
        if self.port is None:
            ports = self.find_ports()
            if not ports:
                raise ConnectionError("No Arduino devices found. Please specify port manually.")
            self.port = ports[0]
            print(f"Auto-detected port: {self.port}")

        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.BAUD_RATE,
                timeout=self.TIMEOUT
            )

            # Wait for Arduino to reset after serial connection
            # CH340-based Nanos need ~3 seconds after reset
            time.sleep(3.0)

            # Clear any startup messages
            self.serial.reset_input_buffer()

            # Verify connection with ping
            if self.ping():
                self._connected = True
                return True
            else:
                self.serial.close()
                raise ConnectionError("Device did not respond to ping")

        except serial.SerialException as e:
            raise ConnectionError(f"Failed to connect to {self.port}: {e}")

    def disconnect(self):
        """Disconnect from the Super Sensor."""
        if self.serial and self.serial.is_open:
            self.serial.close()
        self._connected = False

    def _send_command(self, command: str) -> str:
        """
        Send a command and receive response.

        Args:
            command: Command string to send.

        Returns:
            Response string from device.
        """
        if not self._connected or not self.serial:
            raise ConnectionError("Not connected to device")

        # Clear input buffer
        self.serial.reset_input_buffer()

        # Send command with newline
        self.serial.write(f"{command}\n".encode())
        self.serial.flush()

        # Read response (single line)
        response = self.serial.readline().decode().strip()
        return response

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response, handling errors."""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON response: {response}")

    def ping(self) -> bool:
        """
        Check if device is responding.

        Returns:
            True if device responds with PONG.
        """
        try:
            if not self.serial or not self.serial.is_open:
                return False

            # Clear input buffer
            self.serial.reset_input_buffer()

            # Send ping
            self.serial.write(b"PING\n")
            self.serial.flush()

            # Read response
            response = self.serial.readline().decode().strip()
            return response == "PONG"
        except Exception:
            return False

    def scan(self) -> ScanResult:
        """
        Read all ultrasonic sensors.

        Returns:
            ScanResult with distances in cm (-1 = no reading).
        """
        response = self._send_command("SCAN")
        data = self._parse_json_response(response)

        if 'us' not in data:
            raise ValueError(f"Invalid scan response: {response}")

        us = data['us']
        return ScanResult(
            front_left=us[0],
            front_right=us[1],
            left=us[2],
            right=us[3],
            timestamp=time.time()
        )

    def set_led(self, r: int, g: int, b: int) -> Dict[str, List[int]]:
        """
        Set RGB LED color.

        Args:
            r: Red value (0-255)
            g: Green value (0-255)
            b: Blue value (0-255)

        Returns:
            Dict with confirmed LED values.
        """
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))

        response = self._send_command(f"LED {r} {g} {b}")
        return self._parse_json_response(response)

    def set_servo(self, angle: int) -> Dict[str, int]:
        """
        Set servo angle.

        Args:
            angle: Servo angle (0-180 degrees)

        Returns:
            Dict with confirmed servo angle.
        """
        angle = max(0, min(180, angle))

        response = self._send_command(f"SERVO {angle}")
        return self._parse_json_response(response)

    def status(self) -> Dict[str, Any]:
        """
        Get full system status.

        Returns:
            Dict with all sensor readings and actuator states.
        """
        response = self._send_command("STATUS")
        return self._parse_json_response(response)

    def sweep(self, start_angle: int = 0, end_angle: int = 180) -> List[Dict[str, Any]]:
        """
        Perform a sweep scan - move servo and scan at each position.

        Args:
            start_angle: Starting servo angle (0-180)
            end_angle: Ending servo angle (0-180)

        Returns:
            List of readings at each angle position.
        """
        response = self._send_command(f"SWEEP {start_angle} {end_angle}")
        data = self._parse_json_response(response)

        if 'sweep' not in data:
            raise ValueError(f"Invalid sweep response: {response}")

        return data['sweep']

    # Convenience methods for common LED colors
    def led_off(self):
        """Turn off LED."""
        return self.set_led(0, 0, 0)

    def led_red(self, brightness: int = 255):
        """Set LED to red."""
        return self.set_led(brightness, 0, 0)

    def led_green(self, brightness: int = 255):
        """Set LED to green."""
        return self.set_led(0, brightness, 0)

    def led_blue(self, brightness: int = 255):
        """Set LED to blue."""
        return self.set_led(0, 0, brightness)

    def led_white(self, brightness: int = 255):
        """Set LED to white."""
        return self.set_led(brightness, brightness, brightness)

    def led_yellow(self, brightness: int = 255):
        """Set LED to yellow."""
        return self.set_led(brightness, brightness, 0)

    def led_cyan(self, brightness: int = 255):
        """Set LED to cyan."""
        return self.set_led(0, brightness, brightness)

    def led_magenta(self, brightness: int = 255):
        """Set LED to magenta."""
        return self.set_led(brightness, 0, brightness)

    # Context manager support
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """Command-line interface for testing the Super Sensor."""
    import argparse

    parser = argparse.ArgumentParser(description='Super Sensor Module CLI')
    parser.add_argument('-p', '--port', help='Serial port (auto-detect if not specified)')
    parser.add_argument('--list-ports', action='store_true', help='List available serial ports')

    subparsers = parser.add_subparsers(dest='command', help='Command')

    # Scan command
    subparsers.add_parser('scan', help='Read all ultrasonic sensors')

    # LED command
    led_parser = subparsers.add_parser('led', help='Set RGB LED')
    led_parser.add_argument('r', type=int, help='Red (0-255)')
    led_parser.add_argument('g', type=int, help='Green (0-255)')
    led_parser.add_argument('b', type=int, help='Blue (0-255)')

    # Servo command
    servo_parser = subparsers.add_parser('servo', help='Set servo angle')
    servo_parser.add_argument('angle', type=int, help='Angle (0-180)')

    # Status command
    subparsers.add_parser('status', help='Get full status')

    # Sweep command
    sweep_parser = subparsers.add_parser('sweep', help='Sweep scan')
    sweep_parser.add_argument('--start', type=int, default=0, help='Start angle')
    sweep_parser.add_argument('--end', type=int, default=180, help='End angle')

    # Interactive command
    subparsers.add_parser('interactive', help='Interactive mode')

    args = parser.parse_args()

    # List ports
    if args.list_ports:
        ports = SuperSensor.find_ports()
        if ports:
            print("Available ports:")
            for port in ports:
                print(f"  {port}")
        else:
            print("No Arduino-like devices found")
        return

    if not args.command:
        parser.print_help()
        return

    # Execute commands
    try:
        with SuperSensor(args.port) as sensor:
            if args.command == 'scan':
                result = sensor.scan()
                print(f"Front-Left:  {result.front_left:4d} cm")
                print(f"Front-Right: {result.front_right:4d} cm")
                print(f"Left:        {result.left:4d} cm")
                print(f"Right:       {result.right:4d} cm")

            elif args.command == 'led':
                result = sensor.set_led(args.r, args.g, args.b)
                print(f"LED set to: R={result['led'][0]}, G={result['led'][1]}, B={result['led'][2]}")

            elif args.command == 'servo':
                result = sensor.set_servo(args.angle)
                print(f"Servo angle: {result['servo']}°")

            elif args.command == 'status':
                result = sensor.status()
                print(json.dumps(result, indent=2))

            elif args.command == 'sweep':
                result = sensor.sweep(args.start, args.end)
                print("Sweep results:")
                for reading in result:
                    print(f"  {reading['angle']:3d}°: FL={reading['us'][0]:4d}, FR={reading['us'][1]:4d}, L={reading['us'][2]:4d}, R={reading['us'][3]:4d}")

            elif args.command == 'interactive':
                print("Interactive mode. Type 'help' for commands, 'quit' to exit.")
                while True:
                    try:
                        cmd = input("> ").strip()
                        if cmd.lower() in ('quit', 'exit', 'q'):
                            break
                        elif cmd.lower() == 'help':
                            print("Commands: scan, led R G B, servo ANGLE, status, sweep START END, quit")
                        elif cmd:
                            response = sensor._send_command(cmd)
                            print(response)
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        print(f"Error: {e}")

    except ConnectionError as e:
        print(f"Connection error: {e}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == '__main__':
    main()
