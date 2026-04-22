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
#include "motor_params.h"

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

/* All PID/FF tunables now live in motor_params — firmware defaults are
 * declared in motor_params.c (s_defaults). Runtime changes arrive via
 * MSG_CMD_SET_PARAM and persist to NVS via MSG_CMD_SAVE_NVS. */

// ---- Wheel geometry (from odometry.h) ----
// WHEEL_SEPARATION = 0.2005m, WHEEL_RADIUS = 0.0222m, TICKS_PER_REV = 2640
// (both physically measured 2026-04-22 — see odometry.h for methodology)
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
// s_target_lock protects: s_target_left, s_target_right, s_pid_active,
//                         s_raw_pwm_active, s_raw_pwm_left, s_raw_pwm_right,
//                         s_last_cmd_time_us
static SemaphoreHandle_t s_target_lock = NULL;
static float s_target_left  = 0.0f;  // Target wheel velocity (m/s)
static float s_target_right = 0.0f;
static bool  s_pid_active   = false;  // True when targets are non-zero
static int64_t s_last_cmd_time_us = 0; // Last cmd_vel / raw PWM timestamp

// ---- Raw PWM mode (characterization bypass) ----
// When s_raw_pwm_active, PID task ignores targets and writes s_raw_pwm_*
// directly to the motor driver. Any subsequent cmd_vel clears the flag.
static bool  s_raw_pwm_active = false;
static int16_t s_raw_pwm_left  = 0;
static int16_t s_raw_pwm_right = 0;

// ---- Kickstart / stall watchdog state (PID task local) ----
// These are touched only from pid_task on Core 1 — no lock needed.
static bool    s_was_pid_active     = false;  // transition detector
static int64_t s_kickstart_end_us   = 0;      // 0 = not in kickstart
static int16_t s_kickstart_left_pwm = 0;
static int16_t s_kickstart_right_pwm = 0;
static int64_t s_last_left_tick_us  = 0;      // per-wheel stall detection
static int64_t s_last_right_tick_us = 0;

