"""Arduino CLI utilities for firmware upload."""

import os
import subprocess
import shutil
from typing import Tuple, Optional, Callable
from pathlib import Path

try:
    from .platform_utils import PlatformUtils
except ImportError:
    from platform_utils import PlatformUtils


class ArduinoUtils:
    """Utilities for Arduino CLI operations."""

    # Board FQBNs
    NANO_NEW_BOOTLOADER = "arduino:avr:nano:cpu=atmega328"
    NANO_OLD_BOOTLOADER = "arduino:avr:nano:cpu=atmega328old"

    BOARD_OPTIONS = [
        ("Arduino Nano (ATmega328P)", NANO_NEW_BOOTLOADER),
        ("Arduino Nano (ATmega328P Old Bootloader)", NANO_OLD_BOOTLOADER),
    ]

    # Common installation paths for arduino-cli
    COMMON_PATHS = [
        '/opt/homebrew/bin/arduino-cli',      # macOS Homebrew (Apple Silicon)
        '/usr/local/bin/arduino-cli',          # macOS Homebrew (Intel) / Linux
        os.path.expanduser('~/.local/bin/arduino-cli'),  # Linux user install
        '/usr/bin/arduino-cli',                # Linux system install
    ]

    @staticmethod
    def find_arduino_cli() -> Optional[str]:
        """Find arduino-cli executable, checking PATH and common locations."""
        # First try PATH
        path_result = shutil.which('arduino-cli')
        if path_result:
            return path_result

        # Check common installation paths
        for path in ArduinoUtils.COMMON_PATHS:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        return None

    @staticmethod
    def get_firmware_path() -> Optional[Path]:
        """Get path to firmware directory."""
        # Look relative to this file
        base = Path(__file__).parent.parent.parent
        firmware_path = base / "firmware" / "super_sensor"

        if firmware_path.exists():
            return firmware_path

        # Also check for bundled firmware in app resources
        if hasattr(ArduinoUtils, '_bundled_firmware_path'):
            return ArduinoUtils._bundled_firmware_path

        return None

    @staticmethod
    def is_arduino_cli_installed() -> bool:
        """Check if arduino-cli is available."""
        return ArduinoUtils.find_arduino_cli() is not None

    @staticmethod
    def get_arduino_cli_version() -> Optional[str]:
        """Get arduino-cli version."""
        cli_path = ArduinoUtils.find_arduino_cli()
        if not cli_path:
            return None

        try:
            result = subprocess.run(
                [cli_path, 'version'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Parse version from output
                output = result.stdout.strip()
                if 'Version:' in output:
                    return output.split('Version:')[1].split()[0]
                return output.split()[0] if output else None
        except Exception:
            pass
        return None

    @staticmethod
    def install_arduino_cli(log_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Install arduino-cli using appropriate method for platform."""
        def log(msg: str):
            if log_callback:
                log_callback(msg)

        platform = PlatformUtils.get_platform()

        if platform == 'macos':
            # Use Homebrew
            if shutil.which('brew'):
                log("Installing arduino-cli via Homebrew...")
                try:
                    result = subprocess.run(
                        ['brew', 'install', 'arduino-cli'],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        return True, "arduino-cli installed successfully"
                    return False, result.stderr
                except Exception as e:
                    return False, str(e)
            else:
                return False, "Homebrew not found. Please install Homebrew first: https://brew.sh"

        elif platform == 'linux':
            # Use curl install script
            log("Installing arduino-cli...")
            try:
                result = subprocess.run(
                    ['bash', '-c', 'curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=~/.local/bin sh'],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    return True, "arduino-cli installed to ~/.local/bin"
                return False, result.stderr
            except Exception as e:
                return False, str(e)

        return False, f"Unsupported platform: {platform}"

    @staticmethod
    def is_avr_core_installed() -> bool:
        """Check if Arduino AVR core is installed."""
        cli_path = ArduinoUtils.find_arduino_cli()
        if not cli_path:
            return False

        try:
            result = subprocess.run(
                [cli_path, 'core', 'list'],
                capture_output=True,
                text=True
            )
            return 'arduino:avr' in result.stdout
        except Exception:
            return False

    @staticmethod
    def install_avr_core(log_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Install Arduino AVR core."""
        def log(msg: str):
            if log_callback:
                log_callback(msg)

        cli_path = ArduinoUtils.find_arduino_cli()
        if not cli_path:
            return False, "arduino-cli not found"

        try:
            log("Updating core index...")
            subprocess.run(
                [cli_path, 'core', 'update-index'],
                capture_output=True
            )

            log("Installing arduino:avr core...")
            result = subprocess.run(
                [cli_path, 'core', 'install', 'arduino:avr'],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                return True, "Arduino AVR core installed"
            return False, result.stderr

        except Exception as e:
            return False, str(e)

    @staticmethod
    def is_servo_library_installed() -> bool:
        """Check if Servo library is installed."""
        cli_path = ArduinoUtils.find_arduino_cli()
        if not cli_path:
            return False

        try:
            result = subprocess.run(
                [cli_path, 'lib', 'list'],
                capture_output=True,
                text=True
            )
            return 'Servo' in result.stdout
        except Exception:
            return False

    @staticmethod
    def install_servo_library(log_callback: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
        """Install Servo library."""
        def log(msg: str):
            if log_callback:
                log_callback(msg)

        cli_path = ArduinoUtils.find_arduino_cli()
        if not cli_path:
            return False, "arduino-cli not found"

        try:
            log("Installing Servo library...")
            result = subprocess.run(
                [cli_path, 'lib', 'install', 'Servo'],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                return True, "Servo library installed"
            return False, result.stderr

        except Exception as e:
            return False, str(e)

    @staticmethod
    def compile_firmware(
        board_fqbn: str,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> Tuple[bool, str]:
        """Compile the firmware."""
        def log(msg: str):
            if log_callback:
                log_callback(msg)

        cli_path = ArduinoUtils.find_arduino_cli()
        if not cli_path:
            return False, "arduino-cli not found"

        firmware_path = ArduinoUtils.get_firmware_path()
        if not firmware_path:
            return False, "Firmware not found"

        log(f"Compiling firmware for {board_fqbn}...")

        try:
            result = subprocess.run(
                [cli_path, 'compile', '--fqbn', board_fqbn, str(firmware_path)],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # Parse size info
                for line in result.stdout.split('\n'):
                    if 'Sketch uses' in line or 'Global variables' in line:
                        log(line)
                return True, "Compilation successful"

            return False, result.stderr

        except Exception as e:
            return False, str(e)

    @staticmethod
    def upload_firmware(
        port: str,
        board_fqbn: str,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> Tuple[bool, str]:
        """Upload firmware to Arduino."""
        def log(msg: str):
            if log_callback:
                log_callback(msg)

        firmware_path = ArduinoUtils.get_firmware_path()
        if not firmware_path:
            return False, "Firmware not found"

        # Check prerequisites
        if not ArduinoUtils.is_arduino_cli_installed():
            log("arduino-cli not found, attempting to install...")
            success, msg = ArduinoUtils.install_arduino_cli(log_callback)
            if not success:
                return False, f"Failed to install arduino-cli: {msg}"

        cli_path = ArduinoUtils.find_arduino_cli()
        if not cli_path:
            return False, "arduino-cli not found after installation"

        if not ArduinoUtils.is_avr_core_installed():
            log("Arduino AVR core not found, installing...")
            success, msg = ArduinoUtils.install_avr_core(log_callback)
            if not success:
                return False, f"Failed to install AVR core: {msg}"

        if not ArduinoUtils.is_servo_library_installed():
            log("Servo library not found, installing...")
            success, msg = ArduinoUtils.install_servo_library(log_callback)
            if not success:
                return False, f"Failed to install Servo library: {msg}"

        # Compile
        success, msg = ArduinoUtils.compile_firmware(board_fqbn, log_callback)
        if not success:
            return False, f"Compilation failed: {msg}"

        # Upload
        log(f"Uploading to {port}...")

        try:
            result = subprocess.run(
                [cli_path, 'upload', '-p', port, '--fqbn', board_fqbn, str(firmware_path)],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                log("Upload successful!")
                return True, "Firmware uploaded successfully"

            # Check for common errors
            if 'not in sync' in result.stderr:
                return False, "Upload failed: Try selecting 'Old Bootloader' option"

            return False, result.stderr

        except subprocess.TimeoutExpired:
            return False, "Upload timed out"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def list_boards() -> list:
        """List connected Arduino boards."""
        cli_path = ArduinoUtils.find_arduino_cli()
        if not cli_path:
            return []

        try:
            result = subprocess.run(
                [cli_path, 'board', 'list'],
                capture_output=True,
                text=True
            )
            # Parse output
            boards = []
            for line in result.stdout.split('\n')[1:]:  # Skip header
                if line.strip():
                    parts = line.split()
                    if parts:
                        boards.append({
                            'port': parts[0],
                            'type': ' '.join(parts[1:]) if len(parts) > 1 else 'Unknown'
                        })
            return boards
        except Exception:
            return []
