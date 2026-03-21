/*
 * serial_transport.c — USB Serial Binary Transport (COBS-framed)
 *
 * Replaces uros.c. Communicates with the Pi ROS2 driver over UART0
 * using the ROVAC serial binary protocol (see common/serial_protocol.h).
 *
 * Architecture:
 *   - Three esp_timer periodic callbacks handle TX (odom, imu, diag)
 *   - A FreeRTOS task handles RX (cmd_vel, estop, reset_odom)
 *   - A 10Hz esp_timer callback runs the motor watchdog
 *   - ESP_LOG output is captured and sent as MSG_LOG frames
 *
 * All TX/RX uses UART0 at 460800 baud (CH340 USB-UART on Maker ESP32).
 */
#include "serial_transport.h"
#include "serial_protocol.h"
#include "cobs.h"

#include "motor_control.h"
#include "motor_driver.h"
#include "odometry.h"
#include "bno055.h"
#include "led_status.h"

#include <string.h>
#include <stdio.h>
#include <stdarg.h>
#include <math.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "esp_system.h"

static const char *TAG = "serial_tx";

/* ── UART configuration ─────────────────────────────────── */

#define SERIAL_UART_NUM      UART_NUM_0
#define SERIAL_BAUD          SERIAL_PROTOCOL_BAUD
#define SERIAL_TX_BUF_SIZE   512
#define SERIAL_RX_BUF_SIZE   256

/* ── Connection tracking ────────────────────────────────── */

#define CONNECTION_TIMEOUT_US  5000000  /* 5 seconds */

static volatile int64_t s_last_rx_time_us = 0;
static volatile bool s_connected = false;

/* ── TX buffer (shared by timer callbacks — all run on same timer task) ── */

static uint8_t s_raw_buf[SERIAL_PROTOCOL_MAX_FRAME];
static uint8_t s_cobs_buf[SERIAL_PROTOCOL_MAX_FRAME];

/* ── Custom ESP_LOG handler ─────────────────────────────── */

static vprintf_like_t s_original_vprintf = NULL;

static int serial_log_vprintf(const char *fmt, va_list args)
{
    char log_buf[200];
    int len = vsnprintf(log_buf, sizeof(log_buf), fmt, args);
    if (len <= 0) return len;
    if (len >= (int)sizeof(log_buf)) len = sizeof(log_buf) - 1;

    /* Strip trailing newline for cleaner log frames */
    while (len > 0 && (log_buf[len - 1] == '\n' || log_buf[len - 1] == '\r'))
        log_buf[--len] = '\0';

    if (len == 0) return 0;

    /* Build and send MSG_LOG frame */
    uint8_t raw[208];
    size_t payload_len = (size_t)len + 1;  /* include null terminator */
    if (payload_len > 200) payload_len = 200;
    size_t raw_len = serial_protocol_build_frame(raw, MSG_LOG, log_buf, payload_len);

    uint8_t encoded[212];
    size_t enc_len = cobs_encode(raw, raw_len, encoded);
    encoded[enc_len] = 0x00;

    uart_write_bytes(SERIAL_UART_NUM, encoded, enc_len + 1);
    return len;
}

/* ── TX: Send a framed message ──────────────────────────── */

static void send_frame(uint8_t msg_type, const void *payload, size_t payload_len)
{
    size_t raw_len = serial_protocol_build_frame(s_raw_buf, msg_type, payload, payload_len);
    size_t enc_len = cobs_encode(s_raw_buf, raw_len, s_cobs_buf);
    s_cobs_buf[enc_len] = 0x00;  /* delimiter */
    uart_write_bytes(SERIAL_UART_NUM, s_cobs_buf, enc_len + 1);
}

/* ── TX: Odom timer callback (20 Hz) ───────────────────── */

static void odom_timer_cb(void *arg)
{
    (void)arg;

    odometry_state_t odom;
    odometry_get_state(&odom);

    /* Frame correction: firmware +X = rear, ROS +X = front.
     * Same corrections as uros.c lines 166-179. */
    odom_payload_t msg = {
        .timestamp_us = (uint64_t)esp_timer_get_time(),
        .x          = -odom.x,
        .y          =  odom.y,
        .yaw        = -odom.theta,
        .v_linear   = -odom.v_linear,
        .v_angular  = -odom.v_angular,
        .cov_x      =  odom.cov_x,
        .cov_yaw    =  odom.cov_yaw,
    };

    send_frame(MSG_ODOM, &msg, sizeof(msg));
}

