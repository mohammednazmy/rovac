/*
 * lidar_motor.c — XV11 LIDAR motor PWM control with RPM regulation
 *
 * Drives the XV11 motor via IRLZ44N MOSFET on GPIO4 (ESP32-S3).
 * Proportional controller adjusts PWM to maintain target RPM.
 * RPM feedback comes from lidar_reader parsing XV11 packets.
 *
 * Regulation strategy:
 *   - Asymmetric adjustments: increase faster than decrease (prevent stall)
 *   - Track "last good PWM" so stall recovery jumps to known working point
 *   - Higher MIN_PWM (130) to stay above motor stall threshold
 *   - 2-second stall timeout before recovery kicks in
 */

#include "lidar_motor.h"
#include "driver/ledc.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "lidar_motor";

/* LEDC configuration */
#define LEDC_TIMER          LEDC_TIMER_0
#define LEDC_MODE           LEDC_LOW_SPEED_MODE
#define LEDC_CHANNEL        LEDC_CHANNEL_0

/* RPM regulation deadband (no adjustment if within +-DEADBAND of target) */
#define RPM_DEADBAND        15

/* Stall timeout: if no RPM update for this long, motor might be stalled */
#define RPM_STALL_TIMEOUT_MS 2000

/* Full stall: if at max PWM with no RPM for this long, cycle motor */
#define FULL_STALL_TIMEOUT_MS 8000

/* Motor restart: hold off for this long before ramping again */
#define MOTOR_RESTART_HOLD_MS 300

/* "Last good" PWM: the motor was running at this PWM when we last had RPM data */
#define LAST_GOOD_PWM_DEFAULT LIDAR_MOTOR_INITIAL_PWM

/* ── Module state ──────────────────────────────────────────────────────── */

static uint8_t  current_pwm   = LIDAR_MOTOR_INITIAL_PWM;
static uint16_t target_rpm    = LIDAR_MOTOR_DEFAULT_RPM;
static float    current_rpm   = 0.0f;
static bool     auto_mode     = true;
static uint32_t last_rpm_update_ms = 0;
static uint8_t  last_good_pwm = LAST_GOOD_PWM_DEFAULT;
static uint32_t max_pwm_since_ms   = 0;
static bool     restarting_motor   = false;
static uint32_t restart_start_ms   = 0;

/* ── Internal helpers ──────────────────────────────────────────────────── */

static void apply_pwm(void)
{
    ESP_ERROR_CHECK(ledc_set_duty(LEDC_MODE, LEDC_CHANNEL, current_pwm));
    ESP_ERROR_CHECK(ledc_update_duty(LEDC_MODE, LEDC_CHANNEL));
}

static inline int16_t clamp_i16(int16_t val, int16_t min_val, int16_t max_val)
{
    if (val < min_val) return min_val;
    if (val > max_val) return max_val;
    return val;
}

/* ── Public API ────────────────────────────────────────────────────────── */

