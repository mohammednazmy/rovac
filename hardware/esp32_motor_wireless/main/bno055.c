/*
 * bno055.c — BNO055 9-axis IMU driver (new I2C master API, interrupt-driven)
 *
 * Architecture:
 *   - GPIO25 INT pin configured for data-ready interrupt (GYR_DRDY)
 *   - ISR sends task notification to bno055_task
 *   - Task wakes on notification OR 20ms timeout (50Hz polling fallback)
 *   - Data stored in thread-safe struct, accessed via bno055_get_data()
 *
 * Uses ESP-IDF new I2C master driver (driver/i2c_master.h) which handles
 * BNO055 clock stretching via scl_wait_us parameter. The legacy driver
 * cannot handle the BNO055's I2C protocol violations on reads.
 */
#include "bno055.h"

#include <string.h>
#include <math.h>
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

static const char *TAG = "bno055";

/* ── BNO055 Register Map ───────────────────────────── */
/* Page 0 */
#define REG_CHIP_ID         0x00    /* 0xA0 */
#define REG_ACC_ID          0x01    /* 0xFB */
#define REG_MAG_ID          0x02    /* 0x32 */
#define REG_GYR_ID          0x03    /* 0x0F */
#define REG_SW_REV_LSB      0x04
#define REG_SW_REV_MSB      0x05
#define REG_PAGE_ID         0x07
#define REG_GYR_X_LSB       0x14
#define REG_EULER_H_LSB     0x1A
#define REG_QUA_W_LSB       0x20
#define REG_LIA_X_LSB       0x28
#define REG_CALIB_STAT      0x35
#define REG_SYS_STATUS      0x39
#define REG_UNIT_SEL        0x3B
#define REG_OPR_MODE        0x3D
#define REG_PWR_MODE        0x3E
#define REG_SYS_TRIGGER     0x40

/* Page 1 */
#define REG_INT_MSK         0x0F
#define REG_INT_EN          0x10

/* Operation modes */
#define OPR_MODE_CONFIG     0x00
#define OPR_MODE_NDOF       0x0C

/* INT bits */
#define INT_GYR_DRDY        (1 << 4)

/* Calibration profile registers (22 bytes, read/write in CONFIG mode only) */
#define REG_ACC_OFFSET_X_LSB  0x55   /* 6 bytes: accel offset x,y,z */
#define CAL_PROFILE_SIZE      22     /* 0x55-0x6A inclusive */

/* NVS key for calibration persistence */
#define NVS_NAMESPACE         "bno055"
#define NVS_KEY_CAL           "cal_data"

/* ── Module State ──────────────────────────────────── */
static i2c_master_dev_handle_t s_dev = NULL;
static SemaphoreHandle_t s_data_lock = NULL;    /* Protects s_data */
static TaskHandle_t s_task_handle = NULL;
static bno055_data_t s_data;
static bool s_cal_saved = false;  /* True after calibration saved to NVS this boot */

/* Forward declarations */
static void cal_auto_save(void);

/* ── I2C Helpers (new master driver — thread-safe) ─── */

static esp_err_t bno_write_reg(uint8_t reg, uint8_t val)
{
    uint8_t buf[2] = {reg, val};
    return i2c_master_transmit(s_dev, buf, 2, 500);
}

static esp_err_t bno_read_reg(uint8_t reg, uint8_t *data, size_t len)
{
    return i2c_master_transmit_receive(s_dev, &reg, 1, data, len, 500);
}

/* ── GPIO ISR (data-ready interrupt from BNO055 INT pin) ── */

static void IRAM_ATTR bno055_isr_handler(void *arg)
{
    BaseType_t higher_priority_woken = pdFALSE;
    vTaskNotifyGiveFromISR(s_task_handle, &higher_priority_woken);
    portYIELD_FROM_ISR(higher_priority_woken);
}

/* ── Read all sensor data in one shot ──────────────── */

