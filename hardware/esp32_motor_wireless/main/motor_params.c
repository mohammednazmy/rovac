/*
 * motor_params.c — Runtime-tunable motor control parameters
 *
 * Thread-safety model:
 *   - One mutex (s_params_lock) protects s_params, s_source, and s_inited.
 *   - Callers holding the lock for <10 us at 50 Hz (PID task read) + sub-Hz
 *     (RX task write) — contention is negligible.
 *
 * NVS layout:
 *   - Namespace: "rovac" (shared with nvs_config.c for WiFi settings).
 *   - One key per param. Keys are short (<15 chars, NVS limit) and use the
 *     "p_" prefix to avoid colliding with existing keys (wifi_ssid, etc.).
 *   - We store as float32 (nvs_set_blob with 4 bytes). Could use nvs_set_u32
 *     reinterpret, but blob is portable and explicit.
 *
 * Compile-time defaults:
 *   Derived from the original #define macros in motor_control.c (pre-Phase-2).
 *   Any change here affects the "factory reset" behavior.
 */
#include "motor_params.h"

#include <string.h>
#include <math.h>
#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static const char *TAG = "motor_params";

/* ── NVS ──────────────────────────────────────────────── */

#define PARAMS_NVS_NAMESPACE   "rovac"       /* shared with nvs_config.c */

/* One NVS key per param. Keep each ≤14 chars (NVS limit is 15 incl. null). */
static const char *const s_param_keys[PARAM_ID_MAX + 1] = {
    [0]                            = NULL,          /* unused */
    [PARAM_KP]                     = "p_kp",
    [PARAM_KI]                     = "p_ki",
    [PARAM_KD]                     = "p_kd",
    [PARAM_FF_SCALE]               = "p_ff_sc",
    [PARAM_FF_OFFSET_LEFT_FWD]     = "p_ff_lf",
    [PARAM_FF_OFFSET_LEFT_REV]     = "p_ff_lr",
    [PARAM_FF_OFFSET_RIGHT_FWD]    = "p_ff_rf",
    [PARAM_FF_OFFSET_RIGHT_REV]    = "p_ff_rr",
    [PARAM_MAX_INTEGRAL_PWM]       = "p_max_i",
    [PARAM_MAX_OUTPUT]             = "p_max_o",
    [PARAM_KICKSTART_PWM]          = "p_ks_pwm",
    [PARAM_KICKSTART_MS]           = "p_ks_ms",
    [PARAM_TURN_KP_BOOST]          = "p_turn_kp",
    [PARAM_STALL_FF_BOOST]         = "p_stall",
    [PARAM_GYRO_YAW_KP]            = "p_gyro_kp",
};

/* ── Compile-time defaults ─────────────────────────────── */
/* These preserve pre-Phase-0 behavior byte-for-byte. Phase 3 retune will
 * update these after bench characterization. */

static const motor_params_t s_defaults = {
    .kp                     = 25.0f,
    .ki                     = 60.0f,
    .kd                     = 3.0f,
    .ff_scale               = 200.0f,
    .ff_offset_left_fwd     = 136.0f,
    .ff_offset_left_rev     = 136.0f,   /* Phase 2 will split fwd/rev */
    .ff_offset_right_fwd    = 132.0f,
    .ff_offset_right_rev    = 132.0f,
    .max_integral_pwm       = 150.0f,   /* Phase 2: raised from 50 — paired
                                         * with conditional-integration anti-
                                         * windup so I-term can push near
                                         * saturation under mechanical load. */
    .max_output             = 255.0f,
    .kickstart_pwm          = 0.0f,     /* 0 = disabled; Phase 3 tunes */
    .kickstart_ms           = 0.0f,
    .turn_kp_boost          = 1.0f,     /* 1.0 = no boost; Phase 3 tunes */
    .stall_ff_boost         = 0.0f,     /* 0 = disabled; Phase 3 tunes */
    .gyro_yaw_kp            = 0.0f,     /* 0 = disabled (Phase 4 wires up) */
};

/* ── Runtime state ─────────────────────────────────────── */

static motor_params_t s_params;
static uint8_t s_source[PARAM_ID_MAX + 1];  /* PARAM_SRC_* per ID */
static SemaphoreHandle_t s_params_lock = NULL;
static bool s_inited = false;

/* ── Helpers ───────────────────────────────────────────── */

/* Map a PARAM_* ID to a pointer inside motor_params_t.
 * Returns NULL if the ID is unknown.
 * Caller must hold s_params_lock (or not care about races). */
