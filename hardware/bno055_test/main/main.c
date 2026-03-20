/**
 * BNO055 I2C Test — New ESP-IDF I2C Master Driver
 *
 * Uses driver/i2c_master.h (ESP-IDF 5.2+) which has proper
 * clock-stretching support via scl_wait_us parameter.
 * The legacy driver's hardware I2C peripheral can't handle
 * the BNO055's protocol-violating clock stretching on reads.
 */
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/i2c_master.h"
#include "esp_log.h"

#define I2C_SDA_PIN     21
#define I2C_SCL_PIN     22
#define BNO055_ADDR     0x28

/* BNO055 registers */
#define REG_CHIP_ID     0x00
#define REG_ACC_ID      0x01
#define REG_MAG_ID      0x02
#define REG_GYR_ID      0x03
#define REG_SW_REV_LSB  0x04
#define REG_SW_REV_MSB  0x05
#define REG_CALIB_STAT  0x35
#define REG_OPR_MODE    0x3D
#define REG_PWR_MODE    0x3E
#define REG_SYS_TRIGGER 0x40
#define REG_EULER_H_LSB 0x1A
#define REG_QUA_W_LSB   0x20
#define REG_LIA_X_LSB   0x28
#define REG_GYR_X_LSB   0x14

static const char *TAG = "BNO055";
static i2c_master_dev_handle_t s_dev = NULL;

/* ── I2C helpers using new driver ──────────────────── */

static esp_err_t bno_write_reg(uint8_t reg, uint8_t val)
{
    uint8_t buf[2] = {reg, val};
    return i2c_master_transmit(s_dev, buf, 2, 500);
}

static esp_err_t bno_read_reg(uint8_t reg, uint8_t *data, size_t len)
{
    return i2c_master_transmit_receive(s_dev, &reg, 1, data, len, 500);
}

/* ── I2C Bus Scan ──────────────────────────────────── */

static void i2c_scan(i2c_master_bus_handle_t bus)
{
    printf("\n=== I2C Bus Scan ===\n");
    int found = 0;
    for (uint8_t addr = 0x08; addr < 0x78; addr++) {
        esp_err_t rc = i2c_master_probe(bus, addr, 200);
        if (rc == ESP_OK) {
            printf("  FOUND device at 0x%02X", addr);
            if (addr == 0x28) printf(" (BNO055, ADR=LOW)");
            if (addr == 0x29) printf(" (BNO055, ADR=HIGH)");
            if (addr == 0x3C) printf(" (SSD1306 OLED)");
            printf("\n");
            found++;
        }
    }
    printf("  %d device(s) found\n", found);
}

/* ── Main ──────────────────────────────────────────── */

