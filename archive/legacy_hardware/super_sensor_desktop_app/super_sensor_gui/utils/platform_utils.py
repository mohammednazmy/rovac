"""Platform-specific utilities for Super Sensor GUI."""

import os
import sys
import platform
import subprocess
import shutil
import tempfile
import zipfile
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Tuple, Callable
from pathlib import Path


def get_embedded_resources_dir() -> Path:
    """Get the embedded resources directory (works for both dev and bundled app)."""
    # When running as bundled app, resources are in _MEIPASS
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / 'embedded_resources'
    # When running in development
    return Path(__file__).parent.parent / 'embedded_resources'


class PlatformUtils:
    """Cross-platform utility functions."""

    @staticmethod
    def get_platform() -> str:
        """Get current platform: 'macos', 'linux', or 'windows'."""
        system = platform.system().lower()
        if system == 'darwin':
            return 'macos'
        elif system == 'linux':
            return 'linux'
        elif system == 'windows':
            return 'windows'
        return system

    @staticmethod
    def get_platform_info() -> Dict[str, str]:
        """Get detailed platform information."""
        return {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'python_version': platform.python_version(),
            'python_path': sys.executable,
        }

    @staticmethod
    def is_pyserial_installed() -> bool:
        """Check if pyserial is installed."""
        try:
            import serial
            return True
        except ImportError:
            return False

    @staticmethod
    def get_pyserial_version() -> Optional[str]:
        """Get pyserial version if installed."""
        try:
            import serial
            return serial.__version__
        except (ImportError, AttributeError):
            return None

    @staticmethod
    def install_pyserial(
        log_callback: Optional[Callable[[str], None]] = None
    ) -> Tuple[bool, str]:
        """
        Install pyserial with online/offline fallback.

        Args:
            log_callback: Optional callback for progress messages

        Returns:
            Tuple of (success, message)
        """
        def log(msg: str):
            if log_callback:
                log_callback(msg)

        # Check if already installed
        if PlatformUtils.is_pyserial_installed():
            version = PlatformUtils.get_pyserial_version()
            return True, f"pyserial is already installed (version {version})"

        # Try online installation first
        log("Attempting online installation...")
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', 'pyserial', '--quiet'],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                # Verify installation
                if PlatformUtils.is_pyserial_installed():
                    version = PlatformUtils.get_pyserial_version()
                    return True, f"pyserial {version} installed successfully (online)"
        except subprocess.TimeoutExpired:
            log("Online installation timed out, trying offline...")
        except Exception as e:
            log(f"Online installation failed: {e}")

        # Try offline installation from embedded wheel
        log("Attempting offline installation from bundled package...")
        resources_dir = get_embedded_resources_dir()
        wheel_files = list(resources_dir.glob('pyserial-*.whl'))

        if not wheel_files:
            return False, "No bundled pyserial wheel found and online installation failed"

        wheel_path = wheel_files[0]
        log(f"Found bundled wheel: {wheel_path.name}")

        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', str(wheel_path), '--quiet'],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                if PlatformUtils.is_pyserial_installed():
                    version = PlatformUtils.get_pyserial_version()
                    return True, f"pyserial {version} installed successfully (offline)"
                return False, "Installation completed but pyserial not importable"
            return False, f"Offline installation failed: {result.stderr}"
        except subprocess.TimeoutExpired:
            return False, "Installation timed out"
        except Exception as e:
            return False, f"Installation failed: {str(e)}"

    @staticmethod
    def is_arduino_cli_installed() -> bool:
        """Check if arduino-cli is installed."""
        return shutil.which('arduino-cli') is not None

    @staticmethod
    def get_arduino_cli_path() -> Optional[str]:
        """Get path to arduino-cli."""
        return shutil.which('arduino-cli')

    @staticmethod
    def is_ch340_driver_installed() -> bool:
        """Check if CH340 driver is installed (macOS only)."""
        if PlatformUtils.get_platform() != 'macos':
            return True  # Not applicable on other platforms

        try:
            # Check for the driver extension
            result = subprocess.run(
                ['systemextensionsctl', 'list'],
                capture_output=True,
                text=True
            )
            if 'CH34' in result.stdout or 'wch' in result.stdout.lower():
                return True
        except Exception:
            pass

        # Alternative check - look for the kext or driver
        driver_paths = [
            '/Library/Extensions/usbserial.kext',
            '/Library/Extensions/CH34xVCPDriver.kext',
            '/Library/Extensions/CH341SER_MAC.kext',
        ]
        if any(os.path.exists(p) for p in driver_paths):
            return True

        # Check if CH340 device is already recognized (driver working)
        try:
            result = subprocess.run(
                ['system_profiler', 'SPUSBDataType'],
                capture_output=True,
                text=True,
                timeout=10
            )
            # If we can see CH340 in USB list and have serial ports, driver is working
            if 'CH340' in result.stdout or '1a86' in result.stdout:
                # Check if there's a corresponding serial port
                import serial.tools.list_ports
                for port in serial.tools.list_ports.comports():
                    if port.vid == 0x1a86:
                        return True
        except Exception:
            pass

        return False

    @staticmethod
    def install_ch340_driver(
        log_callback: Optional[Callable[[str], None]] = None
    ) -> Tuple[bool, str]:
        """
        Install CH340 driver on macOS from embedded package.

        Args:
            log_callback: Optional callback for progress messages

        Returns:
            Tuple of (success, message)
        """
        def log(msg: str):
            if log_callback:
                log_callback(msg)

        if PlatformUtils.get_platform() != 'macos':
            return False, "CH340 driver installation is only needed on macOS"

        # Check if already installed
        if PlatformUtils.is_ch340_driver_installed():
            return True, "CH340 driver is already installed"

        # Find the embedded driver package
        resources_dir = get_embedded_resources_dir()
        driver_zip = resources_dir / 'CH341SER_MAC.ZIP'

        if not driver_zip.exists():
            return False, "CH340 driver package not found. Please download from https://www.wch-ic.com/downloads/CH341SER_MAC_ZIP.html"

        log(f"Found driver package: {driver_zip.name}")

        # Extract to temp directory
        temp_dir = Path(tempfile.mkdtemp(prefix='ch340_driver_'))
        try:
            log("Extracting driver package...")
            with zipfile.ZipFile(driver_zip, 'r') as zf:
                zf.extractall(temp_dir)

            # Find the .pkg installer
            pkg_files = list(temp_dir.rglob('*.pkg'))
            if not pkg_files:
                return False, "No .pkg installer found in driver package"

            pkg_path = pkg_files[0]
            log(f"Found installer: {pkg_path.name}")

            # Open the installer (requires user interaction)
            log("Opening driver installer...")
            log("Please follow the installation prompts in the installer window.")
            log("You may need to approve the system extension in System Preferences.")

            result = subprocess.run(
                ['open', str(pkg_path)],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                return False, f"Failed to open installer: {result.stderr}"

            return True, (
                "Driver installer opened. Please complete the installation:\n"
                "1. Follow the installer prompts\n"
                "2. Go to System Preferences > Security & Privacy > General\n"
                "3. Approve the system extension if prompted\n"
                "4. Restart your computer if required"
            )

        except zipfile.BadZipFile:
            return False, "Driver package is corrupted"
        except Exception as e:
            return False, f"Failed to install driver: {str(e)}"
        finally:
            # Note: Don't clean up temp_dir immediately as the installer needs it
            pass

    @staticmethod
    def is_user_in_dialout_group() -> bool:
        """Check if user is in dialout group (Linux only)."""
        if PlatformUtils.get_platform() != 'linux':
            return True  # Not applicable on other platforms

        try:
            result = subprocess.run(['groups'], capture_output=True, text=True)
            groups = result.stdout.strip().split()
            return 'dialout' in groups
        except Exception:
            return False

    @staticmethod
    def is_udev_rule_installed() -> bool:
        """Check if udev rule is installed (Linux only)."""
        if PlatformUtils.get_platform() != 'linux':
            return True  # Not applicable on other platforms

        udev_paths = [
            '/etc/udev/rules.d/99-super-sensor.rules',
            '/lib/udev/rules.d/99-super-sensor.rules',
        ]
        return any(os.path.exists(p) for p in udev_paths)

    @staticmethod
    def get_udev_rule_content() -> str:
        """Get content for udev rules file."""
        return '''# Super Sensor Module USB Serial
# CH340 USB-Serial adapter
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="super_sensor", MODE="0666", GROUP="dialout"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5523", SYMLINK+="super_sensor", MODE="0666", GROUP="dialout"
'''

    @staticmethod
    def install_udev_rule() -> Tuple[bool, str]:
        """Install udev rule (requires sudo on Linux)."""
        if PlatformUtils.get_platform() != 'linux':
            return False, "udev rules are only applicable on Linux"

        rule_content = PlatformUtils.get_udev_rule_content()
        rule_path = '/etc/udev/rules.d/99-super-sensor.rules'

        try:
            # Write to temp file first
            temp_path = '/tmp/99-super-sensor.rules'
            with open(temp_path, 'w') as f:
                f.write(rule_content)

            # Use pkexec or sudo to copy
            copy_cmd = ['sudo', 'cp', temp_path, rule_path]
            result = subprocess.run(copy_cmd, capture_output=True, text=True)

            if result.returncode != 0:
                return False, f"Failed to copy rule: {result.stderr}"

            # Reload udev rules
            subprocess.run(['sudo', 'udevadm', 'control', '--reload-rules'])
            subprocess.run(['sudo', 'udevadm', 'trigger'])

            return True, "udev rule installed successfully"

        except Exception as e:
            return False, str(e)

    @staticmethod
    def add_user_to_dialout() -> Tuple[bool, str]:
        """Add current user to dialout group (Linux only)."""
        if PlatformUtils.get_platform() != 'linux':
            return False, "Only applicable on Linux"

        try:
            username = os.environ.get('USER', os.environ.get('LOGNAME'))
            result = subprocess.run(
                ['sudo', 'usermod', '-a', '-G', 'dialout', username],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return True, f"Added {username} to dialout group. Please log out and back in."
            return False, result.stderr
        except Exception as e:
            return False, str(e)

    @staticmethod
    def get_serial_ports() -> List[Dict[str, str]]:
        """Get list of available serial ports."""
        ports = []
        try:
            import serial.tools.list_ports
            for port in serial.tools.list_ports.comports():
                ports.append({
                    'device': port.device,
                    'description': port.description or '',
                    'hwid': port.hwid or '',
                    'vid': f'{port.vid:04x}' if port.vid else '',
                    'pid': f'{port.pid:04x}' if port.pid else '',
                    'manufacturer': port.manufacturer or '',
                })
        except ImportError:
            pass
        return ports

    @staticmethod
    def find_super_sensor_port() -> Optional[str]:
        """Find the Super Sensor port (looks for CH340 devices)."""
        try:
            import serial.tools.list_ports
            for port in serial.tools.list_ports.comports():
                # Check for CH340 VID:PID
                if port.vid == 0x1a86 and port.pid in [0x7523, 0x5523]:
                    return port.device
                # Check description
                desc = (port.description or '').lower()
                if 'ch340' in desc or 'wchusbserial' in port.device.lower():
                    return port.device
            # Fallback: check for common patterns
            for port in serial.tools.list_ports.comports():
                if 'usbserial' in port.device.lower() or 'ttyUSB' in port.device:
                    return port.device
        except ImportError:
            pass
        return None

    @staticmethod
    def get_app_data_dir() -> Path:
        """Get application data directory."""
        plat = PlatformUtils.get_platform()
        if plat == 'macos':
            base = Path.home() / 'Library' / 'Application Support'
        elif plat == 'linux':
            base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
        else:
            base = Path.home()

        app_dir = base / 'SuperSensor'
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir

    @staticmethod
    def get_config_dir() -> Path:
        """Get configuration directory."""
        plat = PlatformUtils.get_platform()
        if plat == 'macos':
            base = Path.home() / 'Library' / 'Preferences'
        elif plat == 'linux':
            base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
        else:
            base = Path.home()

        config_dir = base / 'SuperSensor'
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir
