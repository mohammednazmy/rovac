/*
 * led_status.c — Simple GPIO2 LED status indicator
 *
 * Uses GPIO2 for LED output (safe on both ESP32 and ESP32-S3).
 * Different blink patterns indicate connection state:
 *   NO_WIFI:   fast blink (200ms on/off)
 *   NO_AGENT:  slow blink (500ms on/off)
 *   CONNECTED: solid ON
 *   ERROR:     very fast blink (100ms on/off)
 *
 * Call led_status_update() at ~20Hz (every 50ms) from a FreeRTOS task or timer.
 */
#include "led_status.h"

#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"

static const char *TAG = "led";

static led_state_t current_state = LED_NO_WIFI;

void led_status_init(void)
{
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << LED_STATUS_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = 0,
        .pull_down_en = 0,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&io_conf);
    gpio_set_level(LED_STATUS_PIN, 0);

    ESP_LOGI(TAG, "GPIO LED initialized on GPIO%d", LED_STATUS_PIN);
}

void led_status_set(led_state_t state)
{
    current_state = state;
}

void led_status_update(void)
{
    uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);  // ms
    bool on;

    switch (current_state) {
        case LED_NO_WIFI:   on = (now / 200) % 2; break;  // fast blink
        case LED_NO_AGENT:  on = (now / 500) % 2; break;  // slow blink
        case LED_CONNECTED: on = true; break;               // solid
        case LED_ERROR:     on = (now / 100) % 2; break;   // very fast
        default:            on = false; break;
    }

    gpio_set_level(LED_STATUS_PIN, on ? 1 : 0);
}
