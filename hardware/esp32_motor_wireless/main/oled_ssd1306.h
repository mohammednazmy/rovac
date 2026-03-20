/*
 * oled_ssd1306.h — Minimal SSD1306 128x32 I2C OLED driver
 *
 * Framebuffer-based: draw to buffer, then flush with oled_update().
 * Supports scaled text rendering (scale=1: 6px wide, scale=2: 12px wide).
 *
 * Hardware: SSD1306 on Maker-ESP32 OLED header (JP2)
 *   SDA=GPIO21, SCL=GPIO22, Addr=0x3C
 *
 * Uses new ESP-IDF I2C master driver (driver/i2c_master.h) which is
 * thread-safe — no external mutex needed for bus sharing with BNO055.
 */
#pragma once

#include "esp_err.h"
#include "driver/i2c_master.h"
#include <stdint.h>

#define OLED_WIDTH   128
#define OLED_HEIGHT  32
#define OLED_I2C_ADDR 0x3C
#define OLED_SDA_PIN  21
#define OLED_SCL_PIN  22

/**
 * Initialize SSD1306 display on an existing I2C bus.
 * @param bus  I2C master bus handle (created by caller).
 * @return ESP_OK or error.
 */
esp_err_t oled_init(i2c_master_bus_handle_t bus);

/** Clear the framebuffer (call oled_update() to push to screen). */
void oled_clear(void);

/** Draw text at pixel position (x,y) with given scale (1 or 2). */
void oled_draw_text(int x, int y, const char *text, int scale);

/** Flush framebuffer to the display over I2C. */
void oled_update(void);