/* ── TX: IMU timer callback (20 Hz, offset 25ms from odom) ── */

static void imu_timer_cb(void *arg)
{
    (void)arg;

    bno055_data_t imu;
    bno055_get_data(&imu);
    if (!imu.valid) return;

    imu_payload_t msg = {
        .timestamp_us = (uint64_t)esp_timer_get_time(),
        .qw = imu.qw,  .qx = imu.qx,  .qy = imu.qy,  .qz = imu.qz,
        .gx = imu.gyro_x,  .gy = imu.gyro_y,  .gz = imu.gyro_z,
        .ax = imu.accel_x, .ay = imu.accel_y, .az = imu.accel_z,
    };

    send_frame(MSG_IMU, &msg, sizeof(msg));
}

/* ── TX: Diagnostics timer callback (1 Hz) ──────────────── */

static void diag_timer_cb(void *arg)
{
    (void)arg;

    float v_left, v_right;
    motor_control_get_velocities(&v_left, &v_right);

    odometry_state_t odom;
    odometry_get_state(&odom);

    bno055_data_t imu;
    bno055_get_data(&imu);

    diag_payload_t msg = {
        .wifi_rssi   = 0,  /* WiFi disabled in serial mode */
        .heap_free   = (uint32_t)esp_get_free_heap_size(),
        .pid_active  = motor_control_is_active() ? 1 : 0,
        .v_left      = v_left,
        .v_right     = v_right,
        .odom_count  = odom.update_count,
        .imu_cal_sys   = imu.valid ? (int8_t)imu.cal_sys   : -1,
        .imu_cal_gyro  = imu.valid ? (int8_t)imu.cal_gyro  : -1,
        .imu_cal_accel = imu.valid ? (int8_t)imu.cal_accel : -1,
        .imu_cal_mag   = imu.valid ? (int8_t)imu.cal_mag   : -1,
    };

    send_frame(MSG_DIAG, &msg, sizeof(msg));

    /* Update LED based on connection state */
    int64_t now = esp_timer_get_time();
    if ((now - s_last_rx_time_us) > CONNECTION_TIMEOUT_US) {
        s_connected = false;
        led_status_set(LED_STATE_NO_AGENT);  /* Yellow blink = waiting for Pi */
    }
}

/* ── TX: Motor watchdog callback (10 Hz) ────────────────── */

static void watchdog_timer_cb(void *arg)
{
    (void)arg;
    motor_control_watchdog();
}

/* ── RX: Process a decoded frame ────────────────────────── */

static void process_frame(const uint8_t *frame, size_t frame_len)
{
    uint8_t msg_type;
    const uint8_t *payload;
    size_t payload_len;

    if (!serial_protocol_parse_frame(frame, frame_len, &msg_type, &payload, &payload_len)) {
        return;  /* CRC mismatch — discard silently */
    }

    /* Mark connection as active */
    s_last_rx_time_us = esp_timer_get_time();
    if (!s_connected) {
        s_connected = true;
        led_status_set(LED_STATE_CONNECTED);
        ESP_LOGI(TAG, "Pi driver connected");
    }

    switch (msg_type) {
    case MSG_CMD_VEL:
        if (payload_len == sizeof(cmd_vel_payload_t)) {
            const cmd_vel_payload_t *cmd = (const cmd_vel_payload_t *)payload;
            /* Frame correction: negate linear_x (same as uros.c line 410).
             * angular_z passes through unchanged (motor label swap inverts it). */
            motor_control_cmd_vel(-cmd->linear_x, cmd->angular_z);
        }
        break;

    case MSG_CMD_ESTOP:
        motor_control_stop();
        motor_driver_brake();
        ESP_LOGW(TAG, "ESTOP received — motors braked");
        break;

    case MSG_CMD_RESET_ODOM:
        odometry_reset();
        ESP_LOGI(TAG, "Odometry reset to zero");
        break;

    default:
        break;  /* Unknown message type — ignore */
    }
}

/* ── RX: UART read task ─────────────────────────────────── */

#define RX_TASK_STACK  4096
#define RX_TASK_PRIO   5
#define RX_BUF_SIZE    SERIAL_PROTOCOL_MAX_FRAME