static float *param_ptr(motor_params_t *p, uint8_t id)
{
    switch (id) {
    case PARAM_KP:                   return &p->kp;
    case PARAM_KI:                   return &p->ki;
    case PARAM_KD:                   return &p->kd;
    case PARAM_FF_SCALE:             return &p->ff_scale;
    case PARAM_FF_OFFSET_LEFT_FWD:   return &p->ff_offset_left_fwd;
    case PARAM_FF_OFFSET_LEFT_REV:   return &p->ff_offset_left_rev;
    case PARAM_FF_OFFSET_RIGHT_FWD:  return &p->ff_offset_right_fwd;
    case PARAM_FF_OFFSET_RIGHT_REV:  return &p->ff_offset_right_rev;
    case PARAM_MAX_INTEGRAL_PWM:     return &p->max_integral_pwm;
    case PARAM_MAX_OUTPUT:           return &p->max_output;
    case PARAM_KICKSTART_PWM:        return &p->kickstart_pwm;
    case PARAM_KICKSTART_MS:         return &p->kickstart_ms;
    case PARAM_TURN_KP_BOOST:        return &p->turn_kp_boost;
    case PARAM_STALL_FF_BOOST:       return &p->stall_ff_boost;
    case PARAM_GYRO_YAW_KP:          return &p->gyro_yaw_kp;
    default:                         return NULL;
    }
}

/* Sanity-check an incoming param value. Rejects NaN/Inf and obvious
 * nonsense for a few specific params (negative gains, etc.). */
static bool param_value_sane(uint8_t id, float value)
{
    if (!isfinite(value)) return false;

    switch (id) {
    case PARAM_KP:
    case PARAM_KI:
    case PARAM_KD:
    case PARAM_FF_SCALE:
    case PARAM_MAX_INTEGRAL_PWM:
    case PARAM_KICKSTART_PWM:
    case PARAM_KICKSTART_MS:
    case PARAM_STALL_FF_BOOST:
    case PARAM_GYRO_YAW_KP:
        return value >= 0.0f;
    case PARAM_TURN_KP_BOOST:
        return value > 0.0f;
    case PARAM_MAX_OUTPUT:
        return value > 0.0f && value <= 255.0f;
    /* ff_offsets can be any sign (though normally positive) */
    default:
        return true;
    }
}

/* Try to read one param from NVS. Returns true if found. */
static bool load_one_from_nvs(nvs_handle_t h, uint8_t id, float *out)
{
    const char *key = s_param_keys[id];
    if (key == NULL) return false;

    float value;
    size_t sz = sizeof(value);
    esp_err_t err = nvs_get_blob(h, key, &value, &sz);
    if (err != ESP_OK || sz != sizeof(value)) return false;
    if (!isfinite(value)) return false;  /* corrupted */

    *out = value;
    return true;
}

/* Write one param to NVS. */
static esp_err_t save_one_to_nvs(nvs_handle_t h, uint8_t id, float value)
{
    const char *key = s_param_keys[id];
    if (key == NULL) return ESP_ERR_INVALID_ARG;
    return nvs_set_blob(h, key, &value, sizeof(value));
}

/* ── Public API ────────────────────────────────────────── */

esp_err_t motor_params_init(void)
{
    if (s_inited) return ESP_OK;

    s_params_lock = xSemaphoreCreateMutex();
    if (s_params_lock == NULL) {
        ESP_LOGE(TAG, "Failed to create params mutex");
        return ESP_ERR_NO_MEM;
    }

    /* Start with defaults */
    xSemaphoreTake(s_params_lock, portMAX_DELAY);
    memcpy(&s_params, &s_defaults, sizeof(s_params));
    for (int i = 0; i <= PARAM_ID_MAX; i++) s_source[i] = PARAM_SRC_DEFAULT;
    xSemaphoreGive(s_params_lock);

    /* Try to overlay NVS values */
    nvs_handle_t h;
    esp_err_t err = nvs_open(PARAMS_NVS_NAMESPACE, NVS_READONLY, &h);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGI(TAG, "No motor params in NVS — using firmware defaults");
        s_inited = true;
        return ESP_OK;
    } else if (err != ESP_OK) {
        ESP_LOGW(TAG, "nvs_open failed (%s) — using defaults",
                 esp_err_to_name(err));
        s_inited = true;
        return ESP_OK;  /* non-fatal */
    }

    int loaded = 0;
    xSemaphoreTake(s_params_lock, portMAX_DELAY);
    for (uint8_t id = 1; id <= PARAM_ID_MAX; id++) {
        float value;
        if (load_one_from_nvs(h, id, &value)) {
            float *slot = param_ptr(&s_params, id);
            if (slot && param_value_sane(id, value)) {
                *slot = value;
                s_source[id] = PARAM_SRC_NVS;
                loaded++;
            }
        }
    }
    xSemaphoreGive(s_params_lock);
    nvs_close(h);

    ESP_LOGI(TAG, "Motor params loaded: %d from NVS, %d firmware defaults",
             loaded, PARAM_ID_MAX - loaded);
    s_inited = true;
    return ESP_OK;
}

void motor_params_reset_to_defaults(void)
{
    if (!s_inited) return;
    xSemaphoreTake(s_params_lock, portMAX_DELAY);
    memcpy(&s_params, &s_defaults, sizeof(s_params));
    for (int i = 0; i <= PARAM_ID_MAX; i++) s_source[i] = PARAM_SRC_DEFAULT;
    xSemaphoreGive(s_params_lock);
    ESP_LOGW(TAG, "Motor params reset to firmware defaults (NVS untouched)");
}

