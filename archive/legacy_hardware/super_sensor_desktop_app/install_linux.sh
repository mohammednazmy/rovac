#!/bin/bash
#
# Super Sensor - Linux Installation Script
#
# This script installs the Super Sensor application on Linux systems
# (Ubuntu, Raspberry Pi OS, Debian, etc.)
#
# Usage:
#   chmod +x install_linux.sh
#   ./install_linux.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Installation directory
INSTALL_DIR="$HOME/.local/share/super_sensor"
BIN_DIR="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║         Super Sensor - Linux Installation Script          ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if running as root (not recommended)
if [ "$EUID" -eq 0 ]; then
    echo -e "${YELLOW}Warning: Running as root is not recommended.${NC}"
    echo "Some steps will use sudo when needed."
    echo ""
fi

# ==================== Functions ====================

print_step() {
    echo -e "\n${BLUE}==> $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_command() {
    command -v "$1" &> /dev/null
}

# ==================== System Detection ====================

print_step "Detecting system..."

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$NAME
    OS_ID=$ID
    OS_VERSION=$VERSION_ID
else
    OS=$(uname -s)
    OS_ID="unknown"
    OS_VERSION=""
fi

# Detect architecture
ARCH=$(uname -m)

# Detect if Raspberry Pi
IS_RASPI=false
if [ -f /proc/device-tree/model ]; then
    if grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
        IS_RASPI=true
    fi
fi

echo "  OS: $OS"
echo "  Architecture: $ARCH"
if $IS_RASPI; then
    echo "  Platform: Raspberry Pi"
fi

# ==================== Python Check ====================

print_step "Checking Python..."

if check_command python3; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    print_success "Python $PYTHON_VERSION found"
else
    print_error "Python 3 not found"
    echo "Please install Python 3:"
    echo "  sudo apt install python3 python3-pip"
    exit 1
fi

# ==================== Install Dependencies ====================

print_step "Installing Python dependencies..."

# Check if pip is available
if ! check_command pip3; then
    echo "Installing pip..."
    sudo apt install -y python3-pip
fi

# Install pyserial
if python3 -c "import serial" 2>/dev/null; then
    print_success "pyserial already installed"
else
    echo "Installing pyserial..."
    pip3 install --user pyserial
    print_success "pyserial installed"
fi

# Install tkinter (for GUI mode)
print_step "Checking tkinter (for GUI mode)..."
if python3 -c "import tkinter" 2>/dev/null; then
    print_success "tkinter available"
else
    echo "Installing tkinter..."
    sudo apt install -y python3-tk
    print_success "tkinter installed"
fi

# ==================== udev Rules ====================

print_step "Setting up udev rules..."

UDEV_RULES_FILE="/etc/udev/rules.d/99-super-sensor.rules"
UDEV_RULES='# Super Sensor USB Serial (CH340/CH341)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666", SYMLINK+="super_sensor"
# FTDI USB Serial
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", MODE="0666"
# Arduino
SUBSYSTEM=="tty", ATTRS{idVendor}=="2341", MODE="0666"'

if [ -f "$UDEV_RULES_FILE" ]; then
    print_success "udev rules already installed"
else
    echo "Installing udev rules (requires sudo)..."
    echo "$UDEV_RULES" | sudo tee "$UDEV_RULES_FILE" > /dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    print_success "udev rules installed"
fi

# ==================== dialout Group ====================

print_step "Checking dialout group membership..."

if groups | grep -q dialout; then
    print_success "User is in dialout group"
else
    echo "Adding user to dialout group (requires sudo)..."
    sudo usermod -a -G dialout "$USER"
    print_success "Added to dialout group"
    print_warning "You will need to log out and back in for this to take effect"
fi

# ==================== Install Application ====================

print_step "Installing Super Sensor application..."

# Create installation directory
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

