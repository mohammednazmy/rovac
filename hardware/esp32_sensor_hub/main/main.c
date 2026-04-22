/*
 * main.c — ROVAC Sensor Hub ESP32 Firmware
 *
 * 4x HC-SR04 ultrasonic obstacle sensors + 2x Sharp IR cliff sensors.
 * Communicates with Raspberry Pi 5 via USB serial (COBS binary).
 *
 * v1.0.1: Added boot diagnostic sequence to isolate ADC/GPIO issues.
 *         Diagnostic results sent via both printf (115200 boot console)
 *         AND ESP_LOG (MSG_LOG frames after COBS init) so we can capture
 *         results regardless of serial capture method.
 *
 * Part of the ROVAC Robotics Project
 */
#include <stdio.h>
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"

#include "ultrasonic.h"
#include "cliff_sensor.h"
#include "sensor_serial.h"

static const char *TAG = "diag";

static const char *us_names[] = {"Front", "Rear", "Left", "Right"};
static const char *cliff_names[] = {"Front", "Rear"};

static const gpio_num_t echo_gpios[] = {
    GPIO_NUM_34, GPIO_NUM_35, GPIO_NUM_36, GPIO_NUM_39
};
/* trig_gpios: GPIO16=Front, GPIO17=Rear, GPIO18=Left, GPIO19=Right
 * (used only for reference; ultrasonic.c owns the actual TRIG logic) */

/* Store diagnostic results for post-COBS reporting */
static int echo_levels_pre_adc[4];
static int echo_levels_post_adc[4];
static ultrasonic_readings_t us_before_adc;
static ultrasonic_readings_t us_after_adc;
static cliff_readings_t cliff_result;

static void run_diagnostics(void)
{
    /* ── Phase 1: GPIO levels before ADC ──── */
    for (int i = 0; i < 4; i++) {
        echo_levels_pre_adc[i] = gpio_get_level(echo_gpios[i]);
    }

    printf("ECHO levels (pre-ADC): 34=%d 35=%d 36=%d 39=%d\n",
           echo_levels_pre_adc[0], echo_levels_pre_adc[1],
           echo_levels_pre_adc[2], echo_levels_pre_adc[3]);

    /* ── Phase 2: Ultrasonic test BEFORE ADC init ──── */
    printf("Testing ultrasonics BEFORE ADC init...\n");
    ultrasonic_read_all(&us_before_adc);
    for (int i = 0; i < 4; i++) {
        if (us_before_adc.distance_m[i] > 0)
            printf("  pre-ADC US %s: %.1f cm [OK]\n", us_names[i], us_before_adc.distance_m[i] * 100.0f);
        else
            printf("  pre-ADC US %s: TIMEOUT\n", us_names[i]);
    }

    /* ── Phase 3: Init ADC1 ──── */
    printf("Initializing ADC1 for cliff sensors...\n");
    ESP_ERROR_CHECK(cliff_sensor_init());

    /* ── Phase 4: GPIO levels after ADC ──── */
    for (int i = 0; i < 4; i++) {
        echo_levels_post_adc[i] = gpio_get_level(echo_gpios[i]);
    }
    printf("ECHO levels (post-ADC): 34=%d 35=%d 36=%d 39=%d\n",
           echo_levels_post_adc[0], echo_levels_post_adc[1],
           echo_levels_post_adc[2], echo_levels_post_adc[3]);

    /* ── Phase 5: Ultrasonic test AFTER ADC init ──── */
    printf("Testing ultrasonics AFTER ADC init...\n");
    ultrasonic_read_all(&us_after_adc);
    for (int i = 0; i < 4; i++) {
        if (us_after_adc.distance_m[i] > 0)
            printf("  post-ADC US %s: %.1f cm [OK]\n", us_names[i], us_after_adc.distance_m[i] * 100.0f);
        else
            printf("  post-ADC US %s: TIMEOUT\n", us_names[i]);
    }

    /* ── Phase 6: Cliff sensor test ──── */
    cliff_sensor_read_all(&cliff_result);
    for (int i = 0; i < CLIFF_COUNT; i++) {
        printf("  Cliff %s: %.1f cm (%d mV)\n", cliff_names[i],
               cliff_result.distance_m[i] * 100.0f, cliff_result.voltage_mv[i]);
    }

    /* ── Phase 7: Impact analysis ──── */
    printf("\n--- ADC Impact ---\n");
    for (int i = 0; i < 4; i++) {
        bool b = (us_before_adc.ok_mask & (1 << i)) != 0;
        bool a = (us_after_adc.ok_mask & (1 << i)) != 0;
        printf("  US %s: before=%s after=%s %s\n", us_names[i],
               b ? "OK" : "FAIL", a ? "OK" : "FAIL",
               (b && !a) ? "*** BROKEN BY ADC ***" : "");
    }
    printf("--- End Boot Diag ---\n");
    fflush(stdout);
}

