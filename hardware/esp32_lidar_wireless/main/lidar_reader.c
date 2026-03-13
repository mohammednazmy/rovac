/*
 * lidar_reader.c — XV11 LIDAR UART reader with revolution accumulation
 *
 * Reads XV11 binary packets from UART1, parses distance/intensity data,
 * accumulates full 360-degree revolutions, and provides complete scans
 * to the micro-ROS publisher via double-buffered scan data.
 *
 * Runs a dedicated FreeRTOS task on Core 1 for uninterrupted UART reading.
 */

#include "lidar_reader.h"
#include "lidar_motor.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <math.h>
#include <string.h>

static const char *TAG = "lidar_reader";

/* Task configuration */
#define READER_TASK_STACK   8192
#define READER_TASK_PRIO    5
#define READER_TASK_CORE    1

/* UART read buffer */
#define UART_RX_BUF_SIZE    1024
#define UART_READ_TIMEOUT_MS 10

/* Stall detection: publish partial revolution after this many ms with no boundary */
#define STALL_TIMEOUT_US    (1000000)  /* 1.0 second in microseconds */

/* RPM regulation interval */
#define RPM_REGULATE_INTERVAL_MS  200  /* call lidar_motor_regulate() at ~5Hz */

/* Scan rate sliding window */
#define SCAN_RATE_WINDOW    10

/* ── Module state ──────────────────────────────────────────────────────── */

/* Double-buffered scan data */
static lidar_scan_t accumulating_scan;
static lidar_scan_t ready_scan;
static SemaphoreHandle_t scan_mutex;

/* Packet parsing state machine */
static uint8_t pkt_buf[LIDAR_PACKET_SIZE];
static uint8_t pkt_pos;      /* bytes accumulated in pkt_buf */
static bool    in_packet;     /* true = we saw 0xFA and are accumulating */

/* Revolution accumulation */
static int      prev_packet_idx;        /* previous packet index (0-89), -1 = none */
static uint16_t packets_seen_this_rev;  /* count of packets in current revolution */
static float    rpm_sum;                /* sum of raw RPM values for averaging */
static uint16_t rpm_count;              /* count of RPM samples this revolution */
static int64_t  rev_start_us;           /* timestamp when current revolution started */

/* Statistics */
static volatile uint32_t total_packets;
static volatile uint32_t total_revs;
static volatile float    latest_rpm;
static volatile uint32_t total_bytes;
static volatile uint32_t checksum_errors;

/* Scan rate tracking (circular buffer of revolution timestamps) */
static int64_t rev_timestamps[SCAN_RATE_WINDOW];
static uint8_t rev_ts_head;
static uint8_t rev_ts_count;

/* Reader task handle */
static TaskHandle_t reader_task_handle;

/* ── Internal helpers ──────────────────────────────────────────────────── */

/**
 * Reset the accumulating scan buffer for a new revolution.
 */
static void reset_accumulation(void)
{
    for (int i = 0; i < LIDAR_POINTS_PER_REV; i++) {
        accumulating_scan.ranges[i] = INFINITY;
        accumulating_scan.intensities[i] = 0.0f;
    }
    accumulating_scan.rpm = 0.0f;
    accumulating_scan.timestamp_ms = 0;
    accumulating_scan.valid_points = 0;
    accumulating_scan.ready = false;

    packets_seen_this_rev = 0;
    rpm_sum = 0.0f;
    rpm_count = 0;
    rev_start_us = esp_timer_get_time();
}

/**
 * Publish the current accumulation as a complete (or partial) scan.
 * Copies to ready_scan under mutex protection.
 */
