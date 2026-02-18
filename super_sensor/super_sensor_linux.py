#!/usr/bin/env python3
"""
Super Sensor - Unified Launcher for Linux

Automatically detects whether a GUI is available:
- If DISPLAY is set and tkinter works: launches GUI mode
- Otherwise: launches CLI mode

Usage:
    ./super_sensor_linux.py [--gui | --cli]

Options:
    --gui   Force GUI mode
    --cli   Force CLI mode
    (default: auto-detect)
"""

import sys
import os


def check_display_available() -> bool:
    """Check if a display is available for GUI."""
    # Check DISPLAY environment variable
    if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        return False

    # Try to initialize tkinter
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


def run_gui():
    """Run the GUI application."""
    try:
        from super_sensor_gui.main import main
        main()
    except ImportError as e:
        print(f"Error: Could not import GUI module: {e}")
        print("Falling back to CLI mode...")
        run_cli()
    except Exception as e:
        print(f"Error starting GUI: {e}")
        print("Falling back to CLI mode...")
        run_cli()


def run_cli():
    """Run the CLI application."""
    try:
        from super_sensor_cli.cli_app import main
        main()
    except ImportError as e:
        print(f"Error: Could not import CLI module: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    # Parse command line arguments
    force_gui = '--gui' in sys.argv
    force_cli = '--cli' in sys.argv

    if force_gui and force_cli:
        print("Error: Cannot specify both --gui and --cli")
        sys.exit(1)

    # Determine mode
    if force_gui:
        print("Starting GUI mode (forced)...")
        run_gui()
    elif force_cli:
        print("Starting CLI mode (forced)...")
        run_cli()
    else:
        # Auto-detect
        if check_display_available():
            print("Display detected, starting GUI mode...")
            print("(Use --cli to force CLI mode)")
            run_gui()
        else:
            print("No display available, starting CLI mode...")
            print("(Use --gui to force GUI mode if display is available)")
            run_cli()


if __name__ == '__main__':
    main()
