"""Screenshot utilities for debugging the Super Sensor GUI."""

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


class ScreenshotUtils:
    """Utilities for capturing screenshots of the GUI."""

    # Default screenshot directory - use a fixed location for easy access
    SCREENSHOT_DIR = Path.home() / '.super_sensor' / 'screenshots'

    @classmethod
    def get_screenshot_dir(cls) -> Path:
        """Get and create screenshot directory."""
        cls.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        return cls.SCREENSHOT_DIR

    @classmethod
    def capture_screen(cls, filename: Optional[str] = None) -> Optional[Path]:
        """
        Capture the entire screen.

        Args:
            filename: Optional filename (without extension)

        Returns:
            Path to screenshot file, or None if failed
        """
        if filename is None:
            filename = f"screenshot_{int(time.time())}"

        screenshot_path = cls.get_screenshot_dir() / f"{filename}.png"

        if sys.platform == 'darwin':
            try:
                # macOS screencapture
                subprocess.run(
                    ['screencapture', '-x', str(screenshot_path)],
                    check=True,
                    capture_output=True
                )
                if screenshot_path.exists():
                    return screenshot_path
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print(f"macOS screencapture failed: {e}")

        elif sys.platform.startswith('linux'):
            # Linux: try various screenshot tools
            for cmd in [
                ['gnome-screenshot', '-f', str(screenshot_path)],
                ['scrot', str(screenshot_path)],
                ['import', '-window', 'root', str(screenshot_path)],  # ImageMagick
            ]:
                try:
                    subprocess.run(cmd, check=True, capture_output=True)
                    if screenshot_path.exists():
                        return screenshot_path
                except (subprocess.CalledProcessError, FileNotFoundError):
                    continue

        return None

    @classmethod
    def capture_window(cls, window_id: str, filename: Optional[str] = None) -> Optional[Path]:
        """
        Capture a specific window by its window ID.

        Args:
            window_id: The window ID to capture
            filename: Optional filename (without extension)

        Returns:
            Path to screenshot file, or None if failed
        """
        if filename is None:
            filename = f"window_{int(time.time())}"

        screenshot_path = cls.get_screenshot_dir() / f"{filename}.png"

        if sys.platform == 'darwin':
            try:
                subprocess.run(
                    ['screencapture', '-l', str(window_id), '-x', str(screenshot_path)],
                    check=True,
                    capture_output=True
                )
                if screenshot_path.exists():
                    return screenshot_path
            except Exception as e:
                print(f"Window capture failed: {e}")

        return None

    @classmethod
    def capture_region(cls, x: int, y: int, width: int, height: int,
                       filename: Optional[str] = None) -> Optional[Path]:
        """
        Capture a specific region of the screen.

        Args:
            x, y: Top-left corner coordinates
            width, height: Region dimensions
            filename: Optional filename (without extension)

        Returns:
            Path to screenshot file, or None if failed
        """
        if filename is None:
            filename = f"region_{int(time.time())}"

        screenshot_path = cls.get_screenshot_dir() / f"{filename}.png"

        if sys.platform == 'darwin':
            try:
                subprocess.run(
                    ['screencapture', '-x', '-R', f'{x},{y},{width},{height}', str(screenshot_path)],
                    check=True,
                    capture_output=True
                )
                if screenshot_path.exists():
                    return screenshot_path
            except Exception:
                pass

        return None

    @classmethod
    def list_screenshots(cls) -> list:
        """List all screenshots in the screenshot directory."""
        screenshot_dir = cls.get_screenshot_dir()
        return sorted(screenshot_dir.glob('*.png'), key=lambda p: p.stat().st_mtime, reverse=True)

    @classmethod
    def get_latest_screenshot(cls) -> Optional[Path]:
        """Get the most recent screenshot."""
        screenshots = cls.list_screenshots()
        return screenshots[0] if screenshots else None

    @classmethod
    def cleanup_old_screenshots(cls, keep: int = 20):
        """Remove old screenshots, keeping only the most recent ones."""
        screenshots = cls.list_screenshots()
        for screenshot in screenshots[keep:]:
            try:
                screenshot.unlink()
            except Exception:
                pass


class TkinterScreenshot:
    """Screenshot utilities using tkinter widget coordinates."""

    @staticmethod
    def capture_widget(widget, filename: Optional[str] = None) -> Optional[Path]:
        """
        Capture a tkinter widget to a file using region capture.

        Args:
            widget: The tkinter widget to capture
            filename: Optional filename (without extension)

        Returns:
            Path to screenshot file, or None if failed
        """
        if filename is None:
            filename = f"widget_{int(time.time())}"

        try:
            # Ensure widget is updated
            widget.update_idletasks()

            # Get widget coordinates on screen
            x = widget.winfo_rootx()
            y = widget.winfo_rooty()
            width = widget.winfo_width()
            height = widget.winfo_height()

            # Use region capture
            return ScreenshotUtils.capture_region(x, y, width, height, filename)

        except Exception as e:
            print(f"Widget capture failed: {e}")
            # Fallback to full screen
            return ScreenshotUtils.capture_screen(filename)

    @staticmethod
    def capture_canvas_to_ps(canvas, filename: Optional[str] = None) -> Optional[Path]:
        """
        Capture a tkinter Canvas widget to PostScript format.

        Args:
            canvas: The tkinter Canvas widget
            filename: Optional filename (without extension)

        Returns:
            Path to file, or None if failed
        """
        if filename is None:
            filename = f"canvas_{int(time.time())}"

        ps_path = ScreenshotUtils.get_screenshot_dir() / f"{filename}.ps"

        try:
            canvas.postscript(file=str(ps_path), colormode='color')
            return ps_path
        except Exception:
            return None
