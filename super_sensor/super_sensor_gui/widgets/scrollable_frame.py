"""Scrollable frame widget with trackpad/mousewheel support."""

import tkinter as tk
from tkinter import ttk
import sys


class ScrollableFrame(ttk.Frame):
    """
    A scrollable frame that supports smooth mousewheel/trackpad scrolling.

    Usage:
        scrollable = ScrollableFrame(parent)
        scrollable.pack(fill='both', expand=True)

        # Add widgets to scrollable.interior
        ttk.Label(scrollable.interior, text="Hello").pack()
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)

        # Create interior frame
        self.interior = ttk.Frame(self.canvas)

        # Create window inside canvas
        self.interior_id = self.canvas.create_window(
            (0, 0),
            window=self.interior,
            anchor='nw'
        )

        # Configure canvas
        self.canvas.configure(yscrollcommand=self._on_scroll)

        # Layout
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scrollbar.pack(side='right', fill='y')

        # Bind events
        self.interior.bind('<Configure>', self._on_interior_configure)
        self.canvas.bind('<Configure>', self._on_canvas_configure)

        # Bind mousewheel/trackpad globally for this widget
        self._bind_mousewheel()

        # Track if content is scrollable
        self._scrollable = False

    def _on_scroll(self, *args):
        """Handle scrollbar updates."""
        self.scrollbar.set(*args)
        # Check if content is scrollable
        if len(args) >= 2:
            self._scrollable = float(args[0]) > 0 or float(args[1]) < 1

    def _on_interior_configure(self, event):
        """Update scroll region when interior size changes."""
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _on_canvas_configure(self, event):
        """Update interior width when canvas size changes."""
        self.canvas.itemconfig(self.interior_id, width=event.width)

    def _bind_mousewheel(self):
        """Bind mousewheel/trackpad scrolling."""
        if sys.platform == 'darwin':
            # macOS - bind to the canvas and interior
            self.canvas.bind('<MouseWheel>', self._on_mousewheel_macos)
            self.interior.bind('<MouseWheel>', self._on_mousewheel_macos)
            # Bind to all child widgets recursively
            self.bind_all('<MouseWheel>', self._on_mousewheel_macos_global, add='+')
        else:
            # Linux/Windows
            self.canvas.bind('<Button-4>', self._on_scroll_up)
            self.canvas.bind('<Button-5>', self._on_scroll_down)
            self.canvas.bind('<MouseWheel>', self._on_mousewheel_windows)

    def _on_mousewheel_macos_global(self, event):
        """Handle mousewheel on macOS - global binding."""
        # Check if the event is within our canvas
        widget = event.widget
        try:
            # Walk up the widget tree to see if we're inside this scrollable frame
            while widget:
                if widget == self.canvas or widget == self.interior:
                    self._do_scroll_macos(event)
                    return
                if widget == self:
                    self._do_scroll_macos(event)
                    return
                widget = widget.master
        except (AttributeError, tk.TclError):
            pass

    def _on_mousewheel_macos(self, event):
        """Handle mousewheel on macOS."""
        self._do_scroll_macos(event)

    def _do_scroll_macos(self, event):
        """Perform smooth scroll on macOS."""
        # macOS trackpad sends small delta values for smooth scrolling
        # event.delta is typically 1, -1, or small values for trackpad

        # Check if we can scroll
        bbox = self.canvas.bbox('all')
        if not bbox:
            return

        canvas_height = self.canvas.winfo_height()
        content_height = bbox[3] - bbox[1]

        if content_height <= canvas_height:
            return  # Nothing to scroll

        # Smooth scrolling - use smaller increments
        # macOS delta is inverted (positive = scroll up, negative = scroll down)
        delta = event.delta

        # Scale the delta for smooth scrolling
        # Trackpad gives values like 1, -1, 2, -2, etc.
        scroll_amount = -delta * 2  # Multiply for reasonable speed

        # Use pixel-based scrolling for smoothness
        current_pos = self.canvas.yview()[0]
        scroll_fraction = scroll_amount / content_height
        new_pos = current_pos + scroll_fraction

        # Clamp to valid range
        new_pos = max(0, min(1, new_pos))
        self.canvas.yview_moveto(new_pos)

    def _on_mousewheel_windows(self, event):
        """Handle mousewheel on Windows."""
        self.canvas.yview_scroll(int(-event.delta / 120), 'units')

    def _on_scroll_up(self, event):
        """Handle scroll up (Linux)."""
        self.canvas.yview_scroll(-3, 'units')

    def _on_scroll_down(self, event):
        """Handle scroll down (Linux)."""
        self.canvas.yview_scroll(3, 'units')

    def scroll_to_top(self):
        """Scroll to top of content."""
        self.canvas.yview_moveto(0)

    def scroll_to_bottom(self):
        """Scroll to bottom of content."""
        self.canvas.yview_moveto(1)
