/*
 * encoder_reader.c — Hardware quadrature encoder reader (ESP-IDF v5.2 PCNT)
 *
 * Uses two PCNT units for full quadrature decoding (4x resolution).
 * Each unit has two channels: channel A counts on A edges with B as level,
 * channel B counts on B edges with A as level — giving 4 counts per
 * encoder cycle (full-quad).
 *
 * At max motor speed (~10 rev/s × 2640 ticks/rev = ~26400 ticks/s),
 * reading at 50Hz gives ~528 ticks per window — well within int16 range,
 * so no overflow handling is needed.
 *
 * Right encoder has A/B swapped in the channel config to match the Arduino
 * firmware: encRight.attachFullQuad(ENC_RIGHT_B, ENC_RIGHT_A) — this makes
 * forward motion produce positive counts on both wheels.
 */
#include "encoder_reader.h"

#include <string.h>
#include "driver/pulse_cnt.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "esp_log.h"

static const char *TAG = "encoder";

// PCNT unit handles
static pcnt_unit_handle_t s_pcnt_left  = NULL;
static pcnt_unit_handle_t s_pcnt_right = NULL;

// Cumulative absolute counts (updated from PCNT hardware counter deltas)
static int32_t s_total_left  = 0;
static int32_t s_total_right = 0;

// Previous PCNT hardware counter values (for delta computation)
static int s_prev_left  = 0;
static int s_prev_right = 0;

// Mutex for thread-safe access
static SemaphoreHandle_t s_lock = NULL;

/**
 * Initialize one PCNT unit for full quadrature decoding.
 *
 * @param enc_a   GPIO for encoder channel A (edge signal for first channel)
 * @param enc_b   GPIO for encoder channel B (level signal for first channel)
 * @param handle  Output: PCNT unit handle
 *
 * For the right encoder, caller swaps A and B to invert counting direction
 * (matching Arduino: attachFullQuad(B, A)).
 */
static esp_err_t init_pcnt_unit(int enc_a, int enc_b, pcnt_unit_handle_t *handle)
{
    esp_err_t err;

    // Enable internal pull-ups on encoder pins (matches Arduino: useInternalWeakPullResistors = up)
    gpio_set_pull_mode((gpio_num_t)enc_a, GPIO_PULLUP_ONLY);
    gpio_set_pull_mode((gpio_num_t)enc_b, GPIO_PULLUP_ONLY);

    // Create PCNT unit
    pcnt_unit_config_t unit_config = {
        .high_limit =  32767,
        .low_limit  = -32767,
    };
    err = pcnt_new_unit(&unit_config, handle);
    if (err != ESP_OK) return err;

    // Glitch filter: reject pulses shorter than 1us (noise suppression)
    pcnt_glitch_filter_config_t filter_config = {
        .max_glitch_ns = 1000,
    };
    err = pcnt_unit_set_glitch_filter(*handle, &filter_config);
    if (err != ESP_OK) return err;

    // Channel A: count on A edges, B determines direction
    pcnt_chan_config_t chan_a_config = {
        .edge_gpio_num  = enc_a,
        .level_gpio_num = enc_b,
    };
    pcnt_channel_handle_t chan_a;
    err = pcnt_new_channel(*handle, &chan_a_config, &chan_a);
    if (err != ESP_OK) return err;

    // Full quadrature channel A: rising A → direction from B
    pcnt_channel_set_edge_action(chan_a,
        PCNT_CHANNEL_EDGE_ACTION_DECREASE,   // Rising edge of A
        PCNT_CHANNEL_EDGE_ACTION_INCREASE);  // Falling edge of A
    pcnt_channel_set_level_action(chan_a,
        PCNT_CHANNEL_LEVEL_ACTION_KEEP,      // B low → keep direction
        PCNT_CHANNEL_LEVEL_ACTION_INVERSE);  // B high → invert direction

    // Channel B: count on B edges, A determines direction (4x resolution)
    pcnt_chan_config_t chan_b_config = {
        .edge_gpio_num  = enc_b,
        .level_gpio_num = enc_a,
    };
    pcnt_channel_handle_t chan_b;
    err = pcnt_new_channel(*handle, &chan_b_config, &chan_b);
    if (err != ESP_OK) return err;

    pcnt_channel_set_edge_action(chan_b,
        PCNT_CHANNEL_EDGE_ACTION_INCREASE,   // Rising edge of B
        PCNT_CHANNEL_EDGE_ACTION_DECREASE);  // Falling edge of B
    pcnt_channel_set_level_action(chan_b,
        PCNT_CHANNEL_LEVEL_ACTION_KEEP,      // A low → keep direction
        PCNT_CHANNEL_LEVEL_ACTION_INVERSE);  // A high → invert direction

    // Enable, clear, and start
    err = pcnt_unit_enable(*handle);
    if (err != ESP_OK) return err;
    err = pcnt_unit_clear_count(*handle);
    if (err != ESP_OK) return err;
    err = pcnt_unit_start(*handle);
    if (err != ESP_OK) return err;

    return ESP_OK;
}

