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
 *   9. Init I2C bus (new master driver, shared by OLED + BNO055)
 *  10. Init OLED status display
 *  11. Init BNO055 IMU
 *  12. Init micro-ROS (publishes /odom, /tf, /imu/data, /diagnostics)
 *
 * Part of the ROVAC Robotics Project
 */
#include <stdio.h>
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2c_master.h"

#include "nvs_config.h"
#include "wifi.h"
#include "led_status.h"
#include "debug_console.h"
#include "motor_driver.h"
#include "encoder_reader.h"
#include "odometry.h"
#include "motor_control.h"
#include "uros.h"
#include "oled_status.h"
#include "oled_ssd1306.h"
#include "bno055.h"

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

/* Initialize shared I2C bus using new master driver (GPIO21=SDA, GPIO22=SCL) */
static i2c_master_bus_handle_t i2c_bus_init(void)
{
    i2c_master_bus_config_t bus_cfg = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .i2c_port = I2C_NUM_0,
        .scl_io_num = OLED_SCL_PIN,    /* GPIO22 */
        .sda_io_num = OLED_SDA_PIN,    /* GPIO21 */
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };

    i2c_master_bus_handle_t bus = NULL;
    esp_err_t rc = i2c_new_master_bus(&bus_cfg, &bus);
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create I2C bus: %s", esp_err_to_name(rc));
        return NULL;
    }

    ESP_LOGI(TAG, "I2C bus initialized: SDA=GPIO%d SCL=GPIO%d (new master driver, OLED+BNO055)",
             OLED_SDA_PIN, OLED_SCL_PIN);
    return bus;
}

void app_main(void)
{
    printf("\n");
    printf("========================================\n");
    printf("  ROVAC Motor Wireless ESP32 v2.0.0\n");
    printf("  TB67H450FNG + PID + BNO055 + uROS\n");
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

    // Step 8: Initialize shared I2C bus (new master driver, before OLED and BNO055)
    ESP_LOGI(TAG, "Initializing I2C bus...");
    i2c_master_bus_handle_t i2c_bus = i2c_bus_init();
    if (i2c_bus == NULL) {
        ESP_LOGE(TAG, "I2C bus init failed — OLED and IMU disabled");
    }

    // Step 9: OLED status display (non-fatal if not connected)
    if (i2c_bus != NULL) {
        ESP_LOGI(TAG, "Initializing OLED display...");
        ESP_ERROR_CHECK(oled_status_init(i2c_bus));
    }

    // Step 10: BNO055 IMU (non-fatal if not connected)
    if (i2c_bus != NULL) {
        ESP_LOGI(TAG, "Initializing BNO055 IMU...");
        esp_err_t bno_rc = bno055_init(i2c_bus);
        if (bno_rc != ESP_OK) {
            ESP_LOGW(TAG, "BNO055 not detected — IMU disabled (rc=%s)", esp_err_to_name(bno_rc));
        }
    }

    // Step 11: micro-ROS node (publishes /odom, /tf, /imu/data, /diagnostics; subscribes /cmd_vel)
    ESP_LOGI(TAG, "Starting micro-ROS...");
    ESP_ERROR_CHECK(uros_init(&g_config));

    ESP_LOGI(TAG, "Motor Wireless startup complete. Heap free: %lu bytes",
             (unsigned long)esp_get_free_heap_size());
}
