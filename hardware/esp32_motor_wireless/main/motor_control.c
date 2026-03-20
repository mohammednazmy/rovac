/*
 * motor_control.c — Closed-loop motor control (PID + odometry)
 *
 * Core control module for the ROVAC motor wireless firmware.
 * Owns a FreeRTOS task pinned to Core 1 that runs the PID loop at 50Hz.
 *
 * Each 20ms cycle:
 *   1. Read encoder deltas via encoder_reader_get_and_reset_deltas()
 *   2. Compute per-wheel velocity (m/s) from tick deltas
 *   3. Update odometry pose (mutex-protected inside odometry.c)
 *   4. If PID active: run PID for each wheel → motor_driver_set()
 *   5. If PID not active: motor_driver_stop()
 *
 * Thread safety:
 *   - Target velocities & active flag: protected by s_target_lock
 *     (written by cmd_vel on Core 0, read by PID task on Core 1)
 *   - Measured velocities: protected by s_meas_lock
 *     (written by PID task, read by odom publisher)
 *   - Encoder reader and odometry have their own internal mutexes
 *
 * PID parameters (calibrated for TB67H450FNG + JGB37-520R60-12):
 *   kp=40, ki=300, kd=10, ff_scale=200, max_output=255
 *   ff_offset_left=136, ff_offset_right=132
 */
#include "motor_control.h"
#include "motor_driver.h"
#include "encoder_reader.h"
#include "pid_controller.h"
#include "odometry.h"
#include "bno055.h"

#include <math.h>
#include <string.h>
#include <inttypes.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_timer.h"
#include "esp_log.h"

static const char *TAG = "motor_ctrl";

#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif

// ---- PID parameters (tuned for 50Hz loop on TB67H450FNG) ----
// Ki/Kd scaled down from Python driver's ~10Hz values:
//   Ki: 300 → 60 (5x reduction for 5x faster loop)
//   Kd: 10 → 3 (less derivative kick at high rate)
//   Kp: 40 → 25 (reduce oscillation, FF does most work)
#define PID_KP       25.0f
#define PID_KI       60.0f
#define PID_KD        3.0f
#define PID_FF_SCALE 200.0f
#define PID_FF_OFFSET_LEFT  136.0f
#define PID_FF_OFFSET_RIGHT 132.0f
#define PID_MAX_OUTPUT      255.0f

// ---- Wheel geometry (from odometry.h) ----
// WHEEL_SEPARATION = 0.155m, WHEEL_RADIUS = 0.032m, TICKS_PER_REV = 2640
static const float METERS_PER_TICK = (2.0f * M_PI * WHEEL_RADIUS) / TICKS_PER_REV;

// ---- Velocity decay timeout ----
// If no encoder ticks for this long, assume wheels are stopped
#define VELOCITY_DECAY_US  150000  // 150ms (same as Python driver)

// ---- PID task ----
#define PID_TASK_STACK_SIZE  4096
#define PID_TASK_PRIORITY    5  // Above normal, below critical
static TaskHandle_t s_pid_task_handle = NULL;

// ---- PID instances (one per wheel) ----
static wheel_pid_t s_pid_left;
static wheel_pid_t s_pid_right;

// ---- Target state (set by cmd_vel, read by PID task) ----
static SemaphoreHandle_t s_target_lock = NULL;
static float s_target_left  = 0.0f;  // Target wheel velocity (m/s)
static float s_target_right = 0.0f;
static bool  s_pid_active   = false;  // True when targets are non-zero
static int64_t s_last_cmd_time_us = 0; // Last cmd_vel timestamp

// ---- Measured state (set by PID task, read by odom publisher) ----
static SemaphoreHandle_t s_meas_lock = NULL;
static float s_meas_left  = 0.0f;  // Measured wheel velocity (m/s)
static float s_meas_right = 0.0f;

// ---- Helpers ----

static inline float clampf(float val, float lo, float hi)
{
    if (val < lo) return lo;
    if (val > hi) return hi;
    return val;
}

// ---- PID Task (Core 1, 50Hz) ----

// Debug: print PID state every N cycles when active (N=10 → 5Hz logging)
#define PID_DEBUG_INTERVAL  10

