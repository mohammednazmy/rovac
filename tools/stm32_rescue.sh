#!/usr/bin/env bash
# STM32 Rescue Tool — diagnose Yahboom YB-ERF01-V3.0 via SWD
#
# Prerequisites:
#   - OpenOCD installed: sudo apt install openocd
#   - Wiring: Pi GPIO24→SWDIO, GPIO25→SWCLK, GND→GND
#
# Usage:
#   ./tools/stm32_rescue.sh probe      # Test SWD connection
#   ./tools/stm32_rescue.sh dump       # Dump first 4KB of flash
#   ./tools/stm32_rescue.sh flash FILE # Flash a .hex or .bin file
#   ./tools/stm32_rescue.sh erase      # Erase entire flash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CFG="$SCRIPT_DIR/openocd_swd_pi5.cfg"
DUMP_FILE="/tmp/stm32_flash_dump.bin"

if [ ! -f "$CFG" ]; then
    echo "ERROR: OpenOCD config not found at $CFG"
    exit 1
fi

case "${1:-probe}" in
    probe)
        echo "========================================"
        echo "  STM32 SWD Probe — Testing Connection"
        echo "========================================"
        echo ""
        echo "Connecting via SWD (GPIO24=SWDIO, GPIO25=SWCLK)..."
        echo ""
        sudo openocd -f "$CFG" \
            -c "init" \
            -c "echo \">>> SWD CONNECTED <<<\"" \
            -c "targets" \
            -c "echo \">>> Reading device ID...\"" \
            -c "stm32f1x device_id" \
            -c "echo \">>> Flash size:\"" \
            -c "flash info 0" \
            -c "echo \">>> CPU halted for register read:\"" \
            -c "halt" \
            -c "reg pc" \
            -c "reg sp" \
            -c "resume" \
            -c "shutdown"
        echo ""
        echo "========================================"
        echo "  PROBE COMPLETE"
        echo "========================================"
        ;;

    dump)
        echo "========================================"
        echo "  STM32 Flash Dump — First 4KB"
        echo "========================================"
        sudo openocd -f "$CFG" \
            -c "init" \
            -c "halt" \
            -c "flash read_image $DUMP_FILE 0x08000000 0x1000" \
            -c "resume" \
            -c "shutdown"
        echo ""
        echo "Dump saved to $DUMP_FILE"
        echo "First 64 bytes (hex):"
        xxd -l 64 "$DUMP_FILE"
        ;;

    flash)
        FW_FILE="${2:-}"
        if [ -z "$FW_FILE" ]; then
            echo "Usage: $0 flash <firmware.hex|firmware.bin>"
            exit 1
        fi
        if [ ! -f "$FW_FILE" ]; then
            echo "ERROR: Firmware file not found: $FW_FILE"
            exit 1
        fi
        echo "========================================"
        echo "  STM32 Flash — Programming"
        echo "========================================"
        echo "  Firmware: $FW_FILE"
        echo ""
        read -p "  This will erase and reprogram the STM32. Continue? [y/N] " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            echo "  Aborted."
            exit 0
        fi
        sudo openocd -f "$CFG" \
            -c "init" \
            -c "halt" \
            -c "flash write_image erase $FW_FILE 0x08000000" \
            -c "verify_image $FW_FILE 0x08000000" \
            -c "reset run" \
            -c "shutdown"
        echo ""
        echo "  *** FLASH COMPLETE — STM32 is running new firmware ***"
        ;;

    erase)
        echo "========================================"
        echo "  STM32 Flash Erase"
        echo "========================================"
        read -p "  This will ERASE ALL flash. Continue? [y/N] " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            echo "  Aborted."
            exit 0
        fi
        sudo openocd -f "$CFG" \
            -c "init" \
            -c "halt" \
            -c "stm32f1x mass_erase 0" \
            -c "shutdown"
        echo ""
        echo "  *** FLASH ERASED ***"
        ;;

    *)
        echo "Usage: $0 {probe|dump|flash <file>|erase}"
        exit 1
        ;;
esac