static bool read_sensor_data(void)
{
    /* Read calibration status (1 byte) */
    uint8_t calib = 0;
    esp_err_t rc = bno_read_reg(REG_CALIB_STAT, &calib, 1);
    if (rc != ESP_OK) return false;

    /* Read quaternion (8 bytes: w,x,y,z — 16-bit LE each) */
    uint8_t quat_raw[8];
    rc = bno_read_reg(REG_QUA_W_LSB, quat_raw, 8);
    if (rc != ESP_OK) return false;

    /* Read gyroscope (6 bytes: x,y,z — 16-bit LE, 1 LSB = 1/16 deg/s) */
    uint8_t gyro_raw[6];
    rc = bno_read_reg(REG_GYR_X_LSB, gyro_raw, 6);
    if (rc != ESP_OK) return false;

    /* Read linear acceleration (6 bytes: x,y,z — 16-bit LE, 1 LSB = 1/100 m/s²) */
    uint8_t lia_raw[6];
    rc = bno_read_reg(REG_LIA_X_LSB, lia_raw, 6);
    if (rc != ESP_OK) return false;

    /* Parse and store — hold data lock */
    int64_t now_us = esp_timer_get_time();

    xSemaphoreTake(s_data_lock, portMAX_DELAY);

    /* Quaternion: 1 LSB = 1/16384 (unitless) */
    s_data.qw = (int16_t)(quat_raw[0] | (quat_raw[1] << 8)) / 16384.0f;
    s_data.qx = (int16_t)(quat_raw[2] | (quat_raw[3] << 8)) / 16384.0f;
    s_data.qy = (int16_t)(quat_raw[4] | (quat_raw[5] << 8)) / 16384.0f;
    s_data.qz = (int16_t)(quat_raw[6] | (quat_raw[7] << 8)) / 16384.0f;

    /* Gyroscope: 1 LSB = 1/16 deg/s → convert to rad/s */
    static const float DEG_TO_RAD = 3.14159265358979323846f / 180.0f;
    s_data.gyro_x = (int16_t)(gyro_raw[0] | (gyro_raw[1] << 8)) / 16.0f * DEG_TO_RAD;
    s_data.gyro_y = (int16_t)(gyro_raw[2] | (gyro_raw[3] << 8)) / 16.0f * DEG_TO_RAD;
    s_data.gyro_z = (int16_t)(gyro_raw[4] | (gyro_raw[5] << 8)) / 16.0f * DEG_TO_RAD;

    /* Linear acceleration: 1 LSB = 1/100 m/s² */
    s_data.accel_x = (int16_t)(lia_raw[0] | (lia_raw[1] << 8)) / 100.0f;
    s_data.accel_y = (int16_t)(lia_raw[2] | (lia_raw[3] << 8)) / 100.0f;
    s_data.accel_z = (int16_t)(lia_raw[4] | (lia_raw[5] << 8)) / 100.0f;

    /* Calibration status */
    s_data.cal_sys   = (calib >> 6) & 0x03;
    s_data.cal_gyro  = (calib >> 4) & 0x03;
    s_data.cal_accel = (calib >> 2) & 0x03;
    s_data.cal_mag   = calib & 0x03;

    s_data.valid = true;
    s_data.timestamp_us = now_us;
    s_data.read_count++;

    xSemaphoreGive(s_data_lock);
    return true;
}

/* ── BNO055 Task ───────────────────────────────────── */

static void bno055_task(void *arg)
{
    (void)arg;
    ESP_LOGI(TAG, "BNO055 task started on Core %d", xPortGetCoreID());

    uint32_t int_wakes = 0;
    uint32_t poll_wakes = 0;

    while (1) {
        /* Wait for interrupt notification OR 20ms timeout (50Hz fallback) */
        uint32_t notified = ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(20));

        if (notified > 0) {
            int_wakes++;
        } else {
            poll_wakes++;
        }

        /* Read all sensor data */
        if (!read_sensor_data()) {
            xSemaphoreTake(s_data_lock, portMAX_DELAY);
            s_data.error_count++;
            xSemaphoreGive(s_data_lock);
        }

        /* Auto-save calibration when all sensors first reach 3/3/3/3 */
        if (!s_cal_saved) {
            bno055_data_t snap;
            bno055_get_data(&snap);
            if (snap.valid &&
                snap.cal_sys == 3 && snap.cal_gyro == 3 &&
                snap.cal_accel == 3 && snap.cal_mag == 3) {
                cal_auto_save();
            }
        }

        /* Periodic stats (every 500 reads ≈ 10s at 50Hz) */
        if ((int_wakes + poll_wakes) % 500 == 0 && (int_wakes + poll_wakes) > 0) {
            bno055_data_t snap;
            bno055_get_data(&snap);
            ESP_LOGI(TAG, "IMU reads=%lu errs=%lu int=%lu poll=%lu cal=S%d/G%d/A%d/M%d%s",
                     (unsigned long)snap.read_count, (unsigned long)snap.error_count,
                     (unsigned long)int_wakes, (unsigned long)poll_wakes,
                     snap.cal_sys, snap.cal_gyro, snap.cal_accel, snap.cal_mag,
                     s_cal_saved ? " [NVS saved]" : "");
        }
    }
}

/* ── Calibration Persistence (NVS) ─────────────────── */

