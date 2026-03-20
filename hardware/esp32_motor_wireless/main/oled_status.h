/*
 * oled_status.h — OLED status display for ROVAC motor controller
 *
 * Drives the SSD1306 128x32 OLED with a 2-line status display:
 *   Line 1: WiFi RSSI + Agent connection status
 *   Line 2: Left/Right motor velocities
 *
 * Runs a 4Hz refresh task on Core 0.
 * Gracefully degrades if OLED hardware is not connected.
 */
#pragma once

#include "esp_err.h"
#include "driver/i2c_master.h"

/**
 * Initialize OLED hardware and start the status display task.
 * @param bus  I2C master bus handle.
 * Non-fatal: logs a warning and returns ESP_OK if OLED is not connected.
 */
esp_err_t oled_status_init(i2c_master_bus_handle_t bus);
