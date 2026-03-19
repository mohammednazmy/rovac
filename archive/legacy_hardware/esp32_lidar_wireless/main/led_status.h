/*
 * led_status.h — Simple GPIO2 LED status indicator
 *
 * Uses GPIO2 for LED output (safe on both ESP32 and ESP32-S3).
 * Different blink patterns indicate connection state.
 *
 * NO_WIFI:  fast blink (200ms)
 * NO_AGENT: slow blink (500ms)
 * CONNECTED: solid ON
 * ERROR:    very fast blink (100ms)
 */
#pragma once

#define LED_STATUS_PIN  2   /* GPIO2 — safe on ESP32-S3 (not used by PSRAM/flash) */

typedef enum {
    LED_NO_WIFI,
    LED_NO_AGENT,
    LED_CONNECTED,
    LED_ERROR
} led_state_t;

/** Configure GPIO2 as output. */
void led_status_init(void);

/** Set the current LED state (changes blink pattern). */
void led_status_set(led_state_t state);

/**
 * Update LED output based on current state and timing.
 * Call at ~20Hz (every 50ms) from a FreeRTOS task or timer.
 */
void led_status_update(void);