void motor_params_get(motor_params_t *out)
{
    if (!s_inited || out == NULL) return;
    xSemaphoreTake(s_params_lock, portMAX_DELAY);
    memcpy(out, &s_params, sizeof(motor_params_t));
    xSemaphoreGive(s_params_lock);
}

esp_err_t motor_params_set_by_id(uint8_t param_id, float value)
{
    if (!s_inited) return ESP_ERR_INVALID_STATE;
    if (param_id == 0 || param_id > PARAM_ID_MAX) return ESP_ERR_INVALID_ARG;
    if (!param_value_sane(param_id, value)) return ESP_ERR_INVALID_ARG;

    xSemaphoreTake(s_params_lock, portMAX_DELAY);
    float *slot = param_ptr(&s_params, param_id);
    if (slot == NULL) {
        xSemaphoreGive(s_params_lock);
        return ESP_ERR_INVALID_ARG;
    }
    *slot = value;
    s_source[param_id] = PARAM_SRC_RUNTIME;
    xSemaphoreGive(s_params_lock);

    ESP_LOGI(TAG, "param[%u] = %.4f (runtime)", (unsigned)param_id, (double)value);
    return ESP_OK;
}

esp_err_t motor_params_get_by_id(uint8_t param_id, float *out_value, uint8_t *out_source)
{
    if (!s_inited) return ESP_ERR_INVALID_STATE;
    if (param_id == 0 || param_id > PARAM_ID_MAX) return ESP_ERR_INVALID_ARG;
    if (out_value == NULL) return ESP_ERR_INVALID_ARG;

    xSemaphoreTake(s_params_lock, portMAX_DELAY);
    const float *slot = param_ptr(&s_params, param_id);
    if (slot == NULL) {
        xSemaphoreGive(s_params_lock);
        return ESP_ERR_INVALID_ARG;
    }
    *out_value = *slot;
    if (out_source) *out_source = s_source[param_id];
    xSemaphoreGive(s_params_lock);
    return ESP_OK;
}

uint8_t motor_params_get_source(uint8_t param_id)
{
    if (!s_inited) return PARAM_SRC_DEFAULT;
    if (param_id == 0 || param_id > PARAM_ID_MAX) return PARAM_SRC_DEFAULT;
    xSemaphoreTake(s_params_lock, portMAX_DELAY);
    uint8_t src = s_source[param_id];
    xSemaphoreGive(s_params_lock);
    return src;
}

esp_err_t motor_params_save_nvs(void)
{
    if (!s_inited) return ESP_ERR_INVALID_STATE;

    nvs_handle_t h;
    esp_err_t err = nvs_open(PARAMS_NVS_NAMESPACE, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_open(RW) failed: %s", esp_err_to_name(err));
        return err;
    }

    /* Snapshot under lock, then write outside the lock (nvs I/O is slow). */
    motor_params_t snap;
    xSemaphoreTake(s_params_lock, portMAX_DELAY);
    memcpy(&snap, &s_params, sizeof(snap));
    xSemaphoreGive(s_params_lock);

    int saved = 0;
    for (uint8_t id = 1; id <= PARAM_ID_MAX; id++) {
        const float *slot = param_ptr(&snap, id);
        if (slot == NULL) continue;
        err = save_one_to_nvs(h, id, *slot);
        if (err == ESP_OK) {
            saved++;
        } else {
            ESP_LOGW(TAG, "Failed to save param[%u]: %s",
                     (unsigned)id, esp_err_to_name(err));
        }
    }
    err = nvs_commit(h);
    nvs_close(h);

    if (err == ESP_OK) {
        /* Mark all successfully-saved params as NVS-sourced. */
        xSemaphoreTake(s_params_lock, portMAX_DELAY);
        for (int i = 1; i <= PARAM_ID_MAX; i++) s_source[i] = PARAM_SRC_NVS;
        xSemaphoreGive(s_params_lock);
        ESP_LOGI(TAG, "Saved %d motor params to NVS", saved);
    } else {
        ESP_LOGE(TAG, "nvs_commit failed: %s", esp_err_to_name(err));
    }
    return err;
}

esp_err_t motor_params_load_nvs(void)
{
    if (!s_inited) return ESP_ERR_INVALID_STATE;

    nvs_handle_t h;
    esp_err_t err = nvs_open(PARAMS_NVS_NAMESPACE, NVS_READONLY, &h);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "No motor params in NVS to load");
        return err;
    } else if (err != ESP_OK) {
        return err;
    }

    int loaded = 0;
    xSemaphoreTake(s_params_lock, portMAX_DELAY);
    for (uint8_t id = 1; id <= PARAM_ID_MAX; id++) {
        float value;
        if (load_one_from_nvs(h, id, &value)) {
            float *slot = param_ptr(&s_params, id);
            if (slot && param_value_sane(id, value)) {
                *slot = value;
                s_source[id] = PARAM_SRC_NVS;
                loaded++;
            }
        }
    }
    xSemaphoreGive(s_params_lock);
    nvs_close(h);

    ESP_LOGI(TAG, "Loaded %d motor params from NVS", loaded);
    return ESP_OK;
}