// ---- Public API ----

esp_err_t encoder_reader_init(void)
{
    s_lock = xSemaphoreCreateMutex();
    if (s_lock == NULL) {
        ESP_LOGE(TAG, "Failed to create mutex");
        return ESP_ERR_NO_MEM;
    }

    s_total_left  = 0;
    s_total_right = 0;
    s_prev_left   = 0;
    s_prev_right  = 0;

    // Left encoder: A=GPIO19, B=GPIO23 (forward = positive)
    esp_err_t err = init_pcnt_unit(ENCODER_LEFT_A, ENCODER_LEFT_B, &s_pcnt_left);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Left encoder init failed: %s", esp_err_to_name(err));
        return err;
    }

    // Right encoder: A/B swapped for forward = positive
    // Arduino: encRight.attachFullQuad(ENC_RIGHT_B, ENC_RIGHT_A) = attachFullQuad(18, 5)
    // So: edge pin = GPIO18 (B physical), level pin = GPIO5 (A physical)
    err = init_pcnt_unit(ENCODER_RIGHT_B, ENCODER_RIGHT_A, &s_pcnt_right);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Right encoder init failed: %s", esp_err_to_name(err));
        return err;
    }

    ESP_LOGI(TAG, "Encoders initialized: Left(GPIO%d/%d) Right(GPIO%d/%d) %d ticks/rev",
             ENCODER_LEFT_A, ENCODER_LEFT_B,
             ENCODER_RIGHT_A, ENCODER_RIGHT_B,
             ENCODER_TICKS_PER_REV);
    return ESP_OK;
}

void encoder_reader_get_counts(int32_t *left, int32_t *right)
{
    int hw_left = 0, hw_right = 0;
    pcnt_unit_get_count(s_pcnt_left, &hw_left);
    pcnt_unit_get_count(s_pcnt_right, &hw_right);

    xSemaphoreTake(s_lock, portMAX_DELAY);

    // Compute deltas from hardware counter and accumulate
    int32_t dl = hw_left  - s_prev_left;
    int32_t dr = hw_right - s_prev_right;
    s_prev_left  = hw_left;
    s_prev_right = hw_right;
    s_total_left  += dl;
    s_total_right += dr;

    if (left)  *left  = s_total_left;
    if (right) *right = s_total_right;

    xSemaphoreGive(s_lock);
}

void encoder_reader_get_and_reset_deltas(int32_t *left_delta, int32_t *right_delta)
{
    int hw_left = 0, hw_right = 0;
    pcnt_unit_get_count(s_pcnt_left, &hw_left);
    pcnt_unit_get_count(s_pcnt_right, &hw_right);

    xSemaphoreTake(s_lock, portMAX_DELAY);

    // Compute deltas from hardware counter since last call
    int32_t dl = hw_left  - s_prev_left;
    int32_t dr = hw_right - s_prev_right;
    s_prev_left  = hw_left;
    s_prev_right = hw_right;

    // Accumulate into totals
    s_total_left  += dl;
    s_total_right += dr;

    if (left_delta)  *left_delta  = dl;
    if (right_delta) *right_delta = dr;

    xSemaphoreGive(s_lock);
}

void encoder_reader_reset(void)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);

    // Clear hardware counters
    pcnt_unit_clear_count(s_pcnt_left);
    pcnt_unit_clear_count(s_pcnt_right);

    // Reset all tracking state
    s_total_left  = 0;
    s_total_right = 0;
    s_prev_left   = 0;
    s_prev_right  = 0;

    xSemaphoreGive(s_lock);

    ESP_LOGI(TAG, "Encoder counts reset to zero");
}