/**
 * Save 22-byte calibration profile from BNO055 to NVS.
 * Must be called while BNO055 is in CONFIG mode.
 */
static bool cal_save_to_nvs(void)
{
    uint8_t cal[CAL_PROFILE_SIZE];
    uint8_t reg = REG_ACC_OFFSET_X_LSB;
    esp_err_t rc = bno_read_reg(reg, cal, CAL_PROFILE_SIZE);
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read calibration registers: %s", esp_err_to_name(rc));
        return false;
    }

    nvs_handle_t nvs;
    rc = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvs);
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "NVS open failed: %s", esp_err_to_name(rc));
        return false;
    }

    rc = nvs_set_blob(nvs, NVS_KEY_CAL, cal, CAL_PROFILE_SIZE);
    if (rc == ESP_OK) rc = nvs_commit(nvs);
    nvs_close(nvs);

    if (rc == ESP_OK) {
        ESP_LOGI(TAG, "Calibration saved to NVS (22 bytes)");
        return true;
    }
    ESP_LOGE(TAG, "NVS write failed: %s", esp_err_to_name(rc));
    return false;
}

/**
 * Restore 22-byte calibration profile from NVS to BNO055.
 * Must be called while BNO055 is in CONFIG mode.
 * Returns true if calibration was restored successfully.
 */
static bool cal_restore_from_nvs(void)
{
    nvs_handle_t nvs;
    esp_err_t rc = nvs_open(NVS_NAMESPACE, NVS_READONLY, &nvs);
    if (rc != ESP_OK) return false;

    uint8_t cal[CAL_PROFILE_SIZE];
    size_t len = CAL_PROFILE_SIZE;
    rc = nvs_get_blob(nvs, NVS_KEY_CAL, cal, &len);
    nvs_close(nvs);

    if (rc != ESP_OK || len != CAL_PROFILE_SIZE) {
        ESP_LOGI(TAG, "No saved calibration in NVS");
        return false;
    }

    /* Write calibration data to BNO055 registers */
    for (int i = 0; i < CAL_PROFILE_SIZE; i++) {
        rc = bno_write_reg(REG_ACC_OFFSET_X_LSB + i, cal[i]);
        if (rc != ESP_OK) {
            ESP_LOGE(TAG, "Failed to write cal register 0x%02X: %s",
                     REG_ACC_OFFSET_X_LSB + i, esp_err_to_name(rc));
            return false;
        }
    }

    ESP_LOGI(TAG, "Calibration restored from NVS (22 bytes)");
    return true;
}

/**
 * Auto-save: switch to CONFIG mode, save calibration, switch back to NDOF.
 * Called from the task when all cal values reach 3 for the first time.
 * Pauses sensor fusion for ~60ms.
 */
static void cal_auto_save(void)
{
    ESP_LOGI(TAG, "All sensors calibrated (3/3/3/3) — saving to NVS...");

    /* Switch to CONFIG mode to read calibration registers */
    esp_err_t rc = bno_write_reg(REG_OPR_MODE, OPR_MODE_CONFIG);
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "Failed to enter CONFIG mode for cal save: %s", esp_err_to_name(rc));
        return;
    }
    vTaskDelay(pdMS_TO_TICKS(30));

    cal_save_to_nvs();

    /* Switch back to NDOF mode */
    rc = bno_write_reg(REG_OPR_MODE, OPR_MODE_NDOF);
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "CRITICAL: Failed to return to NDOF mode after cal save: %s", esp_err_to_name(rc));
        /* Retry once */
        vTaskDelay(pdMS_TO_TICKS(50));
        rc = bno_write_reg(REG_OPR_MODE, OPR_MODE_NDOF);
        if (rc != ESP_OK) {
            ESP_LOGE(TAG, "NDOF retry failed — IMU may be stuck in CONFIG mode");
        }
    }
    vTaskDelay(pdMS_TO_TICKS(30));

    s_cal_saved = true;
}

/* ── Initialization ────────────────────────────────── */

