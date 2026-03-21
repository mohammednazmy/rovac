/*
 * oled_status.c — OLED status display for ROVAC motor controller
 *
 * 2-line display at 2x font scale (128x32 @ 10 chars × 2 lines):
 *   Line 1: W<rssi> A:<status>   — WiFi signal + Agent connection
 *   Line 2: L<vel>  R<vel>       — Motor velocities in m/s
 *
 * Refreshes at 4Hz on Core 0. Non-fatal if OLED is absent.
 */
#include "oled_status.h"
#include "oled_ssd1306.h"
#include "serial_transport.h"
#include "motor_control.h"

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdio.h>

static const char *TAG = "oled_status";
static bool s_oled_ok = false;

static void oled_status_task(void *arg)
{
    (void)arg;

    while (1) {
        oled_clear();

        /* ── Line 1 (y=0): Connectivity ── */
        char line1[12];
        bool usb_ok = serial_transport_is_connected();
        snprintf(line1, sizeof(line1), "USB:%s", usb_ok ? "OK" : "--");
        oled_draw_text(0, 1, line1, 2);

        /* ── Line 2 (y=16): Motor velocities ── */
        char line2[12];
        float vl, vr;
        motor_control_get_velocities(&vl, &vr);
        snprintf(line2, sizeof(line2), "L%.2f R%.2f", vl, vr);
        oled_draw_text(0, 17, line2, 2);

        oled_update();
        vTaskDelay(pdMS_TO_TICKS(250));  /* 4 Hz refresh */
    }
}

esp_err_t oled_status_init(i2c_master_bus_handle_t bus)
{
    esp_err_t rc = oled_init(bus);
    if (rc != ESP_OK) {
        ESP_LOGW(TAG, "OLED not detected — display disabled (not fatal)");
        return ESP_OK;  /* non-fatal */
    }

    s_oled_ok = true;

    /* Show boot message briefly */
    oled_draw_text(16, 1, "ROVAC", 2);
    oled_draw_text(4, 17, "Motor v1.0", 2);
    oled_update();

    BaseType_t ret = xTaskCreatePinnedToCore(
        oled_status_task, "oled", 3072, NULL, 1, NULL, 0);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create OLED task");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "OLED status display started (4Hz, 2-line)");
    return ESP_OK;
}