static void publish_revolution(void)
{
    if (packets_seen_this_rev < 10) {
        return;  /* too few packets for a useful scan */
    }

    /* Compute average RPM for this revolution */
    float avg_rpm = 0.0f;
    if (rpm_count > 0) {
        float avg_raw = rpm_sum / (float)rpm_count;
        avg_rpm = avg_raw / 64.0f;
    }

    accumulating_scan.rpm = avg_rpm;
    accumulating_scan.timestamp_ms = (uint32_t)(esp_timer_get_time() / 1000);
    accumulating_scan.ready = true;

    /* Copy to ready buffer under mutex */
    if (xSemaphoreTake(scan_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
        memcpy(&ready_scan, &accumulating_scan, sizeof(lidar_scan_t));
        xSemaphoreGive(scan_mutex);
    } else {
        ESP_LOGW(TAG, "Failed to acquire mutex for scan publish");
    }

    /* Update statistics */
    total_revs++;

    /* Record timestamp for scan rate calculation */
    int64_t now = esp_timer_get_time();
    rev_timestamps[rev_ts_head] = now;
    rev_ts_head = (rev_ts_head + 1) % SCAN_RATE_WINDOW;
    if (rev_ts_count < SCAN_RATE_WINDOW) {
        rev_ts_count++;
    }

    /* Log periodically */
    if (total_revs <= 10 || total_revs % 10 == 0) {
        ESP_LOGI(TAG, "Rev #%lu: %u/%d pts, %u/%d pkts, RPM=%.0f",
                 (unsigned long)total_revs,
                 accumulating_scan.valid_points, LIDAR_POINTS_PER_REV,
                 packets_seen_this_rev, LIDAR_PACKETS_PER_REV,
                 avg_rpm);
    }
}

/**
 * Validate XV11 packet checksum.
 * Shift-and-add bytes 0-19 as 10 little-endian 16-bit words,
 * fold to 15 bits, compare against checksum at bytes 20-21.
 */
static bool validate_checksum(const uint8_t *pkt)
{
    uint32_t chk32 = 0;
    for (int i = 0; i < 20; i += 2) {
        chk32 = (chk32 << 1) + (pkt[i] | ((uint16_t)pkt[i + 1] << 8));
    }
    uint32_t check = ((chk32 & 0x7FFF) + (chk32 >> 15)) & 0x7FFF;
    uint16_t expected = pkt[20] | ((uint16_t)pkt[21] << 8);
    return (uint16_t)check == expected;
}

/**
 * Process a complete 22-byte XV11 packet.
 */
static void process_packet(const uint8_t *pkt)
{
    /* Validate start byte */
    if (pkt[0] != LIDAR_PACKET_START) {
        return;
    }

    /* Extract packet index (0xA0-0xF9 → 0-89) */
    uint8_t index_byte = pkt[1];
    if (index_byte < 0xA0 || index_byte > 0xF9) {
        return;
    }
    int pkt_idx = index_byte - 0xA0;

    /* Revolution boundary detection:
     * When prev index was high (>=70) and current is low (<=10),
     * and we've seen enough packets, this is a new revolution. */
    if (prev_packet_idx >= 70 && pkt_idx <= 10 && packets_seen_this_rev >= 10) {
        publish_revolution();
        reset_accumulation();
    }

    prev_packet_idx = pkt_idx;
    packets_seen_this_rev++;
    total_packets++;

    /* Extract RPM from bytes 2-3 (little-endian raw value) */
    uint16_t rpm_raw = pkt[2] | ((uint16_t)pkt[3] << 8);
    rpm_sum += (float)rpm_raw;
    rpm_count++;

    /* Update latest RPM for external queries and motor control */
    float rpm = (float)rpm_raw / 64.0f;
    latest_rpm = rpm;
    lidar_motor_update_rpm(rpm);

    /* Extract 4 data points */
    for (int j = 0; j < LIDAR_POINTS_PER_PACKET; j++) {
        int offset = 4 + 4 * j;
        uint8_t byte0 = pkt[offset];
        uint8_t byte1 = pkt[offset + 1];
        uint8_t byte2 = pkt[offset + 2];
        uint8_t byte3 = pkt[offset + 3];

        int point_idx = pkt_idx * LIDAR_POINTS_PER_PACKET + j;
        if (point_idx >= LIDAR_POINTS_PER_REV) {
            continue;
        }

        /* XV11 invalid flag: bit 7 of byte1 */
        if (byte1 & 0x80) {
            /* No valid reading — leave as INFINITY (already set by reset) */
            continue;
        }

        /* Distance: byte0 + lower 6 bits of byte1, in mm */
        uint16_t distance_mm = byte0 | ((uint16_t)(byte1 & 0x3F) << 8);
        float distance_m = (float)distance_mm / 1000.0f;

        accumulating_scan.ranges[point_idx] = distance_m;
        accumulating_scan.valid_points++;

        /* Intensity: bytes 2-3 of data point (little-endian) */
        uint16_t intensity = byte2 | ((uint16_t)byte3 << 8);
        accumulating_scan.intensities[point_idx] = (float)intensity;
    }
}

/**
 * FreeRTOS task: continuously reads UART1 bytes and parses XV11 packets.
 */
static void lidar_reader_task(void *arg)
{
    (void)arg;
    uint8_t uart_buf[256];
    uint32_t last_regulate_ms = 0;

    ESP_LOGI(TAG, "Reader task started on core %d", xPortGetCoreID());

    while (1) {
        /* Read available bytes from UART1 with short timeout */
        int len = uart_read_bytes(LIDAR_UART_NUM, uart_buf, sizeof(uart_buf),
                                  pdMS_TO_TICKS(UART_READ_TIMEOUT_MS));

        if (len > 0) {
            total_bytes += len;
            /* Process each byte through the packet state machine */
            for (int i = 0; i < len; i++) {
                uint8_t b = uart_buf[i];

                if (!in_packet) {
                    /* Looking for start byte 0xFA */
                    if (b == LIDAR_PACKET_START) {
                        in_packet = true;
                        pkt_pos = 0;
                        pkt_buf[pkt_pos++] = b;
                    }
                } else {
                    pkt_buf[pkt_pos++] = b;

                    /* Validate index byte at position 1 */
                    if (pkt_pos == 2) {
                        if (b < 0xA0 || b > 0xF9) {
                            /* Invalid index — abort this packet */
                            in_packet = false;
                            pkt_pos = 0;

                            /* Check if this byte itself is a start byte */
                            if (b == LIDAR_PACKET_START) {
                                in_packet = true;
                                pkt_pos = 0;
                                pkt_buf[pkt_pos++] = b;
                            }
                            continue;
                        }
                    }

                    /* Complete packet received */
                    if (pkt_pos >= LIDAR_PACKET_SIZE) {
                        if (validate_checksum(pkt_buf)) {
                            process_packet(pkt_buf);
                        } else {
                            checksum_errors++;
                        }
                        in_packet = false;
                        pkt_pos = 0;
                    }
                }
            }
        }

        /* Periodically run LIDAR motor RPM regulation (~5Hz) */
        {
            uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000);
            if (now_ms - last_regulate_ms >= RPM_REGULATE_INTERVAL_MS) {
                last_regulate_ms = now_ms;
                lidar_motor_regulate();
            }
        }

        /* Stall detection: if we have partial revolution data and no new
         * boundary for > 1 second, publish what we have */
        if (packets_seen_this_rev > 0) {
            int64_t elapsed_us = esp_timer_get_time() - rev_start_us;
            if (elapsed_us > STALL_TIMEOUT_US) {
                ESP_LOGW(TAG, "Stall detected: publishing partial revolution "
                         "(%u packets)", packets_seen_this_rev);
                publish_revolution();
                reset_accumulation();
            }
        }

        /* Yield to idle task — prevents Task WDT when UART RX is
         * floating/noisy and uart_read_bytes returns immediately. */
        vTaskDelay(1);
    }
}

