"""Scrolling log panel widget."""

import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import Optional


class LogPanel(ttk.Frame):
    """
    Scrolling text log panel.

    Features:
    - Auto-scroll to bottom
    - Timestamp prefixes
    - Color-coded log levels
    - Clear button
    - Copy to clipboard
    """

    # Log level colors
    COLORS = {
        'INFO': '#ffffff',
        'SUCCESS': '#44ff88',
        'WARNING': '#ffcc44',
        'ERROR': '#ff4444',
        'DEBUG': '#888888',
    }

    def __init__(
        self,
        parent,
        height: int = 10,
        show_toolbar: bool = True,
        **kwargs
    ):
        """
        Initialize LogPanel.

        Args:
            parent: Parent widget
            height: Number of visible lines
            show_toolbar: Whether to show clear/copy buttons
        """
        super().__init__(parent, **kwargs)

        self._build_ui(height, show_toolbar)

    def _build_ui(self, height: int, show_toolbar: bool):
        """Build the UI."""
        # Toolbar
        if show_toolbar:
            toolbar = ttk.Frame(self)
            toolbar.pack(fill='x', pady=(0, 5))

            ttk.Button(
                toolbar,
                text='Clear',
                width=8,
                command=self.clear
            ).pack(side='left', padx=(0, 5))

            ttk.Button(
                toolbar,
                text='Copy All',
                width=8,
                command=self._copy_to_clipboard
            ).pack(side='left')

            # Auto-scroll checkbox
            self.auto_scroll_var = tk.BooleanVar(value=True)
            ttk.Checkbutton(
                toolbar,
                text='Auto-scroll',
                variable=self.auto_scroll_var
            ).pack(side='right')

        # Text widget with scrollbar
        text_frame = ttk.Frame(self)
        text_frame.pack(fill='both', expand=True)

        self.text = tk.Text(
            text_frame,
            height=height,
            wrap='word',
            font=('Menlo', 12),
            bg='#1e1e1e',
            fg='#ffffff',
            insertbackground='#ffffff',
            selectbackground='#264f78',
            state='disabled',
            padx=10,
            pady=10
        )
        self.text.pack(side='left', fill='both', expand=True)

        scrollbar = ttk.Scrollbar(text_frame, command=self.text.yview)
        scrollbar.pack(side='right', fill='y')

        self.text.configure(yscrollcommand=scrollbar.set)

        # Configure tags for colors
        for level, color in self.COLORS.items():
            self.text.tag_configure(level, foreground=color)

        self.text.tag_configure('TIMESTAMP', foreground='#666666')

    def log(self, message: str, level: str = 'INFO', timestamp: bool = True):
        """
        Add a log message.

        Args:
            message: Message text
            level: Log level (INFO, SUCCESS, WARNING, ERROR, DEBUG)
            timestamp: Whether to include timestamp
        """
        self.text.configure(state='normal')

        # Add timestamp
        if timestamp:
            ts = datetime.now().strftime('%H:%M:%S')
            self.text.insert('end', f'[{ts}] ', 'TIMESTAMP')

        # Add message with appropriate tag
        tag = level.upper() if level.upper() in self.COLORS else 'INFO'
        self.text.insert('end', f'{message}\n', tag)

        self.text.configure(state='disabled')

        # Auto-scroll
        if hasattr(self, 'auto_scroll_var') and self.auto_scroll_var.get():
            self.text.see('end')

    def info(self, message: str):
        """Log info message."""
        self.log(message, 'INFO')

    def success(self, message: str):
        """Log success message."""
        self.log(message, 'SUCCESS')

    def warning(self, message: str):
        """Log warning message."""
        self.log(message, 'WARNING')

    def error(self, message: str):
        """Log error message."""
        self.log(message, 'ERROR')

    def debug(self, message: str):
        """Log debug message."""
        self.log(message, 'DEBUG')

    def clear(self):
        """Clear all log messages."""
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        self.text.configure(state='disabled')

    def _copy_to_clipboard(self):
        """Copy log contents to clipboard."""
        content = self.text.get('1.0', 'end-1c')
        self.clipboard_clear()
        self.clipboard_append(content)

    def get_content(self) -> str:
        """Get all log content as string."""
        return self.text.get('1.0', 'end-1c')
