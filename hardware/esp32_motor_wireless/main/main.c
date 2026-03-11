/*
 * main.c — ROVAC Motor Wireless ESP32 Firmware
 *
 * Direct motor/encoder/PID controller running on Maker ESP32 (WROOM-32E).
 * Drives TB67H450FNG motor drivers, reads PCNT encoders, runs PID control
 * locally, and communicates with Raspberry Pi 5 via WiFi UDP (micro-ROS).
 *
 * Boot sequence:
 *   1. Print banner
 *   2. Init NVS, load config
 *   3. Init LED status indicator
 *   4. Connect WiFi (wait up to 10s)
 *   5. Init motor hardware (motor_driver, encoder_reader)
 *   6. Init odometry
 *   7. Init motor control (starts PID task on Core 1)
 *   8. Init debug console
 *   9. Init micro-ROS (starts uros task on Core 0)
 *  10. Print heap free
 *
 * Part of the ROVAC Robotics Project
 */
#include <stdio.h>
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "nvs_config.h"
#include "wifi.h"
#include "led_status.h"
#include "debug_console.h"
#include "motor_driver.h"
#include "encoder_reader.h"
#include "odometry.h"
#include "motor_control.h"
#include "uros.h"

static const char *TAG = "main";

// Global config — loaded from NVS at boot, modifiable via debug console
static motor_wireless_config_t g_config;

static void led_update_task(void *arg)
{
    while (1) {
        led_status_update();
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

void app_main(void)
{
    printf("\n");
    printf("========================================\n");
    printf("  ROVAC Motor Wireless ESP32 v1.0.0\n");
    printf("  TB67H450FNG + PCNT + PID + micro-ROS\n");
    printf("========================================\n");

    // Step 1: NVS + config
    ESP_LOGI(TAG, "Loading configuration from NVS...");
    ESP_ERROR_CHECK(nvs_config_init(&g_config));

    // Step 2: LED status indicator
    ESP_LOGI(TAG, "Initializing LED...");
    ESP_ERROR_CHECK(led_status_init());
    led_status_set(LED_STATE_NO_WIFI);
    led_status_update();

    // Start LED update task on Core 0
    xTaskCreatePinnedToCore(led_update_task, "led", 2048, NULL, 1, NULL, 0);

    // Step 3: WiFi
    ESP_LOGI(TAG, "Starting WiFi...");
    ESP_ERROR_CHECK(wifi_init(&g_config));

    // Wait for WiFi connection (up to 10s)
    for (int i = 0; i < 100; i++) {
        if (wifi_is_connected()) break;
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    if (wifi_is_connected()) {
        ESP_LOGI(TAG, "WiFi connected (RSSI %d dBm)", wifi_get_rssi());
        led_status_set(LED_STATE_NO_AGENT);
    } else {
        ESP_LOGW(TAG, "WiFi not connected yet, continuing...");
    }

    // Step 4: Initialize motor hardware
    ESP_LOGI(TAG, "Initializing motor driver...");
    ESP_ERROR_CHECK(motor_driver_init());

    ESP_LOGI(TAG, "Initializing encoders...");
    ESP_ERROR_CHECK(encoder_reader_init());

    // Step 5: Initialize odometry engine
    ESP_LOGI(TAG, "Initializing odometry...");
    odometry_init();

    // Step 6: Initialize motor control (starts PID task on Core 1)
    ESP_LOGI(TAG, "Starting motor control (PID on Core 1)...");
    ESP_ERROR_CHECK(motor_control_init());

    // Step 7: Debug console
    ESP_LOGI(TAG, "Starting debug console...");
    ESP_ERROR_CHECK(debug_console_init(&g_config));

    // Step 8: micro-ROS node (publishes /odom, /tf, /diagnostics; subscribes /cmd_vel)
    ESP_LOGI(TAG, "Starting micro-ROS...");
    ESP_ERROR_CHECK(uros_init(&g_config));

    ESP_LOGI(TAG, "Motor Wireless startup complete. Heap free: %lu bytes",
             (unsigned long)esp_get_free_heap_size());
}