static void pid_task(void *arg)
{
    (void)arg;

    const TickType_t period_ticks = pdMS_TO_TICKS(1000 / MC_PID_RATE_HZ);  // 20ms
    TickType_t last_wake = xTaskGetTickCount();

    int64_t prev_time_us = esp_timer_get_time();
    int64_t last_nonzero_ticks_us = prev_time_us;
    uint32_t debug_counter = 0;

    ESP_LOGI(TAG, "PID task started on core %d at %d Hz",
             xPortGetCoreID(), MC_PID_RATE_HZ);

    while (true) {
        vTaskDelayUntil(&last_wake, period_ticks);

        int64_t now_us = esp_timer_get_time();
        float dt = (float)(now_us - prev_time_us) / 1e6f;
        prev_time_us = now_us;

        // Sanity check dt (protect against timer wrap or anomaly)
        if (dt <= 0.0f || dt > 0.5f) {
            dt = 1.0f / MC_PID_RATE_HZ;
        }

        // ---- Step 1: Read encoder deltas ----
        int32_t left_delta = 0, right_delta = 0;
        encoder_reader_get_and_reset_deltas(&left_delta, &right_delta);

        // ---- Step 2: Compute per-wheel velocity (m/s) ----
        float v_left_meas  = ((float)left_delta  * METERS_PER_TICK) / dt;
        float v_right_meas = ((float)right_delta * METERS_PER_TICK) / dt;

        // Velocity decay: if no ticks for > 150ms, assume stopped
        if (left_delta != 0 || right_delta != 0) {
            last_nonzero_ticks_us = now_us;
        } else if ((now_us - last_nonzero_ticks_us) > VELOCITY_DECAY_US) {
            v_left_meas  = 0.0f;
            v_right_meas = 0.0f;
        }

        // Store measured velocities (thread-safe)
        xSemaphoreTake(s_meas_lock, portMAX_DELAY);
        s_meas_left  = v_left_meas;
        s_meas_right = v_right_meas;
        xSemaphoreGive(s_meas_lock);

        // ---- Step 3: Update odometry ----
        odometry_update(left_delta, right_delta, dt);

        // ---- Step 4: Run PID (if active) ----
        xSemaphoreTake(s_target_lock, portMAX_DELAY);
        bool active = s_pid_active;
        float tgt_left  = s_target_left;
        float tgt_right = s_target_right;
        xSemaphoreGive(s_target_lock);

        if (active) {
            float pwm_left  = pid_update(&s_pid_left,  tgt_left,  v_left_meas,  dt);
            float pwm_right = pid_update(&s_pid_right, tgt_right, v_right_meas, dt);

            // Convert float PWM to int16, rounding
            int16_t cmd_left  = (int16_t)clampf(roundf(pwm_left),  -255.0f, 255.0f);
            int16_t cmd_right = (int16_t)clampf(roundf(pwm_right), -255.0f, 255.0f);

            motor_driver_set(cmd_left, cmd_right);

            // Debug: periodic PID state dump (5Hz when active)
            if (++debug_counter % PID_DEBUG_INTERVAL == 0) {
                ESP_LOGI(TAG, "PID tgt=%.3f/%.3f meas=%.3f/%.3f enc=%ld/%ld pwm=%d/%d dt=%.1fms",
                         tgt_left, tgt_right,
                         v_left_meas, v_right_meas,
                         (long)left_delta, (long)right_delta,
                         cmd_left, cmd_right,
                         dt * 1000.0f);
            }
        } else {
            motor_driver_stop();
            debug_counter = 0;
        }
    }
}

// ---- Public API ----

esp_err_t motor_control_init(void)
{
    // Create mutexes
    s_target_lock = xSemaphoreCreateMutex();
    s_meas_lock   = xSemaphoreCreateMutex();
    if (s_target_lock == NULL || s_meas_lock == NULL) {
        ESP_LOGE(TAG, "Failed to create mutexes");
        return ESP_ERR_NO_MEM;
    }

    // Initialize PID controllers with calibrated parameters
    pid_init(&s_pid_left,  PID_KP, PID_KI, PID_KD,
             PID_FF_SCALE, PID_FF_OFFSET_LEFT, PID_MAX_OUTPUT);
    pid_init(&s_pid_right, PID_KP, PID_KI, PID_KD,
             PID_FF_SCALE, PID_FF_OFFSET_RIGHT, PID_MAX_OUTPUT);

    // Initialize targets
    s_target_left  = 0.0f;
    s_target_right = 0.0f;
    s_pid_active   = false;
    s_last_cmd_time_us = esp_timer_get_time();

    // Start PID task pinned to Core 1
    BaseType_t ret = xTaskCreatePinnedToCore(
        pid_task,
        "pid_ctrl",
        PID_TASK_STACK_SIZE,
        NULL,
        PID_TASK_PRIORITY,
        &s_pid_task_handle,
        1  // Core 1
    );
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create PID task");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Motor control initialized: PID@%dHz on Core 1, "
             "kp=%.0f ki=%.0f kd=%.0f ff_scale=%.0f ff_off=%.0f/%.0f",
             MC_PID_RATE_HZ, PID_KP, PID_KI, PID_KD, PID_FF_SCALE,
             PID_FF_OFFSET_LEFT, PID_FF_OFFSET_RIGHT);
    return ESP_OK;
}

