"""macOS-specific utilities for native integration."""

import subprocess
import sys
from typing import Optional, Callable, Dict, Any
from pathlib import Path


class MacOSTheme:
    """
    Manages macOS theme detection and color schemes.

    Automatically detects light/dark mode and provides appropriate colors.
    """

    # Light mode colors
    LIGHT_THEME = {
        'bg': '#ececec',
        'bg_secondary': '#ffffff',
        'bg_tertiary': '#f5f5f5',
        'fg': '#000000',
        'fg_secondary': '#666666',
        'fg_tertiary': '#999999',
        'accent': '#007aff',
        'accent_hover': '#0056b3',
        'border': '#c8c8c8',
        'border_light': '#e0e0e0',
        'selection': '#b3d7ff',
        'error': '#ff3b30',
        'warning': '#ff9500',
        'success': '#34c759',
        'toolbar_bg': '#f6f6f6',
        'sidebar_bg': '#f0f0f0',
        'listbox_bg': '#ffffff',
        'listbox_fg': '#000000',
        'listbox_select_bg': '#0069d9',
        'listbox_select_fg': '#ffffff',
        'button_bg': '#ffffff',
        'button_fg': '#000000',
        'entry_bg': '#ffffff',
        'entry_fg': '#000000',
    }

    # Dark mode colors (macOS native dark mode palette)
    DARK_THEME = {
        'bg': '#1e1e1e',
        'bg_secondary': '#2d2d2d',
        'bg_tertiary': '#383838',
        'fg': '#ffffff',
        'fg_secondary': '#a0a0a0',
        'fg_tertiary': '#707070',
        'accent': '#0a84ff',
        'accent_hover': '#409cff',
        'border': '#3d3d3d',
        'border_light': '#4a4a4a',
        'selection': '#0a84ff',
        'error': '#ff453a',
        'warning': '#ff9f0a',
        'success': '#32d74b',
        'toolbar_bg': '#323232',
        'sidebar_bg': '#252525',
        'listbox_bg': '#1e1e1e',
        'listbox_fg': '#ffffff',
        'listbox_select_bg': '#0a84ff',
        'listbox_select_fg': '#ffffff',
        'button_bg': '#3a3a3a',
        'button_fg': '#ffffff',
        'entry_bg': '#1e1e1e',
        'entry_fg': '#ffffff',
    }

    _callbacks = []
    _current_mode = None

    @classmethod
    def is_dark_mode(cls) -> bool:
        """
        Detect if macOS is in dark mode.

        Returns:
            True if dark mode is enabled, False otherwise
        """
        if sys.platform != 'darwin':
            return False

        try:
            result = subprocess.run(
                ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                capture_output=True,
                text=True
            )
            return result.stdout.strip().lower() == 'dark'
        except Exception:
            return False

    @classmethod
    def get_theme(cls) -> Dict[str, str]:
        """
        Get the current theme colors.

        Returns:
            Dictionary of color values
        """
        return cls.DARK_THEME if cls.is_dark_mode() else cls.LIGHT_THEME

    @classmethod
    def get_color(cls, key: str) -> str:
        """
        Get a specific color from the current theme.

        Args:
            key: Color key name

        Returns:
            Color hex value
        """
        theme = cls.get_theme()
        return theme.get(key, '#000000')

    @classmethod
    def add_callback(cls, callback: Callable[[bool], None]):
        """Register a callback for theme changes."""
        cls._callbacks.append(callback)

    @classmethod
    def remove_callback(cls, callback: Callable[[bool], None]):
        """Remove a theme change callback."""
        if callback in cls._callbacks:
            cls._callbacks.remove(callback)

    @classmethod
    def check_theme_change(cls) -> bool:
        """
        Check if theme has changed and notify callbacks.

        Returns:
            True if theme changed, False otherwise
        """
        current = cls.is_dark_mode()
        if cls._current_mode is None:
            cls._current_mode = current
            return False

        if current != cls._current_mode:
            cls._current_mode = current
            for callback in cls._callbacks:
                try:
                    callback(current)
                except Exception:
                    pass
            return True
        return False


