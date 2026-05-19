#!/usr/bin/env python3
"""
Super Sensor GUI Application

Cross-platform GUI for controlling and configuring the Super Sensor module.
"""

import sys
import os
from pathlib import Path

# Handle PyInstaller bundle path setup
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle
    bundle_dir = Path(sys._MEIPASS)
    # Add the bundle dir to path for imports
    sys.path.insert(0, str(bundle_dir))
    # Also add the super_sensor_gui package within the bundle
    if (bundle_dir / 'super_sensor_gui').exists():
        sys.path.insert(0, str(bundle_dir / 'super_sensor_gui'))
else:
    # Running from source
    # Add parent directory to path for super_sensor_driver
    sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    """Main entry point."""
    # Check for required dependencies
    try:
        import tkinter as tk
    except ImportError:
        print("Error: tkinter is not installed.")
        print("On Ubuntu: sudo apt-get install python3-tk")
        print("On macOS: tkinter should be included with Python")
        sys.exit(1)

    try:
        import serial
    except ImportError:
        print("Warning: pyserial not installed. Install with: pip install pyserial")
        print("The application will still run but sensor connection will not work.")

    # Import and run app
    # Handle both module execution and PyInstaller bundle
    try:
        from .app import SuperSensorApp
    except ImportError:
        from app import SuperSensorApp

    app = SuperSensorApp()
    app.run()


if __name__ == '__main__':
    main()
