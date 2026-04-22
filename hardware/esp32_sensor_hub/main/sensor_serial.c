/*
 * sensor_serial.c — USB Serial Binary Transport for Sensor Hub
 *
 * Communicates with the Pi ROS2 driver over UART0 using the ROVAC serial
 * binary protocol (COBS-framed, CRC-16 validated).
 *
 * Architecture:
 *   - A FreeRTOS task reads all sensors sequentially (~10Hz loop)
 *   - Two esp_timer callbacks handle TX (sensor data, diagnostics)
 *   - A FreeRTOS task handles RX (connection tracking, future commands)
 *   - ESP_LOG output is captured and sent as MSG_LOG frames
 *
 * All TX/RX uses UART0 at 460800 baud (CP2102 USB-UART on DevKitV1).
 */
#include "sensor_serial.h"
#include "serial_protocol.h"
#include "cobs.h"
#include "ultrasonic.h"
#include "cliff_sensor.h"

#include <string.h>
#include <stdio.h>
#include <stdarg.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "esp_system.h"

static const char *TAG = "sensor_serial";

/* ── UART configuration ─────────────────────────────────── */

#define SERIAL_UART_NUM      UART_NUM_0
#define SERIAL_BAUD          SERIAL_PROTOCOL_BAUD
#define SERIAL_TX_BUF_SIZE   512
#define SERIAL_RX_BUF_SIZE   256

/* ── Status LED (built-in on GPIO2) ─────────────────────── */

#define LED_PIN  GPIO_NUM_2

/* ── Connection tracking ────────────────────────────────── */

#define CONNECTION_TIMEOUT_US  5000000  /* 5 seconds */

static volatile int64_t s_last_rx_time_us = 0;
static volatile bool s_connected = false;

/* ── Shared sensor state (written by sensor task, read by TX timer) ── */

static ultrasonic_readings_t s_us_readings;
static cliff_readings_t s_cliff_readings;
static uint32_t s_read_count = 0;
static portMUX_TYPE s_sensor_mux = portMUX_INITIALIZER_UNLOCKED;

/* ── TX buffers (shared by timer callbacks — all run on same timer task) ── */

static uint8_t s_raw_buf[SERIAL_PROTOCOL_MAX_FRAME];
static uint8_t s_cobs_buf[SERIAL_PROTOCOL_MAX_FRAME];

/* ── Custom ESP_LOG handler ─────────────────────────────── */

static int serial_log_vprintf(const char *fmt, va_list args)
{
    char log_buf[200];
    int len = vsnprintf(log_buf, sizeof(log_buf), fmt, args);
    if (len <= 0) return len;
    if (len >= (int)sizeof(log_buf)) len = sizeof(log_buf) - 1;

    /* Strip trailing newline */
    while (len > 0 && (log_buf[len - 1] == '\n' || log_buf[len - 1] == '\r'))
        log_buf[--len] = '\0';

    if (len == 0) return 0;

    /* Build and send MSG_LOG frame */
    uint8_t raw[208];
    size_t payload_len = (size_t)len + 1;
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
    s_cobs_buf[enc_len] = 0x00;
    uart_write_bytes(SERIAL_UART_NUM, s_cobs_buf, enc_len + 1);
}

/* ── TX: Sensor data timer callback (10 Hz) ─────────────── */

static void sensor_data_timer_cb(void *arg)
{
    (void)arg;

    ultrasonic_readings_t us;
    cliff_readings_t cliff;

    taskENTER_CRITICAL(&s_sensor_mux);
    us = s_us_readings;
    cliff = s_cliff_readings;
    taskEXIT_CRITICAL(&s_sensor_mux);

    sensor_data_payload_t msg = {
        .timestamp_us  = (uint64_t)esp_timer_get_time(),
        .us_front_m    = us.distance_m[US_FRONT],
        .us_rear_m     = us.distance_m[US_REAR],
        .us_left_m     = us.distance_m[US_LEFT],
        .us_right_m    = us.distance_m[US_RIGHT],
        .cliff_front_m = cliff.distance_m[CLIFF_FRONT],
        .cliff_rear_m  = cliff.distance_m[CLIFF_REAR],
        .cliff_detected = cliff.cliff_detected ? 1 : 0,
    };

    send_frame(MSG_SENSOR_DATA, &msg, sizeof(msg));
}

