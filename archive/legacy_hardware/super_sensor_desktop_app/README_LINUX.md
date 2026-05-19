# Super Sensor - Linux Installation Guide

This guide covers installing and running the Super Sensor application on Linux systems, including Raspberry Pi.

## Features

The Linux version provides the same features as the macOS app:

- **GUI Mode**: Full graphical interface (when desktop environment is available)
- **CLI Mode**: Complete text-based interface (for headless systems)
- **Auto-detection**: Automatically chooses GUI or CLI based on display availability

### Feature Comparison

| Feature | GUI Mode | CLI Mode |
|---------|----------|----------|
| Connection management | ✓ | ✓ |
| Ultrasonic sensor display | Visual radar | Text table |
| LED control | Color picker | Menu selection |
| Servo control | Slider + buttons | Menu selection |
| Continuous scan | ✓ | ✓ |
| Calibration | ✓ | ✓ |
| Firmware upload | ✓ | ✓ |
| Profile save/load | ✓ | ✓ |

## Quick Installation

### Automated Installation

```bash
# Clone or download the super_sensor directory to your Pi
cd super_sensor

# Run the installation script
chmod +x install_linux.sh
./install_linux.sh
```

### Manual Installation

1. **Install dependencies**:
   ```bash
   sudo apt update
   sudo apt install python3 python3-pip python3-tk
   pip3 install --user pyserial
   ```

2. **Install udev rules** (for USB device permissions):
   ```bash
   sudo cp udev/99-super-sensor.rules /etc/udev/rules.d/
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

3. **Add user to dialout group** (for serial port access):
   ```bash
   sudo usermod -a -G dialout $USER
   # Log out and back in for this to take effect
   ```

4. **Run the application**:
   ```bash
   python3 super_sensor_linux.py
   ```

## Usage

### Running the Application

```bash
# Auto-detect mode (GUI if display available, otherwise CLI)
python3 super_sensor_linux.py

# Force GUI mode
python3 super_sensor_linux.py --gui

# Force CLI mode (headless)
python3 super_sensor_linux.py --cli
```

If installed via the install script:
```bash
super-sensor          # Auto-detect
super-sensor --gui    # Force GUI
super-sensor --cli    # Force CLI
```

### CLI Mode Navigation

The CLI uses a simple menu-based interface:

```
Main Menu:
  [1] Control & Test
  [2] Setup & Install
  [3] Calibration
  [4] Connect/Disconnect
  [s] Quick Scan
  [q] Quit
```

Use number keys or letters to navigate. Press Enter after each selection.

### SSH Usage (Headless)

To use Super Sensor over SSH on a headless Raspberry Pi:

```bash
# SSH into your Pi
ssh pi@raspberrypi.local

# Run in CLI mode
super-sensor --cli
# or
cd ~/.local/share/super_sensor
python3 super_sensor_linux.py --cli
```

## Firmware Upload

The application can upload firmware to the Arduino Nano directly:

1. Go to **Setup & Install** menu
2. Select **Upload firmware**
3. Choose your serial port
4. Select the board type:
   - Arduino Nano (ATmega328P) - for newer boards
   - Arduino Nano (ATmega328P Old Bootloader) - for older/clone boards
5. Confirm upload

### Installing arduino-cli

If arduino-cli is not installed, you can install it from the Setup menu or manually:

```bash
# Using the install script method
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=~/.local/bin sh

# Add to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Install AVR core
arduino-cli core update-index
arduino-cli core install arduino:avr
arduino-cli lib install Servo
```

## Troubleshooting

### Permission Denied on Serial Port

If you see "Permission denied" when accessing the serial port:

1. Ensure udev rules are installed:
   ```bash
   ls -la /etc/udev/rules.d/99-super-sensor.rules
   ```

2. Ensure you're in the dialout group:
   ```bash
   groups | grep dialout
   ```
   If not, add yourself and log out/in:
   ```bash
   sudo usermod -a -G dialout $USER
   ```

3. Alternatively, run with sudo (not recommended for regular use):
   ```bash
   sudo python3 super_sensor_linux.py --cli
   ```

### Sensor Not Detected

1. Check if the device is connected:
   ```bash
   ls -la /dev/ttyUSB* /dev/ttyACM*
   ```

2. Check dmesg for connection info:
   ```bash
   dmesg | tail -20
   ```

3. Try unplugging and replugging the USB cable.

### GUI Not Starting

If the GUI fails to start on a system with a desktop:

1. Check if tkinter is installed:
   ```bash
   python3 -c "import tkinter; print('OK')"
   ```

2. Install if missing:
   ```bash
   sudo apt install python3-tk
   ```

3. Force CLI mode as fallback:
   ```bash
   super-sensor --cli
   ```

## Raspberry Pi Specific Notes

### Raspberry Pi OS Lite (Headless)

On Raspberry Pi OS Lite (no desktop), the application will automatically use CLI mode:

```bash
super-sensor  # Will auto-detect and use CLI
```

### Raspberry Pi with Desktop

On Raspberry Pi OS with Desktop, you can use either mode:

- Launch from terminal: `super-sensor`
- Launch from applications menu (if installed via install script)

### Serial Port Names

On Raspberry Pi, the USB serial adapter typically appears as:
- `/dev/ttyUSB0` - CH340/FTDI USB adapters
- `/dev/ttyACM0` - Arduino with native USB

The GPIO serial port is:
- `/dev/ttyAMA0` or `/dev/serial0` - GPIO pins (not used for Super Sensor)

## File Locations

After installation:

| Item | Location |
|------|----------|
| Application | `~/.local/share/super_sensor/` |
| Launcher | `~/.local/bin/super-sensor` |
| Desktop entry | `~/.local/share/applications/super-sensor.desktop` |
| Calibration profiles | `~/.config/super_sensor/` |
| udev rules | `/etc/udev/rules.d/99-super-sensor.rules` |

## Uninstallation

To remove Super Sensor:

```bash
# Remove application files
rm -rf ~/.local/share/super_sensor
rm -f ~/.local/bin/super-sensor
rm -f ~/.local/share/applications/super-sensor.desktop

# Optionally remove udev rules
sudo rm /etc/udev/rules.d/99-super-sensor.rules
sudo udevadm control --reload-rules
```
