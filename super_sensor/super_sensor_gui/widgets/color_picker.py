"""RGB Color Picker widget for LED control."""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Tuple


class ColorPicker(ttk.Frame):
    """
    RGB color picker with sliders and preview.

    Features:
    - Separate R, G, B sliders (0-255)
    - Color preview square
    - Preset color buttons
    - Optional callback on color change
    """

    # Preset colors
    PRESETS = [
        ('Red', (255, 0, 0)),
        ('Green', (0, 255, 0)),
        ('Blue', (0, 0, 255)),
        ('Yellow', (255, 255, 0)),
        ('Cyan', (0, 255, 255)),
        ('Magenta', (255, 0, 255)),
        ('White', (255, 255, 255)),
        ('Off', (0, 0, 0)),
    ]

    def __init__(
        self,
        parent,
        on_change: Optional[Callable[[int, int, int], None]] = None,
        **kwargs
    ):
        """
        Initialize ColorPicker.

        Args:
            parent: Parent widget
            on_change: Callback function(r, g, b) called when color changes
        """
        super().__init__(parent, **kwargs)

        self.on_change = on_change

        # Color variables
        self.r_var = tk.IntVar(value=0)
        self.g_var = tk.IntVar(value=0)
        self.b_var = tk.IntVar(value=0)

        # Track changes
        self.r_var.trace_add('write', self._on_value_change)
        self.g_var.trace_add('write', self._on_value_change)
        self.b_var.trace_add('write', self._on_value_change)

        self._build_ui()

    def _build_ui(self):
        """Build the UI."""
        # Main container
        main_frame = ttk.Frame(self)
        main_frame.pack(fill='both', expand=True, padx=5, pady=5)

        # Sliders frame
        sliders_frame = ttk.Frame(main_frame)
        sliders_frame.pack(fill='x', pady=(0, 10))

        # Red slider
        self._create_slider(sliders_frame, 'R', self.r_var, '#ff4444', 0)
        # Green slider
        self._create_slider(sliders_frame, 'G', self.g_var, '#44ff44', 1)
        # Blue slider
        self._create_slider(sliders_frame, 'B', self.b_var, '#4444ff', 2)

        # Preview and presets frame
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill='x')

        # Color preview
        preview_frame = ttk.LabelFrame(bottom_frame, text='Preview')
        preview_frame.pack(side='left', padx=(0, 10))

        self.preview_canvas = tk.Canvas(
            preview_frame,
            width=60,
            height=60,
            bg='black',
            highlightthickness=1,
            highlightbackground='#555'
        )
        self.preview_canvas.pack(padx=5, pady=5)

        # Hex value display
        self.hex_var = tk.StringVar(value='#000000')
        ttk.Label(preview_frame, textvariable=self.hex_var).pack(pady=(0, 5))

        # Presets frame
        presets_frame = ttk.LabelFrame(bottom_frame, text='Presets')
        presets_frame.pack(side='left', fill='both', expand=True)

        # Create preset color swatches using Canvas (works on macOS)
        for i, (name, color) in enumerate(self.PRESETS):
            row = i // 4
            col = i % 4

            # Container frame for swatch + label
            swatch_frame = ttk.Frame(presets_frame)
            swatch_frame.grid(row=row, column=col, padx=4, pady=4, sticky='nsew')

            # Color swatch using Canvas (macOS compatible)
            hex_color = f'#{color[0]:02x}{color[1]:02x}{color[2]:02x}'
            swatch = tk.Canvas(
                swatch_frame,
                width=50,
                height=30,
                bg=hex_color,
                highlightthickness=2,
                highlightbackground='#666',
                cursor='hand2'
            )
            swatch.pack(pady=(0, 2))

            # Add border effect for "Off" (black) preset
            if sum(color) == 0:
                swatch.configure(highlightbackground='#888')

            # Bind click events
            swatch.bind('<Button-1>', lambda e, c=color: self.set_color(*c))
            swatch.bind('<Enter>', lambda e, s=swatch: s.configure(highlightbackground='#0078d4'))
            swatch.bind('<Leave>', lambda e, s=swatch, c=color: s.configure(
                highlightbackground='#888' if sum(c) == 0 else '#666'
            ))

            # Label below swatch
            text_color = 'white' if sum(color) < 384 else 'black'
            ttk.Label(
                swatch_frame,
                text=name,
                font=('SF Pro Text', 11),
                anchor='center'
            ).pack()

        # Configure grid
        for i in range(4):
            presets_frame.columnconfigure(i, weight=1)

    def _create_slider(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.IntVar,
        color: str,
        row: int
    ):
        """Create a labeled slider."""
        # Label
        ttk.Label(parent, text=f'{label}:', width=3).grid(
            row=row, column=0, padx=(0, 5), sticky='e'
        )

        # Slider
        slider = ttk.Scale(
            parent,
            from_=0,
            to=255,
            orient='horizontal',
            variable=variable,
            command=lambda v: variable.set(int(float(v)))
        )
        slider.grid(row=row, column=1, sticky='ew', padx=5)

        # Value display
        value_label = ttk.Label(parent, textvariable=variable, width=4)
        value_label.grid(row=row, column=2, padx=(5, 0))

        # Configure column weights
        parent.columnconfigure(1, weight=1)

    def _on_value_change(self, *args):
        """Handle slider value changes."""
        self._update_preview()

        if self.on_change:
            r, g, b = self.get_color()
            self.on_change(r, g, b)

    def _update_preview(self):
        """Update color preview."""
        r, g, b = self.get_color()
        color = f'#{r:02x}{g:02x}{b:02x}'

        self.preview_canvas.configure(bg=color)
        self.hex_var.set(color.upper())

    def get_color(self) -> Tuple[int, int, int]:
        """Get current RGB color values."""
        return (
            self.r_var.get(),
            self.g_var.get(),
            self.b_var.get()
        )

    def set_color(self, r: int, g: int, b: int):
        """Set RGB color values."""
        self.r_var.set(max(0, min(255, r)))
        self.g_var.set(max(0, min(255, g)))
        self.b_var.set(max(0, min(255, b)))


class LEDPreview(tk.Canvas):
    """Simple LED color preview widget."""

    def __init__(self, parent, size: int = 30, **kwargs):
        kwargs.setdefault('highlightthickness', 0)
        super().__init__(parent, width=size, height=size, **kwargs)

        self.size = size
        self._color = (0, 0, 0)
        self._draw()

    def _draw(self):
        """Draw the LED."""
        self.delete('all')

        r, g, b = self._color
        color = f'#{r:02x}{g:02x}{b:02x}'

        # Draw outer ring
        self.create_oval(
            2, 2, self.size - 2, self.size - 2,
            fill='#333',
            outline='#555'
        )

        # Draw LED center
        margin = 5
        self.create_oval(
            margin, margin,
            self.size - margin, self.size - margin,
            fill=color,
            outline=''
        )

        # Draw highlight (for 3D effect)
        if sum(self._color) > 0:
            highlight_size = self.size // 4
            self.create_oval(
                margin + 3, margin + 3,
                margin + highlight_size, margin + highlight_size,
                fill=self._lighten(color),
                outline=''
            )

    def _lighten(self, color: str) -> str:
        """Lighten a color for highlight effect."""
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)

        r = min(255, r + 80)
        g = min(255, g + 80)
        b = min(255, b + 80)

        return f'#{r:02x}{g:02x}{b:02x}'

    def set_color(self, r: int, g: int, b: int):
        """Set LED color."""
        self._color = (r, g, b)
        self._draw()
