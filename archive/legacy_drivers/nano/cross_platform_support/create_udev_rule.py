#!/usr/bin/env python3
"""
Create udev rules for consistent LIDAR device naming on Linux
"""

import os
import platform
import subprocess


def create_linux_udev_rule():
    """Create udev rule for consistent device naming on Linux"""
    if platform.system() != "Linux":
        print("This script is for Linux systems only")
        return False

    udev_rule = """# ROVAC LIDAR USB Bridge
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="rovac_lidar", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5523", SYMLINK+="rovac_lidar", MODE="0666"
"""

    try:
        # Write udev rule
        with open("/etc/udev/rules.d/99-rovac-lidar.rules", "w") as f:
            f.write(udev_rule)

        # Reload udev rules
        subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
        subprocess.run(["udevadm", "trigger"], check=True)

        print("✅ Linux udev rule created successfully")
        print("   Device will appear as /dev/rovac_lidar")
        return True

    except PermissionError:
        print("❌ Permission denied. Run with sudo:")
        print("   sudo python3 create_udev_rule.py")
        return False
    except Exception as e:
        print(f"❌ Error creating udev rule: {e}")
        return False


def create_macos_setup_script():
    """Create macOS setup script"""
    if platform.system() != "Darwin":
        print("This function creates macOS-specific scripts")
        return False

    setup_script = """#!/bin/bash
# macOS setup for ROVAC LIDAR USB Bridge

echo "ROVAC LIDAR USB Bridge - macOS Setup"
echo "====================================="

# Check if CH340 driver is loaded
if kextstat | grep -q wch; then
    echo "✅ WCH CH340 driver is loaded"
else
    echo "ℹ️  WCH CH340 driver may need to be loaded"
    echo "   If you see permission errors, check System Preferences > Security"
fi

# Test device connection
echo
echo "Testing device connection..."
ls /dev/cu.wchusbserial* 2>/dev/null || echo "No CH340 devices found"

echo
echo "✅ macOS setup completed"
echo "   Device should appear as /dev/cu.wchusbserialXXXX"
"""

    try:
        with open("setup_macos.sh", "w") as f:
            f.write(setup_script)
        os.chmod("setup_macos.sh", 0o755)
        print("✅ macOS setup script created: setup_macos.sh")
        return True
    except Exception as e:
        print(f"❌ Error creating macOS setup script: {e}")
        return False


def create_windows_batch_file():
    """Create Windows batch file for setup"""
    batch_content = """@echo off
echo ROVAC LIDAR USB Bridge - Windows Setup
echo ========================================
echo.

echo Checking for CH340 devices...
driverquery | findstr /i "ch340" >nul
if %errorLevel% == 0 (
    echo ✅ CH340 driver appears to be installed
) else (
    echo ℹ️  CH340 driver may need to be installed
    echo    Download from: http://www.wch.cn/downloads/CH341SER_EXE.html
)

echo.
echo Device Manager Instructions:
echo - Look for "USB Serial Port" with CH340 in description
echo - Hardware ID should contain VID_1A86 PID_7523
echo - Device should appear as COM3, COM4, etc.

echo.
echo ✅ Windows setup information provided
pause
"""

    try:
        with open("setup_windows.bat", "w") as f:
            f.write(batch_content)
        print("✅ Windows setup script created: setup_windows.bat")
        return True
    except Exception as e:
        print(f"❌ Error creating Windows setup script: {e}")
        return False


def main():
    """Main function to create cross-platform setup files"""
    print("Creating cross-platform setup files for ROVAC LIDAR USB Bridge")
    print()

    # Always create all platform files
    create_windows_batch_file()

    if platform.system() == "Linux":
        create_linux_udev_rule()
    elif platform.system() == "Darwin":
        create_macos_setup_script()

    print()
    print("📁 Cross-platform setup files created in current directory")
    print("   Copy these to appropriate system locations as needed")


if __name__ == "__main__":
    main()