// ---- Gyro-assisted angular outer loop state (Phase 4) ----
// The cmd_vel callback on Core 0 stores the commanded (post-heading-correction)
// angular velocity here. The PID task on Core 1 reads it each cycle and, when
// gyro_yaw_kp > 0 and the robot is commanded to turn, biases the per-wheel
// targets to close a feedback loop on BNO055-measured yaw rate.
// float32 stores are atomic on ESP32 at 4-byte alignment — no lock needed.
static volatile float s_current_angular_z_cmd = 0.0f;
// Threshold below which we do NOT engage the outer loop (straight-line drive
// uses the existing HEADING_CORRECTION_KP path in motor_control_cmd_vel).
#define GYRO_LOOP_MIN_ANG 0.10f  // rad/s

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

        // Per-wheel stall detector: remember the last time each wheel saw
        // an encoder tick. Consulted by the active branch below to apply
        // stall_ff_boost when commanded motion is not producing movement.
        if (left_delta  != 0) s_last_left_tick_us  = now_us;
        if (right_delta != 0) s_last_right_tick_us = now_us;

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

        // ---- Step 4: Snapshot target state and mode ----
        xSemaphoreTake(s_target_lock, portMAX_DELAY);
        bool raw_mode     = s_raw_pwm_active;
        int16_t raw_left  = s_raw_pwm_left;
        int16_t raw_right = s_raw_pwm_right;
        bool active       = s_pid_active;
        float tgt_left    = s_target_left;
        float tgt_right   = s_target_right;
        xSemaphoreGive(s_target_lock);

        if (raw_mode) {
            // Characterization bypass: write PWM directly, keep PID state
            // clean so a later cmd_vel starts from a known zero integral.
            pid_reset(&s_pid_left);
            pid_reset(&s_pid_right);
            motor_driver_set(raw_left, raw_right);
            // Exiting raw mode into PID mode counts as an idle→active
            // transition for kickstart purposes.
            s_was_pid_active   = false;
            s_kickstart_end_us = 0;
            if (++debug_counter % PID_DEBUG_INTERVAL == 0) {
                ESP_LOGI(TAG, "RAW pwm=%d/%d meas=%.3f/%.3f enc=%ld/%ld",
                         raw_left, raw_right, v_left_meas, v_right_meas,
                         (long)left_delta, (long)right_delta);
            }
        } else if (active) {
            // Pull latest tunable params each cycle — cheap snapshot under mutex.
            motor_params_t p;
            motor_params_get(&p);

            // Idle→active transition: arm kickstart pulse if configured.
            // kickstart bypasses PID with a fixed-magnitude pulse for
            // kickstart_ms to break stiction, then hands off to normal PID.
            // Disabled by default (kickstart_pwm == 0); Phase 3 tunes.
            if (!s_was_pid_active &&
                p.kickstart_pwm > 0.0f && p.kickstart_ms > 0.0f) {
                s_kickstart_end_us = now_us + (int64_t)(p.kickstart_ms * 1000.0f);
                int16_t mag = (int16_t)clampf(p.kickstart_pwm, 0.0f, p.max_output);
                s_kickstart_left_pwm  = (tgt_left  >= 0.0f) ? mag : (int16_t)-mag;
                s_kickstart_right_pwm = (tgt_right >= 0.0f) ? mag : (int16_t)-mag;
            }
            s_was_pid_active = true;

            if (now_us < s_kickstart_end_us) {
                // Inside kickstart window: fixed pulse, PID state held clean.
                pid_reset(&s_pid_left);
                pid_reset(&s_pid_right);
                motor_driver_set(s_kickstart_left_pwm, s_kickstart_right_pwm);
                if (++debug_counter % PID_DEBUG_INTERVAL == 0) {
                    ESP_LOGI(TAG, "KICK pwm=%d/%d (%dms remaining)",
                             s_kickstart_left_pwm, s_kickstart_right_pwm,
                             (int)((s_kickstart_end_us - now_us) / 1000));
                }
            } else {
                // ── Phase 4 outer loop: close angular-rate feedback on gyro ──
                // When commanded to turn meaningfully and the feature is enabled,
                // measure true yaw rate via BNO055 and bias per-wheel targets so
                // the outer loop drives measured angular velocity toward the
                // commanded value. Compensates for tread slip — encoder-derived
                // angular overestimates ground rotation when treads scrub.
                // Disabled by default (gyro_yaw_kp == 0); Phase 3 tunes.
                float ang_cmd = s_current_angular_z_cmd;
                bool  gyro_loop = (p.gyro_yaw_kp > 0.0f) &&
                                  (fabsf(ang_cmd) > GYRO_LOOP_MIN_ANG);
                if (gyro_loop) {
                    // BNO055 is mounted face-down on this robot (URDF rpy=3.14159 0 0).
                    // Raw chip gyro_z is opposite sign from ROS/base_link convention.
                    // Negate here so gyro_z aligns with ang_cmd's sign convention
                    // (positive = CCW / left turn). External ROS consumers get the
                    // corrected frame via URDF TF on the IMU message; firmware-internal
                    // uses need their own negation.
                    float gyro_z = -bno055_get_gyro_z();
                    if (isfinite(gyro_z)) {
                        float ang_err = ang_cmd - gyro_z;
                        // Clamp error so one bad gyro reading can't snap the
                        // wheel targets beyond the machine's velocity limits.
                        ang_err = clampf(ang_err,
                                         -MC_MAX_ANGULAR_SPEED,
                                         MC_MAX_ANGULAR_SPEED);
                        float delta = p.gyro_yaw_kp * ang_err *
                                      (WHEEL_SEPARATION / 2.0f);
                        tgt_left  -= delta;
                        tgt_right += delta;
                    }
                }

                // Turn-in-place detection: targets have opposite sign (one
                // wheel forward, one reverse) → boost kp for snappier rotation.
                // Disabled by default (turn_kp_boost == 1.0); Phase 3 tunes.
                bool turn_in_place = (tgt_left * tgt_right) < -1e-4f;
                float eff_kp = p.kp * (turn_in_place ? p.turn_kp_boost : 1.0f);

                s_pid_left.kp  = eff_kp;  s_pid_right.kp  = eff_kp;
                s_pid_left.ki  = p.ki;    s_pid_right.ki  = p.ki;
                s_pid_left.kd  = p.kd;    s_pid_right.kd  = p.kd;
                s_pid_left.ff_scale   = p.ff_scale;   s_pid_right.ff_scale   = p.ff_scale;
                s_pid_left.max_output = p.max_output; s_pid_right.max_output = p.max_output;
                s_pid_left.max_integral_pwm  = p.max_integral_pwm;
                s_pid_right.max_integral_pwm = p.max_integral_pwm;

                // Per-wheel stall watchdog: if a commanded wheel is clearly
                // not moving (|meas| < STALL_MEAS_EPS) despite being
                // commanded meaningfully (|tgt| > STALL_TGT_MIN) for
                // STALL_TIMEOUT_US without ticks, temporarily add
                // stall_ff_boost to its feed-forward offset. Released
                // automatically once the wheel starts moving.
                //
                // The STALL_TGT_MIN gate matters at low target velocities:
                // right above stiction, encoder ticks are sparse (1-2 per
                // 20ms cycle) and can have 100+ms gaps normally. Without
                // the gate + |meas| check we false-trigger, blasting 100+
                // PWM of boost at a target that only needs 12 PWM above
                // stiction — catastrophic overshoot.
                //
                // Disabled by default (stall_ff_boost == 0); Phase 3 tunes.
                #define STALL_TIMEOUT_US   150000  /* 150 ms */
                #define STALL_TGT_MIN      0.08f   /* m/s — below this we
                                                      don't assume stall */
                #define STALL_MEAS_EPS     0.015f  /* m/s — measured velocity
                                                      below this counts as
                                                      "not actually moving" */
                bool stall_left  = (fabsf(tgt_left)  > STALL_TGT_MIN) &&
                                   (fabsf(v_left_meas)  < STALL_MEAS_EPS) &&
                                   (now_us - s_last_left_tick_us)  > STALL_TIMEOUT_US;
                bool stall_right = (fabsf(tgt_right) > STALL_TGT_MIN) &&
                                   (fabsf(v_right_meas) < STALL_MEAS_EPS) &&
                                   (now_us - s_last_right_tick_us) > STALL_TIMEOUT_US;

                float ff_off_l = (tgt_left  >= 0.0f) ? p.ff_offset_left_fwd  : p.ff_offset_left_rev;
                float ff_off_r = (tgt_right >= 0.0f) ? p.ff_offset_right_fwd : p.ff_offset_right_rev;
                if (stall_left)  ff_off_l += p.stall_ff_boost;
                if (stall_right) ff_off_r += p.stall_ff_boost;

                // Yaw-rate FF compensation — when commanded to turn in place,
                // pre-bias FF by yaw_rate_ff * |commanded angular| to overcome
                // track-scrub friction without waiting for the integral to
                // build up. Disabled by default (yaw_rate_ff == 0).
                if (turn_in_place && p.yaw_rate_ff > 0.0f) {
                    float yaw_boost = p.yaw_rate_ff *
                                      fabsf(s_current_angular_z_cmd);
                    ff_off_l += yaw_boost;
                    ff_off_r += yaw_boost;
                }

                s_pid_left.ff_offset  = ff_off_l;
                s_pid_right.ff_offset = ff_off_r;

                float pwm_left  = pid_update(&s_pid_left,  tgt_left,  v_left_meas,  dt);
                float pwm_right = pid_update(&s_pid_right, tgt_right, v_right_meas, dt);

                // Convert float PWM to int16, rounding
                int16_t cmd_left  = (int16_t)clampf(roundf(pwm_left),  -p.max_output, p.max_output);
                int16_t cmd_right = (int16_t)clampf(roundf(pwm_right), -p.max_output, p.max_output);

                motor_driver_set(cmd_left, cmd_right);

                if (++debug_counter % PID_DEBUG_INTERVAL == 0) {
                    ESP_LOGI(TAG, "PID tgt=%.3f/%.3f meas=%.3f/%.3f enc=%ld/%ld pwm=%d/%d%s%s%s dt=%.1fms",
                             tgt_left, tgt_right,
                             v_left_meas, v_right_meas,
                             (long)left_delta, (long)right_delta,
                             cmd_left, cmd_right,
                             turn_in_place ? " TURN" : "",
                             stall_left    ? " STL-L" : "",
                             stall_right   ? " STL-R" : "",
                             dt * 1000.0f);
                }
            }
        } else {
            // Honor brake_on_stop: active brake vs coast. Default is coast
            // (brake_on_stop=0). Active brake shorts motor windings, giving
            // a faster stop at the cost of more mechanical/thermal stress.
            motor_params_t p_stop;
            motor_params_get(&p_stop);
            if (p_stop.brake_on_stop >= 0.5f) {
                motor_driver_brake();
            } else {
                motor_driver_stop();
            }
            pid_reset(&s_pid_left);
            pid_reset(&s_pid_right);
            s_was_pid_active   = false;
            s_kickstart_end_us = 0;
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

    // Seed PID structs with current runtime params. The pid_task will keep
    // these in sync every cycle, so this is just the boot-time snapshot.
    motor_params_t p;
    motor_params_get(&p);
    pid_init(&s_pid_left,  p.kp, p.ki, p.kd,
             p.ff_scale, p.ff_offset_left_fwd,
             p.max_output, p.max_integral_pwm);
    pid_init(&s_pid_right, p.kp, p.ki, p.kd,
             p.ff_scale, p.ff_offset_right_fwd,
             p.max_output, p.max_integral_pwm);

    // Initialize targets
    s_target_left  = 0.0f;
    s_target_right = 0.0f;
    s_pid_active   = false;
    s_raw_pwm_active = false;
    s_raw_pwm_left = 0;
    s_raw_pwm_right = 0;
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
             "kp=%.0f ki=%.0f kd=%.0f ff_scale=%.0f ff_off_l=%.0f ff_off_r=%.0f max_i=%.0f",
             MC_PID_RATE_HZ, (double)p.kp, (double)p.ki, (double)p.kd,
             (double)p.ff_scale, (double)p.ff_offset_left_fwd,
             (double)p.ff_offset_right_fwd, (double)p.max_integral_pwm);
    return ESP_OK;
}

