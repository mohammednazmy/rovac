# Super Sensor GUI

A cross-platform GUI application for controlling and configuring the Super Sensor module.

## Features

### Native macOS Experience
- **Light/Dark Mode**: Automatically adapts to system appearance settings
- **Standard Menu Bar**: File, Edit, View, Sensor, Window, Debug, Help menus
- **Keyboard Shortcuts**: Standard macOS shortcuts (⌘Q, ⌘S, ⌘O, etc.)
- **Context Menus**: Right-click for context-sensitive actions
- **Native Window Controls**: Standard close, minimize, zoom buttons

### Sensor Control
- **Real-time Monitoring**: Live display of all 4 ultrasonic sensors
- **Visual Radar View**: Graphical representation of sensor readings
- **Continuous Polling**: Configurable scan rates (5/10/20 Hz)
- **LED Control**: RGB color picker with presets
- **Servo Control**: Angle slider with preset positions and sweep function

### Setup & Installation
- **One-click Driver Installation**: pyserial, udev rules, dialout group
- **Firmware Upload**: Built-in arduino-cli integration
- **Auto-detection**: Automatic port detection for Super Sensor

### Calibration
- **Sensor Offset Calibration**: Individual offset adjustment per sensor
- **Servo Calibration**: Min/center/max angle configuration
- **Profile Management**: Save and load calibration profiles

## Installation

### Requirements
- Python 3.8+
- tkinter (included with Python on macOS)
- pyserial

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run from Source
```bash
cd super_sensor
python3 -m super_sensor_gui.main
```

## Building Standalone App

### macOS
```bash
./build/build_macos.sh
```

This creates `dist/Super Sensor.app` with:
- Native .app bundle
- Info.plist with proper metadata
- Application icon
- All dependencies bundled

### Linux
```bash
./build/build_linux.sh
```

Creates `dist/super-sensor-gui` standalone executable.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| ⌘1-4 | Switch between tabs |
| ⌘R | Refresh serial ports |
| ⌘N | New profile |
| ⌘O | Open profile |
| ⌘S | Save profile |
| ⇧⌘S | Save profile as |
| ⌘M | Minimize window |
| ⌘W | Close window |
| ⌘Q | Quit application |
| F1 | Help |
| ⇧⌘D | Take screenshot (debug) |

## Menu Structure

### File Menu
- New Profile
- Open Profile...
- Save
- Save As...
- Export Log...

### Edit Menu
- Undo / Redo
- Cut / Copy / Paste
- Select All

### View Menu
- Status / Control / Setup / Calibration tabs
- Refresh Ports

### Sensor Menu
- Connect / Disconnect
- Scan Once
- Start/Stop Continuous Scan
- LED Off
- Center Servo

### Window Menu
- Minimize
- Zoom
- Bring All to Front

### Debug Menu
- Take Screenshot
- Screenshot All Tabs
- Open Screenshot Folder
- Ping Sensor
- Get Full Status

### Help Menu
- Super Sensor Help
- Documentation
- Release Notes
- About

## Context Menus

Right-click on different areas for context-sensitive actions:

### Calibration Tab
- Test All Sensors
- Reset All Offsets
- Copy Values
- Test LED channels
- Servo presets
- Profile management

## Theme Support

The app automatically detects and adapts to macOS appearance:

- **Light Mode**: Light backgrounds, dark text
- **Dark Mode**: Dark backgrounds, light text

Theme changes are detected in real-time (every 2 seconds).

## Architecture

```
super_sensor_gui/
├── main.py                 # Entry point
├── app.py                  # Main application (menus, shortcuts, theming)
├── tabs/
│   ├── status_tab.py       # Connection management
│   ├── control_tab.py      # Real-time control
│   ├── installer_tab.py    # Driver/firmware setup
│   └── calibration_tab.py  # Calibration tools
├── widgets/
│   ├── radar_view.py       # Visual sensor display
│   ├── color_picker.py     # RGB color picker
│   └── log_panel.py        # Scrolling log
└── utils/
    ├── platform_utils.py   # Cross-platform utilities
    ├── macos_utils.py      # macOS-specific features
    ├── sensor_controller.py # Thread-safe communication
    ├── arduino_utils.py    # arduino-cli integration
    └── screenshot_utils.py # Debug screenshots
```

## Accessibility

The app follows standard accessibility guidelines:
- All controls are keyboard-navigable
- Standard focus management
- Screen reader compatible labels
- High contrast color schemes

## License

Copyright © 2025 ROVAC Project. All rights reserved.
