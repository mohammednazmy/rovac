"""Status/Info tab for Super Sensor GUI."""

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

try:
    from ..utils.platform_utils import PlatformUtils
    from ..widgets.scrollable_frame import ScrollableFrame
except ImportError:
    from utils.platform_utils import PlatformUtils
    from widgets.scrollable_frame import ScrollableFrame

if TYPE_CHECKING:
    try:
        from ..app import SuperSensorApp
    except ImportError:
        from app import SuperSensorApp


class StatusTab(ttk.Frame):
    """
    Status and Information tab.

    Shows connection status, device info, and system info.
    """

    def __init__(self, parent, app: 'SuperSensorApp'):
        super().__init__(parent)
        self.app = app

        self._build_ui()
        self._refresh_ports()

        # Auto-connect if Super Sensor is detected
        self._try_auto_connect()

    def _build_ui(self):
        """Build the tab UI."""
        # Scrollable container
        self.scrollable = ScrollableFrame(self)
        self.scrollable.pack(fill='both', expand=True)

        # Main container with generous padding
        main = ttk.Frame(self.scrollable.interior, padding=20)
        main.pack(fill='both', expand=True)

        # Connection section
        conn_frame = ttk.LabelFrame(main, text='Connection', padding=15)
        conn_frame.pack(fill='x', pady=(0, 20))

        # Port selection row
        port_row = ttk.Frame(conn_frame)
        port_row.pack(fill='x', pady=(0, 10))

        ttk.Label(port_row, text='Port:').pack(side='left', padx=(0, 10))

        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(
            port_row,
            textvariable=self.port_var,
            width=35,
            state='readonly',
            font=('Menlo', 12)
        )
        self.port_combo.pack(side='left', padx=(0, 15))

        ttk.Button(
            port_row,
            text='Refresh',
            command=self._refresh_ports
        ).pack(side='left', padx=(0, 10))

        # Connect/Disconnect buttons
        self.connect_btn = ttk.Button(
            port_row,
            text='Connect',
            command=self._connect
        )
        self.connect_btn.pack(side='left', padx=(0, 5))

        self.disconnect_btn = ttk.Button(
            port_row,
            text='Disconnect',
            command=self._disconnect,
            state='disabled'
        )
        self.disconnect_btn.pack(side='left')

        # Status display
        status_grid = ttk.Frame(conn_frame)
        status_grid.pack(fill='x')

        # Status fields
        self.status_vars = {}
        status_fields = [
            ('Status', 'status'),
            ('Port', 'port'),
            ('Ping Latency', 'latency'),
        ]

        for i, (label, key) in enumerate(status_fields):
            ttk.Label(status_grid, text=f'{label}:').grid(
                row=i, column=0, sticky='e', padx=(0, 10), pady=2
            )
            var = tk.StringVar(value='--')
            self.status_vars[key] = var
            ttk.Label(status_grid, textvariable=var).grid(
                row=i, column=1, sticky='w', pady=2
            )

        # Ping button
        ttk.Button(
            status_grid,
            text='Ping',
            command=self._ping
        ).grid(row=0, column=2, padx=(20, 0))

        # Device info section
        device_frame = ttk.LabelFrame(main, text='Device Information', padding=15)
        device_frame.pack(fill='x', pady=(0, 20))

        self.device_vars = {}
        device_fields = [
            ('Device', 'Super Sensor Module'),
            ('Firmware', '1.0.0'),
            ('Protocol', 'JSON Serial @ 115200'),
            ('Sensors', '4x HC-SR04 Ultrasonic'),
            ('Actuators', '1x RGB LED, 1x Servo'),
        ]

        for i, (label, default) in enumerate(device_fields):
            ttk.Label(device_frame, text=f'{label}:').grid(
                row=i, column=0, sticky='e', padx=(0, 10), pady=2
            )
            var = tk.StringVar(value=default)
            self.device_vars[label] = var
            ttk.Label(device_frame, textvariable=var).grid(
                row=i, column=1, sticky='w', pady=2
            )

        # System info section
        system_frame = ttk.LabelFrame(main, text='System Information', padding=15)
        system_frame.pack(fill='x', pady=(0, 20))

        self.system_vars = {}
        platform_info = PlatformUtils.get_platform_info()
        system_fields = [
            ('Platform', f"{platform_info['system']} ({platform_info['release']})"),
            ('Python', platform_info['python_version']),
            ('pyserial', PlatformUtils.get_pyserial_version() or 'Not installed'),
        ]

        for i, (label, value) in enumerate(system_fields):
            ttk.Label(system_frame, text=f'{label}:').grid(
                row=i, column=0, sticky='e', padx=(0, 10), pady=2
            )
            var = tk.StringVar(value=value)
            self.system_vars[label] = var
            ttk.Label(system_frame, textvariable=var).grid(
                row=i, column=1, sticky='w', pady=2
            )

        # Available ports section
        ports_frame = ttk.LabelFrame(main, text='Available Serial Ports', padding=15)
        ports_frame.pack(fill='both', expand=True)

        # Ports listbox
        list_frame = ttk.Frame(ports_frame)
        list_frame.pack(fill='both', expand=True)

        # Get theme colors from app
        theme = self.app.theme
        self.ports_list = tk.Listbox(
            list_frame,
            height=8,
            font=('Menlo', 12),
            bg=theme['listbox_bg'],
            fg=theme['listbox_fg'],
            selectbackground=theme['listbox_select_bg'],
            selectforeground=theme['listbox_select_fg'],
            relief='solid',
            borderwidth=1,
            highlightthickness=1,
            highlightbackground=theme['border'],
            highlightcolor=theme['accent']
        )
        self.ports_list.pack(side='left', fill='both', expand=True)

        scrollbar = ttk.Scrollbar(list_frame, command=self.ports_list.yview)
        scrollbar.pack(side='right', fill='y')
        self.ports_list.configure(yscrollcommand=scrollbar.set)

        # Buttons
        btn_frame = ttk.Frame(ports_frame)
        btn_frame.pack(fill='x', pady=(10, 0))

        ttk.Button(
            btn_frame,
            text='Refresh Ports',
            command=self._refresh_ports
        ).pack(side='left', padx=(0, 10))

        ttk.Button(
            btn_frame,
            text='Auto-Detect',
            command=self._auto_detect
        ).pack(side='left')

        # Register callbacks
        self.app.controller.add_status_callback(self._on_status_change)

    def _refresh_ports(self):
        """Refresh list of available ports."""
        ports = PlatformUtils.get_serial_ports()

        # Update combobox
        port_list = [p['device'] for p in ports]
        self.port_combo['values'] = port_list

        # Try to auto-detect Super Sensor port first
        sensor_port = PlatformUtils.find_super_sensor_port()
        if sensor_port and sensor_port in port_list:
            self.port_var.set(sensor_port)
        elif not self.port_var.get() and port_list:
            # Fall back to first port if none selected
            self.port_var.set(port_list[0])

        # Update listbox with highlighting for detected sensor
        self.ports_list.delete(0, tk.END)
        for port in ports:
            desc = port.get('description', '')
            vid_pid = f"({port['vid']}:{port['pid']})" if port.get('vid') else ''
            marker = " ← Super Sensor" if port['device'] == sensor_port else ''
            self.ports_list.insert(tk.END, f"{port['device']}  {desc}  {vid_pid}{marker}")

    def _auto_detect(self):
        """Auto-detect Super Sensor port."""
        port = PlatformUtils.find_super_sensor_port()
        if port:
            self.port_var.set(port)
            self.app.show_info("Auto-Detect", f"Found Super Sensor at {port}")
        else:
            self.app.show_warning("Auto-Detect", "Super Sensor not found. Make sure it's connected.")

    def _try_auto_connect(self):
        """Try to auto-connect if Super Sensor is detected."""
        port = PlatformUtils.find_super_sensor_port()
        if port:
            self.port_var.set(port)
            # Schedule auto-connect after UI is ready
            self.after(500, lambda: self._do_auto_connect(port))

    def _do_auto_connect(self, port):
        """Perform auto-connection."""
        self.connect_btn.configure(state='disabled')
        self.status_vars['status'].set('Connecting...')

        def do_connect():
            return self.app.controller.connect(port)

        def on_complete(success, result):
            if success:
                self.connect_btn.configure(state='disabled')
                self.disconnect_btn.configure(state='normal')
                # Silent auto-connect - no dialog, just update status
                self.status_vars['status'].set('Connected')
                self.status_vars['port'].set(port)
            else:
                self.connect_btn.configure(state='normal')
                self.status_vars['status'].set('Disconnected')

        self.app.run_async("Auto-Connect", do_connect, on_complete)

    def _connect(self):
        """Connect to selected port."""
        port = self.port_var.get()
        if not port:
            self.app.show_warning("Connect", "Please select a port first.")
            return

        self.connect_btn.configure(state='disabled')
        self.status_vars['status'].set('Connecting...')

        def do_connect():
            return self.app.controller.connect(port)

        def on_complete(success, result):
            if success:
                self.connect_btn.configure(state='disabled')
                self.disconnect_btn.configure(state='normal')
            else:
                self.connect_btn.configure(state='normal')
                self.app.show_error("Connection Failed", str(result))

        self.app.run_async("Connect", do_connect, on_complete)

    def _disconnect(self):
        """Disconnect from sensor."""
        self.app.controller.disconnect()
        self.connect_btn.configure(state='normal')
        self.disconnect_btn.configure(state='disabled')
        self.status_vars['status'].set('Disconnected')
        self.status_vars['port'].set('--')
        self.status_vars['latency'].set('--')

    def _ping(self):
        """Ping the sensor."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Ping", "Not connected to sensor.")
            return

        success, latency = self.app.controller.ping()
        if success:
            self.status_vars['latency'].set(f'{latency:.1f} ms')
        else:
            self.status_vars['latency'].set('Failed')

    def _on_status_change(self, status):
        """Handle status changes."""
        self.app._ui(lambda: self._update_status(status))

    def _update_status(self, status):
        """Update status display."""
        if status.connected:
            self.status_vars['status'].set('Connected')
            self.status_vars['port'].set(status.port)
            self.connect_btn.configure(state='disabled')
            self.disconnect_btn.configure(state='normal')
        else:
            self.status_vars['status'].set('Disconnected')
            self.status_vars['port'].set('--')
            self.connect_btn.configure(state='normal')
            self.disconnect_btn.configure(state='disabled')