void lidar_motor_init(void)
{
    ledc_timer_config_t timer_cfg = {
        .speed_mode      = LEDC_MODE,
        .duty_resolution = LIDAR_MOTOR_PWM_RES,
        .timer_num       = LEDC_TIMER,
        .freq_hz         = LIDAR_MOTOR_PWM_FREQ,
        .clk_cfg         = LEDC_AUTO_CLK,
    };
    ESP_ERROR_CHECK(ledc_timer_config(&timer_cfg));

    ledc_channel_config_t chan_cfg = {
        .gpio_num   = LIDAR_MOTOR_PWM_PIN,
        .speed_mode = LEDC_MODE,
        .channel    = LEDC_CHANNEL,
        .timer_sel  = LEDC_TIMER,
        .duty       = LIDAR_MOTOR_INITIAL_PWM,
        .hpoint     = 0,
        .intr_type  = LEDC_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(ledc_channel_config(&chan_cfg));

    current_pwm = LIDAR_MOTOR_INITIAL_PWM;
    target_rpm = LIDAR_MOTOR_DEFAULT_RPM;
    current_rpm = 0.0f;
    auto_mode = true;
    last_rpm_update_ms = 0;
    last_good_pwm = LAST_GOOD_PWM_DEFAULT;
    max_pwm_since_ms = 0;
    restarting_motor = false;

    ESP_LOGI(TAG, "Motor PWM initialized: GPIO%d, %dHz, %d-bit, initial duty=%d",
             LIDAR_MOTOR_PWM_PIN, LIDAR_MOTOR_PWM_FREQ,
             LIDAR_MOTOR_PWM_RES, LIDAR_MOTOR_INITIAL_PWM);
}

void lidar_motor_set_target_rpm(uint16_t rpm)
{
    target_rpm = rpm;
    auto_mode = true;
    ESP_LOGI(TAG, "Target RPM set to %u (auto mode enabled)", rpm);
}

uint16_t lidar_motor_get_target_rpm(void)
{
    return target_rpm;
}

void lidar_motor_set_pwm(uint8_t pwm)
{
    current_pwm = pwm;
    auto_mode = false;
    apply_pwm();
    ESP_LOGI(TAG, "Manual PWM set to %u (auto mode disabled)", pwm);
}

uint8_t lidar_motor_get_pwm(void)
{
    return current_pwm;
}

void lidar_motor_set_auto(bool enable)
{
    auto_mode = enable;
    ESP_LOGI(TAG, "Auto mode %s", enable ? "enabled" : "disabled");
}

bool lidar_motor_is_auto(void)
{
    return auto_mode;
}

void lidar_motor_update_rpm(float rpm)
{
    current_rpm = rpm;
    last_rpm_update_ms = (uint32_t)(esp_timer_get_time() / 1000);

    /* Track last known good PWM when motor is running near target */
    if (rpm > 150.0f && current_pwm >= LIDAR_MOTOR_MIN_PWM) {
        last_good_pwm = current_pwm;
    }
}

void lidar_motor_regulate(void)
{
    if (!auto_mode) {
        return;
    }

    uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000);

    /* Motor restart hold: wait before ramping again */
    if (restarting_motor) {
        if (now_ms - restart_start_ms < MOTOR_RESTART_HOLD_MS) {
            return;
        }
        restarting_motor = false;
        /* Jump to last known good PWM instead of ramping from scratch */
        current_pwm = last_good_pwm;
        apply_pwm();
        max_pwm_since_ms = 0;
        ESP_LOGI(TAG, "Motor restart: jumping to last good PWM %u", current_pwm);
        return;
    }

    /* === Stall detection: no RPM data for > 2 seconds === */
    if (last_rpm_update_ms == 0 ||
        (now_ms - last_rpm_update_ms > RPM_STALL_TIMEOUT_MS)) {

        /* If stuck at max PWM for too long, cycle motor off/on */
        if (current_pwm >= LIDAR_MOTOR_MAX_PWM) {
            if (max_pwm_since_ms == 0) {
                max_pwm_since_ms = now_ms;
            } else if (now_ms - max_pwm_since_ms > FULL_STALL_TIMEOUT_MS) {
                ESP_LOGW(TAG, "Full stall — cycling motor off for %ums",
                         MOTOR_RESTART_HOLD_MS);
                ESP_ERROR_CHECK(ledc_set_duty(LEDC_MODE, LEDC_CHANNEL, 0));
                ESP_ERROR_CHECK(ledc_update_duty(LEDC_MODE, LEDC_CHANNEL));
                restarting_motor = true;
                restart_start_ms = now_ms;
                return;
            }
        }

        /* Ramp PWM up to try to start motor */
        if (current_pwm < LIDAR_MOTOR_MAX_PWM) {
            uint16_t new_val = (uint16_t)current_pwm + 5;
            current_pwm = (new_val > LIDAR_MOTOR_MAX_PWM) ?
                          LIDAR_MOTOR_MAX_PWM : (uint8_t)new_val;
            apply_pwm();
            ESP_LOGW(TAG, "No RPM data — ramping PWM to %u", current_pwm);
        }
        return;
    }

    /* === Getting RPM data — reset stall tracking === */
    max_pwm_since_ms = 0;

    /* === Proportional control with asymmetric adjustments ===
     * Key: reduce PWM GENTLY to prevent stalling, increase faster to recover.
     * Reduce by at most 2 per cycle (at 5Hz = max -10/s).
     * Increase by up to 5 per cycle (at 5Hz = max +25/s).
     */
    int16_t error = (int16_t)target_rpm - (int16_t)current_rpm;

    if (error > RPM_DEADBAND || error < -RPM_DEADBAND) {
        int8_t adjustment = 0;

        if (error > 0) {
            /* RPM too low — increase PWM (faster) */
            if (error > 50)       adjustment = 5;
            else if (error > 20)  adjustment = 3;
            else if (error > 15)  adjustment = 1;
        } else {
            /* RPM too high — decrease PWM (GENTLY to prevent stall) */
            if (error < -80)      adjustment = -2;
            else if (error < -30) adjustment = -1;
            else if (error < -15) adjustment = -1;
        }

        if (adjustment != 0) {
            int16_t new_pwm = (int16_t)current_pwm + adjustment;
            new_pwm = clamp_i16(new_pwm, LIDAR_MOTOR_MIN_PWM, LIDAR_MOTOR_MAX_PWM);

            if ((uint8_t)new_pwm != current_pwm) {
                current_pwm = (uint8_t)new_pwm;
                apply_pwm();
            }
        }
    }
}

void lidar_motor_stop(void)
{
    auto_mode = false;
    current_pwm = 0;
    ESP_ERROR_CHECK(ledc_set_duty(LEDC_MODE, LEDC_CHANNEL, 0));
    ESP_ERROR_CHECK(ledc_update_duty(LEDC_MODE, LEDC_CHANNEL));
    ESP_LOGI(TAG, "Motor stopped (PWM=0, auto disabled)");
}

void lidar_motor_test(void)
{
    /* Test GPIO4 as a plain digital output — bypasses LEDC entirely.
     * If motor spins: MOSFET + wiring confirmed working.
     * If motor doesn't spin: MOSFET is dead or wiring is wrong. */
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << LIDAR_MOTOR_PWM_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&io_conf);

    ESP_LOGW(TAG, "===================================================");
    ESP_LOGW(TAG, "  MOTOR TEST: GPIO%d -> HIGH (3.3V) for 3 seconds", LIDAR_MOTOR_PWM_PIN);
    ESP_LOGW(TAG, "  If motor spins: MOSFET + wiring OK");
    ESP_LOGW(TAG, "  If motor does NOT spin: MOSFET dead or wiring bad");
    ESP_LOGW(TAG, "===================================================");

    gpio_set_level(LIDAR_MOTOR_PWM_PIN, 1);
    vTaskDelay(pdMS_TO_TICKS(3000));

    ESP_LOGW(TAG, "  MOTOR TEST: GPIO%d -> LOW (motor should stop now)", LIDAR_MOTOR_PWM_PIN);
    gpio_set_level(LIDAR_MOTOR_PWM_PIN, 0);
    vTaskDelay(pdMS_TO_TICKS(1000));

    ESP_LOGW(TAG, "  MOTOR TEST COMPLETE — proceeding to LEDC PWM init");
    /* GPIO will be reconfigured by ledc_channel_config() in lidar_motor_init() */
}
