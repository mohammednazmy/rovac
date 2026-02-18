#!/usr/bin/env python3
"""
Quick test script for Phase 3 ROVAC Enhanced System Components
"""

import os
import sys


def test_import(module_name, file_path):
    """Test if a module can be imported"""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None:
            return False, f"❌ {module_name}: Could not create spec"
        module = importlib.util.module_from_spec(spec)
        if spec.loader is not None:
            spec.loader.exec_module(module)
        return True, f"✅ {module_name}: Import successful"
    except Exception as e:
        return False, f"❌ {module_name}: Import failed - {str(e)}"


def check_file_exists(file_path):
    """Check if a file exists"""
    return os.path.exists(file_path)


def main():
    print("🔍 ROVAC Phase 3 Enhanced System - Component Verification")
    print("=" * 60)

    # Define base path
    base_path = "/Users/mohammednazmy/robots/rovac/robot_mcp_server"

    # Phase 3 files to check
    phase3_files = [
        ("dl_path_planning.py", "Deep Learning Path Planning Core"),
        ("dl_path_planning_node.py", "DL Path Planning ROS2 Node"),
        ("dl_path_planning.launch.py", "DL Path Planning Launch Config"),
        ("DL_PATH_PLANNING_README.md", "DL Path Planning Documentation"),
        ("predictive_analytics.py", "Predictive Analytics Core"),
        ("predictive_analytics_node.py", "Predictive Analytics ROS2 Node"),
        ("predictive_analytics.launch.py", "Predictive Analytics Launch Config"),
        ("PREDICTIVE_ANALYTICS_README.md", "Predictive Analytics Documentation"),
    ]

    # Check files exist
    print("📁 Checking Phase 3 required files...")
    all_files_exist = True
    for filename, description in phase3_files:
        full_path = os.path.join(base_path, filename)
        exists = check_file_exists(full_path)
        status = "✅" if exists else "❌"
        print(f"  {status} {filename} - {description}")
        if not exists:
            all_files_exist = False

    # Test core imports
    print("\n🔧 Testing core component imports...")

    # Test Deep Learning Path Planning
    dl_core_path = os.path.join(base_path, "dl_path_planning.py")
    dl_success, dl_message = test_import("dl_path_planning", dl_core_path)
    print(f"  {dl_message}")

    # Test Predictive Analytics
    pa_core_path = os.path.join(base_path, "predictive_analytics.py")
    pa_success, pa_message = test_import("predictive_analytics", pa_core_path)
    print(f"  {pa_message}")

    # Check launch file updates
    print("\n🔄 Checking system integration...")
    main_launch_path = os.path.join(base_path, "rovac_enhanced_system.launch.py")
    launch_updated = False
    if check_file_exists(main_launch_path):
        with open(main_launch_path, "r") as f:
            content = f.read()
            launch_updated = (
                "dl_path_planning_node" in content
                and "predictive_analytics_node" in content
            )

    status = "✅" if launch_updated else "❌"
    print(f"  {status} Main launch file integration")

    # Summary
    print("\n" + "=" * 60)
    print("📋 PHASE 3 VERIFICATION SUMMARY")
    print("=" * 60)

    if all_files_exist:
        print("✅ All Phase 3 files are present")
    else:
        print("❌ Some Phase 3 files are missing")

    if dl_success and pa_success:
        print("✅ Core modules are functional")
    else:
        print("❌ Some modules have import issues")

    if launch_updated:
        print("✅ System integration complete")
    else:
        print("❌ System integration needs attention")

    print("\n📚 DOCUMENTATION:")
    print(
        "   - Deep Learning Path Planning: robot_mcp_server/DL_PATH_PLANNING_README.md"
    )
    print("   - Predictive Analytics: robot_mcp_server/PREDICTIVE_ANALYTICS_README.md")

    print("\n🚀 NEXT STEPS:")
    print("1. To start Phase 3 components:")
    print("   cd ~/robots/rovac")
    print('   eval "$(conda shell.bash hook)"')
    print("   conda activate ros_jazzy")
    print("   source config/ros2_env.sh")
    print("   ros2 launch rovac_enhanced rovac_enhanced_system.launch.py \\")
    print("     enable_dl_planning:=true enable_predictive_analytics:=true")
    print("")
    print("2. Monitor the systems:")
    print("   ros2 topic echo /dl/performance_metrics")
    print("   ros2 topic echo /analytics/component_health")

    # Overall status
    if all_files_exist and dl_success and pa_success and launch_updated:
        print("\n🎉 PHASE 3 SETUP IS COMPLETE AND READY!")
        print("   All components are implemented and integrated.")
        return 0
    else:
        print("\n⚠️  SOME PHASE 3 COMPONENTS NEED ATTENTION")
        return 1


if __name__ == "__main__":
    sys.exit(main())