/* ── Public API ────────────────────────────────────────────────────────── */

void lidar_reader_init(void)
{
    /* Create mutex for double-buffer access */
    scan_mutex = xSemaphoreCreateMutex();
    configASSERT(scan_mutex);

    /* Initialize state */
    in_packet = false;
    pkt_pos = 0;
    prev_packet_idx = -1;
    packets_seen_this_rev = 0;
    rpm_sum = 0.0f;
    rpm_count = 0;
    total_packets = 0;
    total_revs = 0;
    latest_rpm = 0.0f;
    total_bytes = 0;
    checksum_errors = 0;
    rev_ts_head = 0;
    rev_ts_count = 0;

    /* Initialize scan buffers */
    reset_accumulation();
    memset(&ready_scan, 0, sizeof(lidar_scan_t));
    ready_scan.ready = false;

    /* Configure UART1 for XV11 data: 115200 baud, 8N1, no flow control */
    uart_config_t uart_cfg = {
        .baud_rate  = LIDAR_UART_BAUD,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_param_config(LIDAR_UART_NUM, &uart_cfg));

    /* Explicitly set UART2 pins: RX=GPIO16, TX=GPIO17.
     * Must pass actual pin numbers — UART_PIN_NO_CHANGE leaves pins
     * in default GPIO mode (function 0), not UART2 mode (function 4). */
    ESP_ERROR_CHECK(uart_set_pin(LIDAR_UART_NUM,
                                 LIDAR_UART_TX_PIN,    /* TX = GPIO17 */
                                 LIDAR_UART_RX_PIN,    /* RX = GPIO16 */
                                 UART_PIN_NO_CHANGE,   /* RTS */
                                 UART_PIN_NO_CHANGE)); /* CTS */

    /* Install UART driver: RX buffer only, no TX buffer, no event queue */
    ESP_ERROR_CHECK(uart_driver_install(LIDAR_UART_NUM,
                                        UART_RX_BUF_SIZE,  /* rx_buffer */
                                        0,                  /* tx_buffer */
                                        0,                  /* queue_size */
                                        NULL,               /* queue handle */
                                        0));                /* intr_alloc_flags */

    ESP_LOGI(TAG, "UART%d initialized: %d baud, RX=GPIO%d, TX=GPIO%d",
             LIDAR_UART_NUM, LIDAR_UART_BAUD,
             LIDAR_UART_RX_PIN, LIDAR_UART_TX_PIN);
}

