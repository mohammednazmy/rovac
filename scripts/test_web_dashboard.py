#!/usr/bin/env python3
"""
Test script for web dashboard
"""

import sys
import os

# Add the robot_mcp_server directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "robot_mcp_server"))


def test_imports():
    """Test if all required modules can be imported"""
    try:
        import flask

        print("✓ Flask imported successfully")
        print(f"  Flask version: {flask.__version__}")
    except ImportError as e:
        print(f"✗ Flask import failed: {e}")

    try:
        # Try to import our dashboard
        import web_dashboard

        print("✓ Web dashboard imported successfully")
    except ImportError as e:
        print(f"✗ Web dashboard import failed: {e}")


if __name__ == "__main__":
    print("Testing Web Dashboard Imports")
    print("=" * 30)
    test_imports()
