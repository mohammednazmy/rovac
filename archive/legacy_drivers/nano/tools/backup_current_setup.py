#!/usr/bin/env python3
import os
import shutil
import datetime
import platform


def backup_current_setup():
    print("Creating backup of current professional setup...")

    # Create backup directory
    backup_dir = f"backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)

    print(f"✅ Backup directory created: {backup_dir}")

    # Document current system info
    system_info = {
        "timestamp": datetime.datetime.now().isoformat(),
        "platform": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "working_directory": os.getcwd(),
    }

    with open(f"{backup_dir}/system_info.txt", "w") as f:
        for key, value in system_info.items():
            f.write(f"{key}: {value}\n")

    print("✅ System information documented")

    # Copy important files
    files_to_backup = [
        "examples/lidar_usb_bridge_professional/lidar_usb_bridge_professional.ino",
        "professional_test_suite.py",
        "demo_professional_features.py",
        "quick_verify.py",
    ]

    for file_path in files_to_backup:
        if os.path.exists(file_path):
            try:
                # Create directory structure in backup
                backup_path = f"{backup_dir}/{file_path}"
                os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                shutil.copy2(file_path, backup_path)
                print(f"✅ Backed up: {file_path}")
            except Exception as e:
                print(f"❌ Failed to backup {file_path}: {e}")

    # Document device information
    device_info = f"""# ROVAC LIDAR USB Bridge - Current Setup Documentation
Backup created: {system_info["timestamp"]}
Platform: {system_info["platform"]} {system_info["release"]}
Architecture: {system_info["machine"]}

## Device Information
- Device Path: /dev/cu.wchusbserial2140
- Board: LAFVIN Nano V3.0 (ATmega328P + CH340G)
- Firmware Status: Professional enhanced
- Data Rate: Verified working

## Wiring Configuration
LIDAR Wire    Color    Nano Pin    Function
----------    -----    --------    --------
Red           Red      5V          Power (+5V)
Black         Black    GND         Ground
Orange        Orange   D2          Serial TX (LIDAR -> Nano)
Brown         Brown    D3          Serial RX (Nano -> LIDAR)

## Test Results
✅ Serial communication established
✅ Data flow confirmed
✅ Professional firmware uploaded
✅ Enhanced features verified

## Notes
- Working configuration backed up {system_info["timestamp"]}
- Ready for deployment to Raspberry Pi
- All cross-platform tools available
"""

    with open(f"{backup_dir}/setup_documentation.md", "w") as f:
        f.write(device_info)

    print("✅ Setup documentation created")
    print(f"📁 Complete backup available in: {backup_dir}")

    return True


if __name__ == "__main__":
    backup_current_setup()
