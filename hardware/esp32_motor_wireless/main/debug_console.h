/*
 * debug_console.h — UART0 debug console
 *
 * FreeRTOS task that reads lines from UART0 (CH340 USB-serial) and processes
 * '!' prefixed commands for runtime configuration and diagnostics.
 */
#pragma once

#include "esp_err.h"
#include "nvs_config.h"

/**
 * Start the debug console task.
 * Reads from UART0 (CH340), processes ! commands.
 */
esp_err_t debug_console_init(motor_wireless_config_t *cfg);