static bool bno055_chip_init(void)
{
    /* Verify chip ID */
    uint8_t chip_id = 0;
    esp_err_t rc = bno_read_reg(REG_CHIP_ID, &chip_id, 1);
    if (rc != ESP_OK || chip_id != 0xA0) {
        ESP_LOGE(TAG, "BNO055 not found (rc=%s, id=0x%02X)", esp_err_to_name(rc), chip_id);
        return false;
    }

    /* Read sub-IDs */
    uint8_t ids[3];
    bno_read_reg(REG_ACC_ID, ids, 3);
    uint8_t sw_rev[2];
    bno_read_reg(REG_SW_REV_LSB, sw_rev, 2);
    ESP_LOGI(TAG, "BNO055 detected: chip=0xA0 acc=0x%02X mag=0x%02X gyr=0x%02X sw=%d.%d",
             ids[0], ids[1], ids[2], sw_rev[1], sw_rev[0]);

    /* Ensure CONFIG mode */
    bno_write_reg(REG_OPR_MODE, OPR_MODE_CONFIG);
    vTaskDelay(pdMS_TO_TICKS(30));

    /* Normal power mode */
    bno_write_reg(REG_PWR_MODE, 0x00);

    /* Set units: deg/s for gyro (converted to rad/s in software), m/s² for accel */
    bno_write_reg(REG_UNIT_SEL, 0x00);

    /* Clear SYS_TRIGGER */
    bno_write_reg(REG_SYS_TRIGGER, 0x00);

    /* Restore calibration from NVS (if previously saved) */
    cal_restore_from_nvs();

    /* Configure interrupt: enable GYR_DRDY on INT pin (while in CONFIG mode) */
    bno_write_reg(REG_PAGE_ID, 0x01);
    bno_write_reg(REG_INT_MSK, INT_GYR_DRDY);
    bno_write_reg(REG_INT_EN, INT_GYR_DRDY);
    bno_write_reg(REG_PAGE_ID, 0x00);

    /* Switch to NDOF mode — full 9-axis sensor fusion */
    bno_write_reg(REG_OPR_MODE, OPR_MODE_NDOF);
    vTaskDelay(pdMS_TO_TICKS(30));

    ESP_LOGI(TAG, "BNO055 set to NDOF mode (9-axis fusion, INT on GPIO%d)", BNO055_INT_PIN);
    return true;
}

static void bno055_int_pin_init(void)
{
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << BNO055_INT_PIN),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_POSEDGE,
    };
    gpio_config(&io_conf);

    gpio_install_isr_service(0);
    gpio_isr_handler_add(BNO055_INT_PIN, bno055_isr_handler, NULL);

    ESP_LOGI(TAG, "INT pin configured: GPIO%d, rising edge", BNO055_INT_PIN);
}

esp_err_t bno055_init(i2c_master_bus_handle_t bus)
{
    if (bus == NULL) {
        ESP_LOGE(TAG, "I2C bus handle is NULL");
        return ESP_ERR_INVALID_ARG;
    }

    /* Add BNO055 device with clock-stretching tolerance */
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = BNO055_I2C_ADDR,
        .scl_speed_hz = 100000,     /* 100kHz — conservative for BNO055 */
        .scl_wait_us = 5000,        /* 5ms clock-stretch tolerance */
    };
    esp_err_t rc = i2c_master_bus_add_device(bus, &dev_cfg, &s_dev);
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add BNO055 device: %s", esp_err_to_name(rc));
        return rc;
    }

    /* Create data lock */
    s_data_lock = xSemaphoreCreateMutex();
    if (s_data_lock == NULL) {
        return ESP_ERR_NO_MEM;
    }

    /* Clear data */
    memset(&s_data, 0, sizeof(s_data));

    /* Wait for BNO055 power-on reset (650ms POR) */
    ESP_LOGI(TAG, "Waiting for BNO055 power-on reset...");
    vTaskDelay(pdMS_TO_TICKS(800));

    /* Initialize BNO055 chip */
    if (!bno055_chip_init()) {
        return ESP_ERR_NOT_FOUND;
    }

    /* Create task BEFORE enabling interrupt (task handle needed by ISR) */
    BaseType_t ret = xTaskCreatePinnedToCore(
        bno055_task, "bno055", 3072, NULL, 3, &s_task_handle, 0);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create BNO055 task");
        return ESP_FAIL;
    }

    /* Configure INT pin and ISR */
    bno055_int_pin_init();

    ESP_LOGI(TAG, "BNO055 initialized (addr=0x%02X, INT=GPIO%d, NDOF, scl_wait=5ms)",
             BNO055_I2C_ADDR, BNO055_INT_PIN);
    return ESP_OK;
}

/* ── Public Data Access ────────────────────────────── */

void bno055_get_data(bno055_data_t *out)
{
    xSemaphoreTake(s_data_lock, portMAX_DELAY);
    *out = s_data;
    xSemaphoreGive(s_data_lock);
}

float bno055_get_gyro_z(void)
{
    xSemaphoreTake(s_data_lock, portMAX_DELAY);
    float gz = s_data.valid ? s_data.gyro_z : 0.0f;
    xSemaphoreGive(s_data_lock);
    return gz;
}
