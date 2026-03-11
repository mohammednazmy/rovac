/*
 * encoder_reader.h — Hardware quadrature encoder reader (PCNT)
 *
 * Uses ESP32 PCNT (Pulse Counter) hardware peripheral for zero-CPU-overhead
 * full quadrature decoding of JGB37-520R60-12 motor encoders.
 *
 * Pin assignments match Maker ESP32 SPI header (left/right swapped
 * to match motor connector swap — same as Arduino firmware).
 */
#pragma once
#include <stdint.h>
#include "esp_err.h"

// Encoder pin assignments (SPI header on Maker ESP32)
// Left/right swapped to match motor swap
#define ENCODER_LEFT_A   19   // Left encoder channel A
#define ENCODER_LEFT_B   23   // Left encoder channel B
#define ENCODER_RIGHT_A   5   // Right encoder channel A
#define ENCODER_RIGHT_B  18   // Right encoder channel B

// JGB37-520R60-12 encoder specs
#define ENCODER_TICKS_PER_REV  2640  // 11 PPR x 4 (full quad) x 60:1 gear

esp_err_t encoder_reader_init(void);
void encoder_reader_get_counts(int32_t *left, int32_t *right);  // Absolute cumulative
void encoder_reader_get_and_reset_deltas(int32_t *left_delta, int32_t *right_delta);
void encoder_reader_reset(void);