void motor_control_set_target(float v_left, float v_right)
{
    xSemaphoreTake(s_target_lock, portMAX_DELAY);
    s_target_left  = v_left;
    s_target_right = v_right;
    s_pid_active   = true;
    /* Any velocity command exits raw PWM bypass mode */
    s_raw_pwm_active = false;
    s_last_cmd_time_us = esp_timer_get_time();
    xSemaphoreGive(s_target_lock);
}

void motor_control_set_raw_pwm(int16_t left_pwm, int16_t right_pwm)
{
    /* Clamp defensively — driver clamps too, but be explicit. */
    if (left_pwm  >  255) left_pwm  =  255;
    if (left_pwm  < -255) left_pwm  = -255;
    if (right_pwm >  255) right_pwm =  255;
    if (right_pwm < -255) right_pwm = -255;

    xSemaphoreTake(s_target_lock, portMAX_DELAY);
    s_raw_pwm_left   = left_pwm;
    s_raw_pwm_right  = right_pwm;
    s_raw_pwm_active = true;
    s_pid_active     = false;   /* PID off while raw mode is engaged */
    s_last_cmd_time_us = esp_timer_get_time();
    xSemaphoreGive(s_target_lock);
}

bool motor_control_is_raw_mode(void)
{
    xSemaphoreTake(s_target_lock, portMAX_DELAY);
    bool r = s_raw_pwm_active;
    xSemaphoreGive(s_target_lock);
    return r;
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
    // counteract measured yaw rate to maintain heading.
    //
    // SIGN CRITICAL: BNO055 is mounted face-down (URDF rpy=3.14159 0 0),
    // so raw chip gyro_z is the OPPOSITE sign of ROS/base_link convention.
    // We negate at the read site so angular_z and gyro_z live in the same
    // (base_link) frame here. Without this negation, this correction becomes
    // a positive-feedback loop that amplifies drift instead of cancelling it.
    if (fabsf(angular_z) < HEADING_CORRECTION_THRESH && fabsf(linear_x) > 0.02f) {
        float gyro_z = -bno055_get_gyro_z();  // rad/s in base_link frame, 0 if IMU not ready
        if (isfinite(gyro_z)) {
            angular_z += -HEADING_CORRECTION_KP * gyro_z;
            angular_z = clampf(angular_z, -MC_MAX_ANGULAR_SPEED, MC_MAX_ANGULAR_SPEED);
        }
    }

    // Differential drive kinematics:
    //   v_left  = linear_x - angular_z * (wheel_separation / 2)
    //   v_right = linear_x + angular_z * (wheel_separation / 2)
    float half_sep = WHEEL_SEPARATION / 2.0f;
    float v_left  = linear_x - angular_z * half_sep;
    float v_right = linear_x + angular_z * half_sep;

    // Stash commanded angular for the PID task's gyro outer loop (Phase 4).
    // Aligned float store is atomic on ESP32 — no lock required.
    s_current_angular_z_cmd = angular_z;

    motor_control_set_target(v_left, v_right);
}

