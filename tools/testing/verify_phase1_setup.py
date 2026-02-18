#!/usr/bin/env python3
"""
Verification script for ROVAC Phase 1 Enhanced System Setup
"""

import os
import subprocess
import sys
import requests
import time


def check_file_exists(filepath):
    """Check if a file exists"""
    return os.path.exists(filepath)


def check_process_running(pattern):
    """Check if a process is running"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True
        )
        return result.returncode == 0
    except:
        return False


def check_port_open(port):
    """Check if a port is open"""
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}"], capture_output=True, text=True
        )
        return "LISTEN" in result.stdout
    except:
        return False


def check_web_access(url):
    """Check if web URL is accessible"""
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except:
        return False


def check_api_access(url):
    """Check if API endpoint is accessible"""
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200 and response.json()
    except:
        return False


def main():
    print("🔍 ROVAC Phase 1 Enhanced System Verification")
    print("=" * 50)

    # Define file paths
    base_path = "/Users/mohammednazmy/robots/rovac"
    files_to_check = [
        "robot_mcp_server/object_recognition_node.py",
        "robot_mcp_server/object_recognition.launch.py",
        "robot_mcp_server/rovac_enhanced_system.launch.py",
        "robot_mcp_server/web_dashboard.py",
        "robot_mcp_server/templates/dashboard.html",
    ]

    # Check files
    print("📁 Checking required files...")
    all_files_exist = True
    for file_path in files_to_check:
        full_path = os.path.join(base_path, file_path)
        exists = check_file_exists(full_path)
        status = "✅" if exists else "❌"
        print(f"  {status} {file_path}")
        if not exists:
            all_files_exist = False

    # Check web dashboard process
    print("\n🖥️  Checking web dashboard process...")
    dashboard_running = check_process_running("web_dashboard.py")
    status = "✅" if dashboard_running else "⚠️"
    print(f"  {status} Web dashboard process running")

    # Check port 5001
    print("\n🔌 Checking port 5001...")
    port_open = check_port_open(5001)
    status = "✅" if port_open else "⚠️"
    print(f"  {status} Port 5001 open")

    # Check web access
    print("\n🌐 Checking web access...")
    web_accessible = check_web_access("http://localhost:5001/")
    status = "✅" if web_accessible else "⚠️"
    print(f"  {status} Web dashboard accessible")

    # Check API access
    print("\n🔧 Checking API access...")
    api_accessible = check_api_access("http://localhost:5001/api/status")
    status = "✅" if api_accessible else "⚠️"
    print(f"  {status} API endpoint accessible")

    # Summary
    print("\n" + "=" * 50)
    print("📋 VERIFICATION SUMMARY")
    print("=" * 50)

    if all_files_exist:
        print("✅ All required files are present")
    else:
        print("❌ Some required files are missing")

    if dashboard_running and port_open:
        print("✅ Web dashboard is running")
    else:
        print("⚠️  Web dashboard may not be running properly")

    if web_accessible and api_accessible:
        print("✅ Web interface is accessible")
        print("   👉 Open http://localhost:5001/ in your browser")
    else:
        print("⚠️  Web interface may have connectivity issues")

    print("\n🚀 NEXT STEPS:")
    print("1. Open your browser and go to http://localhost:5001/")
    print("2. To start enhanced system components:")
    print("   cd ~/robots/rovac")
    print('   eval "$(conda shell.bash hook)"')
    print("   conda activate ros_jazzy")
    print("   source config/ros2_env.sh")
    print("   ros2 launch rovac_enhanced rovac_enhanced_system.launch.py")

    # Overall status
    if all_files_exist and web_accessible and api_accessible:
        print("\n🎉 PHASE 1 SETUP IS COMPLETE AND WORKING!")
        return 0
    else:
        print("\n⚠️  SOME COMPONENTS NEED ATTENTION")
        return 1


if __name__ == "__main__":
    sys.exit(main())