/* Send diagnostic results as LOG messages after COBS is active */
static void send_diag_over_cobs(void)
{
    vTaskDelay(pdMS_TO_TICKS(500));  /* Let serial transport stabilize */

    ESP_LOGW(TAG, "=== BOOT DIAGNOSTIC RESULTS ===");

    ESP_LOGW(TAG, "ECHO pre-ADC: GPIO34=%d GPIO35=%d GPIO36=%d GPIO39=%d",
             echo_levels_pre_adc[0], echo_levels_pre_adc[1],
             echo_levels_pre_adc[2], echo_levels_pre_adc[3]);

    ESP_LOGW(TAG, "ECHO post-ADC: GPIO34=%d GPIO35=%d GPIO36=%d GPIO39=%d",
             echo_levels_post_adc[0], echo_levels_post_adc[1],
             echo_levels_post_adc[2], echo_levels_post_adc[3]);

    for (int i = 0; i < 4; i++) {
        bool b = (us_before_adc.ok_mask & (1 << i)) != 0;
        bool a = (us_after_adc.ok_mask & (1 << i)) != 0;
        if (b && !a) {
            ESP_LOGE(TAG, "US %s: BROKEN BY ADC INIT (worked before, fails after)", us_names[i]);
        } else if (!b && !a) {
            ESP_LOGE(TAG, "US %s: FAIL both before and after ADC", us_names[i]);
        } else if (b && a) {
            ESP_LOGI(TAG, "US %s: OK (%.1fcm pre, %.1fcm post)", us_names[i],
                     us_before_adc.distance_m[i] * 100.0f,
                     us_after_adc.distance_m[i] * 100.0f);
        } else {
            ESP_LOGW(TAG, "US %s: before=FAIL after=OK (%.1fcm) — intermittent?", us_names[i],
                     us_after_adc.distance_m[i] * 100.0f);
        }
    }

    for (int i = 0; i < CLIFF_COUNT; i++) {
        ESP_LOGI(TAG, "Cliff %s: %.1f cm (%d mV) %s", cliff_names[i],
                 cliff_result.distance_m[i] * 100.0f, cliff_result.voltage_mv[i],
                 cliff_result.voltage_mv[i] < 400 ? "[CLIFF!]" : "[OK]");
    }

    ESP_LOGW(TAG, "=== END DIAGNOSTIC ===");
}

void app_main(void)
{
    printf("\n");
    printf("================================================\n");
    printf("  ROVAC Sensor Hub ESP32 v1.0.1 (diagnostic)\n");
    printf("  4x HC-SR04 + 2x Sharp IR Cliff\n");
    printf("================================================\n\n");

    /* Step 1: Init ultrasonic GPIO only (no ADC yet) */
    ESP_ERROR_CHECK(ultrasonic_init());

    /* Step 2: Run diagnostic sequence (tests before/after ADC init) */
    run_diagnostics();

    /* Step 3: Brief delay so console output can be read if captured */
    vTaskDelay(pdMS_TO_TICKS(1000));

    /* Step 4: Start serial transport (COBS binary) */
    ESP_ERROR_CHECK(sensor_serial_init());

    /* Step 5: Re-send diagnostic results as MSG_LOG frames over COBS */
    send_diag_over_cobs();

    ESP_LOGI(TAG, "Sensor Hub startup complete. Heap free: %lu bytes",
             (unsigned long)esp_get_free_heap_size());
}
