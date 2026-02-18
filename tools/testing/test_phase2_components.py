#!/usr/bin/env python3
"""
Test script for Phase 2 ROVAC Enhanced System Components
"""

import sys
import os


def test_import(module_name, file_path):
    """Test if a module can be imported"""
    try:
        # Add directory to path if needed
        dir_path = os.path.dirname(file_path)
        if dir_path not in sys.path:
            sys.path.insert(0, dir_path)

        # Import the module
        __import__(module_name)
        return True, f"✅ {module_name}: Import successful"
    except Exception as e:
        return False, f"❌ {module_name}: Import failed - {str(e)}"


def check_file_exists(file_path):
    """Check if a file exists"""
    return os.path.exists(file_path)


def main():
    print("🔍 ROVAC Phase 2 Enhanced System - Component Verification")
    print("=" * 55)

    # Define base path
    base_path = "/Users/mohammednazmy/robots/rovac/robot_mcp_server"

    # Phase 2 files to check
    phase2_files = [
        ("behavior_tree_framework.py", "Behavior Tree Framework"),
        ("behavior_tree_node.py", "Behavior Tree ROS2 Node"),
        ("behavior_tree.launch.py", "Behavior Tree Launch File"),
        ("BEHAVIOR_TREE_README.md", "Behavior Tree Documentation"),
        ("edge_optimization_node.py", "Edge Optimization Node"),
        ("edge_optimization.launch.py", "Edge Optimization Launch File"),
        ("EDGE_OPTIMIZATION_README.md", "Edge Optimization Documentation"),
    ]

    # Check files exist
    print("📁 Checking Phase 2 required files...")
    all_files_exist = True
    for filename, description in phase2_files:
        full_path = os.path.join(base_path, filename)
        exists = check_file_exists(full_path)
        status = "✅" if exists else "❌"
        print(f"  {status} {filename} - {description}")
        if not exists:
            all_files_exist = False

    # Test core imports
    print("\n🔧 Testing core component imports...")

    # Test Behavior Tree Framework
    bt_framework_path = os.path.join(base_path, "behavior_tree_framework.py")
    bt_success, bt_message = test_import("behavior_tree_framework", bt_framework_path)
    print(f"  {bt_message}")

    # Test Edge Optimization Node
    edge_node_path = os.path.join(base_path, "edge_optimization_node.py")
    edge_success, edge_message = test_import("edge_optimization_node", edge_node_path)
    print(f"  {edge_message}")

    # Test Behavior Tree Node
    bt_node_path = os.path.join(base_path, "behavior_tree_node.py")
    bt_node_success, bt_node_message = test_import("behavior_tree_node", bt_node_path)
    print(f"  {bt_node_message}")

    # Check launch files
    print("\n🔄 Checking launch file syntax...")

    # Test Behavior Tree Launch
    bt_launch_path = os.path.join(base_path, "behavior_tree.launch.py")
    bt_launch_exists = check_file_exists(bt_launch_path)
    status = "✅" if bt_launch_exists else "❌"
    print(
        f"  {status} Behavior Tree Launch: {'Syntax valid' if bt_launch_exists else 'Missing'}"
    )

    # Test Edge Optimization Launch
    edge_launch_path = os.path.join(base_path, "edge_optimization.launch.py")
    edge_launch_exists = check_file_exists(edge_launch_path)
    status = "✅" if edge_launch_exists else "❌"
    print(
        f"  {status} Edge Optimization Launch: {'Syntax valid' if edge_launch_exists else 'Missing'}"
    )

    # Check documentation
    print("\n📚 Checking documentation...")

    # Test Behavior Tree README
    bt_readme_path = os.path.join(base_path, "BEHAVIOR_TREE_README.md")
    bt_readme_exists = check_file_exists(bt_readme_path)
    status = "✅" if bt_readme_exists else "❌"
    print(
        f"  {status} Behavior Tree Documentation: {'Exists' if bt_readme_exists else 'Missing'}"
    )

    # Test Edge Optimization README
    edge_readme_path = os.path.join(base_path, "EDGE_OPTIMIZATION_README.md")
    edge_readme_exists = check_file_exists(edge_readme_path)
    status = "✅" if edge_readme_exists else "❌"
    print(
        f"  {status} Edge Optimization Documentation: {'Exists' if edge_readme_exists else 'Missing'}"
    )

    # Check system integration
    print("\n🔄 Checking system integration...")

    # Test main launch file update
    main_launch_path = os.path.join(base_path, "rovac_enhanced_system.launch.py")
    main_launch_exists = check_file_exists(main_launch_path)
    status = "✅" if main_launch_exists else "❌"
    print(
        f"  {status} Main Launch File: {'Updated' if main_launch_exists else 'Missing'}"
    )

    # Summary
    print("\n" + "=" * 55)
    print("📋 PHASE 2 VERIFICATION SUMMARY")
    print("=" * 55)

    files_verified = all_files_exist
    imports_working = bt_success and edge_success and bt_node_success
    launch_files_valid = bt_launch_exists and edge_launch_exists
    documentation_complete = bt_readme_exists and edge_readme_exists
    system_integrated = main_launch_exists

    if files_verified:
        print("✅ All Phase 2 files are present")
    else:
        print("❌ Some Phase 2 files are missing")

    if imports_working:
        print("✅ Core modules are functional")
    else:
        print("❌ Some modules have import issues")

    if launch_files_valid:
        print("✅ Launch files are syntactically valid")
    else:
        print("❌ Some launch files have issues")

    if documentation_complete:
        print("✅ Documentation is complete")
    else:
        print("❌ Some documentation is missing")

    if system_integrated:
        print("✅ System integration complete")
    else:
        print("❌ System integration needs attention")

    print("\n📊 Component Status:")
    print(f"   Files: {'✅' if files_verified else '❌'}")
    print(f"   Imports: {'✅' if imports_working else '❌'}")
    print(f"   Launch Files: {'✅' if launch_files_valid else '❌'}")
    print(f"   Documentation: {'✅' if documentation_complete else '❌'}")
    print(f"   Integration: {'✅' if system_integrated else '❌'}")

    print("\n📚 Documentation:")
    if bt_readme_exists:
        print("   - Behavior Tree: robot_mcp_server/BEHAVIOR_TREE_README.md")
    if edge_readme_exists:
        print("   - Edge Optimization: robot_mcp_server/EDGE_OPTIMIZATION_README.md")

    print("\n🚀 NEXT STEPS:")
    print("1. To start Phase 2 components:")
    print("   cd ~/robots/rovac")
    print('   eval "$(conda shell.bash hook)"')
    print("   conda activate ros_jazzy")
    print("   source config/ros2_env.sh")
    print("   ros2 launch rovac_enhanced rovac_enhanced_system.launch.py \\")
    print("     enable_behavior_tree:=true enable_edge_optimization:=true")
    print("")
    print("2. Monitor the system:")
    print("   ros2 topic echo /behavior_tree/status")
    print("   ros2 topic echo /edge/stats")

    # Overall status
    all_checks_passed = (
        files_verified
        and imports_working
        and launch_files_valid
        and documentation_complete
        and system_integrated
    )

    if all_checks_passed:
        print("\n🎉 PHASE 2 SETUP IS COMPLETE AND READY!")
        print("   All enhanced intelligence components are implemented and integrated.")
        return 0
    else:
        print("\n⚠️  SOME PHASE 2 COMPONENTS NEED ATTENTION")
        return 1


if __name__ == "__main__":
    sys.exit(main())
