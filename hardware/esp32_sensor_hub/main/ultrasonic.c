/*
 * ultrasonic.c — HC-SR04 ultrasonic sensor driver
 *
 * Reads 4 HC-SR04 sensors sequentially to avoid acoustic crosstalk.
 * Each sensor: 10us TRIG pulse → wait for ECHO HIGH → measure duration.
 *
 * Pin assignments (through 1.3k + 2.2k voltage dividers on ECHO):
 *   Front: TRIG=GPIO16, ECHO=GPIO34
 *   Rear:  TRIG=GPIO17, ECHO=GPIO35
 *   Left:  TRIG=GPIO18, ECHO=GPIO36 (VP)
 *   Right: TRIG=GPIO19, ECHO=GPIO39 (VN)
 */
#include "ultrasonic.h"

#include <string.h>
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "rom/ets_sys.h"

static const char *TAG = "ultrasonic";

/* GPIO assignments */
static const gpio_num_t trig_pins[US_COUNT] = {
    [US_FRONT] = GPIO_NUM_16,
    [US_REAR]  = GPIO_NUM_17,
    [US_LEFT]  = GPIO_NUM_18,
    [US_RIGHT] = GPIO_NUM_19,
};

static const gpio_num_t echo_pins[US_COUNT] = {
    [US_FRONT] = GPIO_NUM_34,
    [US_REAR]  = GPIO_NUM_35,
    [US_LEFT]  = GPIO_NUM_36,
    [US_RIGHT] = GPIO_NUM_39,
};

static const char *sensor_names[US_COUNT] = {"Front", "Rear", "Left", "Right"};

/* Timing constants */
#define TRIG_PULSE_US       10      /* 10us trigger pulse */
#define ECHO_TIMEOUT_US     25000   /* 25ms = ~4.3m max range */
#define ECHO_WAIT_US        5000    /* 5ms max wait for echo to start */
#define INTER_SENSOR_US     10000   /* 10ms gap between sensors — allows residual echoes to dissipate */
#define SPEED_OF_SOUND_MPS  343.0f  /* m/s at ~20°C */

/* Debug counters */
static uint32_t s_debug_cycle = 0;
#define DEBUG_LOG_INTERVAL  50      /* Log every 50th cycle (~5 seconds) */

/* Failure mode tracking */
typedef enum {
    ECHO_OK = 0,
    ECHO_ALREADY_HIGH,      /* Pin was HIGH before trigger — stuck/interference */
    ECHO_NEVER_HIGH,        /* Pin never went HIGH after trigger — timeout */
    ECHO_TOO_LONG,          /* Echo lasted > 25ms — nothing in range */
} echo_fail_t;

/**
 * Read a single HC-SR04 sensor with failure mode tracking.
 * Returns distance in meters, or -1.0 on timeout/error.
 * Sets *fail_mode to indicate what happened.
 */
static float read_one(int idx, echo_fail_t *fail_mode)
{
    gpio_num_t trig = trig_pins[idx];
    gpio_num_t echo = echo_pins[idx];

    *fail_mode = ECHO_OK;

    /* Wait for ECHO pin to settle LOW before triggering.
     * The pin may be HIGH from: a previous sensor's residual echo,
     * ADC1 interference on VP/VN pins, or capacitive coupling.
     * Give it up to 5ms to clear — this is critical for reliability. */
    int64_t settle_start = esp_timer_get_time();
    while (gpio_get_level(echo) == 1) {
        if ((esp_timer_get_time() - settle_start) > 5000) {
            *fail_mode = ECHO_ALREADY_HIGH;
            return -1.0f;
        }
    }

    /* Small delay after echo settles to ensure clean state */
    ets_delay_us(10);

    /* Send 10us trigger pulse */
    gpio_set_level(trig, 0);
    ets_delay_us(2);
    gpio_set_level(trig, 1);
    ets_delay_us(TRIG_PULSE_US);
    gpio_set_level(trig, 0);

    /* Wait for ECHO to go HIGH (start of return pulse) */
    int64_t wait_start = esp_timer_get_time();
    while (gpio_get_level(echo) == 0) {
        if ((esp_timer_get_time() - wait_start) > ECHO_WAIT_US) {
            *fail_mode = ECHO_NEVER_HIGH;
            return -1.0f;
        }
    }

    /* Measure how long ECHO stays HIGH */
    int64_t echo_start = esp_timer_get_time();
    while (gpio_get_level(echo) == 1) {
        if ((esp_timer_get_time() - echo_start) > ECHO_TIMEOUT_US) {
            *fail_mode = ECHO_TOO_LONG;
            return -1.0f;
        }
    }
    int64_t echo_end = esp_timer_get_time();

    /* Calculate distance: d = (t * v) / 2 */
    float duration_s = (float)(echo_end - echo_start) / 1000000.0f;
    float distance_m = (duration_s * SPEED_OF_SOUND_MPS) / 2.0f;

    /* Reject readings outside useful range (2cm - 4m) */
    if (distance_m < 0.02f || distance_m > 4.0f) {
        *fail_mode = ECHO_TOO_LONG;
        return -1.0f;
    }

    return distance_m;
}

