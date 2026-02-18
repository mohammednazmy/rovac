#!/usr/bin/env python3
"""
Linux setup utilities for Super Sensor CLI.

Handles:
- udev rules installation for USB device permissions
- dialout group membership
- arduino-cli installation (supports offline installation)
- Firmware upload

Offline Installation:
    If offline_deps/ directory exists with bundled dependencies,
    installation can proceed without internet access.
"""

import os
import sys
import subprocess
import shutil
import pwd
import grp
import platform
import tarfile
from pathlib import Path
from typing import Tuple, Optional, Callable


class LinuxSetup:
    """Linux-specific setup and installation utilities."""

    # udev rules for Super Sensor (CH340/CH341 USB-Serial)
    UDEV_RULES = """# Super Sensor USB Serial (CH340/CH341)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666", SYMLINK+="super_sensor"
# FTDI USB Serial
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", MODE="0666"
# Arduino
SUBSYSTEM=="tty", ATTRS{idVendor}=="2341", MODE="0666"
"""

    UDEV_RULES_PATH = "/etc/udev/rules.d/99-super-sensor.rules"

    # Common arduino-cli paths
    ARDUINO_CLI_PATHS = [
        '/usr/local/bin/arduino-cli',
        '/usr/bin/arduino-cli',
        str(Path.home() / '.local' / 'bin' / 'arduino-cli'),
        str(Path.home() / 'bin' / 'arduino-cli'),
    ]

    def __init__(self, cli_app):
        self.cli = cli_app
        # Path to offline dependencies (bundled with the app)
        self.offline_deps_path = Path(__file__).parent.parent / 'offline_deps'

    def get_offline_deps_path(self) -> Optional[Path]:
        """Get path to offline dependencies if available."""
        if self.offline_deps_path.exists():
            return self.offline_deps_path
        return None

    def has_offline_deps(self) -> bool:
        """Check if offline dependencies are available."""
        return self.offline_deps_path.exists()

    def menu(self):
        """Show setup menu."""
        while True:
            self.cli.clear_screen()
            self.cli.print_header("SETUP & INSTALL")

            # Check status
            self._show_status()

            # Show offline mode indicator
            if self.has_offline_deps():
                print(f"{self.cli.Colors.GREEN}[Offline installation available]{self.cli.Colors.RESET}\n")

            options = [
                ('1', 'Install udev rules (requires sudo)'),
                ('2', 'Add user to dialout group (requires sudo)'),
                ('3', 'Install pyserial'),
                ('4', 'Install arduino-cli'),
                ('5', 'Install Arduino AVR core'),
                ('6', 'Upload firmware'),
                ('7', 'Check all requirements'),
                ('b', 'Back'),
            ]

            self.cli.print_menu(options)
            choice = self.cli.get_input().lower()

            if choice == '1':
                self.install_udev_rules()
            elif choice == '2':
                self.add_to_dialout()
            elif choice == '3':
                self.install_pyserial()
            elif choice == '4':
                self.install_arduino_cli()
            elif choice == '5':
                self.install_avr_core()
            elif choice == '6':
                self.upload_firmware_menu()
            elif choice == '7':
                self.check_all_requirements()
            elif choice == 'b':
                break

    def _show_status(self):
        """Show current setup status."""
        print(f"{self.cli.Colors.BOLD}System Status:{self.cli.Colors.RESET}\n")

        # Platform
        import platform
        self.cli.print_status("Platform", platform.system())
        self.cli.print_status("Architecture", platform.machine())

        # Python
        self.cli.print_status("Python", sys.version.split()[0])

        # pyserial
        try:
            import serial
            self.cli.print_status("pyserial", serial.__version__, self.cli.Colors.GREEN)
        except ImportError:
            self.cli.print_status("pyserial", "Not installed", self.cli.Colors.RED)

        # udev rules
        if self.check_udev_rules():
            self.cli.print_status("udev rules", "Installed", self.cli.Colors.GREEN)
        else:
            self.cli.print_status("udev rules", "Not installed", self.cli.Colors.YELLOW)

        # dialout group
        if self.check_dialout_membership():
            self.cli.print_status("dialout group", "Member", self.cli.Colors.GREEN)
        else:
            self.cli.print_status("dialout group", "Not member", self.cli.Colors.YELLOW)

        # arduino-cli
        cli_path = self.find_arduino_cli()
        if cli_path:
            version = self.get_arduino_cli_version()
            self.cli.print_status("arduino-cli", version or "Installed", self.cli.Colors.GREEN)
        else:
            self.cli.print_status("arduino-cli", "Not installed", self.cli.Colors.YELLOW)

        # AVR core
        if cli_path and self.check_avr_core():
            self.cli.print_status("AVR core", "Installed", self.cli.Colors.GREEN)
        else:
            self.cli.print_status("AVR core", "Not installed", self.cli.Colors.YELLOW)

        print()

    # ==================== udev Rules ====================

    def check_udev_rules(self) -> bool:
        """Check if udev rules are installed."""
        return Path(self.UDEV_RULES_PATH).exists()

    def install_udev_rules(self):
        """Install udev rules for USB device permissions."""
        self.cli.clear_screen()
        self.cli.print_header("INSTALL UDEV RULES")

        if self.check_udev_rules():
            self.cli.print_info("udev rules already installed")
            self.cli.wait_for_key()
            return

        print("This will install udev rules to allow non-root access to USB serial devices.")
        print(f"\nRules file: {self.UDEV_RULES_PATH}")
        print(f"\nRules content:\n{self.cli.Colors.DIM}{self.UDEV_RULES}{self.cli.Colors.RESET}")

        confirm = self.cli.get_input("\nInstall? (requires sudo) [y/N]: ").lower()
        if confirm != 'y':
            return

        # Write rules to temp file and use sudo to move
        temp_file = Path("/tmp/99-super-sensor.rules")
        try:
            temp_file.write_text(self.UDEV_RULES)

            # Use sudo to copy and reload
            result = subprocess.run(
                ['sudo', 'cp', str(temp_file), self.UDEV_RULES_PATH],
                capture_output=True, text=True
            )

            if result.returncode != 0:
                self.cli.print_error(f"Failed to copy rules: {result.stderr}")
                self.cli.wait_for_key()
                return

            # Reload udev rules
            subprocess.run(['sudo', 'udevadm', 'control', '--reload-rules'],
                          capture_output=True)
            subprocess.run(['sudo', 'udevadm', 'trigger'],
                          capture_output=True)

            temp_file.unlink()

            self.cli.print_success("udev rules installed successfully")
            self.cli.print_info("You may need to reconnect your USB device")

        except Exception as e:
            self.cli.print_error(f"Installation failed: {e}")

        self.cli.wait_for_key()

    # ==================== dialout Group ====================

    def check_dialout_membership(self) -> bool:
        """Check if current user is in dialout group."""
        try:
            username = pwd.getpwuid(os.getuid()).pw_name
            groups = [g.gr_name for g in grp.getgrall() if username in g.gr_mem]
            # Also check primary group
            primary_gid = pwd.getpwuid(os.getuid()).pw_gid
            primary_group = grp.getgrgid(primary_gid).gr_name
            groups.append(primary_group)
            return 'dialout' in groups
        except Exception:
            return False

    def add_to_dialout(self):
        """Add current user to dialout group."""
        self.cli.clear_screen()
        self.cli.print_header("ADD TO DIALOUT GROUP")

        if self.check_dialout_membership():
            self.cli.print_info("You are already a member of the dialout group")
            self.cli.wait_for_key()
            return

        username = pwd.getpwuid(os.getuid()).pw_name
        print(f"This will add user '{username}' to the 'dialout' group.")
        print("This is required for serial port access without sudo.")
        print(f"\n{self.cli.Colors.YELLOW}Note: You will need to log out and back in for this to take effect.{self.cli.Colors.RESET}")

        confirm = self.cli.get_input("\nProceed? (requires sudo) [y/N]: ").lower()
        if confirm != 'y':
            return

        try:
            result = subprocess.run(
                ['sudo', 'usermod', '-a', '-G', 'dialout', username],
                capture_output=True, text=True
            )

            if result.returncode == 0:
                self.cli.print_success(f"Added {username} to dialout group")
                self.cli.print_warning("Please log out and log back in for changes to take effect")
            else:
                self.cli.print_error(f"Failed: {result.stderr}")

        except Exception as e:
            self.cli.print_error(f"Failed: {e}")

        self.cli.wait_for_key()

    # ==================== pyserial ====================

    def check_pyserial(self) -> bool:
        """Check if pyserial is installed."""
        try:
            import serial
            return True
        except ImportError:
            return False

    def get_pyserial_version(self) -> Optional[str]:
        """Get pyserial version if installed."""
        try:
            import serial
            return serial.__version__
        except ImportError:
            return None

    def _get_pyserial_wheel(self) -> Optional[Path]:
        """Get path to bundled pyserial wheel."""
        if not self.has_offline_deps():
            return None

        pyserial_dir = self.offline_deps_path / 'pyserial'
        if not pyserial_dir.exists():
            return None

        # Find any pyserial wheel file
        wheels = list(pyserial_dir.glob('pyserial-*.whl'))
        return wheels[0] if wheels else None

    def install_pyserial(self):
        """Install pyserial (supports offline installation)."""
        self.cli.clear_screen()
        self.cli.print_header("INSTALL PYSERIAL")

        if self.check_pyserial():
            version = self.get_pyserial_version()
            self.cli.print_info(f"pyserial already installed: {version}")
            self.cli.wait_for_key()
            return

        # Check for offline wheel
        offline_wheel = self._get_pyserial_wheel()
        if offline_wheel:
            print("Found bundled pyserial (offline installation).")
            print(f"Wheel: {offline_wheel.name}")
        else:
            print("This will install pyserial using pip.")
            print("(Requires internet connection if not bundled)")

        confirm = self.cli.get_input("\nInstall? [y/N]: ").lower()
        if confirm != 'y':
            return

        if offline_wheel:
            # Offline installation from bundled wheel
            print("\nInstalling pyserial from bundled wheel...")
            try:
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '--user', str(offline_wheel)],
                    capture_output=True, text=True
                )

                if result.returncode == 0:
                    self.cli.print_success("pyserial installed successfully (offline)")
                else:
                    self.cli.print_error(f"Installation failed: {result.stderr}")

            except Exception as e:
                self.cli.print_error(f"Installation failed: {e}")
        else:
            # Online installation
            print("\nInstalling pyserial from PyPI...")
            try:
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '--user', 'pyserial'],
                    capture_output=True, text=True
                )

                if result.returncode == 0:
                    self.cli.print_success("pyserial installed successfully")
                else:
                    self.cli.print_error(f"Installation failed: {result.stderr}")

            except Exception as e:
                self.cli.print_error(f"Installation failed: {e}")

        self.cli.wait_for_key()

    # ==================== arduino-cli ====================

    def find_arduino_cli(self) -> Optional[str]:
        """Find arduino-cli executable."""
        # Check PATH first
        path_result = shutil.which('arduino-cli')
        if path_result:
            return path_result

        # Check common locations
        for path in self.ARDUINO_CLI_PATHS:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path

        return None

    def get_arduino_cli_version(self) -> Optional[str]:
        """Get arduino-cli version."""
        cli_path = self.find_arduino_cli()
        if not cli_path:
            return None

        try:
            result = subprocess.run(
                [cli_path, 'version'],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if 'Version:' in output:
                    return output.split('Version:')[1].split()[0]
                return output.split()[0] if output else None
        except Exception:
            pass
        return None

    def _get_arduino_cli_archive(self) -> Optional[Path]:
        """Get path to bundled arduino-cli archive for current architecture."""
        if not self.has_offline_deps():
            return None

        arch = platform.machine().lower()
        arduino_dir = self.offline_deps_path / 'arduino-cli'

        if arch in ('aarch64', 'arm64'):
            archive = arduino_dir / 'arduino-cli_Linux_ARM64.tar.gz'
        elif arch.startswith('arm'):
            archive = arduino_dir / 'arduino-cli_Linux_ARMv7.tar.gz'
        elif arch in ('x86_64', 'amd64'):
            archive = arduino_dir / 'arduino-cli_Linux_64bit.tar.gz'
        else:
            return None

        return archive if archive.exists() else None

    def install_arduino_cli(self):
        """Install arduino-cli (supports offline installation)."""
        self.cli.clear_screen()
        self.cli.print_header("INSTALL ARDUINO-CLI")

        existing = self.find_arduino_cli()
        if existing:
            version = self.get_arduino_cli_version()
            self.cli.print_info(f"arduino-cli already installed: {version}")
            self.cli.print_status("Path", existing)
            self.cli.wait_for_key()
            return

        # Check for offline archive
        offline_archive = self._get_arduino_cli_archive()
        if offline_archive:
            print("Found bundled arduino-cli (offline installation).")
            print(f"Archive: {offline_archive.name}")
        else:
            print("This will install arduino-cli using the official install script.")
            print("(Requires internet connection)")

        print(f"Installation directory: ~/.local/bin/")

        confirm = self.cli.get_input("\nInstall? [y/N]: ").lower()
        if confirm != 'y':
            return

        # Create ~/.local/bin if it doesn't exist
        local_bin = Path.home() / '.local' / 'bin'
        local_bin.mkdir(parents=True, exist_ok=True)

        if offline_archive:
            # Offline installation from bundled archive
            print("\nInstalling arduino-cli from bundled archive...")
            try:
                with tarfile.open(offline_archive, 'r:gz') as tar:
                    # Extract only the arduino-cli binary
                    for member in tar.getmembers():
                        if member.name == 'arduino-cli':
                            member.name = 'arduino-cli'  # Flatten path
                            tar.extract(member, local_bin)
                            break

                # Make executable
                cli_path = local_bin / 'arduino-cli'
                cli_path.chmod(0o755)

                self.cli.print_success("arduino-cli installed successfully (offline)")

            except Exception as e:
                self.cli.print_error(f"Offline installation failed: {e}")
                self.cli.wait_for_key()
                return
        else:
            # Online installation
            print("\nDownloading and installing arduino-cli...")

            try:
                # Use curl to download and run install script
                install_cmd = f'curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR={local_bin} sh'
                result = subprocess.run(
                    ['bash', '-c', install_cmd],
                    capture_output=True, text=True
                )

                if result.returncode == 0:
                    self.cli.print_success("arduino-cli installed successfully")
                else:
                    self.cli.print_error(f"Installation failed: {result.stderr}")
                    self.cli.wait_for_key()
                    return

            except Exception as e:
                self.cli.print_error(f"Installation failed: {e}")
                self.cli.wait_for_key()
                return

        # Check if ~/.local/bin is in PATH
        if str(local_bin) not in os.environ.get('PATH', ''):
            self.cli.print_warning(f"\nNote: Add {local_bin} to your PATH:")
            print(f'  echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.bashrc')
            print(f'  source ~/.bashrc')

        self.cli.wait_for_key()

    def check_avr_core(self) -> bool:
        """Check if Arduino AVR core is installed."""
        cli_path = self.find_arduino_cli()
        if not cli_path:
            return False

        try:
            result = subprocess.run(
                [cli_path, 'core', 'list'],
                capture_output=True, text=True
            )
            return 'arduino:avr' in result.stdout
        except Exception:
            return False

    def install_avr_core(self):
        """Install Arduino AVR core."""
        self.cli.clear_screen()
        self.cli.print_header("INSTALL AVR CORE")

        cli_path = self.find_arduino_cli()
        if not cli_path:
            self.cli.print_error("arduino-cli not found. Please install it first.")
            self.cli.wait_for_key()
            return

        if self.check_avr_core():
            self.cli.print_info("Arduino AVR core already installed")
            self.cli.wait_for_key()
            return

        print("Installing Arduino AVR core...")

        try:
            # Update core index
            print("Updating core index...")
            subprocess.run([cli_path, 'core', 'update-index'],
                          capture_output=True)

            # Install AVR core
            print("Installing arduino:avr...")
            result = subprocess.run(
                [cli_path, 'core', 'install', 'arduino:avr'],
                capture_output=True, text=True
            )

            if result.returncode == 0:
                self.cli.print_success("Arduino AVR core installed")
            else:
                self.cli.print_error(f"Failed: {result.stderr}")

            # Also install Servo library
            print("Installing Servo library...")
            subprocess.run(
                [cli_path, 'lib', 'install', 'Servo'],
                capture_output=True
            )

        except Exception as e:
            self.cli.print_error(f"Installation failed: {e}")

        self.cli.wait_for_key()

    # ==================== Firmware Upload ====================

    def get_firmware_path(self) -> Optional[Path]:
        """Get path to firmware directory."""
        # Look relative to this file
        base = Path(__file__).parent.parent
        firmware_path = base / "firmware" / "super_sensor"

        if firmware_path.exists():
            return firmware_path

        return None

    def upload_firmware_menu(self):
        """Firmware upload menu."""
        self.cli.clear_screen()
        self.cli.print_header("UPLOAD FIRMWARE")

        cli_path = self.find_arduino_cli()
        if not cli_path:
            self.cli.print_error("arduino-cli not found. Please install it first.")
            self.cli.wait_for_key()
            return

        firmware_path = self.get_firmware_path()
        if not firmware_path:
            self.cli.print_error("Firmware not found")
            self.cli.wait_for_key()
            return

        self.cli.print_status("Firmware", str(firmware_path))

        # Show available ports
        ports = self.cli.get_available_ports()
        print(f"\n{self.cli.Colors.BOLD}Available Ports:{self.cli.Colors.RESET}")
        for i, port in enumerate(ports):
            print(f"  {self.cli.Colors.GREEN}[{i+1}]{self.cli.Colors.RESET} {port['device']}")
            print(f"      {self.cli.Colors.DIM}{port['description']}{self.cli.Colors.RESET}")

        if not ports:
            self.cli.print_warning("No serial ports found")
            self.cli.wait_for_key()
            return

        # Select port
        port_choice = self.cli.get_input("\nSelect port (or press Enter for first): ")
        if port_choice:
            try:
                idx = int(port_choice) - 1
                if 0 <= idx < len(ports):
                    port = ports[idx]['device']
                else:
                    self.cli.print_error("Invalid selection")
                    self.cli.wait_for_key()
                    return
            except ValueError:
                port = port_choice  # Assume direct path
        else:
            port = ports[0]['device']

        # Select bootloader
        print(f"\n{self.cli.Colors.BOLD}Board Type:{self.cli.Colors.RESET}")
        print(f"  {self.cli.Colors.GREEN}[1]{self.cli.Colors.RESET} Arduino Nano (ATmega328P)")
        print(f"  {self.cli.Colors.GREEN}[2]{self.cli.Colors.RESET} Arduino Nano (ATmega328P Old Bootloader)")

        board_choice = self.cli.get_input("\nSelect board type [1]: ") or "1"

        if board_choice == "2":
            fqbn = "arduino:avr:nano:cpu=atmega328old"
        else:
            fqbn = "arduino:avr:nano:cpu=atmega328"

        # Confirm
        print(f"\n{self.cli.Colors.BOLD}Upload Configuration:{self.cli.Colors.RESET}")
        self.cli.print_status("Port", port)
        self.cli.print_status("Board", fqbn)
        self.cli.print_status("Firmware", str(firmware_path))

        confirm = self.cli.get_input("\nUpload firmware? [y/N]: ").lower()
        if confirm != 'y':
            return

        # Disconnect sensor if connected
        if self.cli.is_connected:
            self.cli.print_info("Disconnecting sensor for upload...")
            self.cli.disconnect()

        # Compile
        print("\nCompiling firmware...")
        try:
            result = subprocess.run(
                [cli_path, 'compile', '--fqbn', fqbn, str(firmware_path)],
                capture_output=True, text=True
            )

            if result.returncode != 0:
                self.cli.print_error(f"Compilation failed: {result.stderr}")
                self.cli.wait_for_key()
                return

            # Show size info
            for line in result.stdout.split('\n'):
                if 'Sketch uses' in line or 'Global variables' in line:
                    print(f"  {line}")

            self.cli.print_success("Compilation successful")

        except Exception as e:
            self.cli.print_error(f"Compilation failed: {e}")
            self.cli.wait_for_key()
            return

        # Upload
        print("\nUploading to device...")
        try:
            result = subprocess.run(
                [cli_path, 'upload', '-p', port, '--fqbn', fqbn, str(firmware_path)],
                capture_output=True, text=True,
                timeout=120
            )

            if result.returncode == 0:
                self.cli.print_success("Firmware uploaded successfully!")
            else:
                if 'not in sync' in result.stderr:
                    self.cli.print_error("Upload failed: Try selecting 'Old Bootloader' option")
                else:
                    self.cli.print_error(f"Upload failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            self.cli.print_error("Upload timed out")
        except Exception as e:
            self.cli.print_error(f"Upload failed: {e}")

        self.cli.wait_for_key()

    # ==================== Requirements Check ====================

    def check_all_requirements(self):
        """Check all requirements and show summary."""
        self.cli.clear_screen()
        self.cli.print_header("REQUIREMENTS CHECK")

        all_good = True

        # Python
        print(f"{self.cli.Colors.GREEN}✓{self.cli.Colors.RESET} Python {sys.version.split()[0]}")

        # pyserial
        try:
            import serial
            print(f"{self.cli.Colors.GREEN}✓{self.cli.Colors.RESET} pyserial {serial.__version__}")
        except ImportError:
            print(f"{self.cli.Colors.RED}✗{self.cli.Colors.RESET} pyserial not installed")
            print(f"  {self.cli.Colors.DIM}Install: pip install pyserial{self.cli.Colors.RESET}")
            all_good = False

        # udev rules
        if self.check_udev_rules():
            print(f"{self.cli.Colors.GREEN}✓{self.cli.Colors.RESET} udev rules installed")
        else:
            print(f"{self.cli.Colors.YELLOW}○{self.cli.Colors.RESET} udev rules not installed (optional)")

        # dialout group
        if self.check_dialout_membership():
            print(f"{self.cli.Colors.GREEN}✓{self.cli.Colors.RESET} User in dialout group")
        else:
            print(f"{self.cli.Colors.YELLOW}○{self.cli.Colors.RESET} User not in dialout group (may need sudo for serial access)")

        # arduino-cli
        cli_path = self.find_arduino_cli()
        if cli_path:
            version = self.get_arduino_cli_version()
            print(f"{self.cli.Colors.GREEN}✓{self.cli.Colors.RESET} arduino-cli {version}")
        else:
            print(f"{self.cli.Colors.YELLOW}○{self.cli.Colors.RESET} arduino-cli not installed (needed for firmware upload)")

        # AVR core
        if cli_path and self.check_avr_core():
            print(f"{self.cli.Colors.GREEN}✓{self.cli.Colors.RESET} Arduino AVR core installed")
        elif cli_path:
            print(f"{self.cli.Colors.YELLOW}○{self.cli.Colors.RESET} Arduino AVR core not installed")

        # Firmware
        firmware_path = self.get_firmware_path()
        if firmware_path:
            print(f"{self.cli.Colors.GREEN}✓{self.cli.Colors.RESET} Firmware found at {firmware_path}")
        else:
            print(f"{self.cli.Colors.YELLOW}○{self.cli.Colors.RESET} Firmware not found")

        print()
        if all_good:
            self.cli.print_success("All required components are installed!")
        else:
            self.cli.print_warning("Some components are missing. See above for details.")

        self.cli.wait_for_key()
