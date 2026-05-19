"""Installer/Setup tab for Super Sensor GUI."""

import os
import sys
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog
from typing import TYPE_CHECKING
import webbrowser
from pathlib import Path

try:
    from ..utils.platform_utils import PlatformUtils
    from ..utils.arduino_utils import ArduinoUtils
    from ..widgets.log_panel import LogPanel
    from ..widgets.scrollable_frame import ScrollableFrame
except ImportError:
    from utils.platform_utils import PlatformUtils
    from utils.arduino_utils import ArduinoUtils
    from widgets.log_panel import LogPanel
    from widgets.scrollable_frame import ScrollableFrame


def get_firmware_dir() -> Path:
    """Get the firmware directory (works for both dev and bundled app)."""
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / 'firmware' / 'super_sensor'
    return Path(__file__).parent.parent.parent / 'firmware' / 'super_sensor'

if TYPE_CHECKING:
    try:
        from ..app import SuperSensorApp
    except ImportError:
        from app import SuperSensorApp


class InstallerTab(ttk.Frame):
    """
    Installer and Setup tab.

    Handles driver installation, udev rules, and firmware upload.
    """

    def __init__(self, parent, app: 'SuperSensorApp'):
        super().__init__(parent)
        self.app = app

        self._build_ui()
        self._check_status()

    def _build_ui(self):
        """Build the tab UI."""
        # Scrollable container
        self.scrollable = ScrollableFrame(self)
        self.scrollable.pack(fill='both', expand=True)

        # Main container
        main = ttk.Frame(self.scrollable.interior, padding=20)
        main.pack(fill='both', expand=True)

        # Status section
        status_frame = ttk.LabelFrame(main, text='System Status', padding=15)
        status_frame.pack(fill='x', pady=(0, 20))

        self.status_vars = {}
        status_items = [
            ('platform', 'Platform'),
            ('python', 'Python'),
            ('pyserial', 'pyserial'),
            ('arduino_cli', 'arduino-cli'),
        ]

        # Add platform-specific items
        if PlatformUtils.get_platform() == 'macos':
            status_items.append(('ch340_driver', 'CH340 Driver'))
        elif PlatformUtils.get_platform() == 'linux':
            status_items.append(('udev_rule', 'udev Rule'))
            status_items.append(('dialout', 'dialout Group'))

        for i, (key, label) in enumerate(status_items):
            ttk.Label(status_frame, text=f'{label}:').grid(
                row=i, column=0, sticky='e', padx=(0, 10), pady=2
            )
            var = tk.StringVar(value='Checking...')
            self.status_vars[key] = var
            ttk.Label(status_frame, textvariable=var).grid(
                row=i, column=1, sticky='w', pady=2
            )

        ttk.Button(
            status_frame,
            text='Refresh Status',
            command=self._check_status
        ).grid(row=len(status_items), column=0, columnspan=2, pady=(10, 0))

        # Driver installation section
        driver_frame = ttk.LabelFrame(main, text='Driver Installation', padding=15)
        driver_frame.pack(fill='x', pady=(0, 20))

        # pyserial
        pyserial_row = ttk.Frame(driver_frame)
        pyserial_row.pack(fill='x', pady=5)

        ttk.Label(pyserial_row, text='Python Serial Library:').pack(side='left')
        self.pyserial_btn = ttk.Button(
            pyserial_row,
            text='Install pyserial',
            command=self._install_pyserial
        )
        self.pyserial_btn.pack(side='right')

        # Platform-specific
        if PlatformUtils.get_platform() == 'macos':
            ch340_row = ttk.Frame(driver_frame)
            ch340_row.pack(fill='x', pady=5)

            ttk.Label(ch340_row, text='CH340 USB Driver (macOS):').pack(side='left')
            self.ch340_btn = ttk.Button(
                ch340_row,
                text='Install Driver',
                command=self._install_ch340_driver
            )
            self.ch340_btn.pack(side='right')

        elif PlatformUtils.get_platform() == 'linux':
            udev_row = ttk.Frame(driver_frame)
            udev_row.pack(fill='x', pady=5)

            ttk.Label(udev_row, text='udev Rule (auto-detection):').pack(side='left')
            self.udev_btn = ttk.Button(
                udev_row,
                text='Install udev Rule',
                command=self._install_udev_rule
            )
            self.udev_btn.pack(side='right')

            dialout_row = ttk.Frame(driver_frame)
            dialout_row.pack(fill='x', pady=5)

            ttk.Label(dialout_row, text='Serial Port Access:').pack(side='left')
            self.dialout_btn = ttk.Button(
                dialout_row,
                text='Add to dialout Group',
                command=self._add_to_dialout
            )
            self.dialout_btn.pack(side='right')

        # Firmware upload section
        firmware_frame = ttk.LabelFrame(main, text='Firmware Upload', padding=15)
        firmware_frame.pack(fill='x', pady=(0, 20))

        # Firmware info row
        info_row = ttk.Frame(firmware_frame)
        info_row.pack(fill='x', pady=(0, 10))

        ttk.Label(info_row, text='Bundled Firmware:').pack(side='left', padx=(0, 10))
        self.firmware_path_var = tk.StringVar(value='super_sensor.ino')
        ttk.Label(info_row, textvariable=self.firmware_path_var,
                  font=('Menlo', 11)).pack(side='left', padx=(0, 15))

        ttk.Button(
            info_row,
            text='View Code',
            command=self._view_firmware
        ).pack(side='left', padx=(0, 5))

        ttk.Button(
            info_row,
            text='Open Folder',
            command=self._open_firmware_folder
        ).pack(side='left', padx=(0, 5))

        ttk.Button(
            info_row,
            text='Export',
            command=self._export_firmware
        ).pack(side='left')

        # Port selection
        port_row = ttk.Frame(firmware_frame)
        port_row.pack(fill='x', pady=(0, 10))

        ttk.Label(port_row, text='Arduino Port:').pack(side='left', padx=(0, 10))

        self.fw_port_var = tk.StringVar()
        self.fw_port_combo = ttk.Combobox(
            port_row,
            textvariable=self.fw_port_var,
            width=25,
            state='readonly'
        )
        self.fw_port_combo.pack(side='left', padx=(0, 10))

        ttk.Button(
            port_row,
            text='Refresh',
            command=self._refresh_ports
        ).pack(side='left')

        # Board selection
        board_row = ttk.Frame(firmware_frame)
        board_row.pack(fill='x', pady=(0, 10))

        ttk.Label(board_row, text='Board Type:').pack(side='left', padx=(0, 10))

        self.board_var = tk.StringVar()
        board_options = [name for name, _ in ArduinoUtils.BOARD_OPTIONS]
        self.board_combo = ttk.Combobox(
            board_row,
            textvariable=self.board_var,
            values=board_options,
            width=35,
            state='readonly'
        )
        self.board_combo.pack(side='left')
        self.board_combo.set(board_options[0])

        # Upload button
        btn_row = ttk.Frame(firmware_frame)
        btn_row.pack(fill='x')

        self.upload_btn = ttk.Button(
            btn_row,
            text='Upload Firmware',
            command=self._upload_firmware
        )
        self.upload_btn.pack(side='left', padx=(0, 10))

        self.upload_status_var = tk.StringVar(value='Ready')
        ttk.Label(btn_row, textvariable=self.upload_status_var).pack(side='left')

        # Log panel
        log_frame = ttk.LabelFrame(main, text='Log', padding=15)
        log_frame.pack(fill='both', expand=True)

        self.log = LogPanel(log_frame, height=8)
        self.log.pack(fill='both', expand=True)

        # Initial port refresh
        self._refresh_ports()

        # Startup message
        self.log.info("Setup tab ready. Use the buttons above to install drivers or upload firmware.")

    def _check_status(self):
        """Check and update system status."""
        # Platform
        platform_info = PlatformUtils.get_platform_info()
        self.status_vars['platform'].set(
            f"{platform_info['system']} {platform_info['release']}"
        )

        # Python
        self.status_vars['python'].set(platform_info['python_version'])

        # pyserial - keep button enabled for user feedback
        if PlatformUtils.is_pyserial_installed():
            version = PlatformUtils.get_pyserial_version()
            self.status_vars['pyserial'].set(f"OK ({version})")
        else:
            self.status_vars['pyserial'].set("Not installed")

        # arduino-cli
        if ArduinoUtils.is_arduino_cli_installed():
            version = ArduinoUtils.get_arduino_cli_version()
            self.status_vars['arduino_cli'].set(f"OK ({version})")
        else:
            self.status_vars['arduino_cli'].set("Not installed (will auto-install)")

        # Platform-specific - keep buttons enabled for user feedback
        if PlatformUtils.get_platform() == 'macos':
            if PlatformUtils.is_ch340_driver_installed():
                self.status_vars['ch340_driver'].set("OK (installed)")
            else:
                self.status_vars['ch340_driver'].set("Not detected")

        elif PlatformUtils.get_platform() == 'linux':
            if PlatformUtils.is_udev_rule_installed():
                self.status_vars['udev_rule'].set("OK (installed)")
                self.udev_btn.configure(state='disabled')
            else:
                self.status_vars['udev_rule'].set("Not installed")
                self.udev_btn.configure(state='normal')

            if PlatformUtils.is_user_in_dialout_group():
                self.status_vars['dialout'].set("OK (member)")
                self.dialout_btn.configure(state='disabled')
            else:
                self.status_vars['dialout'].set("Not a member")
                self.dialout_btn.configure(state='normal')

    def _refresh_ports(self):
        """Refresh port list."""
        ports = PlatformUtils.get_serial_ports()
        port_list = [p['device'] for p in ports]
        self.fw_port_combo['values'] = port_list

        if port_list and not self.fw_port_var.get():
            # Try to find Super Sensor port
            sensor_port = PlatformUtils.find_super_sensor_port()
            if sensor_port:
                self.fw_port_var.set(sensor_port)
            else:
                self.fw_port_var.set(port_list[0])

    def _install_pyserial(self):
        """Install pyserial with online/offline fallback."""
        # Check if already installed first
        if PlatformUtils.is_pyserial_installed():
            version = PlatformUtils.get_pyserial_version()
            self.log.info(f"pyserial is already installed (version {version})")
            self.app.show_info("Already Installed", f"pyserial {version} is already installed.")
            return

        self.log.info("Installing pyserial...")
        self.pyserial_btn.configure(state='disabled')

        def log_callback(msg):
            self.app._ui(lambda m=msg: self.log.info(m))

        def do_install():
            return PlatformUtils.install_pyserial(log_callback=log_callback)

        def on_complete(success, result):
            self.pyserial_btn.configure(state='normal')

            if isinstance(result, tuple):
                success, msg = result
            else:
                msg = str(result)

            if success:
                self.log.success(msg)
                self._check_status()
                if "already installed" in msg.lower():
                    self.app.show_info("Already Installed", msg)
                else:
                    self.app.show_info("Installation Complete", msg)
            else:
                self.log.error(f"Failed: {msg}")
                self.app.show_error("Installation Failed", msg)

        self.app.run_async("Install pyserial", do_install, on_complete)

    def _install_ch340_driver(self):
        """Install CH340 driver from embedded package."""
        # Check if already installed first
        if PlatformUtils.is_ch340_driver_installed():
            self.log.info("CH340 driver is already installed")
            self.app.show_info("Already Installed", "CH340 driver is already installed and working.")
            return

        self.log.info("Installing CH340 driver...")
        self.ch340_btn.configure(state='disabled')

        def log_callback(msg):
            self.app._ui(lambda m=msg: self.log.info(m))

        def do_install():
            return PlatformUtils.install_ch340_driver(log_callback=log_callback)

        def on_complete(success, result):
            self.ch340_btn.configure(state='normal')

            if isinstance(result, tuple):
                success, msg = result
            else:
                msg = str(result)

            if success:
                self.log.success("Driver installer launched!")
                for line in msg.split('\n'):
                    if line.strip():
                        self.log.info(line)
                self._check_status()
                self.app.show_info("Driver Installation", msg)
            else:
                self.log.error(f"Failed: {msg}")
                self.app.show_error("Installation Failed", msg)

        self.app.run_async("Install CH340 Driver", do_install, on_complete)

    def _download_ch340_driver(self):
        """Open CH340 driver download page (fallback)."""
        url = "https://www.wch-ic.com/downloads/CH341SER_MAC_ZIP.html"
        webbrowser.open(url)
        self.log.info(f"Opened driver download page: {url}")
        self.log.info("After installing, you may need to approve the system extension in:")
        self.log.info("System Preferences → Security & Privacy → General")

    def _install_udev_rule(self):
        """Install udev rule."""
        self.log.info("Installing udev rule...")
        self.log.info("You may be prompted for your password (sudo required)")

        def do_install():
            return PlatformUtils.install_udev_rule()

        def on_complete(success, result):
            if isinstance(result, tuple):
                success, msg = result
            else:
                msg = str(result)

            if success:
                self.log.success(msg)
                self._check_status()
            else:
                self.log.error(f"Failed: {msg}")

        self.app.run_async("Install udev rule", do_install, on_complete)

    def _add_to_dialout(self):
        """Add user to dialout group."""
        self.log.info("Adding user to dialout group...")
        self.log.info("You may be prompted for your password (sudo required)")

        def do_add():
            return PlatformUtils.add_user_to_dialout()

        def on_complete(success, result):
            if isinstance(result, tuple):
                success, msg = result
            else:
                msg = str(result)

            if success:
                self.log.success(msg)
                self.log.warning("You must log out and back in for changes to take effect!")
                self._check_status()
            else:
                self.log.error(f"Failed: {msg}")

        self.app.run_async("Add to dialout", do_add, on_complete)

    def _upload_firmware(self):
        """Upload firmware to Arduino."""
        port = self.fw_port_var.get()
        if not port:
            self.app.show_warning("Upload", "Please select a port first.")
            return

        # Get board FQBN
        board_name = self.board_var.get()
        board_fqbn = None
        for name, fqbn in ArduinoUtils.BOARD_OPTIONS:
            if name == board_name:
                board_fqbn = fqbn
                break

        if not board_fqbn:
            self.app.show_error("Upload", "Invalid board selection.")
            return

        # Disconnect if connected
        if self.app.controller.is_connected:
            self.log.info("Disconnecting sensor for firmware upload...")
            self.app.controller.disconnect()

        self.upload_btn.configure(state='disabled')
        self.upload_status_var.set('Uploading...')
        self.log.info(f"Starting firmware upload to {port}")

        def do_upload():
            return ArduinoUtils.upload_firmware(
                port,
                board_fqbn,
                log_callback=lambda msg: self.app._ui(lambda m=msg: self.log.info(m))
            )

        def on_complete(success, result):
            self.upload_btn.configure(state='normal')

            if isinstance(result, tuple):
                success, msg = result
            else:
                msg = str(result)

            if success:
                self.upload_status_var.set('Success!')
                self.log.success("Firmware upload complete!")
            else:
                self.upload_status_var.set('Failed')
                self.log.error(f"Upload failed: {msg}")

                # Suggest trying old bootloader
                if 'not in sync' in msg.lower():
                    self.log.warning("Try selecting 'Old Bootloader' option and upload again.")

        self.app.run_async("Upload firmware", do_upload, on_complete)

    def _get_firmware_path(self) -> Path:
        """Get the path to the firmware .ino file."""
        firmware_dir = get_firmware_dir()
        return firmware_dir / 'super_sensor.ino'

    def _view_firmware(self):
        """Open firmware code in a viewer window."""
        firmware_path = self._get_firmware_path()

        if not firmware_path.exists():
            self.app.show_error("Firmware Not Found", f"Could not find firmware at:\n{firmware_path}")
            return

        # Read firmware content
        try:
            with open(firmware_path, 'r') as f:
                content = f.read()
        except Exception as e:
            self.app.show_error("Error", f"Could not read firmware: {e}")
            return

        # Create viewer window
        viewer = tk.Toplevel(self)
        viewer.title("Super Sensor Firmware - super_sensor.ino")
        viewer.geometry("900x700")
        viewer.minsize(600, 400)

        # Main frame
        main_frame = ttk.Frame(viewer, padding=10)
        main_frame.pack(fill='both', expand=True)

        # Info label
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill='x', pady=(0, 10))

        ttk.Label(info_frame, text=f"Path: {firmware_path}",
                  font=('Menlo', 10)).pack(side='left')

        ttk.Button(info_frame, text="Copy Path",
                   command=lambda: self._copy_to_clipboard(str(firmware_path))).pack(side='right')

        # Text widget with scrollbar
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill='both', expand=True)

        text_widget = tk.Text(
            text_frame,
            wrap='none',
            font=('Menlo', 12),
            bg='#1e1e1e',
            fg='#d4d4d4',
            insertbackground='white',
            selectbackground='#264f78',
            padx=10,
            pady=10
        )
        text_widget.pack(side='left', fill='both', expand=True)

        # Scrollbars
        v_scroll = ttk.Scrollbar(text_frame, orient='vertical', command=text_widget.yview)
        v_scroll.pack(side='right', fill='y')
        text_widget.configure(yscrollcommand=v_scroll.set)

        h_scroll = ttk.Scrollbar(main_frame, orient='horizontal', command=text_widget.xview)
        h_scroll.pack(fill='x')
        text_widget.configure(xscrollcommand=h_scroll.set)

        # Insert content
        text_widget.insert('1.0', content)
        text_widget.configure(state='disabled')  # Read-only

        # Button frame
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=(10, 0))

        ttk.Button(btn_frame, text="Open in Default Editor",
                   command=lambda: self._open_in_editor(firmware_path)).pack(side='left', padx=(0, 5))
        ttk.Button(btn_frame, text="Copy All",
                   command=lambda: self._copy_to_clipboard(content)).pack(side='left', padx=(0, 5))
        ttk.Button(btn_frame, text="Close",
                   command=viewer.destroy).pack(side='right')

        self.log.info(f"Opened firmware viewer: {firmware_path}")

    def _open_firmware_folder(self):
        """Open the firmware folder in file manager."""
        firmware_dir = get_firmware_dir()

        if not firmware_dir.exists():
            self.app.show_error("Folder Not Found", f"Firmware folder not found:\n{firmware_dir}")
            return

        try:
            if PlatformUtils.get_platform() == 'macos':
                subprocess.run(['open', str(firmware_dir)])
            elif PlatformUtils.get_platform() == 'linux':
                subprocess.run(['xdg-open', str(firmware_dir)])
            else:
                subprocess.run(['explorer', str(firmware_dir)])

            self.log.info(f"Opened firmware folder: {firmware_dir}")
        except Exception as e:
            self.app.show_error("Error", f"Could not open folder: {e}")

    def _export_firmware(self):
        """Export firmware to a user-selected location."""
        firmware_dir = get_firmware_dir()
        firmware_path = firmware_dir / 'super_sensor.ino'

        if not firmware_path.exists():
            self.app.show_error("Firmware Not Found", f"Could not find firmware at:\n{firmware_path}")
            return

        # Ask user where to save
        dest_dir = filedialog.askdirectory(
            title="Select destination folder for firmware export",
            initialdir=str(Path.home() / 'Documents')
        )

        if not dest_dir:
            return  # User cancelled

        dest_path = Path(dest_dir) / 'super_sensor'

        try:
            # Copy entire firmware directory
            if dest_path.exists():
                # Ask to overwrite
                if not self.app.ask_yes_no("Overwrite?",
                        f"Folder already exists:\n{dest_path}\n\nOverwrite?"):
                    return
                shutil.rmtree(dest_path)

            shutil.copytree(firmware_dir, dest_path)

            self.log.success(f"Firmware exported to: {dest_path}")
            self.app.show_info("Export Complete",
                f"Firmware exported to:\n{dest_path}\n\n"
                "You can now modify the code and upload it using Arduino IDE or this app.")

            # Open the exported folder
            if PlatformUtils.get_platform() == 'macos':
                subprocess.run(['open', str(dest_path)])
            elif PlatformUtils.get_platform() == 'linux':
                subprocess.run(['xdg-open', str(dest_path)])

        except Exception as e:
            self.log.error(f"Export failed: {e}")
            self.app.show_error("Export Failed", str(e))

    def _open_in_editor(self, file_path: Path):
        """Open file in system default editor."""
        try:
            if PlatformUtils.get_platform() == 'macos':
                subprocess.run(['open', str(file_path)])
            elif PlatformUtils.get_platform() == 'linux':
                subprocess.run(['xdg-open', str(file_path)])
            else:
                subprocess.run(['notepad', str(file_path)])
            self.log.info(f"Opened in editor: {file_path}")
        except Exception as e:
            self.app.show_error("Error", f"Could not open editor: {e}")

    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard."""
        self.clipboard_clear()
        self.clipboard_append(text)
        self.log.info("Copied to clipboard")