class MacOSIntegration:
    """
    Provides macOS-specific integration features.
    """

    @staticmethod
    def get_accent_color() -> Optional[str]:
        """
        Get the system accent color.

        Returns:
            Hex color string or None
        """
        if sys.platform != 'darwin':
            return None

        try:
            result = subprocess.run(
                ['defaults', 'read', '-g', 'AppleAccentColor'],
                capture_output=True,
                text=True
            )
            accent_id = result.stdout.strip()

            # Map accent color IDs to hex values
            accent_colors = {
                '-1': '#8c8c8c',  # Graphite
                '0': '#ff5257',   # Red
                '1': '#f7821b',   # Orange
                '2': '#ffc600',   # Yellow
                '3': '#62ba46',   # Green
                '4': '#007aff',   # Blue (default)
                '5': '#a550a7',   # Purple
                '6': '#f74f9e',   # Pink
            }
            return accent_colors.get(accent_id, '#007aff')
        except Exception:
            return '#007aff'  # Default blue

    @staticmethod
    def request_notification_permission():
        """Request permission for notifications on macOS."""
        if sys.platform != 'darwin':
            return

        try:
            # This requires pyobjc, fallback silently if not available
            from Foundation import NSUserNotificationCenter
        except ImportError:
            pass

    @staticmethod
    def show_notification(title: str, message: str):
        """
        Show a macOS notification.

        Args:
            title: Notification title
            message: Notification body
        """
        if sys.platform != 'darwin':
            return

        try:
            subprocess.run([
                'osascript', '-e',
                f'display notification "{message}" with title "{title}"'
            ], capture_output=True)
        except Exception:
            pass

    @staticmethod
    def open_preferences():
        """Open the app's preferences (placeholder for future implementation)."""
        pass

    @staticmethod
    def reveal_in_finder(path: str):
        """
        Reveal a file or folder in Finder.

        Args:
            path: Path to reveal
        """
        if sys.platform != 'darwin':
            return

        try:
            subprocess.run(['open', '-R', path], capture_output=True)
        except Exception:
            pass

    @staticmethod
    def get_downloads_folder() -> Path:
        """Get the user's Downloads folder."""
        return Path.home() / 'Downloads'

    @staticmethod
    def get_documents_folder() -> Path:
        """Get the user's Documents folder."""
        return Path.home() / 'Documents'

    @staticmethod
    def set_app_icon(window, icon_path: str):
        """
        Set the application icon (requires icon file).

        Args:
            window: Tk root window
            icon_path: Path to .icns file
        """
        if sys.platform != 'darwin':
            return

        try:
            # On macOS, the dock icon is set via Info.plist in the .app bundle
            # For development, we can try to set it via tkinter
            window.iconbitmap(icon_path)
        except Exception:
            pass


class MacOSKeyboardShortcuts:
    """
    Standard macOS keyboard shortcuts.
    """

    # Map of action names to (modifier, key) tuples
    SHORTCUTS = {
        'quit': ('Command', 'q'),
        'close_window': ('Command', 'w'),
        'preferences': ('Command', ','),
        'minimize': ('Command', 'm'),
        'hide': ('Command', 'h'),
        'hide_others': ('Command-Option', 'h'),
        'select_all': ('Command', 'a'),
        'copy': ('Command', 'c'),
        'paste': ('Command', 'v'),
        'cut': ('Command', 'x'),
        'undo': ('Command', 'z'),
        'redo': ('Command-Shift', 'z'),
        'save': ('Command', 's'),
        'save_as': ('Command-Shift', 's'),
        'open': ('Command', 'o'),
        'new': ('Command', 'n'),
        'print': ('Command', 'p'),
        'find': ('Command', 'f'),
        'zoom_in': ('Command', '+'),
        'zoom_out': ('Command', '-'),
        'zoom_reset': ('Command', '0'),
        'fullscreen': ('Command-Control', 'f'),
        'refresh': ('Command', 'r'),
        'help': ('Command', '?'),
    }

    @classmethod
    def get_accelerator(cls, action: str) -> str:
        """
        Get the accelerator string for a menu item.

        Args:
            action: Action name

        Returns:
            Accelerator string (e.g., "Cmd+Q")
        """
        if action not in cls.SHORTCUTS:
            return ''

        modifier, key = cls.SHORTCUTS[action]
        return f"{modifier}+{key.upper()}"

    @classmethod
    def get_binding(cls, action: str) -> str:
        """
        Get the tkinter binding string for an action.

        Args:
            action: Action name

        Returns:
            Tkinter binding string (e.g., "<Command-q>")
        """
        if action not in cls.SHORTCUTS:
            return ''

        modifier, key = cls.SHORTCUTS[action]

        # Convert modifier to tkinter format
        tkinter_modifier = modifier.replace('Command', 'Command').replace('-', '-')

        return f"<{tkinter_modifier}-{key}>"


class MacOSDragDrop:
    """
    Helpers for macOS drag and drop operations.
    """

    @staticmethod
    def enable_file_drop(widget, callback: Callable[[list], None]):
        """
        Enable file drop on a widget.

        Args:
            widget: Tkinter widget
            callback: Function to call with list of dropped file paths
        """
        try:
            # Try to use tkinterdnd2 if available
            import tkinterdnd2
            widget.drop_target_register(tkinterdnd2.DND_FILES)
            widget.dnd_bind('<<Drop>>', lambda e: callback(e.data.split()))
        except ImportError:
            # Fallback: no drag-drop support without tkinterdnd2
            pass

    @staticmethod
    def start_file_drag(widget, file_paths: list):
        """
        Start a file drag operation.

        Args:
            widget: Source widget
            file_paths: List of file paths to drag
        """
        try:
            import tkinterdnd2
            widget.drag_source_register(tkinterdnd2.DND_FILES)
        except ImportError:
            pass