void app_main(void)
{
    printf("\n");
    printf("=============================================\n");
    printf("  BNO055 Test — New I2C Master Driver\n");
    printf("  SDA=GPIO%d  SCL=GPIO%d\n", I2C_SDA_PIN, I2C_SCL_PIN);
    printf("=============================================\n");

    /* Create I2C master bus */
    i2c_master_bus_config_t bus_cfg = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .i2c_port = I2C_NUM_0,
        .scl_io_num = I2C_SCL_PIN,
        .sda_io_num = I2C_SDA_PIN,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    i2c_master_bus_handle_t bus = NULL;
    esp_err_t rc = i2c_new_master_bus(&bus_cfg, &bus);
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create I2C bus: %s", esp_err_to_name(rc));
        return;
    }
    ESP_LOGI(TAG, "I2C bus created (new master driver)");

    /* Wait for BNO055 POR */
    printf("\nWaiting 1.5s for BNO055 power-on reset...\n");
    vTaskDelay(pdMS_TO_TICKS(1500));

    /* Scan bus */
    i2c_scan(bus);

    /* Add BNO055 device with generous clock-stretching tolerance */
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = BNO055_ADDR,
        .scl_speed_hz = 100000,
        .scl_wait_us = 5000,  /* 5ms clock-stretch tolerance (BNO055 needs this!) */
    };
    rc = i2c_master_bus_add_device(bus, &dev_cfg, &s_dev);
    if (rc != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add BNO055 device: %s", esp_err_to_name(rc));
        return;
    }
    ESP_LOGI(TAG, "BNO055 device added (addr=0x%02X, 100kHz, scl_wait=5ms)", BNO055_ADDR);

    /* Read chip ID */
    printf("\n=== Reading BNO055 Chip ID ===\n");
    uint8_t chip_id = 0;
    rc = bno_read_reg(REG_CHIP_ID, &chip_id, 1);
    printf("  Chip ID: rc=%s data=0x%02X %s\n",
           esp_err_to_name(rc), chip_id,
           (rc == ESP_OK && chip_id == 0xA0) ? "*** BNO055 DETECTED! ***" :
           (rc == ESP_OK) ? "(unexpected ID)" : "(FAILED)");

    if (rc != ESP_OK || chip_id != 0xA0) {
        printf("\n  BNO055 read failed. Trying address 0x29...\n");
        i2c_master_bus_rm_device(s_dev);
        dev_cfg.device_address = 0x29;
        i2c_master_bus_add_device(bus, &dev_cfg, &s_dev);
        rc = bno_read_reg(REG_CHIP_ID, &chip_id, 1);
        printf("  0x29 Chip ID: rc=%s data=0x%02X %s\n",
               esp_err_to_name(rc), chip_id,
               (rc == ESP_OK && chip_id == 0xA0) ? "*** BNO055 at 0x29! ***" : "(FAILED)");

        if (rc != ESP_OK || chip_id != 0xA0) {
            printf("\n  BNO055 not responding on either address.\n");
            printf("  Halting.\n");
            while (1) vTaskDelay(pdMS_TO_TICKS(10000));
        }
    }

    /* Read sub-IDs */
    uint8_t ids[3];
    bno_read_reg(REG_ACC_ID, ids, 3);
    uint8_t sw[2];
    bno_read_reg(REG_SW_REV_LSB, sw, 2);
    printf("\n=== BNO055 Identified ===\n");
    printf("  Chip=0xA0  Acc=0x%02X  Mag=0x%02X  Gyr=0x%02X  SW=%d.%d\n",
           ids[0], ids[1], ids[2], sw[1], sw[0]);

    /* Set NDOF mode */
    bno_write_reg(REG_OPR_MODE, 0x00);  /* CONFIG */
    vTaskDelay(pdMS_TO_TICKS(30));
    bno_write_reg(REG_PWR_MODE, 0x00);  /* Normal */
    bno_write_reg(REG_SYS_TRIGGER, 0x00);
    bno_write_reg(REG_OPR_MODE, 0x0C);  /* NDOF */
    vTaskDelay(pdMS_TO_TICKS(30));
    printf("  Mode: NDOF (9-axis fusion)\n\n");

    /* Read loop */
    printf("=== Streaming sensor data (5Hz) ===\n");
    printf("Rotate sensor to calibrate. Cal: 0=none, 3=full\n\n");

    while (1) {
        uint8_t calib = 0;
        bno_read_reg(REG_CALIB_STAT, &calib, 1);

        uint8_t euler[6];
        bno_read_reg(REG_EULER_H_LSB, euler, 6);
        float heading = (int16_t)(euler[0] | (euler[1] << 8)) / 16.0f;
        float roll    = (int16_t)(euler[2] | (euler[3] << 8)) / 16.0f;
        float pitch   = (int16_t)(euler[4] | (euler[5] << 8)) / 16.0f;

        uint8_t quat[8];
        bno_read_reg(REG_QUA_W_LSB, quat, 8);
        float qw = (int16_t)(quat[0] | (quat[1] << 8)) / 16384.0f;
        float qx = (int16_t)(quat[2] | (quat[3] << 8)) / 16384.0f;
        float qy = (int16_t)(quat[4] | (quat[5] << 8)) / 16384.0f;
        float qz = (int16_t)(quat[6] | (quat[7] << 8)) / 16384.0f;

        printf("H=%6.1f R=%6.1f P=%6.1f  Q=(%5.3f,%5.3f,%5.3f,%5.3f)  Cal:S%d G%d A%d M%d\n",
               heading, roll, pitch, qw, qx, qy, qz,
               (calib >> 6) & 3, (calib >> 4) & 3,
               (calib >> 2) & 3, calib & 3);

        vTaskDelay(pdMS_TO_TICKS(200));
    }
}
