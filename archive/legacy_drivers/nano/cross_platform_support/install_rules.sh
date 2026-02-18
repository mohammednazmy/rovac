#!/bin/bash
# Cross-platform installation script for LIDAR USB bridge

PLATFORM=$(uname -s)

echo "Installing ROVAC LIDAR USB Bridge support for $PLATFORM..."

case $PLATFORM in
    "Darwin")
        echo "Setting up macOS support..."
        # macOS typically handles CH340 devices automatically
        # Ensure the kext is loaded
        if kextstat | grep -q wch; then
            echo "✅ WCH driver already loaded"
        else
            echo "ℹ️  You may need to approve the WCH driver in System Preferences > Security"
        fi
        ;;
        
    "Linux")
        echo "Setting up Linux support..."
        # Create udev rule for consistent device naming
        sudo tee /etc/udev/rules.d/99-rovac-lidar.rules > /dev/null <<'EOF'
# ROVAC LIDAR USB Bridge
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", SYMLINK+="rovac_lidar", MODE="0666"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5523", SYMLINK+="rovac_lidar", MODE="0666"
EOF
        
        # Reload udev rules
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        
        # Add user to dialout group
        sudo usermod -a -G dialout $USER
        
        echo "✅ Linux support installed"
        echo "ℹ️  You may need to log out and back in for group changes to take effect"
        ;;
        
    *)
        echo "⚠️  Unsupported platform: $PLATFORM"
        echo "Please install CH340 drivers manually"
        ;;
esac

echo "Installation complete!"
echo ""
echo "To test the device:"
echo "  1. Connect the LIDAR USB bridge"
echo "  2. Run: ~/robots/rovac/nano/cross_platform_support/test_device.py"