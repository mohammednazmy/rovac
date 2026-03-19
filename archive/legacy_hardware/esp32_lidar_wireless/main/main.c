/*
 * main.c — ROVAC LIDAR Wireless ESP32 Firmware
 *
 * XV11 LIDAR reader running on ESP32-S3 WROOM (Lonely Binary, USB-C CDC).
 * Reads XV11 binary UART data, accumulates 360-degree revolutions,
 * and publishes LaserScan messages to the micro-ROS Agent via WiFi UDP.
 *
 * Boot sequence:
 *   1. Print banner
 *   2. Init NVS, load config
 *   3. Init LED status indicator
 *   4. Connect WiFi (wait up to 10s)
 *   5. Init LIDAR motor (start spinning)
 *   6. Init LIDAR reader + start (UART task on Core 1)
 *   7. Init debug console
 *   8. Init micro-ROS (starts uros task on Core 0)
 *   9. Print heap free
 *
 * Part of the ROVAC Robotics Project
 */
#include <stdio.h>
#include "esp_log.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "nvs_config.h"
#include "wifi.h"
#include "led_status.h"
#include "lidar_motor.h"
#include "lidar_reader.h"
#include "debug_console.h"
#include "uros.h"
#include "hal/wdt_hal.h"
#include "driver/gpio.h"

static const char *TAG = "main";

// Global config — loaded from NVS at boot, modifiable via debug console
// Not static: debug_console.c accesses via extern
lidar_wireless_config_t g_config;

static void led_update_task(void *arg)
{
    while (1) {
        led_status_update();
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

void app_main(void)
{
    /* Disable RTC Watchdog Timer immediately — the bootloader WDT
     * (CONFIG_BOOTLOADER_WDT_TIME_MS=9000) is causing reboot loops
     * when boot takes too long (WiFi wait + micro-ROS init). */
    wdt_hal_context_t rtc_wdt_ctx = RWDT_HAL_CONTEXT_DEFAULT();
    wdt_hal_write_protect_disable(&rtc_wdt_ctx);
    wdt_hal_disable(&rtc_wdt_ctx);
    wdt_hal_write_protect_enable(&rtc_wdt_ctx);

    printf("\n");
    printf("========================================\n");
    printf("  ROVAC LIDAR Wireless ESP32 v1.0.0\n");
    printf("  XV11 + micro-ROS LaserScan Publisher\n");
    printf("========================================\n");

    // Step 1: NVS + config (nvs_config_init handles nvs_flash_init internally)
    ESP_LOGI(TAG, "[1/7] Loading configuration from NVS...");
    nvs_config_init(&g_config);
    ESP_LOGI(TAG, "  Heap after NVS: %lu bytes", (unsigned long)esp_get_free_heap_size());

    // Step 2: LED status indicator
    ESP_LOGI(TAG, "[2/7] Initializing LED...");
    led_status_init();
    led_status_set(LED_NO_WIFI);
    led_status_update();

    // Start LED update task on Core 0
    xTaskCreatePinnedToCore(led_update_task, "led", 2048, NULL, 1, NULL, 0);
    ESP_LOGI(TAG, "  Heap after LED: %lu bytes", (unsigned long)esp_get_free_heap_size());

    // Step 3: WiFi
    ESP_LOGI(TAG, "[3/7] Starting WiFi...");
    ESP_ERROR_CHECK(wifi_init(&g_config));
    ESP_LOGI(TAG, "  Heap after WiFi init: %lu bytes", (unsigned long)esp_get_free_heap_size());

    // Wait for WiFi connection (up to 5s — reduced from 10s)
    ESP_LOGI(TAG, "  Waiting for WiFi connection (up to 5s)...");
    for (int i = 0; i < 50; i++) {
        if (wifi_is_connected()) break;
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    if (wifi_is_connected()) {
        ESP_LOGI(TAG, "  WiFi connected (RSSI %d dBm)", wifi_get_rssi());
        led_status_set(LED_NO_AGENT);
    } else {
        ESP_LOGW(TAG, "  WiFi not connected yet, continuing...");
    }
    ESP_LOGI(TAG, "  Heap after WiFi wait: %lu bytes", (unsigned long)esp_get_free_heap_size());

    // GPIO probe: check both GPIO16 and GPIO17 for LIDAR signal
    {
        for (int pin = 16; pin <= 17; pin++) {
            gpio_config_t io_conf = {
                .pin_bit_mask = (1ULL << pin),
                .mode = GPIO_MODE_INPUT,
                .pull_up_en = GPIO_PULLUP_ENABLE,
                .pull_down_en = GPIO_PULLDOWN_DISABLE,
                .intr_type = GPIO_INTR_DISABLE,
            };
            gpio_config(&io_conf);
        }
        vTaskDelay(pdMS_TO_TICKS(100));  // let signals settle

        // Sample each pin rapidly to detect toggling (UART data)
        for (int pin = 16; pin <= 17; pin++) {
            int highs = 0, lows = 0;
            for (int i = 0; i < 1000; i++) {
                if (gpio_get_level(pin)) highs++; else lows++;
            }
            ESP_LOGI(TAG, "GPIO%d probe: highs=%d lows=%d (%s)",
                     pin, highs, lows,
                     (lows > 50) ? "SIGNAL DETECTED" : "idle/floating");
        }
        // Reset pins to default so UART can claim them
        gpio_reset_pin(16);
        gpio_reset_pin(17);
    }

    // Step 4: LIDAR motor init (PWM via IRLZ44N MOSFET on GPIO4)
    ESP_LOGI(TAG, "[4/7] Starting LIDAR motor...");
    lidar_motor_init();
    lidar_motor_set_target_rpm(g_config.target_rpm);
    ESP_LOGI(TAG, "  Heap after motor: %lu bytes", (unsigned long)esp_get_free_heap_size());

    // Step 5: LIDAR reader init + start (UART task on Core 1)
    ESP_LOGI(TAG, "[5/7] Starting LIDAR reader...");
    lidar_reader_init();
    lidar_reader_start();
    ESP_LOGI(TAG, "  Heap after reader: %lu bytes", (unsigned long)esp_get_free_heap_size());

    // Step 6: Debug console
    ESP_LOGI(TAG, "[6/7] Starting debug console...");
    debug_console_init();
    ESP_LOGI(TAG, "  Heap after console: %lu bytes", (unsigned long)esp_get_free_heap_size());

    // Step 7: micro-ROS node (publishes /scan, /diagnostics)
    ESP_LOGI(TAG, "[7/7] Starting micro-ROS...");
    uros_init(g_config.agent_ip, g_config.agent_port);

    ESP_LOGI(TAG, "=== BOOT COMPLETE === Heap free: %lu bytes",
             (unsigned long)esp_get_free_heap_size());
}
