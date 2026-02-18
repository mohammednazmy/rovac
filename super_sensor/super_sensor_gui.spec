# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Super Sensor GUI.

Usage:
    pyinstaller super_sensor_gui.spec
"""

import sys
from pathlib import Path

block_cipher = None

# Determine platform
is_macos = sys.platform == 'darwin'
is_linux = sys.platform.startswith('linux')

# App name
app_name = 'Super Sensor' if is_macos else 'super-sensor-gui'

# Data files to include
datas = [
    ('firmware', 'firmware'),
    ('super_sensor_driver.py', '.'),
    # Include super_sensor_gui package for relative imports
    ('super_sensor_gui', 'super_sensor_gui'),
    # Embedded resources for offline installation
    ('super_sensor_gui/embedded_resources', 'embedded_resources'),
]

# Add udev rules on Linux
if is_linux:
    datas.append(('udev', 'udev'))

# Hidden imports - include all package modules
hiddenimports = [
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'serial',
    'serial.tools',
    'serial.tools.list_ports',
    'json',
    'threading',
    'time',
    'subprocess',
    'pathlib',
    # super_sensor_gui package modules
    'super_sensor_gui',
    'super_sensor_gui.app',
    'super_sensor_gui.tabs',
    'super_sensor_gui.tabs.status_tab',
    'super_sensor_gui.tabs.control_tab',
    'super_sensor_gui.tabs.installer_tab',
    'super_sensor_gui.tabs.calibration_tab',
    'super_sensor_gui.widgets',
    'super_sensor_gui.widgets.radar_view',
    'super_sensor_gui.widgets.color_picker',
    'super_sensor_gui.widgets.log_panel',
    'super_sensor_gui.widgets.scrollable_frame',
    'super_sensor_gui.utils',
    'super_sensor_gui.utils.platform_utils',
    'super_sensor_gui.utils.sensor_controller',
    'super_sensor_gui.utils.arduino_utils',
    'super_sensor_gui.utils.screenshot_utils',
    'super_sensor_gui.utils.macos_utils',
]

a = Analysis(
    ['super_sensor_gui/main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if is_macos:
    # macOS: Create .app bundle
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=app_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name=app_name,
    )
    app = BUNDLE(
        coll,
        name=f'{app_name}.app',
        icon='assets/icon.icns' if Path('assets/icon.icns').exists() else None,
        bundle_identifier='com.rovac.supersensor',
        info_plist={
            'NSHighResolutionCapable': 'True',
            'CFBundleShortVersionString': '1.0.0',
        },
    )
else:
    # Linux: Create single executable
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name=app_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