void lidar_reader_start(void)
{
    BaseType_t ret = xTaskCreatePinnedToCore(
        lidar_reader_task,
        "lidar_reader",
        READER_TASK_STACK,
        NULL,
        READER_TASK_PRIO,
        &reader_task_handle,
        READER_TASK_CORE
    );

    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create reader task");
    } else {
        ESP_LOGI(TAG, "Reader task started (core %d, prio %d, stack %d)",
                 READER_TASK_CORE, READER_TASK_PRIO, READER_TASK_STACK);
    }
}

bool lidar_reader_get_scan(lidar_scan_t *scan)
{
    if (scan == NULL) {
        return false;
    }

    bool got_scan = false;

    if (xSemaphoreTake(scan_mutex, pdMS_TO_TICKS(5)) == pdTRUE) {
        if (ready_scan.ready) {
            memcpy(scan, &ready_scan, sizeof(lidar_scan_t));
            ready_scan.ready = false;
            got_scan = true;
        }
        xSemaphoreGive(scan_mutex);
    }

    return got_scan;
}

float lidar_reader_get_rpm(void)
{
    return latest_rpm;
}

uint32_t lidar_reader_get_packet_count(void)
{
    return total_packets;
}

uint32_t lidar_reader_get_rev_count(void)
{
    return total_revs;
}

uint32_t lidar_reader_get_byte_count(void)
{
    return total_bytes;
}

void lidar_reader_suspend(void)
{
    if (reader_task_handle) {
        vTaskSuspend(reader_task_handle);
        vTaskDelay(pdMS_TO_TICKS(50));  /* let UART read finish */
    }
}

void lidar_reader_resume(void)
{
    if (reader_task_handle) {
        vTaskResume(reader_task_handle);
    }
}

float lidar_reader_get_scan_rate(void)
{
    if (rev_ts_count < 2) {
        return 0.0f;
    }

    /* Find oldest and newest timestamps in the circular buffer */
    uint8_t oldest_idx;
    if (rev_ts_count < SCAN_RATE_WINDOW) {
        oldest_idx = 0;
    } else {
        oldest_idx = rev_ts_head;  /* head points to next write = oldest entry */
    }
    uint8_t newest_idx = (rev_ts_head + SCAN_RATE_WINDOW - 1) % SCAN_RATE_WINDOW;

    int64_t dt_us = rev_timestamps[newest_idx] - rev_timestamps[oldest_idx];
    if (dt_us <= 0) {
        return 0.0f;
    }

    /* (count - 1) intervals span the window */
    float hz = (float)(rev_ts_count - 1) * 1000000.0f / (float)dt_us;
    return hz;
}

uint32_t lidar_reader_get_checksum_errors(void)
{
    return checksum_errors;
}
