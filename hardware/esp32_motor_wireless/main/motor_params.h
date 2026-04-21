/*
 * motor_params.h — Runtime-tunable motor control parameters
 *
 * Centralized, thread-safe, NVS-backed storage for every parameter that
 * participates in motor control. Replaces the compile-time #define macros
 * that used to live in motor_control.c / pid_controller.c.
 *
 * Design:
 *   - A single motor_params_t struct holds the current runtime values.
 *   - A mutex protects reads/writes (writer = serial RX task, readers =
 *     PID task on Core 1 and the serial TX path).
 *   - On boot, motor_params_init() tries to load each param from NVS.
 *     Missing keys fall back to the compile-time defaults in motor_params.c.
 *   - SET does NOT auto-persist. Call motor_params_save_nvs() to commit.
 *
 * Parameter IDs are defined in common/serial_protocol.h (PARAM_*).
 */
#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "serial_protocol.h"

/* ── Runtime parameter struct ───────────────────────────── */

typedef struct {
    /* PID gains (shared across both wheels for now) */
    float kp;
    float ki;
    float kd;

    /* Feed-forward model */
    float ff_scale;                 /* PWM per (m/s) — linear region slope */
    float ff_offset_left_fwd;       /* Stiction PWM, left motor, forward */
    float ff_offset_left_rev;       /* Stiction PWM, left motor, reverse */
    float ff_offset_right_fwd;      /* Stiction PWM, right motor, forward */
    float ff_offset_right_rev;      /* Stiction PWM, right motor, reverse */

    /* Output limits */
    float max_integral_pwm;         /* Cap on I-term PWM contribution */
    float max_output;               /* Max PID output magnitude */

    /* Phase 2 features (stored now, wired up in Phase 2) */
    float kickstart_pwm;            /* PWM applied during kickstart pulse */
    float kickstart_ms;             /* Kickstart pulse duration (ms) */
    float turn_kp_boost;            /* kp multiplier during turn-in-place */
    float stall_ff_boost;           /* Extra FF PWM when stall detected */

    /* Phase 4 feature (stored now, wired up in Phase 4) */
    float gyro_yaw_kp;              /* Outer-loop gyro yaw-rate gain */
} motor_params_t;

/* ── Source-of-value tracking ──────────────────────────── */
/* For each param we remember where the current runtime value came from.
 * Useful for diagnostics — e.g., "is this value saved or just runtime?" */

uint8_t motor_params_get_source(uint8_t param_id);

/* ── Lifecycle ─────────────────────────────────────────── */

/**
 * Initialize the params module. Must be called after nvs_flash_init().
 * Loads each param from NVS; missing keys get compile-time defaults.
 * Safe to call once at boot.
 */
esp_err_t motor_params_init(void);

/**
 * Reset runtime values to compile-time defaults. Does NOT erase NVS.
 * After this call, motor_params_get_source() returns PARAM_SRC_DEFAULT for all.
 */
void motor_params_reset_to_defaults(void);

/* ── Accessors ─────────────────────────────────────────── */

/**
 * Snapshot all current runtime params into a caller-provided struct.
 * Thread-safe. Typical use: called once per PID cycle (50 Hz).
 */
void motor_params_get(motor_params_t *out);

/**
 * Set a single param by ID. Returns ESP_ERR_INVALID_ARG if ID is unknown
 * or value is out-of-range (NaN, etc.).
 * Does NOT persist — call motor_params_save_nvs() to commit.
 */
esp_err_t motor_params_set_by_id(uint8_t param_id, float value);

/**
 * Get a single param by ID. out_source receives PARAM_SRC_* (optional — pass NULL).
 */
esp_err_t motor_params_get_by_id(uint8_t param_id, float *out_value, uint8_t *out_source);

/* ── NVS persistence ───────────────────────────────────── */

/**
 * Persist ALL current runtime values to NVS. After this, a reboot loads
 * exactly these values. Updates source to PARAM_SRC_NVS for each.
 */
esp_err_t motor_params_save_nvs(void);

/**
 * Load params from NVS into runtime. Missing keys keep their current
 * runtime value (not reset to default — call motor_params_reset_to_defaults()
 * first if you want a clean slate).
 */
esp_err_t motor_params_load_nvs(void);
