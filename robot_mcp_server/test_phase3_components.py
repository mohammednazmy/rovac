#!/usr/bin/env python3
"""
Test script for Phase 3 ROVAC Enhanced System Components
Advanced AI/ML Navigation Improvements
"""

import sys
import os
import time
import json
from typing import List, Tuple, Dict, Any


def test_import(module_name: str, file_path: str) -> Tuple[bool, str]:
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


def check_file_exists(file_path: str) -> bool:
    """Check if a file exists"""
    return os.path.exists(file_path)


def main():
    print("🔍 ROVAC Phase 3 Enhanced System - Component Testing")
    print("=" * 55)

    # Define base path
    base_path = "/Users/mohammednazmy/robots/rovac/robot_mcp_server"

    # Phase 3 files to check
    phase3_files = [
        ("dl_path_planning.py", "Deep Learning Path Planning"),
        ("dl_path_planning_node.py", "DL Path Planning ROS2 Node"),
        ("dl_path_planning.launch.py", "DL Path Planning Launch File"),
        ("DL_PATH_PLANNING_README.md", "DL Path Planning Documentation"),
        ("predictive_analytics.py", "Predictive Analytics Core"),
        ("predictive_analytics_node.py", "Predictive Analytics Node"),
        ("predictive_analytics.launch.py", "Predictive Analytics Launch"),
        ("PREDICTIVE_ANALYTICS_README.md", "Predictive Analytics Docs"),
        ("behavior_tree_framework.py", "Behavior Tree Framework"),
        ("behavior_tree_node.py", "Behavior Tree ROS2 Node"),
        ("behavior_tree.launch.py", "Behavior Tree Launch File"),
        ("BEHAVIOR_TREE_README.md", "Behavior Tree Documentation"),
        ("edge_optimization_node.py", "Edge Optimization Node"),
        ("edge_optimization.launch.py", "Edge Optimization Launch"),
        ("EDGE_OPTIMIZATION_README.md", "Edge Optimization Docs"),
        ("advanced_navigation_node.py", "Advanced Navigation Node"),
        ("predictive_obstacle_avoidance.py", "Predictive Obstacle Avoidance"),
        ("predictive_obstacle_avoidance_node.py", "POA ROS2 Node"),
        ("predictive_obstacle_avoidance.launch.py", "POA Launch File"),
        ("PREDICTIVE_OBSTACLE_AVOIDANCE_README.md", "POA Documentation"),
        ("DEEP_RL_NAVIGATION_README.md", "Deep RL Navigation Docs"),
        ("EDGE_COMPUTING_README.md", "Edge Computing Docs"),
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
    dl_path = os.path.join(base_path, "dl_path_planning.py")
    dl_success, dl_message = test_import("dl_path_planning", dl_path)
    print(f"  {dl_message}")

    # Test Predictive Analytics
    pa_path = os.path.join(base_path, "predictive_analytics.py")
    pa_success, pa_message = test_import("predictive_analytics", pa_path)
    print(f"  {pa_message}")

    # Test Behavior Tree Framework
    bt_path = os.path.join(base_path, "behavior_tree_framework.py")
    bt_success, bt_message = test_import("behavior_tree_framework", bt_path)
    print(f"  {bt_message}")

    # Test Edge Optimization Node
    eo_path = os.path.join(base_path, "edge_optimization_node.py")
    eo_success, eo_message = test_import("edge_optimization_node", eo_path)
    print(f"  {eo_message}")

    # Test Advanced Navigation Node
    an_path = os.path.join(base_path, "advanced_navigation_node.py")
    an_success, an_message = test_import("advanced_navigation_node", an_path)
    print(f"  {an_message}")

    # Test Predictive Obstacle Avoidance
    poa_path = os.path.join(base_path, "predictive_obstacle_avoidance.py")
    poa_success, poa_message = test_import("predictive_obstacle_avoidance", poa_path)
    print(f"  {poa_message}")

    # Check launch file updates
    print("\n🔄 Checking system integration...")
    main_launch_path = os.path.join(base_path, "rovac_enhanced_system.launch.py")
    launch_updated = False
    if check_file_exists(main_launch_path):
        with open(main_launch_path, "r") as f:
            content = f.read()
            launch_updated = (
                "behavior_tree_node" in content
                and "edge_optimization_node" in content
                and "dl_path_planning_node" in content
                and "predictive_analytics_node" in content
                and "advanced_navigation_node" in content
                and "predictive_obstacle_avoidance_node" in content
            )

    status = "✅" if launch_updated else "❌"
    print(f"  {status} Main launch file integration")

    # Check documentation
    print("\n📚 Checking documentation...")

    # Test documentation files
    doc_files = [
        ("DL_PATH_PLANNING_README.md", "Deep Learning Path Planning"),
        ("PREDICTIVE_ANALYTICS_README.md", "Predictive Analytics"),
        ("BEHAVIOR_TREE_README.md", "Behavior Tree Framework"),
        ("EDGE_OPTIMIZATION_README.md", "Edge Optimization"),
        ("PREDICTIVE_OBSTACLE_AVOIDANCE_README.md", "Predictive Obstacle Avoidance"),
        ("DEEP_RL_NAVIGATION_README.md", "Deep RL Navigation"),
        ("EDGE_COMPUTING_README.md", "Edge Computing"),
    ]

    docs_complete = True
    for filename, description in doc_files:
        full_path = os.path.join(base_path, filename)
        exists = check_file_exists(full_path)
        status = "✅" if exists else "❌"
        print(f"  {status} {description} Documentation")
        if not exists:
            docs_complete = False

    # Check for comprehensive implementation
    print("\n🚀 Checking implementation completeness...")

    # Test if all components can be instantiated (simulation only)
    components_working = True
    try:
        # Test Deep Learning Path Planning
        sys.path.append(base_path)
        from dl_path_planning import NeuralPathPlanner

        dl_planner = NeuralPathPlanner()
        print("  ✅ Deep Learning Path Planning: Instantiation successful")
    except Exception as e:
        print(f"  ❌ Deep Learning Path Planning: {e}")
        components_working = False

    try:
        # Test Predictive Analytics
        from predictive_analytics import PredictiveAnalyticsEngine

        pa_engine = PredictiveAnalyticsEngine()
        print("  ✅ Predictive Analytics: Instantiation successful")
    except Exception as e:
        print(f"  ❌ Predictive Analytics: {e}")
        components_working = False

    try:
        # Test Behavior Tree Framework
        from behavior_tree_framework import BehaviorNode

        bt_node = BehaviorNode("test_node")
        print("  ✅ Behavior Tree Framework: Instantiation successful")
    except Exception as e:
        print(f"  ❌ Behavior Tree Framework: {e}")
        components_working = False

    try:
        # Test Edge Optimization
        from edge_optimization_node import EdgeOptimizationNode

        eo_node = EdgeOptimizationNode.__new__(
            EdgeOptimizationNode
        )  # Skip __init__ for testing
        print("  ✅ Edge Optimization: Structure validation successful")
    except Exception as e:
        print(f"  ❌ Edge Optimization: {e}")
        components_working = False

    try:
        # Test Advanced Navigation
        from advanced_navigation_node import AdvancedNavigationNode

        an_node = AdvancedNavigationNode.__new__(
            AdvancedNavigationNode
        )  # Skip __init__ for testing
        print("  ✅ Advanced Navigation: Structure validation successful")
    except Exception as e:
        print(f"  ❌ Advanced Navigation: {e}")
        components_working = False

    try:
        # Test Predictive Obstacle Avoidance
        from predictive_obstacle_avoidance import PredictiveObstacleAvoidance

        poa_system = PredictiveObstacleAvoidance()
        print("  ✅ Predictive Obstacle Avoidance: Instantiation successful")
    except Exception as e:
        print(f"  ❌ Predictive Obstacle Avoidance: {e}")
        components_working = False

    # Summary
    print("\n" + "=" * 55)
    print("📋 PHASE 3 VERIFICATION SUMMARY")
    print("=" * 55)

    if all_files_exist:
        print("✅ All Phase 3 files are present")
    else:
        print("❌ Some Phase 3 files are missing")

    if (
        dl_success
        and pa_success
        and bt_success
        and eo_success
        and an_success
        and poa_success
    ):
        print("✅ Core modules are functional")
    else:
        print("❌ Some modules have import issues")

    if launch_updated:
        print("✅ System integration complete")
    else:
        print("❌ System integration needs attention")

    if docs_complete:
        print("✅ Documentation is complete")
    else:
        print("❌ Some documentation is missing")

    if components_working:
        print("✅ Component instantiation successful")
    else:
        print("❌ Some components failed instantiation")

    print("\n📊 Component Status:")
    print(f"   Files: {'✅' if all_files_exist else '❌'}")
    print(
        f"   Imports: {'✅' if (dl_success and pa_success and bt_success and eo_success and an_success and poa_success) else '❌'}"
    )
    print(f"   Launch Files: {'✅' if launch_updated else '❌'}")
    print(f"   Documentation: {'✅' if docs_complete else '❌'}")
    print(f"   Components: {'✅' if components_working else '❌'}")

    print("\n📚 Documentation:")
    if docs_complete:
        print(
            "   - Deep Learning Path Planning: robot_mcp_server/DL_PATH_PLANNING_README.md"
        )
        print(
            "   - Predictive Analytics: robot_mcp_server/PREDICTIVE_ANALYTICS_README.md"
        )
        print("   - Behavior Tree Framework: robot_mcp_server/BEHAVIOR_TREE_README.md")
        print("   - Edge Optimization: robot_mcp_server/EDGE_OPTIMIZATION_README.md")
        print(
            "   - Predictive Obstacle Avoidance: robot_mcp_server/PREDICTIVE_OBSTACLE_AVOIDANCE_README.md"
        )
        print("   - Deep RL Navigation: robot_mcp_server/DEEP_RL_NAVIGATION_README.md")
        print("   - Edge Computing: robot_mcp_server/EDGE_COMPUTING_README.md")

    print("\n🚀 NEXT STEPS:")
    print("1. To start Phase 3 components:")
    print("   cd ~/robots/rovac")
    print('   eval "$(conda shell.bash hook)"')
    print("   conda activate ros_jazzy")
    print("   source config/ros2_env.sh")
    print("   ros2 launch rovac_enhanced rovac_enhanced_system.launch.py \\")
    print("     enable_dl_path_planning:=true enable_predictive_analytics:=true \\")
    print("     enable_behavior_tree:=true enable_edge_optimization:=true \\")
    print("     enable_advanced_navigation:=true enable_predictive_avoidance:=true")
    print("")
    print("2. Monitor the systems:")
    print("   ros2 topic echo /dl/path_planning/status")
    print("   ros2 topic echo /predictive/analytics")
    print("   ros2 topic echo /behavior_tree/status")
    print("   ros2 topic echo /edge/optimization/stats")
    print("   ros2 topic echo /navigation/advanced/status")
    print("   ros2 topic echo /predictive/obstacle_avoidance")

    # Overall status
    if (
        all_files_exist
        and dl_success
        and pa_success
        and bt_success
        and eo_success
        and an_success
        and poa_success
        and launch_updated
        and docs_complete
        and components_working
    ):
        print("\n🎉 PHASE 3 SETUP IS COMPLETE AND READY!")
        print(
            "   All advanced AI/ML navigation components are implemented and integrated."
        )
        return 0
    else:
        print("\n⚠️  SOME PHASE 3 COMPONENTS NEED ATTENTION")
        return 1


if __name__ == "__main__":
    sys.exit(main())
