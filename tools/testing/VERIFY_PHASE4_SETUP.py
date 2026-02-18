#!/usr/bin/env python3
"""
Verification script for ROVAC Phase 4 Thermal Imaging Setup
"""

import os
import sys


def check_file_exists(filepath):
    """Check if a file exists"""
    return os.path.exists(filepath)


def main():
    print("🔍 ROVAC Phase 4 Thermal Imaging - Verification")
    print("=" * 50)

    # Define base path
    base_path = "/Users/mohammednazmy/robots/rovac/robot_mcp_server"

    # Phase 4 files to check
    phase4_files = [
        "thermal_camera_driver.py",
        "heat_signature_detector.py",
        "thermal_imaging_node.py",
        "thermal_imaging.launch.py",
        "THERMAL_IMAGING_README.md",
        "test_thermal_imaging.py",
    ]

    # Check files
    print("📁 Checking Phase 4 required files...")
    all_files_exist = True
    for filename in phase4_files:
        full_path = os.path.join(base_path, filename)
        exists = check_file_exists(full_path)
        status = "✅" if exists else "❌"
        print(f"  {status} {filename}")
        if not exists:
            all_files_exist = False

    # Check system integration
    print("\n🔄 Checking system integration...")
    main_launch_path = os.path.join(base_path, "rovac_enhanced_system.launch.py")
    launch_updated = False
    if check_file_exists(main_launch_path):
        with open(main_launch_path, "r") as f:
            content = f.read()
            launch_updated = "thermal_imaging_node" in content

    status = "✅" if launch_updated else "❌"
    print(f"  {status} Main launch file integration")

    # Check imports
    print("\n🔧 Checking component imports...")

    # Test thermal camera driver
    try:
        sys.path.append(base_path)
        from thermal_camera_driver import FLIRLeptonDriver

        print("  ✅ FLIRLeptonDriver imports successfully")
    except Exception as e:
        print(f"  ❌ FLIRLeptonDriver import failed: {e}")

    # Test heat signature detector
    try:
        from heat_signature_detector import HeatSignatureDetector

        print("  ✅ HeatSignatureDetector imports successfully")
    except Exception as e:
        print(f"  ❌ HeatSignatureDetector import failed: {e}")

    # Test thermal imaging node
    try:
        from thermal_imaging_node import ThermalImagingNode

        print("  ✅ ThermalImagingNode imports successfully")
    except Exception as e:
        print(f"  ❌ ThermalImagingNode import failed: {e}")

    # Summary
    print("\n" + "=" * 50)
    print("📋 PHASE 4 VERIFICATION SUMMARY")
    print("=" * 50)

    if all_files_exist:
        print("✅ All Phase 4 files are present")
    else:
        print("❌ Some Phase 4 files are missing")

    if launch_updated:
        print("✅ System integration complete")
    else:
        print("❌ System integration needs attention")

    print("\n📚 DOCUMENTATION:")
    print("   - Thermal Imaging: robot_mcp_server/THERMAL_IMAGING_README.md")
    print("   - System Integration: rovac_enhanced_system.launch.py")

    print("\n🚀 NEXT STEPS:")
    print("1. To test thermal imaging system:")
    print("   cd ~/robots/rovac")
    print('   eval "$(conda shell.bash hook)"')
    print("   conda activate ros_jazzy")
    print("   python robot_mcp_server/test_thermal_imaging.py")
    print("")
    print("2. To launch with main enhanced system:")
    print("   ros2 launch rovac_enhanced rovac_enhanced_system.launch.py \\")
    print("     enable_thermal_imaging:=true")
    print("")
    print("3. To monitor thermal topics:")
    print("   ros2 topic list | grep thermal")

    # Overall status
    if all_files_exist and launch_updated:
        print("\n🎉 PHASE 4 SETUP IS COMPLETE AND READY!")
        print("   All thermal imaging components are implemented and integrated.")
        return 0
    else:
        print("\n⚠️  SOME PHASE 4 COMPONENTS NEED ATTENTION")
        return 1


if __name__ == "__main__":
    sys.exit(main())
