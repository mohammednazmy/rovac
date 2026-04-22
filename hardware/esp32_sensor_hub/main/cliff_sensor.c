/*
 * cliff_sensor.c — Sharp GP2Y0A51SK0F IR cliff sensor driver
 *
 * Reads 2 analog IR distance sensors via ESP32 ADC1.
 * Detects cliffs/edges when the floor drops away (voltage < threshold).
 *
 * Pin assignments:
 *   Front cliff: GPIO32 (ADC1_CH4)
 *   Rear cliff:  GPIO33 (ADC1_CH5)
 *
 * Sensor characteristics:
 *   Range: 2-15cm, output: ~2400mV at 2cm, ~300mV at 15cm
 *   Floor at 3-5cm: ~1000-1500mV (normal)
 *   Cliff (>15cm):  <400mV (cliff detected)
 */
#include "cliff_sensor.h"

#include <string.h>
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_log.h"

static const char *TAG = "cliff";

/* ADC channels: GPIO32 = ADC1_CH4, GPIO33 = ADC1_CH5 */
static const adc_channel_t adc_channels[CLIFF_COUNT] = {
    [CLIFF_FRONT] = ADC_CHANNEL_4,  /* GPIO32 */
    [CLIFF_REAR]  = ADC_CHANNEL_5,  /* GPIO33 */
};

/* Cliff detection threshold in millivolts.
 * Below this = no floor detected = cliff.
 * 400mV corresponds to ~15cm (edge of sensor range). */
#define CLIFF_THRESHOLD_MV  400

/* Number of ADC samples to average (reduces ESP32 ADC noise) */
#define ADC_SAMPLES  16

/* ADC handles */
static adc_oneshot_unit_handle_t s_adc_handle = NULL;
static adc_cali_handle_t s_cali_handle = NULL;

/**
 * Convert voltage (mV) to approximate distance (m).
 * Based on Sharp GP2Y0A51SK0F characteristic curve.
 * Returns -1.0 if voltage is out of useful range.
 */
static float voltage_to_distance_m(int voltage_mv)
{
    if (voltage_mv < 250) {
        return -1.0f;  /* Below sensor floor — nothing in range */
    }
    if (voltage_mv > 2500) {
        return 0.01f;  /* Saturated — object extremely close (<2cm) */
    }

    /* Approximate inverse relationship from datasheet curve.
     * distance_cm ≈ 12.0 / ((voltage_mV / 1000.0) + 0.05) - 0.42
     * This is a rough fit; exact calibration per sensor is ideal. */
    float v = (float)voltage_mv / 1000.0f;
    float dist_cm = 12.0f / (v + 0.05f) - 0.42f;

    if (dist_cm < 1.0f) dist_cm = 1.0f;
    if (dist_cm > 20.0f) return -1.0f;  /* Beyond reliable range */

    return dist_cm / 100.0f;  /* Convert cm to meters */
}

esp_err_t cliff_sensor_init(void)
{
    /* Initialize ADC1 unit */
    adc_oneshot_unit_init_cfg_t unit_cfg = {
        .unit_id = ADC_UNIT_1,
    };
    ESP_ERROR_CHECK(adc_oneshot_new_unit(&unit_cfg, &s_adc_handle));

    /* Configure both channels: 12dB attenuation for 0-2600mV range */
    adc_oneshot_chan_cfg_t chan_cfg = {
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_12,
    };
    for (int i = 0; i < CLIFF_COUNT; i++) {
        ESP_ERROR_CHECK(adc_oneshot_config_channel(s_adc_handle, adc_channels[i], &chan_cfg));
    }

    /* Set up calibration for voltage conversion */
    adc_cali_line_fitting_config_t cali_cfg = {
        .unit_id = ADC_UNIT_1,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_12,
    };
    esp_err_t cali_ret = adc_cali_create_scheme_line_fitting(&cali_cfg, &s_cali_handle);
    if (cali_ret != ESP_OK) {
        ESP_LOGW(TAG, "ADC calibration not available (rc=%s), using raw values", esp_err_to_name(cali_ret));
        s_cali_handle = NULL;
    }

    ESP_LOGI(TAG, "Initialized 2x Sharp IR cliff: Front=GPIO32(CH4) Rear=GPIO33(CH5)");
    return ESP_OK;
}

void cliff_sensor_read_all(cliff_readings_t *out)
{
    memset(out, 0, sizeof(*out));
    out->cliff_detected = false;
    out->ok_mask = 0;

    for (int i = 0; i < CLIFF_COUNT; i++) {
        /* Take multiple samples and average to reduce noise */
        int32_t sum = 0;
        int valid_samples = 0;

        for (int s = 0; s < ADC_SAMPLES; s++) {
            int raw;
            if (adc_oneshot_read(s_adc_handle, adc_channels[i], &raw) == ESP_OK) {
                sum += raw;
                valid_samples++;
            }
        }

        if (valid_samples == 0) {
            out->distance_m[i] = -1.0f;
            out->voltage_mv[i] = 0;
            continue;
        }

        int avg_raw = sum / valid_samples;

        /* Convert to millivolts */
        int voltage_mv;
        if (s_cali_handle != NULL) {
            adc_cali_raw_to_voltage(s_cali_handle, avg_raw, &voltage_mv);
        } else {
            /* Rough conversion without calibration: 12-bit ADC, 0-2600mV at 12dB atten */
            voltage_mv = (avg_raw * 2600) / 4095;
        }

        out->voltage_mv[i] = voltage_mv;
        out->distance_m[i] = voltage_to_distance_m(voltage_mv);
        out->ok_mask |= (1 << i);

        /* Cliff detection: voltage below threshold means no floor */
        if (voltage_mv < CLIFF_THRESHOLD_MV) {
            out->cliff_detected = true;
        }
    }
}