void motor_control_set_target(float v_left, float v_right)
{
    xSemaphoreTake(s_target_lock, portMAX_DELAY);
    s_target_left  = v_left;
    s_target_right = v_right;
    s_pid_active   = true;
    s_last_cmd_time_us = esp_timer_get_time();
    xSemaphoreGive(s_target_lock);
}

// ---- Gyro-assisted heading correction ----
// When cmd_vel requests straight-line motion (angular_z ≈ 0), the gyro
// detects yaw drift from wheel asymmetry and feeds back a correction.
// Proportional gain: angular_correction = -KP_HEADING * measured_gyro_z
#define HEADING_CORRECTION_KP    0.5f    // Tunable: start conservative
#define HEADING_CORRECTION_THRESH 0.05f  // rad/s — only correct if target angular < this

void motor_control_cmd_vel(float linear_x, float angular_z)
{
    // Clamp inputs
    linear_x  = clampf(linear_x,  -MC_MAX_LINEAR_SPEED,  MC_MAX_LINEAR_SPEED);
    angular_z = clampf(angular_z, -MC_MAX_ANGULAR_SPEED, MC_MAX_ANGULAR_SPEED);

    // Dead zone: if both components are negligible, just stop
    if (fabsf(linear_x) < 0.01f && fabsf(angular_z) < 0.01f) {
        motor_control_stop();
        return;
    }

    // Gyro heading correction: when driving "straight" (angular ≈ 0),
    // counteract measured yaw rate to maintain heading
    if (fabsf(angular_z) < HEADING_CORRECTION_THRESH && fabsf(linear_x) > 0.02f) {
        float gyro_z = bno055_get_gyro_z();  // rad/s, 0 if IMU not ready
        angular_z += -HEADING_CORRECTION_KP * gyro_z;
        angular_z = clampf(angular_z, -MC_MAX_ANGULAR_SPEED, MC_MAX_ANGULAR_SPEED);
    }

    // Differential drive kinematics:
    //   v_left  = linear_x - angular_z * (wheel_separation / 2)
    //   v_right = linear_x + angular_z * (wheel_separation / 2)
    float half_sep = WHEEL_SEPARATION / 2.0f;
    float v_left  = linear_x - angular_z * half_sep;
    float v_right = linear_x + angular_z * half_sep;

    motor_control_set_target(v_left, v_right);
}

void motor_control_stop(void)
{
    xSemaphoreTake(s_target_lock, portMAX_DELAY);
    s_target_left  = 0.0f;
    s_target_right = 0.0f;
    s_pid_active   = false;
    xSemaphoreGive(s_target_lock);

    // Reset PID state to avoid stale integral/derivative on next start
    pid_reset(&s_pid_left);
    pid_reset(&s_pid_right);

    // Immediately stop motors (don't wait for PID task cycle)
    motor_driver_stop();
}

void motor_control_watchdog(void)
{
    xSemaphoreTake(s_target_lock, portMAX_DELAY);
    bool active = s_pid_active;
    int64_t last_cmd = s_last_cmd_time_us;
    xSemaphoreGive(s_target_lock);

    if (!active) {
        return;
    }

    int64_t now_us = esp_timer_get_time();
    int64_t elapsed_ms = (now_us - last_cmd) / 1000;

    if (elapsed_ms > MC_CMD_VEL_TIMEOUT_MS) {
        ESP_LOGW(TAG, "cmd_vel timeout (%" PRId64 " ms > %d ms) — stopping motors",
                 elapsed_ms, MC_CMD_VEL_TIMEOUT_MS);
        motor_control_stop();
    }
}

bool motor_control_is_active(void)
{
    xSemaphoreTake(s_target_lock, portMAX_DELAY);
    bool active = s_pid_active;
    xSemaphoreGive(s_target_lock);
    return active;
}

void motor_control_get_velocities(float *v_left, float *v_right)
{
    xSemaphoreTake(s_meas_lock, portMAX_DELAY);
    if (v_left)  *v_left  = s_meas_left;
    if (v_right) *v_right = s_meas_right;
    xSemaphoreGive(s_meas_lock);
}
