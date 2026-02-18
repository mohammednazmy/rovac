#!/usr/bin/env python3
"""
Debug screenshot tool for Super Sensor GUI.

This script launches the GUI, takes screenshots of all tabs, and exits.
Useful for automated testing and debugging.

Usage:
    python -m super_sensor_gui.debug_screenshot [--delay SECONDS] [--output-dir PATH]
"""

import argparse
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Take debug screenshots of Super Sensor GUI')
    parser.add_argument('--delay', type=float, default=1.0,
                        help='Delay before taking screenshots (seconds)')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Output directory for screenshots')
    parser.add_argument('--single', action='store_true',
                        help='Take single screenshot of current tab only')
    parser.add_argument('--tab', type=int, default=None,
                        help='Switch to specific tab (0-3) before screenshot')
    parser.add_argument('--keep-open', action='store_true',
                        help='Keep the GUI open after taking screenshots')
    args = parser.parse_args()

    # Import tkinter and check if available
    try:
        import tkinter as tk
    except ImportError:
        print("Error: tkinter is not installed.")
        print("On Ubuntu: sudo apt-get install python3-tk")
        print("On macOS: tkinter should be included with Python")
        sys.exit(1)

    # Add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from super_sensor_gui.app import SuperSensorApp
    from super_sensor_gui.utils.screenshot_utils import ScreenshotUtils

    # Set custom output directory if specified
    if args.output_dir:
        ScreenshotUtils.SCREENSHOT_DIR = Path(args.output_dir)

    print(f"Screenshot directory: {ScreenshotUtils.get_screenshot_dir()}")

    # Create and configure app
    app = SuperSensorApp()

    def bring_to_front():
        """Bring the window to the front."""
        app.root.lift()
        app.root.attributes('-topmost', True)
        app.root.update()
        app.root.attributes('-topmost', False)
        app.root.focus_force()

    # Schedule screenshot taking
    def take_screenshots():
        time.sleep(args.delay)

        # Bring window to front
        app.root.after(0, bring_to_front)
        time.sleep(0.5)

        if args.tab is not None:
            app.notebook.select(args.tab)
            app.root.update()
            time.sleep(0.2)

        if args.single:
            # Use full screen capture
            path = ScreenshotUtils.capture_screen(f"debug_{app._get_current_tab_name()}")
            if path:
                print(f"Screenshot saved: {path}")
        else:
            paths = []
            tab_count = app.notebook.index('end')
            for i in range(tab_count):
                app.notebook.select(i)
                app.root.update_idletasks()
                app.root.update()
                bring_to_front()
                time.sleep(0.5)  # Allow UI to render

                tab_name = app._get_current_tab_name()
                # Use full screen capture instead of region
                path = ScreenshotUtils.capture_screen(f"debug_{tab_name}")
                if path:
                    paths.append(path)
                    print(f"Screenshot saved: {path}")

            print(f"\nTotal: {len(paths)} screenshots saved")

        if not args.keep_open:
            app.root.after(500, app.root.destroy)

    # Start screenshot thread
    import threading
    thread = threading.Thread(target=take_screenshots, daemon=True)
    thread.start()

    # Run the app
    try:
        app.run()
    except tk.TclError:
        pass  # Window was destroyed

    print(f"\nScreenshots location: {ScreenshotUtils.get_screenshot_dir()}")

    # List recent screenshots
    screenshots = ScreenshotUtils.list_screenshots()[:10]
    if screenshots:
        print("\nRecent screenshots:")
        for s in screenshots:
            print(f"  {s}")


if __name__ == '__main__':
    main()
