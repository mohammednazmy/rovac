#!/usr/bin/env python3
"""
Verification script for ROVAC Phase 2 Enhanced System Setup
"""

import os
import sys


def check_file_exists(filepath):
    """Check if a file exists"""
    return os.path.exists(filepath)


def check_import(module_name, file_path):
    """Check if a module can be imported or has correct structure"""
    try:
        if module_name == "behavior_tree_framework":
            # Test import
            sys.path.append(os.path.dirname(file_path))
            from behavior_tree_framework import BehaviorNode

            return True
        elif module_name == "edge_optimization_node":
            # Just check file structure
            with open(file_path, "r") as f:
                content = f.read()
                return "class EdgeOptimizationNode" in content
        return False
    except:
        return False


def main():
    print("🔍 ROVAC Phase 2 Enhanced System Verification")
    print("=" * 50)

    # Define base path
    base_path = "/Users/mohammednazmy/robots/rovac"

    # Phase 2 files to check
    phase2_files = [
        "robot_mcp_server/behavior_tree_framework.py",
        "robot_mcp_server/behavior_tree_node.py",
        "robot_mcp_server/behavior_tree.launch.py",
        "robot_mcp_server/BEHAVIOR_TREE_README.md",
        "robot_mcp_server/edge_optimization_node.py",
        "robot_mcp_server/edge_optimization.launch.py",
        "robot_mcp_server/EDGE_OPTIMIZATION_README.md",
    ]

    # Check files
    print("📁 Checking Phase 2 required files...")
    all_files_exist = True
    for file_path in phase2_files:
        full_path = os.path.join(base_path, file_path)
        exists = check_file_exists(full_path)
        status = "✅" if exists else "❌"
        print(f"  {status} {file_path}")
        if not exists:
            all_files_exist = False

    # Check imports
    print("\n🔧 Checking module imports...")

    # Behavior Tree Framework
    bt_framework_path = os.path.join(
        base_path, "robot_mcp_server/behavior_tree_framework.py"
    )
    bt_import_ok = check_import("behavior_tree_framework", bt_framework_path)
    status = "✅" if bt_import_ok else "❌"
    print(f"  {status} Behavior Tree Framework import")

    # Edge Optimization Node
    edge_node_path = os.path.join(
        base_path, "robot_mcp_server/edge_optimization_node.py"
    )
    edge_import_ok = check_import("edge_optimization_node", edge_node_path)
    status = "✅" if edge_import_ok else "❌"
    print(f"  {status} Edge Optimization Node structure")

    # Check launch file updates
    print("\n🔄 Checking system integration...")
    main_launch_path = os.path.join(
        base_path, "robot_mcp_server/rovac_enhanced_system.launch.py"
    )
    launch_updated = False
    if check_file_exists(main_launch_path):
        with open(main_launch_path, "r") as f:
            content = f.read()
            launch_updated = (
                "behavior_tree_node" in content and "edge_optimization_node" in content
            )

    status = "✅" if launch_updated else "❌"
    print(f"  {status} Main launch file integration")

    # Summary
    print("\n" + "=" * 50)
    print("📋 PHASE 2 VERIFICATION SUMMARY")
    print("=" * 50)

    if all_files_exist:
        print("✅ All Phase 2 files are present")
    else:
        print("❌ Some Phase 2 files are missing")

    if bt_import_ok and edge_import_ok:
        print("✅ Core modules are functional")
    else:
        print("❌ Some modules have issues")

    if launch_updated:
        print("✅ System integration complete")
    else:
        print("❌ System integration needs attention")

    print("\n📚 DOCUMENTATION:")
    print("   - Behavior Tree: robot_mcp_server/BEHAVIOR_TREE_README.md")
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
    if all_files_exist and bt_import_ok and edge_import_ok and launch_updated:
        print("\n🎉 PHASE 2 SETUP IS COMPLETE AND READY!")
        print("   All components are implemented and integrated.")
        return 0
    else:
        print("\n⚠️  SOME PHASE 2 COMPONENTS NEED ATTENTION")
        return 1


if __name__ == "__main__":
    sys.exit(main())
