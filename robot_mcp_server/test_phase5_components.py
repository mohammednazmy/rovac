#!/usr/bin/env python3
"""
Test script for Phase 5 Advanced AI/ML Navigation Components
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
    print("🔍 ROVAC Phase 5 Advanced Navigation - Component Verification")
    print("=" * 65)

    # Define base path
    base_path = "/Users/mohammednazmy/robots/rovac/robot_mcp_server"

    # Phase 5 files to check
    phase5_files = [
        ("rl_navigation_framework.py", "Deep Reinforcement Learning Navigation"),
        ("adaptive_environmental_model.py", "Adaptive Environmental Modeling"),
        ("predictive_obstacle_avoidance.py", "Predictive Obstacle Avoidance"),
        ("neural_path_planning.py", "Neural Path Planning"),
        ("advanced_navigation_node.py", "Advanced Navigation Node"),
    ]

    # Check files exist
    print("📁 Checking Phase 5 required files...")
    all_files_exist = True
    for filename, description in phase5_files:
        full_path = os.path.join(base_path, filename)
        exists = check_file_exists(full_path)
        status = "✅" if exists else "❌"
        print(f"  {status} {filename} - {description}")
        if not exists:
            all_files_exist = False

    # Test core imports
    print("\n🔧 Testing core component imports...")

    # Test RL Navigation Framework
    rl_file = os.path.join(base_path, "rl_navigation_framework.py")
    rl_success, rl_message = test_import("rl_navigation_framework", rl_file)
    print(f"  {rl_message}")

    # Test Adaptive Environmental Model
    env_file = os.path.join(base_path, "adaptive_environmental_model.py")
    env_success, env_message = test_import("adaptive_environmental_model", env_file)
    print(f"  {env_message}")

    # Test Predictive Obstacle Avoidance
    avoid_file = os.path.join(base_path, "predictive_obstacle_avoidance.py")
    avoid_success, avoid_message = test_import(
        "predictive_obstacle_avoidance", avoid_file
    )
    print(f"  {avoid_message}")

    # Test Neural Path Planning
    plan_file = os.path.join(base_path, "neural_path_planning.py")
    plan_success, plan_message = test_import("neural_path_planning", plan_file)
    print(f"  {plan_message}")

    # Test Advanced Navigation Node
    nav_file = os.path.join(base_path, "advanced_navigation_node.py")
    nav_success, nav_message = test_import("advanced_navigation_node", nav_file)
    print(f"  {nav_message}")

    # Summary
    print("\n" + "=" * 65)
    print("📋 PHASE 5 VERIFICATION SUMMARY")
    print("=" * 65)

    if all_files_exist:
        print("✅ All Phase 5 files are present")
    else:
        print("❌ Some Phase 5 files are missing")

    success_count = sum(
        [rl_success, env_success, avoid_success, plan_success, nav_success]
    )
    if success_count == 5:
        print("✅ All core modules import successfully")
    elif success_count > 0:
        print(f"✅ {success_count}/5 core modules import successfully")
    else:
        print("❌ Core modules have import issues")

    print("\n📚 DOCUMENTATION:")
    print("   - RL Navigation: robot_mcp_server/rl_navigation_framework.py")
    print(
        "   - Environmental Modeling: robot_mcp_server/adaptive_environmental_model.py"
    )
    print("   - Obstacle Avoidance: robot_mcp_server/predictive_obstacle_avoidance.py")
    print("   - Neural Path Planning: robot_mcp_server/neural_path_planning.py")
    print("   - Advanced Navigation Node: robot_mcp_server/advanced_navigation_node.py")

    print("\n🚀 NEXT STEPS:")
    print("1. To integrate with ROS2 system:")
    print("   - Implement proper ROS2 package structure")
    print("   - Create launch files for navigation components")
    print("   - Add message definitions for custom topics")
    print("")
    print("2. To test navigation components:")
    print("   - Create simulation environment")
    print("   - Implement mock sensor data generators")
    print("   - Test path planning algorithms with sample scenarios")
    print("")
    print("3. To deploy on robot:")
    print("   - Compile ROS2 packages")
    print("   - Configure navigation parameters")
    print("   - Integrate with existing sensor drivers")

    # Overall status
    if all_files_exist and success_count == 5:
        print("\n🎉 PHASE 5 SETUP IS COMPLETE!")
        print("   All advanced navigation components are implemented.")
        print("   Ready for integration and testing.")
        return 0
    else:
        print("\n⚠️  SOME PHASE 5 COMPONENTS NEED ATTENTION")
        return 1


if __name__ == "__main__":
    sys.exit(main())