# Copy files
echo "Copying files to $INSTALL_DIR..."
cp -r "$SCRIPT_DIR/super_sensor_driver.py" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/super_sensor_gui" "$INSTALL_DIR/" 2>/dev/null || true
cp -r "$SCRIPT_DIR/super_sensor_cli" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/super_sensor_linux.py" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/firmware" "$INSTALL_DIR/" 2>/dev/null || true

# Create launcher script
cat > "$BIN_DIR/super-sensor" << 'LAUNCHER'
#!/bin/bash
# Super Sensor Launcher
cd "$HOME/.local/share/super_sensor"
python3 super_sensor_linux.py "$@"
LAUNCHER
chmod +x "$BIN_DIR/super-sensor"

print_success "Application installed to $INSTALL_DIR"
print_success "Launcher created at $BIN_DIR/super-sensor"

# ==================== Desktop Entry (if GUI available) ====================

if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
    print_step "Creating desktop entry..."

    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"

    cat > "$DESKTOP_DIR/super-sensor.desktop" << DESKTOP
[Desktop Entry]
Name=Super Sensor
Comment=Control and test Super Sensor module
Exec=$BIN_DIR/super-sensor --gui
Icon=utilities-system-monitor
Terminal=false
Type=Application
Categories=Utility;Development;
DESKTOP

    # Update desktop database
    if check_command update-desktop-database; then
        update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    fi

    print_success "Desktop entry created"
fi

# ==================== PATH Check ====================

print_step "Checking PATH..."

if echo "$PATH" | grep -q "$BIN_DIR"; then
    print_success "$BIN_DIR is in PATH"
else
    print_warning "$BIN_DIR is not in PATH"
    echo ""
    echo "Add the following line to your ~/.bashrc or ~/.profile:"
    echo -e "  ${BLUE}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
    echo ""
    echo "Then run: source ~/.bashrc"

    # Offer to add it automatically
    read -p "Add to ~/.bashrc now? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
        print_success "Added to ~/.bashrc"
        echo "Run 'source ~/.bashrc' or start a new terminal to apply."
    fi
fi

# ==================== arduino-cli (Optional) ====================

print_step "Checking arduino-cli (optional, for firmware upload)..."

if check_command arduino-cli; then
    ARDUINO_VERSION=$(arduino-cli version 2>&1 | grep -oP 'Version:\s*\K[\d.]+' || echo "installed")
    print_success "arduino-cli $ARDUINO_VERSION found"
else
    print_warning "arduino-cli not installed"
    echo ""
    read -p "Install arduino-cli? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Installing arduino-cli..."
        mkdir -p "$BIN_DIR"
        curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR="$BIN_DIR" sh

        if [ -f "$BIN_DIR/arduino-cli" ]; then
            print_success "arduino-cli installed"

            # Install AVR core
            echo "Installing Arduino AVR core..."
            "$BIN_DIR/arduino-cli" core update-index
            "$BIN_DIR/arduino-cli" core install arduino:avr
            "$BIN_DIR/arduino-cli" lib install Servo
            print_success "Arduino AVR core and Servo library installed"
        else
            print_error "arduino-cli installation failed"
        fi
    fi
fi

# ==================== Summary ====================

echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              Installation Complete!                       ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo "To run Super Sensor:"
echo ""
echo "  CLI mode (headless):    super-sensor --cli"
echo "  GUI mode (desktop):     super-sensor --gui"
echo "  Auto-detect:            super-sensor"
echo ""

if ! groups | grep -q dialout; then
    echo -e "${YELLOW}IMPORTANT: Log out and back in for dialout group changes to take effect.${NC}"
    echo ""
fi

if ! echo "$PATH" | grep -q "$BIN_DIR"; then
    echo -e "${YELLOW}IMPORTANT: Run 'source ~/.bashrc' or start a new terminal.${NC}"
    echo ""
fi

echo "For more help, run: super-sensor --cli and select Setup & Install"
echo ""
