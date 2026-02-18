"""Control/Test tab for Super Sensor GUI."""

import tkinter as tk
from tkinter import ttk
import threading
import time
from typing import TYPE_CHECKING, Optional, Any

try:
    from ..widgets.radar_view import RadarView
    from ..widgets.color_picker import ColorPicker
    from ..widgets.scrollable_frame import ScrollableFrame
except ImportError:
    from widgets.radar_view import RadarView
    from widgets.color_picker import ColorPicker
    from widgets.scrollable_frame import ScrollableFrame

if TYPE_CHECKING:
    try:
        from ..app import SuperSensorApp
    except ImportError:
        from app import SuperSensorApp


class ControlTab(ttk.Frame):
    """
    Control and Test tab.

    Provides real-time sensor display and manual control of LED/servo.
    Uses throttled UI updates to prevent freezing during continuous scanning.
    """

    # UI update throttling settings
    MIN_UPDATE_INTERVAL_MS = 50  # Minimum 50ms between UI updates (max 20 FPS)

    def __init__(self, parent, app: 'SuperSensorApp'):
        super().__init__(parent)
        self.app = app
        self._polling = False

        # UI update throttling to prevent queue overflow
        self._pending_update = False  # Flag to track if update is scheduled
        self._latest_result: Optional[Any] = None  # Latest scan result
        self._last_update_time = 0  # Time of last UI update
        self._update_lock = threading.Lock()  # Protect throttling state

        self._build_ui()

        # Register callbacks
        self.app.controller.add_scan_callback(self._on_scan)

    def _build_ui(self):
        """Build the tab UI."""
        # Scrollable container
        self.scrollable = ScrollableFrame(self)
        self.scrollable.pack(fill='both', expand=True)

        # Main container
        main = ttk.Frame(self.scrollable.interior, padding=20)
        main.pack(fill='both', expand=True)

        # Top row - sensor display and LED control
        top_row = ttk.Frame(main)
        top_row.pack(fill='both', expand=True, pady=(0, 20))

        # Left side - Radar view
        radar_frame = ttk.LabelFrame(top_row, text='Sensor Display', padding=15)
        radar_frame.pack(side='left', fill='both', expand=True, padx=(0, 15))

        self.radar = RadarView(radar_frame, size=450)
        self.radar.pack(pady=10)

        # Right side - LED and Servo control
        controls_frame = ttk.Frame(top_row)
        controls_frame.pack(side='right', fill='y')

        # LED Control
        led_frame = ttk.LabelFrame(controls_frame, text='LED Control', padding=15)
        led_frame.pack(fill='x', pady=(0, 15))

        self.color_picker = ColorPicker(led_frame, on_change=self._on_color_change)
        self.color_picker.pack(fill='x')

        ttk.Button(
            led_frame,
            text='Apply Color',
            command=self._apply_color
        ).pack(pady=(10, 0))

        # Servo Control
        servo_frame = ttk.LabelFrame(controls_frame, text='Servo Control', padding=15)
        servo_frame.pack(fill='x')

        # Angle slider
        slider_frame = ttk.Frame(servo_frame)
        slider_frame.pack(fill='x', pady=(0, 10))

        ttk.Label(slider_frame, text='Angle:').pack(side='left')

        self.servo_var = tk.IntVar(value=90)
        self.servo_scale = ttk.Scale(
            slider_frame,
            from_=0,
            to=180,
            orient='horizontal',
            variable=self.servo_var,
            command=self._on_servo_change
        )
        self.servo_scale.pack(side='left', fill='x', expand=True, padx=10)

        self.servo_label = ttk.Label(slider_frame, text='90°', width=5)
        self.servo_label.pack(side='left')

        # Preset buttons
        preset_frame = ttk.Frame(servo_frame)
        preset_frame.pack(fill='x')

        for angle in [0, 45, 90, 135, 180]:
            ttk.Button(
                preset_frame,
                text=f'{angle}°',
                width=5,
                command=lambda a=angle: self._set_servo(a)
            ).pack(side='left', padx=2)

        # Sweep button
        ttk.Button(
            servo_frame,
            text='Sweep',
            command=self._sweep
        ).pack(pady=(10, 0))

        # Bottom row - Quick actions and polling
        bottom_row = ttk.Frame(main)
        bottom_row.pack(fill='x')

        # Polling controls
        poll_frame = ttk.LabelFrame(bottom_row, text='Continuous Scan', padding=15)
        poll_frame.pack(side='left', fill='x', expand=True, padx=(0, 15))

        poll_controls = ttk.Frame(poll_frame)
        poll_controls.pack(fill='x')

        self.poll_btn = ttk.Button(
            poll_controls,
            text='Start',
            command=self._toggle_polling
        )
        self.poll_btn.pack(side='left', padx=(0, 10))

        ttk.Label(poll_controls, text='Rate:').pack(side='left')

        self.rate_var = tk.StringVar(value='10 Hz')
        rate_combo = ttk.Combobox(
            poll_controls,
            textvariable=self.rate_var,
            values=['5 Hz', '10 Hz', '20 Hz'],
            width=8,
            state='readonly'
        )
        rate_combo.pack(side='left', padx=5)
        rate_combo.bind('<<ComboboxSelected>>', self._on_rate_change)

        # Quick actions
        actions_frame = ttk.LabelFrame(bottom_row, text='Quick Actions', padding=15)
        actions_frame.pack(side='right')

        ttk.Button(
            actions_frame,
            text='Scan Once',
            command=self._scan_once
        ).pack(side='left', padx=5)

        ttk.Button(
            actions_frame,
            text='Get Status',
            command=self._get_status
        ).pack(side='left', padx=5)

        ttk.Button(
            actions_frame,
            text='LED Off',
            command=self._led_off
        ).pack(side='left', padx=5)

    def _on_scan(self, result):
        """
        Handle scan results from controller (called from background thread).

        Uses throttling to prevent UI queue overflow:
        - Stores the latest result
        - Only schedules UI update if one isn't already pending
        - Skips updates if they come too fast
        """
        current_time = time.time() * 1000  # ms

        with self._update_lock:
            # Always store the latest result
            self._latest_result = result

            # Check if we should schedule an update
            time_since_last = current_time - self._last_update_time

            if time_since_last < self.MIN_UPDATE_INTERVAL_MS:
                # Too soon since last update - skip
                return

            if self._pending_update:
                # Update already scheduled - it will use the latest result
                return

            # Schedule update
            self._pending_update = True
            self._last_update_time = current_time

        # Schedule on UI thread (outside lock to prevent deadlock)
        try:
            self.app._ui(self._do_update)
        except Exception:
            # Reset flag if scheduling fails
            with self._update_lock:
                self._pending_update = False

    def _do_update(self):
        """
        Perform the actual UI update (runs on main thread).

        Gets the latest result and updates the display.
        """
        with self._update_lock:
            result = self._latest_result
            self._pending_update = False

        if result is not None:
            try:
                self.radar.update_readings(result)
            except Exception:
                pass  # Don't crash on display errors

    def _update_display(self, result):
        """Update display with scan results (for manual/single scans)."""
        try:
            self.radar.update_readings(result)
        except Exception:
            pass

    def _scan_once(self):
        """Perform a single scan."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Scan", "Not connected to sensor.")
            return

        result = self.app.controller.scan()
        if result:
            self._update_display(result)

    def _toggle_polling(self):
        """Toggle continuous polling."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Polling", "Not connected to sensor.")
            return

        if self._polling:
            self._polling = False
            self.app.controller.stop_polling()
            self.poll_btn.configure(text='Start')
        else:
            self._polling = True
            rate = int(self.rate_var.get().split()[0])
            interval = 1000 // rate
            self.app.controller.start_polling(interval)
            self.poll_btn.configure(text='Stop')

    def _on_rate_change(self, event):
        """Handle rate change."""
        if self._polling:
            rate = int(self.rate_var.get().split()[0])
            interval = 1000 // rate
            self.app.controller.set_poll_interval(interval)

    def _on_color_change(self, r, g, b):
        """Handle color picker change (live update disabled by default)."""
        pass  # Only update on Apply button

    def _apply_color(self):
        """Apply selected color to LED."""
        if not self.app.controller.is_connected:
            self.app.show_warning("LED", "Not connected to sensor.")
            return

        r, g, b = self.color_picker.get_color()
        self.app.controller.set_led(r, g, b)

    def _led_off(self):
        """Turn off LED."""
        if not self.app.controller.is_connected:
            return
        self.app.controller.set_led(0, 0, 0)
        self.color_picker.set_color(0, 0, 0)

    def _on_servo_change(self, value):
        """Handle servo slider change."""
        angle = int(float(value))
        self.servo_label.configure(text=f'{angle}°')

    def _set_servo(self, angle):
        """Set servo to specific angle."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Servo", "Not connected to sensor.")
            return

        self.servo_var.set(angle)
        self.servo_label.configure(text=f'{angle}°')
        self.app.controller.set_servo(angle)

    def _sweep(self):
        """Perform smooth servo sweep."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Sweep", "Not connected to sensor.")
            return

        def on_progress(angle, total):
            # Update servo display during sweep (throttled)
            self.app._ui(lambda a=angle: self._update_servo_display(a))

        def do_sweep():
            # Use smooth sweep for better motion
            return self.app.controller.smooth_sweep(
                start_angle=0,
                end_angle=180,
                step=1,
                delay_ms=10,
                progress_callback=on_progress
            )

        def on_complete(success, result):
            if success and result:
                # Update radar with the last scan from sweep
                if result and len(result) > 0:
                    center_reading = None
                    for reading in result:
                        if reading.get('angle') == 90:
                            center_reading = reading
                            break
                    if not center_reading:
                        center_reading = result[-1]

                    us = center_reading.get('us', [-1, -1, -1, -1])
                    # Mapping: us[0]=front_top, us[1]=left, us[2]=right, us[3]=front_bottom
                    self.app._ui(lambda: self.radar.update_readings(
                        front_top=us[0],
                        left=us[1],
                        right=us[2],
                        front_bottom=us[3]
                    ))
            # Return to center
            self.app._ui(lambda: self._set_servo(90))

        self.app.run_async("Smooth Sweep", do_sweep, on_complete)

    def _update_servo_display(self, angle):
        """Update servo display without sending command."""
        self.servo_var.set(angle)
        self.servo_label.configure(text=f'{angle}°')

    def _get_status(self):
        """Get full status and update display."""
        if not self.app.controller.is_connected:
            self.app.show_warning("Status", "Not connected to sensor.")
            return

        status = self.app.controller.get_status()
        if status:
            # Update radar display with ultrasonic readings
            # Mapping: us[0]=front_top, us[1]=left, us[2]=right, us[3]=front_bottom
            us = status.get('us', [-1, -1, -1, -1])
            if us and len(us) >= 4:
                self.radar.update_readings(
                    front_top=us[0],
                    left=us[1],
                    right=us[2],
                    front_bottom=us[3]
                )

            # Update servo display
            servo_angle = status.get('servo', 90)
            self.servo_var.set(servo_angle)
            self.servo_label.configure(text=f'{servo_angle}°')

            # Update LED display
            led = status.get('led', [0, 0, 0])
            if led and len(led) >= 3:
                self.color_picker.set_color(led[0], led[1], led[2])
