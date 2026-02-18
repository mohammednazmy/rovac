@echo off
echo ROVAC LIDAR USB Bridge Windows Installation
echo ==========================================

echo.
echo This script helps set up the ROVAC LIDAR USB Bridge on Windows.
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running with administrator privileges
) else (
    echo Warning: This script may require administrator privileges
    echo Right-click and select "Run as administrator" if problems occur
)

echo.
echo Step 1: Checking for CH340 drivers
echo ----------------------------------

driverquery | findstr /i "ch340"
if %errorLevel% == 0 (
    echo ✅ CH340 driver appears to be installed
) else (
    echo ℹ️  CH340 driver may need to be installed
    echo    Download from: http://www.wch.cn/downloads/CH341SER_EXE.html
)

echo.
echo Step 2: Information for Device Manager
echo -------------------------------------

echo When viewing the device in Device Manager, look for:
echo - USB Serial Port (with CH340 in the name)
echo - Hardware ID should contain VID_1A86 PID_7523

echo.
echo Step 3: Testing the device
echo --------------------------

echo To test the device, run:
echo python "%~dp0test_device.py"

echo.
echo Installation notes:
echo - The device should appear as a COM port
echo - Standard baud rate is 115200
echo - No additional drivers are typically required for Windows 10/11

pause