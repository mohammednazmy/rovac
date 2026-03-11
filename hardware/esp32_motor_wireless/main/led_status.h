/*
 * led_status.h — WS2812 NeoPixel LED status indicator
 *
 * Uses 4x WS2812 NeoPixels on GPIO16 via RMT peripheral.
 * (GPIO2 is used by the TB67H450FNG motor driver on this board.)
 *
 * State mapping:
 *   No WiFi    = Red blinking
 *   No agent   = Yellow blinking
 *   Connected  = Green solid
 *   Error      = Red fast blink
 */
#pragma once

#include "esp_err.h"

typedef enum {
    LED_STATE_NO_WIFI,       // Red blinking
    LED_STATE_NO_AGENT,      // Yellow blinking
    LED_STATE_CONNECTED,     // Green solid
    LED_STATE_ERROR,         // Red fast blink
} led_state_t;

/**
 * Initialize the WS2812 LED driver on GPIO16.
 */
esp_err_t led_status_init(void);

/**
 * Set the LED state. Thread-safe.
 */
void led_status_set(led_state_t state);

/**
 * Call periodically (~50ms) to update blink patterns.
 */
void led_status_update(void);
