#!/bin/bash
# Run stereo camera integration tests
# Usage: ./run_tests.sh [--quick] [--ros2]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Stereo Camera Integration Tests ===${NC}"
echo ""

# Check if running on Pi or Mac
if [ -f /etc/os-release ] && grep -q "Ubuntu" /etc/os-release; then
    echo "Running on Pi (Ubuntu)"
    IS_PI=true
else
    echo "Running on Mac (remote tests)"
    IS_PI=false
fi

case "${1:-}" in
    --quick)
        echo "Running quick tests (no ROS2)..."
        if [ "$IS_PI" = true ]; then
            python3 test_stereo_integration.py --quick
        else
            ssh pi@192.168.1.200 "cd ~/rovac/hardware/stereo_cameras/tests && python3 test_stereo_integration.py --quick"
        fi
        ;;
    --ros2)
        echo "Running full ROS2 integration tests..."
        echo -e "${YELLOW}Note: Stereo nodes must be running for these tests${NC}"
        if [ "$IS_PI" = true ]; then
            source /opt/ros/jazzy/setup.bash
            [ -f /home/pi/robots/rovac/config/ros2_env.sh ] && source /home/pi/robots/rovac/config/ros2_env.sh
            python3 test_stereo_integration.py
        else
            ssh pi@192.168.1.200 bash -lc "
                source /opt/ros/jazzy/setup.bash
                [ -f /home/pi/robots/rovac/config/ros2_env.sh ] && source /home/pi/robots/rovac/config/ros2_env.sh
                cd ~/rovac/hardware/stereo_cameras/tests
                python3 test_stereo_integration.py
            "
        fi
        ;;
    *)
        echo "Usage: $0 {--quick|--ros2}"
        echo ""
        echo "  --quick  Run quick tests (camera, calibration - no ROS2 required)"
        echo "  --ros2   Run full tests (requires ROS2 and running nodes)"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}Tests complete!${NC}"
