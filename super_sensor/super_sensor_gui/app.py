"""Main application class for Super Sensor GUI with native macOS support."""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import sys
from typing import Callable, Optional
from pathlib import Path

try:
    from .utils.sensor_controller import SensorController
    from .utils.platform_utils import PlatformUtils
    from .utils.screenshot_utils import ScreenshotUtils, TkinterScreenshot
    from .utils.macos_utils import MacOSTheme, MacOSIntegration, MacOSKeyboardShortcuts
except ImportError:
    from utils.sensor_controller import SensorController
    from utils.platform_utils import PlatformUtils
    from utils.screenshot_utils import ScreenshotUtils, TkinterScreenshot
    from utils.macos_utils import MacOSTheme, MacOSIntegration, MacOSKeyboardShortcuts


class SuperSensorApp:
    """
    Main application class for Super Sensor GUI.

    Provides native macOS experience with:
    - Light/dark mode support
    - Standard menu bar
    - Keyboard shortcuts
    - Native window management
    """

    APP_NAME = "Super Sensor"
    APP_VERSION = "1.0.0"
    WINDOW_SIZE = "1200x900"
    MIN_WIDTH = 1000
    MIN_HEIGHT = 750

    def __init__(self):
        """Initialize the application."""
        self.root = tk.Tk()
        self.root.title(f"{self.APP_NAME} - Control Panel")
        self.root.geometry(self.WINDOW_SIZE)
        self.root.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)

        # Ensure window is resizable and movable
        self.root.resizable(True, True)

        # Enable macOS native features
        if sys.platform == 'darwin':
            self._setup_macos_native()

        # Get current theme
        self.theme = MacOSTheme.get_theme()
        self.is_dark_mode = MacOSTheme.is_dark_mode()

        # Set theme
        self.style = ttk.Style()
        self._configure_styles()

        # Sensor controller (shared across tabs)
        self.controller = SensorController()

        # Build UI
        self._build_menu_bar()
        self._build_ui()

        # Bind keyboard shortcuts
        self._bind_shortcuts()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Debug mode flag
        self._debug_mode = False
        self._screenshot_counter = 0

        # Start theme monitor
        self._start_theme_monitor()

    def _setup_macos_native(self):
        """Configure macOS-native window behaviors."""
        try:
            # Enable native window controls
            self.root.createcommand('tk::mac::Quit', self._on_close)
            self.root.createcommand('tk::mac::ShowPreferences', self._show_preferences)
            self.root.createcommand('tk::mac::ShowHelp', self._show_help)

            # Set app to use native title bar style with resize support
            self.root.tk.call('::tk::unsupported::MacWindowStyle', 'style',
                             self.root._w, 'document', 'closeBox collapseBox resizeable')
        except tk.TclError:
            pass  # Older Tk versions may not support these

    def _configure_styles(self):
        """Configure ttk styles based on current theme."""
        theme = self.theme

        # Use 'clam' theme for better control over styling
        available_themes = self.style.theme_names()
        if 'clam' in available_themes:
            self.style.theme_use('clam')

        # Configure root window
        self.root.configure(bg=theme['bg'])

        # Frame backgrounds
        self.style.configure('TFrame', background=theme['bg'])
        self.style.configure('Toolbar.TFrame', background=theme['toolbar_bg'])
        self.style.configure('Sidebar.TFrame', background=theme['sidebar_bg'])

        # LabelFrame - prominent section headers
        self.style.configure('TLabelframe',
                           background=theme['bg'],
                           bordercolor=theme['border'],
                           relief='groove',
                           borderwidth=2)
        self.style.configure('TLabelframe.Label',
                           background=theme['bg'],
                           foreground=theme['accent'],
                           font=('Helvetica Neue', 14, 'bold'),
                           padding=(5, 2))

        # Labels - clean, readable text
        self.style.configure('TLabel',
                           background=theme['bg'],
                           foreground=theme['fg'],
                           font=('Helvetica Neue', 13))
        self.style.configure('Header.TLabel',
                           font=('Helvetica Neue', 18, 'bold'),
                           foreground=theme['fg'])
        self.style.configure('Status.TLabel',
                           font=('Helvetica Neue', 13),
                           foreground=theme['fg_secondary'])
        self.style.configure('Secondary.TLabel',
                           font=('Helvetica Neue', 12),
                           foreground=theme['fg_secondary'])
        self.style.configure('Value.TLabel',
                           font=('Menlo', 13),
                           foreground=theme['fg'])

        # Buttons - modern, prominent styling
        self.style.configure('TButton',
                           padding=(16, 10),
                           font=('Helvetica Neue', 13, 'bold'),
                           background=theme['button_bg'],
                           foreground=theme['button_fg'],
                           borderwidth=1,
                           relief='raised')
        self.style.map('TButton',
                      background=[('active', theme['accent']),
                                 ('pressed', theme['accent_hover'])],
                      foreground=[('active', '#ffffff'),
                                 ('pressed', '#ffffff')])

        # Primary action buttons
        self.style.configure('Primary.TButton',
                           background=theme['accent'],
                           foreground='#ffffff')
        self.style.map('Primary.TButton',
                      background=[('active', theme['accent_hover']),
                                 ('pressed', theme['accent_hover'])])

        # Danger/warning buttons
        self.style.configure('Danger.TButton',
                           background=theme['error'],
                           foreground='#ffffff')

        # Success buttons
        self.style.configure('Success.TButton',
                           background=theme['success'],
                           foreground='#ffffff')

        # Notebook (tabs) - clean, prominent tabs
        self.style.configure('TNotebook',
                           background=theme['bg'],
                           borderwidth=0)
        self.style.configure('TNotebook.Tab',
                           padding=[24, 12],
                           font=('Helvetica Neue', 13, 'bold'),
                           background=theme['bg_secondary'],
                           foreground=theme['fg'])
        self.style.map('TNotebook.Tab',
                      background=[('selected', theme['accent'])],
                      foreground=[('selected', '#ffffff')],
                      expand=[('selected', [0, 0, 0, 2])])

        # Entry - clean input fields
        self.style.configure('TEntry',
                           fieldbackground=theme['entry_bg'],
                           foreground=theme['entry_fg'],
                           font=('Helvetica Neue', 13),
                           padding=8,
                           borderwidth=1,
                           relief='solid')

        # Combobox - styled dropdowns
        self.style.configure('TCombobox',
                           fieldbackground=theme['entry_bg'],
                           foreground=theme['entry_fg'],
                           font=('Helvetica Neue', 13),
                           padding=6,
                           arrowsize=14)

        # Spinbox - clean number inputs
        self.style.configure('TSpinbox',
                           fieldbackground=theme['entry_bg'],
                           foreground=theme['entry_fg'],
                           font=('Helvetica Neue', 13),
                           padding=6,
                           arrowsize=14)

        # Scale (slider)
        self.style.configure('TScale',
                           background=theme['bg'],
                           troughcolor=theme['border'],
                           sliderlength=20)

        # Separator
        self.style.configure('TSeparator', background=theme['border'])

        # Checkbutton
        self.style.configure('TCheckbutton',
                           background=theme['bg'],
                           foreground=theme['fg'],
                           font=('Helvetica Neue', 12))

    def _build_menu_bar(self):
        """Build the macOS-style menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # App menu (macOS-specific)
        if sys.platform == 'darwin':
            app_menu = tk.Menu(menubar, name='apple', tearoff=0)
            menubar.add_cascade(menu=app_menu)
            app_menu.add_command(label=f'About {self.APP_NAME}',
                               command=self._show_about)
            app_menu.add_separator()
            app_menu.add_command(label='Preferences...',
                               accelerator='⌘,',
                               command=self._show_preferences)
            app_menu.add_separator()

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Profile",
                            accelerator="⌘N" if sys.platform == 'darwin' else "Ctrl+N",
                            command=self._new_profile)
        file_menu.add_command(label="Open Profile...",
                            accelerator="⌘O" if sys.platform == 'darwin' else "Ctrl+O",
                            command=self._open_profile)
        file_menu.add_separator()
        file_menu.add_command(label="Save",
                            accelerator="⌘S" if sys.platform == 'darwin' else "Ctrl+S",
                            command=self._save_profile)
        file_menu.add_command(label="Save As...",
                            accelerator="⇧⌘S" if sys.platform == 'darwin' else "Ctrl+Shift+S",
                            command=self._save_profile_as)
        file_menu.add_separator()
        file_menu.add_command(label="Export Log...",
                            command=self._export_log)
        if sys.platform != 'darwin':
            file_menu.add_separator()
            file_menu.add_command(label="Exit",
                                accelerator="Ctrl+Q",
                                command=self._on_close)

        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Undo",
                            accelerator="⌘Z" if sys.platform == 'darwin' else "Ctrl+Z",
                            command=self._undo)
        edit_menu.add_command(label="Redo",
                            accelerator="⇧⌘Z" if sys.platform == 'darwin' else "Ctrl+Shift+Z",
                            command=self._redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Cut",
                            accelerator="⌘X" if sys.platform == 'darwin' else "Ctrl+X",
                            command=self._cut)
        edit_menu.add_command(label="Copy",
                            accelerator="⌘C" if sys.platform == 'darwin' else "Ctrl+C",
                            command=self._copy)
        edit_menu.add_command(label="Paste",
                            accelerator="⌘V" if sys.platform == 'darwin' else "Ctrl+V",
                            command=self._paste)
        edit_menu.add_command(label="Select All",
                            accelerator="⌘A" if sys.platform == 'darwin' else "Ctrl+A",
                            command=self._select_all)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Status",
                            command=lambda: self.notebook.select(0))
        view_menu.add_command(label="Control",
                            command=lambda: self.notebook.select(1))
        view_menu.add_command(label="Setup",
                            command=lambda: self.notebook.select(2))
        view_menu.add_command(label="Calibration",
                            command=lambda: self.notebook.select(3))
        view_menu.add_separator()
        view_menu.add_command(label="Refresh Ports",
                            accelerator="⌘R" if sys.platform == 'darwin' else "Ctrl+R",
                            command=self._refresh_all_ports)

        # Sensor menu
        sensor_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Sensor", menu=sensor_menu)
        sensor_menu.add_command(label="Connect",
                              command=self._connect_sensor)
        sensor_menu.add_command(label="Disconnect",
                              command=self._disconnect_sensor)
        sensor_menu.add_separator()
        sensor_menu.add_command(label="Scan Once",
                              command=self._scan_once)
        sensor_menu.add_command(label="Start Continuous Scan",
                              command=self._start_polling)
        sensor_menu.add_command(label="Stop Continuous Scan",
                              command=self._stop_polling)
        sensor_menu.add_separator()
        sensor_menu.add_command(label="LED Off",
                              command=self._led_off)
        sensor_menu.add_command(label="Center Servo",
                              command=self._center_servo)

        # Window menu
        window_menu = tk.Menu(menubar, name='window', tearoff=0)
        menubar.add_cascade(label="Window", menu=window_menu)
        window_menu.add_command(label="Minimize",
                              accelerator="⌘M" if sys.platform == 'darwin' else "",
                              command=self._minimize)
        window_menu.add_command(label="Zoom",
                              command=self._zoom)
        window_menu.add_separator()
        window_menu.add_command(label="Bring All to Front",
                              command=self._bring_to_front)

        # Debug menu
        debug_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Debug", menu=debug_menu)
        debug_menu.add_command(label="Take Screenshot",
                             accelerator="⇧⌘S" if sys.platform == 'darwin' else "Ctrl+Shift+S",
                             command=self.take_screenshot)
        debug_menu.add_command(label="Screenshot All Tabs",
                             command=self.screenshot_all_tabs)
        debug_menu.add_separator()
        debug_menu.add_command(label="Open Screenshot Folder",
                             command=self._open_screenshot_folder)
        debug_menu.add_command(label="Show Screenshot Path",
                             command=self._show_screenshot_path)
        debug_menu.add_separator()
        debug_menu.add_command(label="Ping Sensor",
                             command=self._ping_sensor)
        debug_menu.add_command(label="Get Full Status",
                             command=self._get_full_status)

        # Help menu
        help_menu = tk.Menu(menubar, name='help', tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label=f"{self.APP_NAME} Help",
                            accelerator="⌘?" if sys.platform == 'darwin' else "F1",
                            command=self._show_help)
        help_menu.add_separator()
        help_menu.add_command(label="Documentation",
                            command=self._open_documentation)
        help_menu.add_command(label="Release Notes",
                            command=self._show_release_notes)
        if sys.platform != 'darwin':
            help_menu.add_separator()
            help_menu.add_command(label=f"About {self.APP_NAME}",
                                command=self._show_about)

    def _build_ui(self):
        """Build the main UI."""
        theme = self.theme

        # Main container
        main_frame = ttk.Frame(self.root, padding=0)
        main_frame.pack(fill='both', expand=True)

        # Toolbar
        toolbar_frame = ttk.Frame(main_frame, style='Toolbar.TFrame', padding=(10, 8))
        toolbar_frame.pack(fill='x')

        # App title in toolbar
        ttk.Label(
            toolbar_frame,
            text=f"{self.APP_NAME}",
            style='Header.TLabel'
        ).pack(side='left')

        # Connection status indicator (right side of toolbar)
        self.status_frame = ttk.Frame(toolbar_frame, style='Toolbar.TFrame')
        self.status_frame.pack(side='right', padx=(0, 10))

        # Status indicator - larger, more visible
        self.status_indicator = tk.Canvas(
            self.status_frame,
            width=16,
            height=16,
            highlightthickness=0,
            bg=theme['toolbar_bg']
        )
        self.status_indicator.pack(side='left', padx=(0, 8))
        self._update_status_indicator(False)

        self.status_label = ttk.Label(
            self.status_frame,
            text="Disconnected",
            font=('Helvetica Neue', 13, 'bold'),
            foreground=theme['error']
        )
        self.status_label.pack(side='left')

        # Content area with padding
        content_frame = ttk.Frame(main_frame, padding=10)
        content_frame.pack(fill='both', expand=True)

        # Create notebook (tabs)
        self.notebook = ttk.Notebook(content_frame)
        self.notebook.pack(fill='both', expand=True)

        # Import and create tabs
        try:
            from .tabs.status_tab import StatusTab
            from .tabs.control_tab import ControlTab
            from .tabs.installer_tab import InstallerTab
            from .tabs.calibration_tab import CalibrationTab
        except ImportError:
            from tabs.status_tab import StatusTab
            from tabs.control_tab import ControlTab
            from tabs.installer_tab import InstallerTab
            from tabs.calibration_tab import CalibrationTab

        # Create tab instances
        self.status_tab = StatusTab(self.notebook, self)
        self.control_tab = ControlTab(self.notebook, self)
        self.installer_tab = InstallerTab(self.notebook, self)
        self.calibration_tab = CalibrationTab(self.notebook, self)

        # Add tabs to notebook
        self.notebook.add(self.status_tab, text='  Status  ')
        self.notebook.add(self.control_tab, text='  Control  ')
        self.notebook.add(self.installer_tab, text='  Setup  ')
        self.notebook.add(self.calibration_tab, text='  Calibration  ')

        # Register status callback
        self.controller.add_status_callback(self._on_status_change)

    def _bind_shortcuts(self):
        """Bind keyboard shortcuts."""
        # Use Command on macOS, Control on other platforms
        mod = 'Command' if sys.platform == 'darwin' else 'Control'

        # File shortcuts
        self.root.bind(f'<{mod}-n>', lambda e: self._new_profile())
        self.root.bind(f'<{mod}-o>', lambda e: self._open_profile())
        self.root.bind(f'<{mod}-s>', lambda e: self._save_profile())
        self.root.bind(f'<{mod}-Shift-s>', lambda e: self._save_profile_as())

        # View shortcuts
        self.root.bind(f'<{mod}-r>', lambda e: self._refresh_all_ports())

        # Debug shortcut
        self.root.bind(f'<{mod}-Shift-d>', lambda e: self.take_screenshot())

        # Window shortcuts
        self.root.bind(f'<{mod}-m>', lambda e: self._minimize())
        self.root.bind(f'<{mod}-w>', lambda e: self._on_close())

        # Quit shortcut (macOS)
        if sys.platform == 'darwin':
            self.root.bind('<Command-q>', lambda e: self._on_close())
        else:
            self.root.bind('<Control-q>', lambda e: self._on_close())

        # Tab switching
        self.root.bind(f'<{mod}-1>', lambda e: self.notebook.select(0))
        self.root.bind(f'<{mod}-2>', lambda e: self.notebook.select(1))
        self.root.bind(f'<{mod}-3>', lambda e: self.notebook.select(2))
        self.root.bind(f'<{mod}-4>', lambda e: self.notebook.select(3))

        # Help
        self.root.bind('<F1>', lambda e: self._show_help())
        if sys.platform == 'darwin':
            self.root.bind('<Command-?>', lambda e: self._show_help())

    def _start_theme_monitor(self):
        """Start monitoring for theme changes."""
        def check_theme():
            if MacOSTheme.check_theme_change():
                self._on_theme_change(MacOSTheme.is_dark_mode())
            self.root.after(2000, check_theme)  # Check every 2 seconds

        self.root.after(2000, check_theme)

    def _on_theme_change(self, is_dark: bool):
        """Handle theme change."""
        self.is_dark_mode = is_dark
        self.theme = MacOSTheme.get_theme()
        self._configure_styles()
        # Note: Full refresh would require recreating widgets

    def _update_status_indicator(self, connected: bool):
        """Update the connection status indicator."""
        self.status_indicator.delete('all')
        if connected:
            fill_color = self.theme['success']
            outline_color = '#2a9d4a'  # Darker green
        else:
            fill_color = self.theme['error']
            outline_color = '#cc2a2a'  # Darker red
        # Draw larger indicator with outline for visibility
        self.status_indicator.create_oval(2, 2, 14, 14, fill=fill_color, outline=outline_color, width=2)

    def _on_status_change(self, status):
        """Handle sensor status changes."""
        self._ui(lambda: self._update_status_display(status))

    def _update_status_display(self, status):
        """Update status display in UI thread."""
        self._update_status_indicator(status.connected)
        if status.connected:
            self.status_label.configure(
                text=f"Connected: {status.port}",
                foreground=self.theme['success']
            )
        else:
            self.status_label.configure(
                text="Disconnected",
                foreground=self.theme['error']
            )

    # ==================== Menu Actions ====================

    def _new_profile(self):
        """Create a new calibration profile."""
        if hasattr(self, 'calibration_tab'):
            self.notebook.select(3)  # Switch to calibration tab
            # Reset to defaults
            for var in self.calibration_tab.offset_vars:
                var.set(0)
            self.calibration_tab.servo_min_var.set(0)
            self.calibration_tab.servo_center_var.set(90)
            self.calibration_tab.servo_max_var.set(180)
            self.calibration_tab.profile_var.set('Untitled')

    def _open_profile(self):
        """Open a calibration profile."""
        if hasattr(self, 'calibration_tab'):
            self.notebook.select(3)
            self.calibration_tab._load_profile()

    def _save_profile(self):
        """Save current profile."""
        if hasattr(self, 'calibration_tab'):
            self.calibration_tab._save_profile()

    def _save_profile_as(self):
        """Save profile with new name."""
        if hasattr(self, 'calibration_tab'):
            self.calibration_tab._save_profile_as()

    def _export_log(self):
        """Export the installer log."""
        if hasattr(self, 'installer_tab') and hasattr(self.installer_tab, 'log'):
            self.installer_tab.log._copy_all()
            self.show_info("Export", "Log copied to clipboard")

    def _undo(self):
        """Undo action (placeholder)."""
        try:
            self.root.focus_get().event_generate('<<Undo>>')
        except Exception:
            pass

    def _redo(self):
        """Redo action (placeholder)."""
        try:
            self.root.focus_get().event_generate('<<Redo>>')
        except Exception:
            pass

    def _cut(self):
        """Cut to clipboard."""
        try:
            self.root.focus_get().event_generate('<<Cut>>')
        except Exception:
            pass

    def _copy(self):
        """Copy to clipboard."""
        try:
            self.root.focus_get().event_generate('<<Copy>>')
        except Exception:
            pass

    def _paste(self):
        """Paste from clipboard."""
        try:
            self.root.focus_get().event_generate('<<Paste>>')
        except Exception:
            pass

    def _select_all(self):
        """Select all."""
        try:
            self.root.focus_get().event_generate('<<SelectAll>>')
        except Exception:
            pass

    def _refresh_all_ports(self):
        """Refresh ports in all tabs."""
        if hasattr(self, 'status_tab'):
            self.status_tab._refresh_ports()
        if hasattr(self, 'installer_tab'):
            self.installer_tab._refresh_ports()

    def _connect_sensor(self):
        """Connect to sensor from menu."""
        if hasattr(self, 'status_tab'):
            self.status_tab._connect()

    def _disconnect_sensor(self):
        """Disconnect sensor from menu."""
        if hasattr(self, 'status_tab'):
            self.status_tab._disconnect()

    def _scan_once(self):
        """Perform single scan."""
        if hasattr(self, 'control_tab'):
            self.control_tab._scan_once()

    def _start_polling(self):
        """Start continuous scanning."""
        if hasattr(self, 'control_tab'):
            if not self.control_tab._polling:
                self.control_tab._toggle_polling()

    def _stop_polling(self):
        """Stop continuous scanning."""
        if hasattr(self, 'control_tab'):
            if self.control_tab._polling:
                self.control_tab._toggle_polling()

    def _led_off(self):
        """Turn off LED."""
        if self.controller.is_connected:
            self.controller.set_led(0, 0, 0)

    def _center_servo(self):
        """Center the servo."""
        if self.controller.is_connected:
            self.controller.set_servo(90)

    def _ping_sensor(self):
        """Ping the sensor."""
        if hasattr(self, 'status_tab'):
            self.status_tab._ping()

    def _get_full_status(self):
        """Get full sensor status."""
        if hasattr(self, 'control_tab'):
            self.control_tab._get_status()

    def _minimize(self):
        """Minimize window."""
        self.root.iconify()

    def _zoom(self):
        """Zoom/maximize window."""
        current_state = self.root.state()
        if current_state == 'zoomed' or current_state == 'fullscreen':
            self.root.state('normal')
        else:
            self.root.state('zoomed')

    def _bring_to_front(self):
        """Bring window to front."""
        self.root.lift()
        self.root.focus_force()

    def _show_preferences(self):
        """Show preferences dialog."""
        # TODO: Implement preferences dialog
        self.show_info("Preferences", "Preferences dialog coming soon.")

    def _show_help(self):
        """Show help."""
        self.show_info(
            f"{self.APP_NAME} Help",
            f"{self.APP_NAME} v{self.APP_VERSION}\n\n"
            "Keyboard Shortcuts:\n"
            "  ⌘1-4  Switch tabs\n"
            "  ⌘R    Refresh ports\n"
            "  ⌘S    Save profile\n"
            "  ⌘O    Open profile\n"
            "  ⌘Q    Quit\n\n"
            "For more help, visit the documentation."
        )

    def _open_documentation(self):
        """Open documentation."""
        import webbrowser
        # TODO: Add actual documentation URL
        webbrowser.open("https://github.com/")

    def _show_release_notes(self):
        """Show release notes."""
        self.show_info(
            "Release Notes",
            f"{self.APP_NAME} v{self.APP_VERSION}\n\n"
            "• Initial release\n"
            "• Cross-platform GUI for Super Sensor\n"
            "• Real-time sensor monitoring\n"
            "• LED and servo control\n"
            "• Calibration profiles\n"
            "• Built-in firmware upload"
        )

    def _show_about(self):
        """Show about dialog."""
        self.show_info(
            f"About {self.APP_NAME}",
            f"{self.APP_NAME} v{self.APP_VERSION}\n\n"
            "Cross-platform GUI for controlling the\n"
            "Super Sensor module (Arduino Nano).\n\n"
            "Features:\n"
            "• 4x Ultrasonic sensors\n"
            "• RGB LED control\n"
            "• Servo control\n"
            "• Calibration tools\n"
            "• Built-in firmware upload\n\n"
            "© 2025 ROVAC Project"
        )

    # ==================== Screenshot Methods ====================

    def take_screenshot(self, filename: str = None) -> Optional[Path]:
        """Take a screenshot of the application window."""
        self.root.update_idletasks()
        self.root.update()

        if filename is None:
            self._screenshot_counter += 1
            tab_name = self._get_current_tab_name()
            filename = f"super_sensor_{tab_name}_{self._screenshot_counter:03d}"

        # Use region capture based on window coordinates
        screenshot_path = TkinterScreenshot.capture_widget(self.root, filename)

        if screenshot_path and screenshot_path.exists():
            print(f"Screenshot saved: {screenshot_path}")
            return screenshot_path
        else:
            print("Screenshot failed - trying full screen capture")
            screenshot_path = ScreenshotUtils.capture_screen(filename)
            if screenshot_path and screenshot_path.exists():
                print(f"Full screen screenshot saved: {screenshot_path}")
                return screenshot_path
            print("Screenshot failed")
            return None

    def screenshot_all_tabs(self) -> list:
        """Take screenshots of all tabs."""
        screenshots = []
        original_tab = self.notebook.index(self.notebook.select())

        tab_count = self.notebook.index('end')
        for i in range(tab_count):
            self.notebook.select(i)
            self.root.update_idletasks()
            self.root.after(100)
            self.root.update()

            tab_name = self._get_current_tab_name()
            path = self.take_screenshot(f"super_sensor_{tab_name}")
            if path:
                screenshots.append(path)

        self.notebook.select(original_tab)

        if screenshots:
            self.show_info(
                "Screenshots",
                f"Saved {len(screenshots)} screenshots to:\n{ScreenshotUtils.get_screenshot_dir()}"
            )

        return screenshots

    def _get_current_tab_name(self) -> str:
        """Get the name of the currently selected tab."""
        try:
            tab_id = self.notebook.select()
            tab_name = self.notebook.tab(tab_id, 'text').strip().lower().replace(' ', '_')
            return tab_name
        except Exception:
            return "unknown"

    def _open_screenshot_folder(self):
        """Open the screenshot folder in Finder."""
        folder = ScreenshotUtils.get_screenshot_dir()
        MacOSIntegration.reveal_in_finder(str(folder))

    def _show_screenshot_path(self):
        """Show the screenshot folder path."""
        folder = ScreenshotUtils.get_screenshot_dir()
        self.show_info("Screenshot Folder", str(folder))

    def get_screenshot_dir(self) -> Path:
        """Get the screenshot directory path."""
        return ScreenshotUtils.get_screenshot_dir()

    # ==================== Lifecycle ====================

    def _on_close(self):
        """Handle window close."""
        # Stop polling
        self.controller.stop_polling()

        # Disconnect
        self.controller.disconnect()

        # Destroy window
        self.root.destroy()

    def run(self):
        """Run the application main loop."""
        self.root.mainloop()

    # ==================== Utilities ====================

    def _ui(self, fn: Callable):
        """Schedule a function to run on the UI thread."""
        self.root.after(0, fn)

    def run_async(self, label: str, fn: Callable, on_complete: Optional[Callable] = None):
        """Run a function asynchronously."""
        def worker():
            try:
                result = fn()
                if on_complete:
                    self._ui(lambda: on_complete(True, result))
            except Exception as e:
                if on_complete:
                    self._ui(lambda: on_complete(False, str(e)))
                else:
                    self._ui(lambda: messagebox.showerror("Error", str(e)))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def show_info(self, title: str, message: str):
        """Show info dialog."""
        messagebox.showinfo(title, message)

    def show_error(self, title: str, message: str):
        """Show error dialog."""
        messagebox.showerror(title, message)

    def show_warning(self, title: str, message: str):
        """Show warning dialog."""
        messagebox.showwarning(title, message)

    def ask_yes_no(self, title: str, message: str) -> bool:
        """Show yes/no dialog."""
        return messagebox.askyesno(title, message)

    def get_theme_color(self, key: str) -> str:
        """Get a color from the current theme."""
        return self.theme.get(key, '#000000')