void motor_control_stop(void)
{
    xSemaphoreTake(s_target_lock, portMAX_DELAY);
    s_target_left    = 0.0f;
    s_target_right   = 0.0f;
    s_pid_active     = false;
    s_raw_pwm_active = false;
    s_raw_pwm_left   = 0;
    s_raw_pwm_right  = 0;
    xSemaphoreGive(s_target_lock);

    // Clear Phase 4 outer-loop target so a stale angular doesn't leak
    // into the next command.
    s_current_angular_z_cmd = 0.0f;

    // PID state is reset by the PID task when it sees active=false,
    // avoiding a cross-core data race with pid_update() on Core 1.

    // Immediately stop motors (don't wait for PID task cycle).
    // Honor brake_on_stop param — default is coast.
    motor_params_t p_stop;
    motor_params_get(&p_stop);
    if (p_stop.brake_on_stop >= 0.5f) {
        motor_driver_brake();
    } else {
        motor_driver_stop();
    }
}

void motor_control_watchdog(void)
{
    xSemaphoreTake(s_target_lock, portMAX_DELAY);
    bool active = s_pid_active || s_raw_pwm_active;
    bool raw    = s_raw_pwm_active;
    int64_t last_cmd = s_last_cmd_time_us;
    xSemaphoreGive(s_target_lock);

    if (!active) {
        return;
    }

    int64_t now_us = esp_timer_get_time();
    int64_t elapsed_ms = (now_us - last_cmd) / 1000;

    if (elapsed_ms > MC_CMD_VEL_TIMEOUT_MS) {
        ESP_LOGW(TAG, "%s timeout (%" PRId64 " ms > %d ms) — stopping motors",
                 raw ? "raw-pwm" : "cmd_vel",
                 elapsed_ms, MC_CMD_VEL_TIMEOUT_MS);
        motor_control_stop();
    }
}

bool motor_control_is_active(void)
{
    xSemaphoreTake(s_target_lock, portMAX_DELAY);
    bool active = s_pid_active || s_raw_pwm_active;
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
