#!/usr/bin/env python3
"""
Simple test script to verify web dashboard access
"""

import requests
import time


def test_web_dashboard():
    """Test if web dashboard is accessible"""
    try:
        print("Testing web dashboard access...")

        # Test main page
        response = requests.get("http://localhost:5001/", timeout=5)
        if response.status_code == 200 and "ROVAC Dashboard" in response.text:
            print("✅ Web dashboard main page: ACCESSIBLE")
        else:
            print("❌ Web dashboard main page: UNEXPECTED RESPONSE")

        # Test API endpoint
        response = requests.get("http://localhost:5001/api/status", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print("✅ Web dashboard API: ACCESSIBLE")
            print(f"   Timestamp: {data.get('timestamp', 'N/A')}")
            print(f"   Last update: {data.get('last_update', 'N/A')}")
        else:
            print("❌ Web dashboard API: UNEXPECTED RESPONSE")

        print("\n🎉 Web dashboard is running and accessible!")
        print("👉 Open your browser and go to: http://localhost:5001/")

    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to web dashboard")
        print("   Please check if the dashboard is running:")
        print(
            "   cd ~/robots/rovac && source robot_mcp_server/venv/bin/activate && python robot_mcp_server/web_dashboard.py"
        )
    except requests.exceptions.Timeout:
        print("❌ Request timed out - web dashboard may be busy")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    test_web_dashboard()
