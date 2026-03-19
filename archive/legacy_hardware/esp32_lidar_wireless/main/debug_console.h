/*
 * debug_console.h — Serial debug console for LIDAR firmware
 *
 * Reads !-prefixed commands from stdin (USB CDC console on ESP32-S3).
 * Provides LIDAR status, RPM control, WiFi config, and system commands.
 */
#pragma once

/** Start the debug console task on Core 0. */
void debug_console_init(void);
