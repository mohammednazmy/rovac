/*
 * main.c — ROVAC Motor Serial ESP32 Firmware
 *
 * Direct motor/encoder/PID controller running on Maker ESP32 (WROOM-32E).
 * Drives TB67H450FNG motor drivers, reads PCNT encoders, runs PID control
 * locally, and communicates with Raspberry Pi 5 via USB serial (COBS binary).
 *
 * Boot sequence:
 *   1. Print banner
 *   2. Init NVS
 *   3. Init LED status indicator
 *   4. Init motor hardware (motor_driver, encoder_reader)
 *   5. Init odometry
 *   6. Init motor control (starts PID task on Core 1)
 *   7. Init I2C bus (new master driver, shared by OLED + BNO055)
 *   8. Init OLED status display
 *   9. Init BNO055 IMU
 *  10. Init serial transport (COBS binary on UART0 @ 460800 baud)
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
#include "led_status.h"
#include "motor_driver.h"
#include "encoder_reader.h"
#include "odometry.h"
#include "motor_params.h"
#include "motor_control.h"
#include "serial_transport.h"
#include "oled_status.h"
#include "oled_ssd1306.h"
#include "bno055.h"

static const char *TAG = "main";

// Global config — loaded from NVS at boot
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
    printf("  ROVAC Motor Serial ESP32 v3.0.0\n");
    printf("  TB67H450FNG + PID + BNO055 + USB\n");
    printf("========================================\n");

    // Step 1: NVS + config
    ESP_LOGI(TAG, "Loading configuration from NVS...");
    ESP_ERROR_CHECK(nvs_config_init(&g_config));

    // Step 1b: Motor tunable params (NVS-backed, overlays firmware defaults)
    // Must come before motor_control_init — PID gets seeded from these.
    ESP_LOGI(TAG, "Loading motor tunable params...");
    ESP_ERROR_CHECK(motor_params_init());

    // Step 2: LED status indicator
    ESP_LOGI(TAG, "Initializing LED...");
    ESP_ERROR_CHECK(led_status_init());
    led_status_set(LED_STATE_NO_AGENT);  /* Yellow = waiting for Pi driver */
    led_status_update();

    // Start LED update task on Core 0
    xTaskCreatePinnedToCore(led_update_task, "led", 2048, NULL, 1, NULL, 0);

    // Step 3: Initialize motor hardware
    ESP_LOGI(TAG, "Initializing motor driver...");
    ESP_ERROR_CHECK(motor_driver_init());

    ESP_LOGI(TAG, "Initializing encoders...");
    ESP_ERROR_CHECK(encoder_reader_init());

    // Step 4: Initialize odometry engine
    ESP_LOGI(TAG, "Initializing odometry...");
    odometry_init();

    // Step 5: Initialize motor control (starts PID task on Core 1)
    ESP_LOGI(TAG, "Starting motor control (PID on Core 1)...");
    ESP_ERROR_CHECK(motor_control_init());

    // Step 6: Initialize shared I2C bus (new master driver, before OLED and BNO055)
    ESP_LOGI(TAG, "Initializing I2C bus...");
    i2c_master_bus_handle_t i2c_bus = i2c_bus_init();
    if (i2c_bus == NULL) {
        ESP_LOGE(TAG, "I2C bus init failed — OLED and IMU disabled");
    }

    // Step 7: OLED status display (non-fatal if not connected)
    if (i2c_bus != NULL) {
        ESP_LOGI(TAG, "Initializing OLED display...");
        ESP_ERROR_CHECK(oled_status_init(i2c_bus));
    }

    // Step 8: BNO055 IMU (non-fatal if not connected)
    if (i2c_bus != NULL) {
        ESP_LOGI(TAG, "Initializing BNO055 IMU...");
        esp_err_t bno_rc = bno055_init(i2c_bus);
        if (bno_rc != ESP_OK) {
            ESP_LOGW(TAG, "BNO055 not detected — IMU disabled (rc=%s)", esp_err_to_name(bno_rc));
        }
    }

    // Step 9: Serial transport (COBS binary on UART0 @ 460800 baud)
    // NOTE: This takes over UART0 from the console. All ESP_LOG output
    // after this point is routed through MSG_LOG binary frames.
    ESP_LOGI(TAG, "Starting serial transport (USB COBS binary)...");
    ESP_ERROR_CHECK(serial_transport_init());

    ESP_LOGI(TAG, "Motor Serial startup complete. Heap free: %lu bytes",
             (unsigned long)esp_get_free_heap_size());
}