esp_err_t ultrasonic_init(void)
{
    /* Configure TRIG pins as outputs */
    for (int i = 0; i < US_COUNT; i++) {
        gpio_config_t trig_cfg = {
            .pin_bit_mask = (1ULL << trig_pins[i]),
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        ESP_ERROR_CHECK(gpio_config(&trig_cfg));
        gpio_set_level(trig_pins[i], 0);
    }

    /* Configure ECHO pins as inputs (GPIO34,35,36,39 are input-only) */
    for (int i = 0; i < US_COUNT; i++) {
        gpio_config_t echo_cfg = {
            .pin_bit_mask = (1ULL << echo_pins[i]),
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        ESP_ERROR_CHECK(gpio_config(&echo_cfg));
    }

    /* Log initial ECHO pin levels */
    ESP_LOGI(TAG, "Initialized 4x HC-SR04: TRIG=[16,17,18,19] ECHO=[34,35,36,39]");
    for (int i = 0; i < US_COUNT; i++) {
        ESP_LOGI(TAG, "  %s ECHO GPIO%d initial level: %d",
                 sensor_names[i], echo_pins[i], gpio_get_level(echo_pins[i]));
    }

    return ESP_OK;
}

void ultrasonic_read_all(ultrasonic_readings_t *out)
{
    memset(out, 0, sizeof(*out));
    out->ok_mask = 0;

    /* Re-assert GPIO input mode for ALL echo pins before each cycle.
     * The ADC1 driver (used by cliff sensors on GPIO32/33) can alter
     * the IO_MUX routing for other ADC1 pins (GPIO34/35/36/39),
     * switching them from GPIO mode to ADC mode internally.
     * This explicit reconfiguration restores digital GPIO function. */
    for (int i = 0; i < US_COUNT; i++) {
        gpio_set_direction(echo_pins[i], GPIO_MODE_INPUT);
    }

    echo_fail_t fail_modes[US_COUNT];
    bool do_log = (s_debug_cycle % DEBUG_LOG_INTERVAL == 0);

    for (int i = 0; i < US_COUNT; i++) {
        out->distance_m[i] = read_one(i, &fail_modes[i]);
        if (out->distance_m[i] > 0.0f) {
            out->ok_mask |= (1 << i);
        }
        /* Inter-sensor delay to prevent crosstalk */
        ets_delay_us(INTER_SENSOR_US);
    }

    /* Periodic debug logging for failing sensors */
    if (do_log) {
        for (int i = 0; i < US_COUNT; i++) {
            if (fail_modes[i] != ECHO_OK) {
                const char *reason;
                switch (fail_modes[i]) {
                    case ECHO_ALREADY_HIGH: reason = "ECHO stuck HIGH (ADC interference?)"; break;
                    case ECHO_NEVER_HIGH:   reason = "ECHO never went HIGH (no trigger response)"; break;
                    case ECHO_TOO_LONG:     reason = "echo >25ms (nothing in range)"; break;
                    default:                reason = "unknown"; break;
                }
                int level = gpio_get_level(echo_pins[i]);
                ESP_LOGW(TAG, "%s(GPIO%d/%d) FAIL: %s [pin_now=%d]",
                         sensor_names[i], trig_pins[i], echo_pins[i], reason, level);
            }
        }
    }

    s_debug_cycle++;
}
