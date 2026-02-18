"""Calibration tab for Super Sensor GUI."""

import json
import tkinter as tk
from tkinter import ttk, filedialog
from typing import TYPE_CHECKING, Dict, Any
from pathlib import Path

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


class CalibrationTab(ttk.Frame):
    """
    Calibration tab.

    Allows testing individual components and saving calibration profiles.
    Features:
    - Individual sensor testing with offset calibration
    - LED channel testing
    - Servo calibration with min/center/max positions
    - Profile save/load functionality
    - Context menu support
    """

    # Sensor names matching the physical orientation and firmware order:
    # - us[0] (front_left)  → Front-Top: Forward-facing sensor at top of module
    # - us[1] (front_right) → Left: Side-facing sensor pointing left
    # - us[2] (left)        → Right: Side-facing sensor pointing right
    # - us[3] (right)       → Front-Bottom: Forward-facing sensor at bottom of module
    SENSOR_NAMES = ['Front-Top', 'Left', 'Right', 'Front-Bottom']

    def __init__(self, parent, app: 'SuperSensorApp'):
        super().__init__(parent)
        self.app = app

        # Get theme colors
        self.theme = app.theme

        # Calibration data
        self.calibration = {
            'sensor_offsets': [0, 0, 0, 0],
            'servo_min': 0,
            'servo_center': 90,
            'servo_max': 180,
        }

        self._build_ui()
        self._build_context_menus()

    def _build_ui(self):
        """Build the tab UI."""
        # Scrollable container
        self.scrollable = ScrollableFrame(self)
        self.scrollable.pack(fill='both', expand=True)

        # Main container
        main = ttk.Frame(self.scrollable.interior, padding=20)
        main.pack(fill='both', expand=True)

        # Profile management
        profile_frame = ttk.Frame(main)
        profile_frame.pack(fill='x', pady=(0, 20))

        ttk.Label(profile_frame, text='Profile:').pack(side='left', padx=(0, 10))

        self.profile_var = tk.StringVar(value='Default')
        self.profile_combo = ttk.Combobox(
            profile_frame,
            textvariable=self.profile_var,
            values=['Default'],
            width=20
        )
        self.profile_combo.pack(side='left', padx=(0, 10))

        ttk.Button(
            profile_frame,
            text='Load',
            command=self._load_profile
        ).pack(side='left', padx=2)

        ttk.Button(
            profile_frame,
            text='Save',
            command=self._save_profile
        ).pack(side='left', padx=2)

        ttk.Button(
            profile_frame,
            text='Save As...',
            command=self._save_profile_as
        ).pack(side='left', padx=2)

        # Sensor testing section
        sensor_frame = ttk.LabelFrame(main, text='Ultrasonic Sensor Testing', padding=15)
        sensor_frame.pack(fill='x', pady=(0, 20))

        # Colors from theme
        bg_color = self.theme['bg']
        fg_color = self.theme['fg']

        # Create a inner frame for grid content
        sensor_grid = ttk.Frame(sensor_frame)
        sensor_grid.pack(fill='x')

        # Create header
        headers = ['Sensor', 'Reading', 'Offset', 'Corrected', 'Status', 'Test']
        for i, header in enumerate(headers):
            tk.Label(sensor_grid, text=header, font=('SF Pro Display', 12, 'bold'),
                    bg=bg_color, fg=fg_color).grid(
                row=0, column=i, padx=8, pady=(0, 8), sticky='w'
            )

        # Create sensor rows
        self.sensor_vars = []
        self.offset_vars = []
        self.corrected_vars = []
        self.status_vars = []

        for i, name in enumerate(self.SENSOR_NAMES):
            row = i + 1

            # Name
            tk.Label(sensor_grid, text=name, font=('SF Pro Text', 13),
                    bg=bg_color, fg=fg_color).grid(
                row=row, column=0, padx=8, pady=4, sticky='w'
            )

            # Reading
            reading_var = tk.StringVar(value='-- cm')
            self.sensor_vars.append(reading_var)
            tk.Label(sensor_grid, textvariable=reading_var, width=10,
                    font=('SF Mono', 12), bg=bg_color, fg=fg_color).grid(
                row=row, column=1, padx=8, pady=4
            )

            # Offset spinbox
            offset_var = tk.IntVar(value=0)
            self.offset_vars.append(offset_var)
            offset_spin = ttk.Spinbox(
                sensor_grid,
                from_=-50,
                to=50,
                width=8,
                textvariable=offset_var,
                command=lambda idx=i: self._on_offset_change(idx)
            )
            offset_spin.grid(row=row, column=2, padx=8, pady=4)

            # Corrected
            corrected_var = tk.StringVar(value='-- cm')
            self.corrected_vars.append(corrected_var)
            tk.Label(sensor_grid, textvariable=corrected_var, width=10,
                    font=('SF Mono', 12), bg=bg_color, fg=fg_color).grid(
                row=row, column=3, padx=8, pady=4
            )

            # Status indicator
            status_var = tk.StringVar(value='--')
            self.status_vars.append(status_var)
            tk.Label(sensor_grid, textvariable=status_var, width=6,
                    font=('SF Pro Text', 12, 'bold'), bg=bg_color, fg=fg_color).grid(
                row=row, column=4, padx=8, pady=4
            )

            # Test button
            ttk.Button(
                sensor_grid,
                text='Test',
                width=8,
                command=lambda idx=i: self._test_sensor(idx)
            ).grid(row=row, column=5, padx=8, pady=4)

        # Test all button
        ttk.Button(
            sensor_grid,
            text='Test All Sensors',
            command=self._test_all_sensors
        ).grid(row=len(self.SENSOR_NAMES) + 1, column=0, columnspan=6, pady=(10, 0))

        # LED testing section
        led_frame = ttk.LabelFrame(main, text='LED Channel Testing', padding=15)
        led_frame.pack(fill='x', pady=(0, 20))

        led_controls = ttk.Frame(led_frame)
        led_controls.pack(fill='x')

        for i, (color, name) in enumerate([('R', 'Red'), ('G', 'Green'), ('B', 'Blue')]):
            ttk.Button(
                led_controls,
                text=f'Test {name}',
                command=lambda c=color: self._test_led_channel(c)
            ).pack(side='left', padx=5)

        ttk.Button(
            led_controls,
            text='Test All',
            command=self._test_all_leds
        ).pack(side='left', padx=5)

        ttk.Button(
            led_controls,
            text='Rainbow Cycle',
            command=self._rainbow_cycle
        ).pack(side='left', padx=5)

        ttk.Button(
            led_controls,
            text='LED Off',
            command=self._led_off
        ).pack(side='right', padx=5)

        # Servo calibration section
        servo_frame = ttk.LabelFrame(main, text='Servo Calibration', padding=15)
        servo_frame.pack(fill='x')

        servo_grid = ttk.Frame(servo_frame)
        servo_grid.pack(fill='x')

        # Min angle
        tk.Label(servo_grid, text='Minimum Angle:', font=('SF Pro Text', 13),
                bg=bg_color, fg=fg_color).grid(
            row=0, column=0, padx=8, pady=8, sticky='e'
        )
        self.servo_min_var = tk.IntVar(value=0)
        ttk.Spinbox(
            servo_grid,
            from_=0,
            to=90,
            width=8,
            textvariable=self.servo_min_var
        ).grid(row=0, column=1, padx=8, pady=8)
        ttk.Button(
            servo_grid,
            text='Test Min',
            command=lambda: self._test_servo_position('min')
        ).grid(row=0, column=2, padx=8, pady=8)

        # Center angle
        tk.Label(servo_grid, text='Center Angle:', font=('SF Pro Text', 13),
                bg=bg_color, fg=fg_color).grid(
            row=1, column=0, padx=8, pady=8, sticky='e'
        )
        self.servo_center_var = tk.IntVar(value=90)
        ttk.Spinbox(
            servo_grid,
            from_=45,
            to=135,
            width=8,
            textvariable=self.servo_center_var
        ).grid(row=1, column=1, padx=8, pady=8)
        ttk.Button(
            servo_grid,
            text='Test Center',
            command=lambda: self._test_servo_position('center')
        ).grid(row=1, column=2, padx=8, pady=8)

        # Max angle
        tk.Label(servo_grid, text='Maximum Angle:', font=('SF Pro Text', 13),
                bg=bg_color, fg=fg_color).grid(
            row=2, column=0, padx=8, pady=8, sticky='e'
        )
        self.servo_max_var = tk.IntVar(value=180)
        ttk.Spinbox(
            servo_grid,
            from_=90,
            to=180,
            width=8,
            textvariable=self.servo_max_var
        ).grid(row=2, column=1, padx=8, pady=8)
        ttk.Button(
            servo_grid,
            text='Test Max',
            command=lambda: self._test_servo_position('max')
        ).grid(row=2, column=2, padx=8, pady=8)

        # Full sweep
        ttk.Button(
            servo_grid,
            text='Test Full Sweep',
            command=self._test_servo_sweep
        ).grid(row=3, column=0, columnspan=3, pady=(10, 0))

    def _build_context_menus(self):
        """Build context menus for right-click actions."""
        # Sensor context menu
        self.sensor_context_menu = tk.Menu(self, tearoff=0)
        self.sensor_context_menu.add_command(label="Test All Sensors",
                                             command=self._test_all_sensors)
        self.sensor_context_menu.add_command(label="Reset All Offsets",
                                             command=self._reset_all_offsets)
        self.sensor_context_menu.add_separator()
        self.sensor_context_menu.add_command(label="Copy Values",
                                             command=self._copy_sensor_values)

        # LED context menu
        self.led_context_menu = tk.Menu(self, tearoff=0)
        self.led_context_menu.add_command(label="Test Red", command=lambda: self._test_led_channel('R'))
        self.led_context_menu.add_command(label="Test Green", command=lambda: self._test_led_channel('G'))
        self.led_context_menu.add_command(label="Test Blue", command=lambda: self._test_led_channel('B'))
        self.led_context_menu.add_separator()
        self.led_context_menu.add_command(label="Rainbow Cycle", command=self._rainbow_cycle)
        self.led_context_menu.add_command(label="LED Off", command=self._led_off)

        # Servo context menu
        self.servo_context_menu = tk.Menu(self, tearoff=0)
        self.servo_context_menu.add_command(label="Test Min", command=lambda: self._test_servo_position('min'))
        self.servo_context_menu.add_command(label="Test Center", command=lambda: self._test_servo_position('center'))
        self.servo_context_menu.add_command(label="Test Max", command=lambda: self._test_servo_position('max'))
        self.servo_context_menu.add_separator()
        self.servo_context_menu.add_command(label="Full Sweep", command=self._test_servo_sweep)
        self.servo_context_menu.add_command(label="Reset to Defaults", command=self._reset_servo_defaults)

        # Profile context menu
        self.profile_context_menu = tk.Menu(self, tearoff=0)
        self.profile_context_menu.add_command(label="Load Profile", command=self._load_profile)
        self.profile_context_menu.add_command(label="Save Profile", command=self._save_profile)
        self.profile_context_menu.add_command(label="Save As...", command=self._save_profile_as)
        self.profile_context_menu.add_separator()
        self.profile_context_menu.add_command(label="Reset to Defaults", command=self._reset_to_defaults)

        # Bind right-click to show context menus
        self.bind('<Button-2>', self._show_context_menu)  # macOS right-click
        self.bind('<Button-3>', self._show_context_menu)  # Linux/Windows right-click

    def _show_context_menu(self, event):
        """Show appropriate context menu based on click location."""
        # Show profile context menu as default
        try:
            self.profile_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.profile_context_menu.grab_release()

    def _reset_all_offsets(self):
        """Reset all sensor offsets to zero."""
        for var in self.offset_vars:
            var.set(0)
        for i in range(len(self.SENSOR_NAMES)):
            self.calibration['sensor_offsets'][i] = 0

    def _copy_sensor_values(self):
        """Copy sensor values to clipboard."""
        values = []
        for i, name in enumerate(self.SENSOR_NAMES):
            reading = self.sensor_vars[i].get()
            offset = self.offset_vars[i].get()
            corrected = self.corrected_vars[i].get()
            values.append(f"{name}: {reading} (offset: {offset}, corrected: {corrected})")

        text = "\n".join(values)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.show_info("Copied", "Sensor values copied to clipboard")

    def _reset_servo_defaults(self):
        """Reset servo to default values."""
        self.servo_min_var.set(0)
        self.servo_center_var.set(90)
        self.servo_max_var.set(180)

    def _reset_to_defaults(self):
        """Reset all calibration to defaults."""
        self._reset_all_offsets()
        self._reset_servo_defaults()
        self.profile_var.set('Default')
        self.app.show_info("Reset", "Calibration reset to defaults")

    def _on_offset_change(self, idx: int):
        """Handle offset value change."""
        self.calibration['sensor_offsets'][idx] = self.offset_vars[idx].get()

    def _test_sensor(self, idx: int):
        """Test a single sensor."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Test", "Not connected to sensor.")
            return

        result = self.app.controller.scan()
        if result:
            readings = [result.front_left, result.front_right, result.left, result.right]
            self._update_sensor_display(idx, readings[idx])

    def _test_all_sensors(self):
        """Test all sensors."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Test", "Not connected to sensor.")
            return

        result = self.app.controller.scan()
        if result:
            # Use explicit property access to match _test_sensor behavior
            # Mapping: SENSOR_NAMES[0]='Front-Top', [1]='Left', [2]='Right', [3]='Front-Bottom'
            self._update_sensor_display(0, result.front_left)   # Front-Top <- us[0]
            self._update_sensor_display(1, result.front_right)  # Left <- us[1]
            self._update_sensor_display(2, result.left)         # Right <- us[2]
            self._update_sensor_display(3, result.right)        # Front-Bottom <- us[3]

    def _update_sensor_display(self, idx: int, reading: int):
        """Update sensor display for given index."""
        self.sensor_vars[idx].set(f'{reading} cm' if reading > 0 else '-- cm')

        offset = self.offset_vars[idx].get()
        corrected = reading + offset if reading > 0 else -1
        self.corrected_vars[idx].set(f'{corrected} cm' if corrected > 0 else '-- cm')

        if reading <= 0:
            self.status_vars[idx].set('FAIL')
        elif reading < 5 or reading > 350:
            self.status_vars[idx].set('WARN')
        else:
            self.status_vars[idx].set('OK')

    def _test_led_channel(self, channel: str):
        """Test a single LED channel."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Test", "Not connected to sensor.")
            return

        colors = {'R': (255, 0, 0), 'G': (0, 255, 0), 'B': (0, 0, 255)}
        r, g, b = colors.get(channel, (0, 0, 0))
        self.app.controller.set_led(r, g, b)

    def _test_all_leds(self):
        """Test all LED channels sequentially."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Test", "Not connected to sensor.")
            return

        import time

        def do_test():
            colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
            for r, g, b in colors:
                self.app._ui(lambda r=r, g=g, b=b: self.app.controller.set_led(r, g, b))
                time.sleep(0.5)
            self.app._ui(lambda: self.app.controller.set_led(0, 0, 0))

        self.app.run_async("LED Test", do_test)

    def _rainbow_cycle(self):
        """Run rainbow color cycle."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Test", "Not connected to sensor.")
            return

        import time

        def do_rainbow():
            # Simple rainbow cycle
            colors = [
                (255, 0, 0),    # Red
                (255, 127, 0),  # Orange
                (255, 255, 0),  # Yellow
                (0, 255, 0),    # Green
                (0, 255, 255),  # Cyan
                (0, 0, 255),    # Blue
                (127, 0, 255),  # Purple
                (255, 0, 255),  # Magenta
            ]
            for _ in range(2):  # 2 cycles
                for r, g, b in colors:
                    self.app._ui(lambda r=r, g=g, b=b: self.app.controller.set_led(r, g, b))
                    time.sleep(0.2)
            self.app._ui(lambda: self.app.controller.set_led(0, 0, 0))

        self.app.run_async("Rainbow", do_rainbow)

    def _led_off(self):
        """Turn off LED."""
        if self.app.controller.is_connected:
            self.app.controller.set_led(0, 0, 0)

    def _test_servo_position(self, position: str):
        """Test servo at calibrated position."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Test", "Not connected to sensor.")
            return

        if position == 'min':
            angle = self.servo_min_var.get()
        elif position == 'center':
            angle = self.servo_center_var.get()
        elif position == 'max':
            angle = self.servo_max_var.get()
        else:
            return

        self.app.controller.set_servo(angle)

    def _test_servo_sweep(self):
        """Test full servo sweep."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Test", "Not connected to sensor.")
            return

        min_angle = self.servo_min_var.get()
        max_angle = self.servo_max_var.get()
        center = self.servo_center_var.get()

        import time

        def do_sweep():
            # Go to min
            self.app._ui(lambda: self.app.controller.set_servo(min_angle))
            time.sleep(0.5)
            # Sweep to max
            for angle in range(min_angle, max_angle + 1, 5):
                self.app._ui(lambda a=angle: self.app.controller.set_servo(a))
                time.sleep(0.05)
            time.sleep(0.3)
            # Return to center
            self.app._ui(lambda: self.app.controller.set_servo(center))

        self.app.run_async("Servo Sweep", do_sweep)

    def _get_profile_dir(self) -> Path:
        """Get calibration profiles directory."""
        config_dir = PlatformUtils.get_config_dir()
        profiles_dir = config_dir / 'calibration_profiles'
        profiles_dir.mkdir(parents=True, exist_ok=True)
        return profiles_dir

    def _save_profile(self):
        """Save current profile."""
        profile_name = self.profile_var.get()
        if not profile_name:
            self._save_profile_as()
            return

        self._do_save_profile(profile_name)

    def _save_profile_as(self):
        """Save profile with new name."""
        profile_dir = self._get_profile_dir()
        filepath = filedialog.asksaveasfilename(
            initialdir=str(profile_dir),
            defaultextension='.json',
            filetypes=[('JSON files', '*.json'), ('All files', '*.*')]
        )

        if filepath:
            profile_name = Path(filepath).stem
            self.profile_var.set(profile_name)
            self._do_save_profile(profile_name)

    def _do_save_profile(self, name: str):
        """Actually save the profile."""
        profile_dir = self._get_profile_dir()
        filepath = profile_dir / f'{name}.json'

        # Update calibration from UI
        self.calibration['sensor_offsets'] = [v.get() for v in self.offset_vars]
        self.calibration['servo_min'] = self.servo_min_var.get()
        self.calibration['servo_center'] = self.servo_center_var.get()
        self.calibration['servo_max'] = self.servo_max_var.get()

        with open(filepath, 'w') as f:
            json.dump(self.calibration, f, indent=2)

        self.app.show_info("Save Profile", f"Profile saved: {name}")

    def _load_profile(self):
        """Load a profile."""
        profile_dir = self._get_profile_dir()
        filepath = filedialog.askopenfilename(
            initialdir=str(profile_dir),
            filetypes=[('JSON files', '*.json'), ('All files', '*.*')]
        )

        if filepath:
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)

                # Update UI from loaded data
                for i, offset in enumerate(data.get('sensor_offsets', [0, 0, 0, 0])):
                    if i < len(self.offset_vars):
                        self.offset_vars[i].set(offset)

                self.servo_min_var.set(data.get('servo_min', 0))
                self.servo_center_var.set(data.get('servo_center', 90))
                self.servo_max_var.set(data.get('servo_max', 180))

                self.calibration = data
                self.profile_var.set(Path(filepath).stem)

                self.app.show_info("Load Profile", f"Profile loaded: {Path(filepath).stem}")

            except Exception as e:
                self.app.show_error("Load Profile", f"Failed to load profile: {e}")