/* ── TX: Diagnostics timer callback (1 Hz) ──────────────── */

static void diag_timer_cb(void *arg)
{
    (void)arg;

    ultrasonic_readings_t us;
    cliff_readings_t cliff;
    uint32_t count;

    taskENTER_CRITICAL(&s_sensor_mux);
    us = s_us_readings;
    cliff = s_cliff_readings;
    count = s_read_count;
    taskEXIT_CRITICAL(&s_sensor_mux);

    sensor_diag_payload_t msg = {
        .heap_free  = (uint32_t)esp_get_free_heap_size(),
        .read_count = count,
        .us_ok      = us.ok_mask,
        .cliff_ok   = cliff.ok_mask,
    };

    send_frame(MSG_SENSOR_DIAG, &msg, sizeof(msg));

    /* Update LED based on connection state */
    int64_t now = esp_timer_get_time();
    if ((now - s_last_rx_time_us) > CONNECTION_TIMEOUT_US) {
        s_connected = false;
    }
}

/* ── Sensor reading task ────────────────────────────────── */

#define SENSOR_TASK_STACK  4096
#define SENSOR_TASK_PRIO   5

static void sensor_read_task(void *arg)
{
    (void)arg;
    ESP_LOGI(TAG, "Sensor read task started on core %d", xPortGetCoreID());

    while (1) {
        ultrasonic_readings_t us;
        cliff_readings_t cliff;

        /* Read cliff sensors first (fast, safety-critical) */
        cliff_sensor_read_all(&cliff);

        /* Read all 4 ultrasonics sequentially (~100ms) */
        ultrasonic_read_all(&us);

        /* Read cliff again after ultrasonics for freshness */
        cliff_readings_t cliff_fresh;
        cliff_sensor_read_all(&cliff_fresh);

        /* Use the freshest cliff reading */
        taskENTER_CRITICAL(&s_sensor_mux);
        s_us_readings = us;
        s_cliff_readings = cliff_fresh;
        s_read_count++;
        taskEXIT_CRITICAL(&s_sensor_mux);

        /* Brief yield — the ultrasonic reads already took ~100ms,
         * so this just ensures other tasks get a chance. */
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

/* ── RX: Process a decoded frame ────────────────────────── */

static void process_frame(const uint8_t *frame, size_t frame_len)
{
    uint8_t msg_type;
    const uint8_t *payload;
    size_t payload_len;

    if (!serial_protocol_parse_frame(frame, frame_len, &msg_type, &payload, &payload_len)) {
        return;  /* CRC mismatch — discard */
    }

    /* Mark connection as active */
    s_last_rx_time_us = esp_timer_get_time();
    if (!s_connected) {
        s_connected = true;
        gpio_set_level(LED_PIN, 1);  /* LED on = connected */
        ESP_LOGI(TAG, "Pi driver connected");
    }

    /* Future: handle configuration commands from Pi here */
    (void)msg_type;
    (void)payload;
    (void)payload_len;
}

/* ── RX: UART read task ─────────────────────────────────── */

#define RX_TASK_STACK  4096
#define RX_TASK_PRIO   4

static void rx_task(void *arg)
{
    (void)arg;
    uint8_t byte_buf[64];
    uint8_t frame_buf[SERIAL_PROTOCOL_MAX_FRAME];
    size_t frame_pos = 0;
    uint8_t decoded[SERIAL_PROTOCOL_MAX_FRAME];

    ESP_LOGI(TAG, "RX task started on core %d", xPortGetCoreID());

    while (1) {
        int len = uart_read_bytes(SERIAL_UART_NUM, byte_buf, sizeof(byte_buf),
                                  pdMS_TO_TICKS(50));
        if (len <= 0) continue;

        for (int i = 0; i < len; i++) {
            if (byte_buf[i] == 0x00) {
                if (frame_pos > 0) {
                    size_t dec_len = cobs_decode(frame_buf, frame_pos, decoded);
                    if (dec_len >= 3) {
                        process_frame(decoded, dec_len);
                    }
                    frame_pos = 0;
                }
            } else {
                if (frame_pos < SERIAL_PROTOCOL_MAX_FRAME) {
                    frame_buf[frame_pos++] = byte_buf[i];
                } else {
                    frame_pos = 0;
                }
            }
        }
    }
}

/* ── LED blink task ─────────────────────────────────────── */

static void led_task(void *arg)
{
    (void)arg;
    while (1) {
        if (!s_connected) {
            /* Blink: waiting for Pi */
            gpio_set_level(LED_PIN, 1);
            vTaskDelay(pdMS_TO_TICKS(100));
            gpio_set_level(LED_PIN, 0);
            vTaskDelay(pdMS_TO_TICKS(900));
        } else {
            /* Solid: connected */
            gpio_set_level(LED_PIN, 1);
            vTaskDelay(pdMS_TO_TICKS(500));
        }
    }
}

/* ── Public API ──────────────────────────────────────────── */

esp_err_t sensor_serial_init(void)
{
    ESP_LOGI(TAG, "Initializing serial transport (UART%d @ %d baud)...",
             SERIAL_UART_NUM, SERIAL_BAUD);

    /* Configure status LED */
    gpio_config_t led_cfg = {
        .pin_bit_mask = (1ULL << LED_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&led_cfg));
    gpio_set_level(LED_PIN, 0);

    /* Configure UART0 */
    uart_config_t uart_cfg = {
        .baud_rate  = SERIAL_BAUD,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_param_config(SERIAL_UART_NUM, &uart_cfg));

    ESP_ERROR_CHECK(uart_driver_install(
        SERIAL_UART_NUM,
        SERIAL_RX_BUF_SIZE * 2,
        SERIAL_TX_BUF_SIZE,
        0, NULL, 0));

    /* Redirect ESP_LOG to binary MSG_LOG frames */
    esp_log_set_vprintf(serial_log_vprintf);

    s_last_rx_time_us = esp_timer_get_time();

    /* ── Start TX timers ──────────────────────────────── */

    /* Sensor data at 10Hz (100ms period) */
    const esp_timer_create_args_t data_args = {
        .callback = sensor_data_timer_cb,
        .name = "sensor_data",
    };
    esp_timer_handle_t data_timer;
    ESP_ERROR_CHECK(esp_timer_create(&data_args, &data_timer));
    ESP_ERROR_CHECK(esp_timer_start_periodic(data_timer, 100000));  /* 100ms */

    /* Diagnostics at 1Hz (1000ms period) */
    const esp_timer_create_args_t diag_args = {
        .callback = diag_timer_cb,
        .name = "sensor_diag",
    };
    esp_timer_handle_t diag_timer;
    ESP_ERROR_CHECK(esp_timer_create(&diag_args, &diag_timer));
    ESP_ERROR_CHECK(esp_timer_start_periodic(diag_timer, 1000000));  /* 1s */

    /* ── Start tasks ──────────────────────────────────── */

    /* Sensor reading task on Core 1 */
    xTaskCreatePinnedToCore(sensor_read_task, "sensor_read",
                            SENSOR_TASK_STACK, NULL, SENSOR_TASK_PRIO, NULL, 1);

    /* RX task on Core 0 */
    xTaskCreatePinnedToCore(rx_task, "serial_rx",
                            RX_TASK_STACK, NULL, RX_TASK_PRIO, NULL, 0);

    /* LED task on Core 0 */
    xTaskCreatePinnedToCore(led_task, "led",
                            2048, NULL, 1, NULL, 0);

    ESP_LOGI(TAG, "Serial transport ready: SENSOR_DATA@10Hz, DIAG@1Hz");
    return ESP_OK;
}

bool sensor_serial_is_connected(void)
{
    return s_connected;
}
