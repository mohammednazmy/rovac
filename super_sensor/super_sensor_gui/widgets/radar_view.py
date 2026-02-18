"""Optimized Radar-style visual display for ultrasonic sensors."""

import math
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional, Dict, Tuple
from collections import deque
import time


class RadarView(tk.Canvas):
    """
    Optimized visual radar-style display showing ultrasonic sensor readings.

    Performance optimizations:
    - Reuses canvas items instead of delete/recreate
    - Minimizes canvas operations
    - Caches computed values
    - Skips redundant redraws

    Features:
    - Radar sweep visualization with distance rings
    - Color-coded beams based on distance
    - Distance bars for each sensor
    - Warning indicators for obstacles
    - Min/max/avg statistics
    """

    # Sensor configuration
    SENSOR_CONFIG = {
        'front_top': {'angle': 15, 'label': 'FT', 'full_name': 'Front Top', 'index': 0},
        'front_bottom': {'angle': -15, 'label': 'FB', 'full_name': 'Front Bottom', 'index': 1},
        'left': {'angle': 90, 'label': 'L', 'full_name': 'Left', 'index': 2},
        'right': {'angle': -90, 'label': 'R', 'full_name': 'Right', 'index': 3},
    }

    # Color scheme
    COLORS = {
        'bg': '#0d1117',
        'grid': '#21262d',
        'grid_label': '#484f58',
        'robot': '#1f6feb',
        'robot_outline': '#58a6ff',
        'danger': '#f85149',
        'caution': '#d29922',
        'safe': '#3fb950',
        'invalid': '#484f58',
        'text': '#c9d1d9',
        'text_dim': '#8b949e',
    }

    # Distance thresholds (cm)
    DANGER_THRESHOLD = 30
    CAUTION_THRESHOLD = 60

    def __init__(self, parent, size: int = 400, max_range: int = 400, **kwargs):
        kwargs.setdefault('bg', self.COLORS['bg'])
        kwargs.setdefault('highlightthickness', 0)

        super().__init__(parent, width=size, height=size, **kwargs)

        self.size = size
        self.center_x = size // 2
        self.center_y = int(size * 0.55)
        self.max_range = max_range
        self.radar_radius = int(size * 0.38)

        # Current readings
        self._readings: Dict[str, int] = {
            'front_top': -1,
            'front_bottom': -1,
            'left': -1,
            'right': -1,
        }

        # Previous readings (for change detection)
        self._prev_readings: Dict[str, int] = dict(self._readings)

        # History for trends (limited size)
        self._history: Dict[str, deque] = {
            key: deque(maxlen=10) for key in self._readings
        }

        # Canvas item IDs for reuse (initialized to None)
        self._beam_items: Dict[str, int] = {}
        self._marker_items: Dict[str, int] = {}
        self._bar_fill_items: Dict[str, int] = {}
        self._distance_text_items: Dict[str, int] = {}
        self._status_text_item: Optional[int] = None
        self._stat_text_items: Dict[str, int] = {}

        # Create fonts
        self._create_fonts()

        # Draw static background once
        self._draw_background()

        # Create reusable sensor items
        self._create_sensor_items()

        # Create info panel items
        self._create_info_panel_items()

    def _create_fonts(self):
        """Create custom fonts for the display."""
        self.font_medium = tkfont.Font(family='Menlo', size=12, weight='bold')
        self.font_small = tkfont.Font(family='Menlo', size=10)
        self.font_tiny = tkfont.Font(family='Menlo', size=9)

    def _cm_to_pixels(self, cm: int) -> int:
        """Convert centimeters to pixel radius."""
        if cm <= 0:
            return self.radar_radius
        return int((min(cm, self.max_range) / self.max_range) * self.radar_radius)

    def _draw_background(self):
        """Draw static background elements (called once)."""
        # Range circles
        for distance in [100, 200, 300, 400]:
            if distance <= self.max_range:
                radius = self._cm_to_pixels(distance)
                self.create_oval(
                    self.center_x - radius, self.center_y - radius,
                    self.center_x + radius, self.center_y + radius,
                    outline=self.COLORS['grid'],
                    width=2 if distance % 100 == 0 else 1,
                    tags='static'
                )
                # Range label
                self.create_text(
                    self.center_x + radius - 20, self.center_y - 8,
                    text=f'{distance}cm',
                    fill=self.COLORS['grid_label'],
                    font=self.font_tiny,
                    tags='static'
                )

        # Danger zone circle
        danger_radius = self._cm_to_pixels(self.DANGER_THRESHOLD)
        self.create_oval(
            self.center_x - danger_radius, self.center_y - danger_radius,
            self.center_x + danger_radius, self.center_y + danger_radius,
            outline=self.COLORS['danger'],
            width=1,
            dash=(4, 2),
            tags='static'
        )

        # Sensor direction lines
        for name, config in self.SENSOR_CONFIG.items():
            angle = config['angle']
            rad = math.radians(90 - angle)
            x = self.center_x + self.radar_radius * math.cos(rad)
            y = self.center_y - self.radar_radius * math.sin(rad)
            self.create_line(
                self.center_x, self.center_y, x, y,
                fill=self.COLORS['grid'],
                dash=(1, 4),
                tags='static'
            )

        # Robot body
        robot_size = 18
        self.create_rectangle(
            self.center_x - robot_size, self.center_y - robot_size * 1.2,
            self.center_x + robot_size, self.center_y + robot_size * 1.2,
            fill=self.COLORS['robot'],
            outline=self.COLORS['robot_outline'],
            width=2,
            tags='static'
        )

        # Front indicator
        self.create_polygon(
            self.center_x, self.center_y - robot_size * 1.2 - 12,
            self.center_x - 8, self.center_y - robot_size * 1.2,
            self.center_x + 8, self.center_y - robot_size * 1.2,
            fill=self.COLORS['robot_outline'],
            tags='static'
        )

    def _create_sensor_items(self):
        """Create reusable canvas items for sensors."""
        for name, config in self.SENSOR_CONFIG.items():
            # Create beam line (initially hidden)
            self._beam_items[name] = self.create_line(
                0, 0, 0, 0,
                fill=self.COLORS['invalid'],
                width=2,
                tags='sensor'
            )

            # Create marker circle (initially hidden)
            self._marker_items[name] = self.create_oval(
                0, 0, 0, 0,
                fill=self.COLORS['invalid'],
                outline='white',
                width=2,
                tags='sensor'
            )

    def _create_info_panel_items(self):
        """Create reusable info panel items."""
        panel_y = 25
        bar_height = 12
        bar_width = 80

        # Title
        self.create_text(
            self.size // 2, panel_y - 10,
            text='ULTRASONIC SENSORS',
            fill=self.COLORS['text'],
            font=self.font_small,
            tags='static'
        )

        # Sensor bars and labels
        sensors = ['left', 'front_top', 'front_bottom', 'right']
        start_x = 25
        total_width = self.size - 50

        for i, name in enumerate(sensors):
            config = self.SENSOR_CONFIG[name]
            x = start_x + (i * total_width // 4) + 10
            y = panel_y + 10

            # Sensor label (static)
            self.create_text(
                x + bar_width // 2, y - 8,
                text=config['full_name'],
                fill=self.COLORS['text_dim'],
                font=self.font_tiny,
                tags='static'
            )

            # Background bar (static)
            self.create_rectangle(
                x, y, x + bar_width, y + bar_height,
                fill='#21262d',
                outline='#30363d',
                tags='static'
            )

            # Fill bar (dynamic - reusable)
            self._bar_fill_items[name] = self.create_rectangle(
                x, y, x, y + bar_height,
                fill=self.COLORS['safe'],
                outline='',
                tags='info'
            )

            # Distance text (dynamic - reusable)
            self._distance_text_items[name] = self.create_text(
                x + bar_width // 2, y + bar_height + 12,
                text='--',
                fill=self.COLORS['invalid'],
                font=self.font_medium,
                tags='info'
            )

        # Stats panel background
        stats_y = self.size - 55
        self.create_rectangle(
            10, stats_y - 5,
            self.size - 10, self.size - 10,
            fill='#161b22',
            outline='#30363d',
            tags='static'
        )

        # Status text (dynamic)
        self._status_text_item = self.create_text(
            self.size // 2, stats_y + 8,
            text='NO READING',
            fill=self.COLORS['invalid'],
            font=self.font_medium,
            tags='info'
        )

        # Statistics labels (static) and values (dynamic)
        stat_y = stats_y + 28
        stat_width = (self.size - 40) // 3

        for i, label in enumerate(['MIN', 'AVG', 'MAX']):
            x = 20 + i * stat_width + stat_width // 2

            # Label (static)
            self.create_text(
                x, stat_y - 8,
                text=label,
                fill=self.COLORS['text_dim'],
                font=self.font_tiny,
                tags='static'
            )

            # Value (dynamic)
            self._stat_text_items[label] = self.create_text(
                x, stat_y + 5,
                text='--',
                fill=self.COLORS['text'],
                font=self.font_small,
                tags='info'
            )

    def update_readings(self, scan_result=None, **kwargs):
        """
        Update sensor display with new readings.

        Optimized to only update changed values.
        """
        # Parse input
        # Mapping from firmware sensor names to physical positions:
        # - front_left (us[0]) → Front Top sensor
        # - front_right (us[1]) → Left sensor
        # - left (us[2]) → Right sensor
        # - right (us[3]) → Front Bottom sensor
        if scan_result is not None:
            new_readings = {
                'front_top': scan_result.front_left,      # us[0]
                'left': scan_result.front_right,          # us[1]
                'right': scan_result.left,                # us[2]
                'front_bottom': scan_result.right,        # us[3]
            }
        else:
            new_readings = dict(self._readings)
            for key in ['front_top', 'front_bottom', 'left', 'right']:
                if key in kwargs:
                    new_readings[key] = kwargs[key]

        # Check if anything changed
        if new_readings == self._readings:
            return  # No change, skip update

        # Update history for changed values
        for key, value in new_readings.items():
            if value > 0 and value != self._readings.get(key):
                self._history[key].append(value)

        # Store new readings
        self._prev_readings = dict(self._readings)
        self._readings = new_readings

        # Update display
        self._update_sensors()
        self._update_info_panel()

    def _get_distance_color(self, distance: int) -> str:
        """Get color based on distance."""
        if distance <= 0:
            return self.COLORS['invalid']
        elif distance < self.DANGER_THRESHOLD:
            return self.COLORS['danger']
        elif distance < self.CAUTION_THRESHOLD:
            return self.COLORS['caution']
        else:
            return self.COLORS['safe']

    def _update_sensors(self):
        """Update sensor beam positions and colors."""
        for name, distance in self._readings.items():
            config = self.SENSOR_CONFIG[name]
            angle = config['angle']
            color = self._get_distance_color(distance)

            rad = math.radians(90 - angle)
            pixel_radius = self._cm_to_pixels(distance) if distance > 0 else self.radar_radius

            x = self.center_x + pixel_radius * math.cos(rad)
            y = self.center_y - pixel_radius * math.sin(rad)

            # Update beam line
            self.coords(
                self._beam_items[name],
                self.center_x, self.center_y, x, y
            )
            self.itemconfigure(
                self._beam_items[name],
                fill=color,
                width=4 if distance > 0 and distance < 100 else 2
            )

            # Update marker
            if distance > 0:
                marker_size = 6
                self.coords(
                    self._marker_items[name],
                    x - marker_size, y - marker_size,
                    x + marker_size, y + marker_size
                )
                self.itemconfigure(
                    self._marker_items[name],
                    fill=color,
                    state='normal'
                )
            else:
                self.itemconfigure(self._marker_items[name], state='hidden')

    def _update_info_panel(self):
        """Update info panel values."""
        panel_y = 25
        bar_height = 12
        bar_width = 80
        sensors = ['left', 'front_top', 'front_bottom', 'right']
        start_x = 25
        total_width = self.size - 50

        for i, name in enumerate(sensors):
            distance = self._readings[name]
            color = self._get_distance_color(distance)
            x = start_x + (i * total_width // 4) + 10
            y = panel_y + 10

            # Update fill bar
            if distance > 0:
                fill_ratio = max(0, min(1, 1 - (distance / self.max_range)))
                fill_width = int(bar_width * fill_ratio)
                self.coords(
                    self._bar_fill_items[name],
                    x, y, x + max(1, fill_width), y + bar_height
                )
                self.itemconfigure(self._bar_fill_items[name], fill=color, state='normal')
            else:
                self.itemconfigure(self._bar_fill_items[name], state='hidden')

            # Update distance text
            dist_text = f'{distance}cm' if distance > 0 else '--'
            self.itemconfigure(
                self._distance_text_items[name],
                text=dist_text,
                fill=color
            )

        # Calculate statistics
        valid = [d for d in self._readings.values() if d > 0]
        min_dist = min(valid) if valid else -1
        max_dist = max(valid) if valid else -1
        avg_dist = int(sum(valid) / len(valid)) if valid else -1

        # Update status
        if min_dist <= 0:
            status_text = "NO READING"
            status_color = self.COLORS['invalid']
        elif min_dist < self.DANGER_THRESHOLD:
            status_text = "⚠ OBSTACLE"
            status_color = self.COLORS['danger']
        elif min_dist < self.CAUTION_THRESHOLD:
            status_text = "CAUTION"
            status_color = self.COLORS['caution']
        else:
            status_text = "CLEAR"
            status_color = self.COLORS['safe']

        self.itemconfigure(
            self._status_text_item,
            text=status_text,
            fill=status_color
        )

        # Update statistics
        stats = [
            ('MIN', min_dist, self._get_distance_color(min_dist)),
            ('AVG', avg_dist, self.COLORS['text']),
            ('MAX', max_dist, self._get_distance_color(max_dist)),
        ]

        for label, value, color in stats:
            value_text = f'{value}cm' if value > 0 else '--'
            self.itemconfigure(
                self._stat_text_items[label],
                text=value_text,
                fill=color
            )

    def get_min_distance(self) -> int:
        """Get minimum valid distance from all sensors."""
        valid = [d for d in self._readings.values() if d > 0]
        return min(valid) if valid else -1

    def has_obstacle(self, threshold: int = 30) -> bool:
        """Check if any sensor detects an obstacle within threshold."""
        min_dist = self.get_min_distance()
        return min_dist > 0 and min_dist < threshold

    def get_all_readings(self) -> Dict[str, int]:
        """Get all current readings."""
        return dict(self._readings)

    def get_statistics(self) -> Dict[str, int]:
        """Get computed statistics."""
        valid = [d for d in self._readings.values() if d > 0]
        return {
            'min': min(valid) if valid else -1,
            'max': max(valid) if valid else -1,
            'avg': int(sum(valid) / len(valid)) if valid else -1,
            'count': len(valid),
        }
