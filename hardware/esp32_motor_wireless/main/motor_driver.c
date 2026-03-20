/*
 * motor_driver.c — TB67H450FNG motor driver (ESP-IDF LEDC)
 *
 * Ported from maker_esp32_firmware.ino setMotorChannel() / setMotors().
 * Uses ESP-IDF LEDC peripheral for 4-channel PWM on the TB67H450FNG
 * 2-pin motor driver inputs.
 *
 * LEDC channel assignment:
 *   Channel 0: MOTOR_LEFT_IN1  (GPIO4)  — left forward
 *   Channel 1: MOTOR_LEFT_IN2  (GPIO2)  — left reverse
 *   Channel 2: MOTOR_RIGHT_IN1 (GPIO13) — right forward
 *   Channel 3: MOTOR_RIGHT_IN2 (GPIO27) — right reverse
 *
 * All 4 channels share LEDC timer 0 at 5kHz, 8-bit resolution.
 */
#include "motor_driver.h"

#include <stdlib.h>
#include "driver/ledc.h"
#include "esp_log.h"

static const char *TAG = "motor_drv";

// LEDC channel assignments
#define LEDC_LEFT_IN1_CH   LEDC_CHANNEL_0
#define LEDC_LEFT_IN2_CH   LEDC_CHANNEL_1
#define LEDC_RIGHT_IN1_CH  LEDC_CHANNEL_2
#define LEDC_RIGHT_IN2_CH  LEDC_CHANNEL_3

// Current commanded speeds (logical, before negation)
static int16_t s_left_speed = 0;
static int16_t s_right_speed = 0;

// ---- Helpers ----

static inline int16_t clamp_i16(int16_t val, int16_t lo, int16_t hi)
{
    if (val < lo) return lo;
    if (val > hi) return hi;
    return val;
}

/**
 * Set a single motor channel (TB67H450FNG 2-pin control).
 *   speed: -255 to 255
 *   fwd_ch / rev_ch: LEDC channels for forward / reverse pins
 */
static void set_motor_channel(ledc_channel_t fwd_ch, ledc_channel_t rev_ch,
                              int16_t speed)
{
    if (speed == 0) {
        // Coast: both pins LOW
        ledc_set_duty(LEDC_LOW_SPEED_MODE, fwd_ch, 0);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, fwd_ch);
        ledc_set_duty(LEDC_LOW_SPEED_MODE, rev_ch, 0);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, rev_ch);
        return;
    }

    uint32_t duty = (uint32_t)abs(speed);

    if (speed > 0) {
        // Forward: fwd=duty, rev=0
        ledc_set_duty(LEDC_LOW_SPEED_MODE, rev_ch, 0);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, rev_ch);
        ledc_set_duty(LEDC_LOW_SPEED_MODE, fwd_ch, duty);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, fwd_ch);
    } else {
        // Reverse: fwd=0, rev=duty
        ledc_set_duty(LEDC_LOW_SPEED_MODE, fwd_ch, 0);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, fwd_ch);
        ledc_set_duty(LEDC_LOW_SPEED_MODE, rev_ch, duty);
        ledc_update_duty(LEDC_LOW_SPEED_MODE, rev_ch);
    }
}

// ---- Public API ----

esp_err_t motor_driver_init(void)
{
    // Configure LEDC timer 0 (shared by all 4 motor channels)
    ledc_timer_config_t timer_cfg = {
        .speed_mode      = LEDC_LOW_SPEED_MODE,
        .duty_resolution = MOTOR_PWM_RESOLUTION,
        .timer_num       = LEDC_TIMER_0,
        .freq_hz         = MOTOR_PWM_FREQ_HZ,
        .clk_cfg         = LEDC_AUTO_CLK,
    };
    esp_err_t err = ledc_timer_config(&timer_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "LEDC timer config failed: %s", esp_err_to_name(err));
        return err;
    }

    // Configure 4 LEDC channels — one per motor pin
    const struct {
        int gpio;
        ledc_channel_t channel;
    } channels[] = {
        { MOTOR_LEFT_IN1,  LEDC_LEFT_IN1_CH  },
        { MOTOR_LEFT_IN2,  LEDC_LEFT_IN2_CH  },
        { MOTOR_RIGHT_IN1, LEDC_RIGHT_IN1_CH },
        { MOTOR_RIGHT_IN2, LEDC_RIGHT_IN2_CH },
    };

    for (int i = 0; i < 4; i++) {
        ledc_channel_config_t ch_cfg = {
            .gpio_num   = channels[i].gpio,
            .speed_mode = LEDC_LOW_SPEED_MODE,
            .channel    = channels[i].channel,
            .intr_type  = LEDC_INTR_DISABLE,
            .timer_sel  = LEDC_TIMER_0,
            .duty       = 0,   // Start in coast state (LOW)
            .hpoint     = 0,
        };
        err = ledc_channel_config(&ch_cfg);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "LEDC channel %d config failed: %s",
                     i, esp_err_to_name(err));
            return err;
        }
    }

    s_left_speed = 0;
    s_right_speed = 0;

    ESP_LOGI(TAG, "Motor driver initialized: L(GPIO%d/%d) R(GPIO%d/%d) @ %dHz %d-bit",
             MOTOR_LEFT_IN1, MOTOR_LEFT_IN2,
             MOTOR_RIGHT_IN1, MOTOR_RIGHT_IN2,
             MOTOR_PWM_FREQ_HZ, MOTOR_PWM_RESOLUTION);
    return ESP_OK;
}

void motor_driver_set(int16_t left, int16_t right)
{
    left  = clamp_i16(left,  -255, 255);
    right = clamp_i16(right, -255, 255);

    s_left_speed  = left;
    s_right_speed = right;

    set_motor_channel(LEDC_LEFT_IN1_CH,  LEDC_LEFT_IN2_CH,  left);
    set_motor_channel(LEDC_RIGHT_IN1_CH, LEDC_RIGHT_IN2_CH, right);
}

void motor_driver_stop(void)
{
    s_left_speed = 0;
    s_right_speed = 0;

    // Coast: all 4 channels duty = 0
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_LEFT_IN1_CH, 0);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_LEFT_IN1_CH);
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_LEFT_IN2_CH, 0);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_LEFT_IN2_CH);
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_RIGHT_IN1_CH, 0);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_RIGHT_IN1_CH);
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_RIGHT_IN2_CH, 0);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_RIGHT_IN2_CH);
}

void motor_driver_brake(void)
{
    s_left_speed = 0;
    s_right_speed = 0;

    // Brake: all 4 channels duty = 255 (shorts motor windings)
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_LEFT_IN1_CH, 255);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_LEFT_IN1_CH);
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_LEFT_IN2_CH, 255);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_LEFT_IN2_CH);
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_RIGHT_IN1_CH, 255);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_RIGHT_IN1_CH);
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_RIGHT_IN2_CH, 255);
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_RIGHT_IN2_CH);
}

int16_t motor_driver_get_left(void)
{
    return s_left_speed;
}

int16_t motor_driver_get_right(void)
{
    return s_right_speed;
}
