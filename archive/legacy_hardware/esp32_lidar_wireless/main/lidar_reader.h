/*
 * lidar_reader.h — XV11 LIDAR UART reader with revolution accumulation
 *
 * Reads XV11 binary packets from UART1, parses distance/intensity data,
 * accumulates full 360-degree revolutions, and provides complete scans
 * to the micro-ROS publisher via double-buffered scan data.
 *
 * Runs a dedicated FreeRTOS task on Core 1 for uninterrupted UART reading.
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>

/* XV11 packet format constants */
#define LIDAR_POINTS_PER_REV    360
#define LIDAR_PACKETS_PER_REV   90
#define LIDAR_POINTS_PER_PACKET 4
#define LIDAR_PACKET_SIZE       22
#define LIDAR_PACKET_START      0xFA

/* UART pin assignments (ESP32-S3 WROOM, Lonely Binary board) */
#define LIDAR_UART_NUM          2
#define LIDAR_UART_TX_PIN       16   /* ESP32 TX → LIDAR RX (Brown wire, GPIO16) */
#define LIDAR_UART_RX_PIN       17   /* ESP32 RX ← LIDAR TX (Orange wire, GPIO17) */
#define LIDAR_UART_BAUD         115200

/**
 * Complete 360-degree LIDAR scan data.
 * Filled by the reader task, consumed by the uros publisher.
 */
typedef struct {
    float ranges[LIDAR_POINTS_PER_REV];       /* meters (INFINITY = no return) */
    float intensities[LIDAR_POINTS_PER_REV];  /* raw intensity value */
    float rpm;                                 /* motor RPM at time of scan */
    uint32_t timestamp_ms;                     /* esp_timer_get_time()/1000 at revolution boundary */
    uint16_t valid_points;                     /* count of non-INFINITY ranges */
    bool ready;                                /* true = new unread scan available */
} lidar_scan_t;

/**
 * Initialize UART1 for XV11 data and internal state.
 * Does NOT start the reader task — call lidar_reader_start() for that.
 */
void lidar_reader_init(void);

/**
 * Start the UART reader task on Core 1.
 * Continuously reads XV11 packets and accumulates revolutions.
 */
void lidar_reader_start(void);

/**
 * Copy the latest complete scan into *scan.
 * Returns true if a new (unread) scan was available, false if no new data.
 * Clears the ready flag after successful copy.
 * Thread-safe (mutex-protected).
 */
bool lidar_reader_get_scan(lidar_scan_t *scan);

/** Get the most recent RPM reading (updated per-packet). */
float lidar_reader_get_rpm(void);

/** Total packets parsed since init. */
uint32_t lidar_reader_get_packet_count(void);

/** Total complete revolutions since init. */
uint32_t lidar_reader_get_rev_count(void);

/** Average scan rate in Hz (computed over recent revolutions). */
float lidar_reader_get_scan_rate(void);

/** Total raw bytes received on UART (for diagnostics). */
uint32_t lidar_reader_get_byte_count(void);

/** Total packets rejected by checksum validation. */
uint32_t lidar_reader_get_checksum_errors(void);

/** Suspend the reader task (for UART diagnostics). */
void lidar_reader_suspend(void);

/** Resume the reader task after diagnostics. */
void lidar_reader_resume(void);
