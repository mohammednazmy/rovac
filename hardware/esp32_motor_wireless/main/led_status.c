/*
 * led_status.c — WS2812 NeoPixel LED status indicator (RMT driver)
 *
 * Drives 4x WS2812 NeoPixels on GPIO16 via ESP-IDF v5.2 RMT TX.
 * GPIO2 is used by the TB67H450FNG motor driver, so LEDs are on GPIO16.
 *
 * State animations (all 4 LEDs identical):
 *   NO_WIFI    — Red blinking (500ms on/off)
 *   NO_AGENT   — Yellow blinking (500ms on/off)
 *   CONNECTED  — Green solid
 *   ERROR      — Red fast blink (150ms on/off)
 *
 * Call led_status_update() at ~50ms intervals for smooth animation.
 */
#include "led_status.h"

#include <string.h>
#include "esp_log.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"
#include "freertos/FreeRTOS.h"
#include "esp_timer.h"

static const char *TAG = "led";

#define WS2812_GPIO       16
#define NUM_LEDS           4
#define RMT_RESOLUTION_HZ 10000000  // 10MHz → 100ns per tick

// LED state
static led_state_t s_state = LED_STATE_NO_WIFI;
static bool s_initialized = false;

// RMT handles
static rmt_channel_handle_t s_rmt_chan = NULL;
static rmt_encoder_handle_t s_encoder = NULL;

// LED pixel buffer (GRB format, 3 bytes per LED)
static uint8_t s_pixels[NUM_LEDS * 3];

// Animation timing
static int64_t s_last_toggle_us = 0;
static bool s_blink_on = true;

// ---- Helpers ----

static void set_all_pixels(uint8_t r, uint8_t g, uint8_t b)
{
    for (int i = 0; i < NUM_LEDS; i++) {
        s_pixels[i * 3 + 0] = g;  // WS2812 is GRB order
        s_pixels[i * 3 + 1] = r;
        s_pixels[i * 3 + 2] = b;
    }
}

static void transmit_pixels(void)
{
    if (!s_initialized) return;

    rmt_transmit_config_t tx_config = {
        .loop_count = 0,
    };
    rmt_transmit(s_rmt_chan, s_encoder, s_pixels, sizeof(s_pixels), &tx_config);
    rmt_tx_wait_all_done(s_rmt_chan, pdMS_TO_TICKS(100));
}

// ---- Public API ----

esp_err_t led_status_init(void)
{
    // Configure RMT TX channel
    rmt_tx_channel_config_t tx_config = {
        .gpio_num = WS2812_GPIO,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = RMT_RESOLUTION_HZ,
        .mem_block_symbols = 64,  // 64 symbols = enough for 4 LEDs (96 bits)
        .trans_queue_depth = 4,
    };
    esp_err_t err = rmt_new_tx_channel(&tx_config, &s_rmt_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "RMT TX channel create failed: %s", esp_err_to_name(err));
        return err;
    }

    // Create bytes encoder with WS2812 timing
    // At 10MHz (100ns/tick):
    //   Bit 0: HIGH 3 ticks (300ns), LOW 9 ticks (900ns)  → total 1200ns
    //   Bit 1: HIGH 7 ticks (700ns), LOW 6 ticks (600ns)  → total 1300ns
    rmt_bytes_encoder_config_t bytes_config = {
        .bit0 = {
            .level0 = 1, .duration0 = 3,   // T0H = 300ns
            .level1 = 0, .duration1 = 9,   // T0L = 900ns
        },
        .bit1 = {
            .level0 = 1, .duration0 = 7,   // T1H = 700ns
            .level1 = 0, .duration1 = 6,   // T1L = 600ns
        },
        .flags.msb_first = 1,  // WS2812 expects MSB first
    };
    err = rmt_new_bytes_encoder(&bytes_config, &s_encoder);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "RMT bytes encoder create failed: %s", esp_err_to_name(err));
        return err;
    }

    // Enable channel
    err = rmt_enable(s_rmt_chan);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "RMT enable failed: %s", esp_err_to_name(err));
        return err;
    }

    s_initialized = true;
    s_last_toggle_us = esp_timer_get_time();

    // Start with all LEDs off
    set_all_pixels(0, 0, 0);
    transmit_pixels();

    ESP_LOGI(TAG, "WS2812 LED driver initialized on GPIO%d (%d LEDs)", WS2812_GPIO, NUM_LEDS);
    return ESP_OK;
}

void led_status_set(led_state_t state)
{
    if (state != s_state) {
        s_state = state;
        s_blink_on = true;  // Reset blink phase on state change
        s_last_toggle_us = esp_timer_get_time();
    }
}

void led_status_update(void)
{
    if (!s_initialized) return;

    int64_t now_us = esp_timer_get_time();

    // Determine blink period based on state
    int64_t blink_period_us;
    switch (s_state) {
    case LED_STATE_NO_WIFI:
        blink_period_us = 500000;  // 500ms
        break;
    case LED_STATE_NO_AGENT:
        blink_period_us = 500000;  // 500ms
        break;
    case LED_STATE_CONNECTED:
        blink_period_us = 0;  // Solid (no blink)
        break;
    case LED_STATE_ERROR:
        blink_period_us = 150000;  // 150ms fast blink
        break;
    default:
        blink_period_us = 500000;
        break;
    }

    // Toggle blink state
    if (blink_period_us > 0 && (now_us - s_last_toggle_us) >= blink_period_us) {
        s_blink_on = !s_blink_on;
        s_last_toggle_us = now_us;
    }

    // Set pixel color based on state and blink phase
    // Brightness scaled to ~25% to avoid blinding in close quarters
    if (s_state == LED_STATE_CONNECTED || s_blink_on) {
        switch (s_state) {
        case LED_STATE_NO_WIFI:
            set_all_pixels(40, 0, 0);      // Red
            break;
        case LED_STATE_NO_AGENT:
            set_all_pixels(40, 25, 0);     // Yellow/amber
            break;
        case LED_STATE_CONNECTED:
            set_all_pixels(0, 40, 0);      // Green
            break;
        case LED_STATE_ERROR:
            set_all_pixels(40, 0, 0);      // Red
            break;
        }
    } else {
        set_all_pixels(0, 0, 0);  // Off (blink off phase)
    }

    transmit_pixels();
}