static void rx_task(void *arg)
{
    (void)arg;
    uint8_t byte_buf[64];
    uint8_t frame_buf[RX_BUF_SIZE];
    size_t frame_pos = 0;
    uint8_t decoded[RX_BUF_SIZE];

    ESP_LOGI(TAG, "RX task started on core %d", xPortGetCoreID());

    while (1) {
        int len = uart_read_bytes(SERIAL_UART_NUM, byte_buf, sizeof(byte_buf),
                                  pdMS_TO_TICKS(50));
        if (len <= 0) continue;

        for (int i = 0; i < len; i++) {
            if (byte_buf[i] == 0x00) {
                /* Frame delimiter — decode accumulated bytes */
                if (frame_pos > 0) {
                    size_t dec_len = cobs_decode(frame_buf, frame_pos, decoded);
                    if (dec_len >= 3) {  /* min: 1 type + 0 payload + 2 CRC */
                        process_frame(decoded, dec_len);
                    }
                    frame_pos = 0;
                }
            } else {
                if (frame_pos < RX_BUF_SIZE) {
                    frame_buf[frame_pos++] = byte_buf[i];
                } else {
                    /* Overflow — discard and resync on next 0x00 */
                    frame_pos = 0;
                }
            }
        }
    }
}

/* ── Public API ──────────────────────────────────────────── */

esp_err_t serial_transport_init(void)
{
    ESP_LOGI(TAG, "Initializing serial transport (UART%d @ %d baud)...",
             SERIAL_UART_NUM, SERIAL_BAUD);

    /* Configure UART0 — takes over from the ESP console */
    uart_config_t uart_cfg = {
        .baud_rate  = SERIAL_BAUD,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_param_config(SERIAL_UART_NUM, &uart_cfg));

    /* Install UART driver (replaces VFS/console driver) */
    ESP_ERROR_CHECK(uart_driver_install(
        SERIAL_UART_NUM,
        SERIAL_RX_BUF_SIZE * 2,  /* RX ring buffer */
        SERIAL_TX_BUF_SIZE,      /* TX ring buffer */
        0, NULL, 0));

    /* Redirect ESP_LOG output to MSG_LOG binary frames */
    s_original_vprintf = esp_log_set_vprintf(serial_log_vprintf);

    /* Initialize connection tracking */
    s_last_rx_time_us = esp_timer_get_time();

    /* ── Start TX timers ──────────────────────────────── */

    /* Odom at 20Hz (50ms period) */
    const esp_timer_create_args_t odom_args = {
        .callback = odom_timer_cb,
        .name = "serial_odom",
    };
    esp_timer_handle_t odom_timer;
    ESP_ERROR_CHECK(esp_timer_create(&odom_args, &odom_timer));
    ESP_ERROR_CHECK(esp_timer_start_periodic(odom_timer, 50000));  /* 50ms */

    /* IMU at 20Hz (50ms period, offset 25ms from odom) */
    const esp_timer_create_args_t imu_args = {
        .callback = imu_timer_cb,
        .name = "serial_imu",
    };
    esp_timer_handle_t imu_timer;
    ESP_ERROR_CHECK(esp_timer_create(&imu_args, &imu_timer));
    /* Delay start by 25ms for bandwidth smoothing */
    vTaskDelay(pdMS_TO_TICKS(25));
    ESP_ERROR_CHECK(esp_timer_start_periodic(imu_timer, 50000));  /* 50ms */

    /* Diagnostics at 1Hz (1000ms period) */
    const esp_timer_create_args_t diag_args = {
        .callback = diag_timer_cb,
        .name = "serial_diag",
    };
    esp_timer_handle_t diag_timer;
    ESP_ERROR_CHECK(esp_timer_create(&diag_args, &diag_timer));
    ESP_ERROR_CHECK(esp_timer_start_periodic(diag_timer, 1000000));  /* 1s */

    /* Motor watchdog at 10Hz (100ms period) */
    const esp_timer_create_args_t wd_args = {
        .callback = watchdog_timer_cb,
        .name = "serial_wd",
    };
    esp_timer_handle_t wd_timer;
    ESP_ERROR_CHECK(esp_timer_create(&wd_args, &wd_timer));
    ESP_ERROR_CHECK(esp_timer_start_periodic(wd_timer, 100000));  /* 100ms */

    /* ── Start RX task ────────────────────────────────── */

    BaseType_t ret = xTaskCreatePinnedToCore(
        rx_task, "serial_rx", RX_TASK_STACK, NULL, RX_TASK_PRIO, NULL, 0);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create RX task");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Serial transport ready: ODOM+IMU@20Hz, DIAG@1Hz, WD@10Hz");
    return ESP_OK;
}

bool serial_transport_is_connected(void)
{
    return s_connected;
}
