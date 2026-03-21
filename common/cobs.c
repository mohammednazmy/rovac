/*
 * cobs.c — Consistent Overhead Byte Stuffing (COBS) implementation
 *
 * Reference: Cheshire & Baker, "Consistent Overhead Byte Stuffing", 1999
 *            IEEE/ACM Transactions on Networking, Vol. 7, No. 2
 */
#include "cobs.h"

size_t cobs_encode(const uint8_t *input, size_t input_len, uint8_t *output)
{
    size_t read_idx = 0;
    size_t write_idx = 1;  /* Skip the first code byte (filled later) */
    size_t code_idx = 0;   /* Position of the current code byte */
    uint8_t code = 1;      /* Distance to next zero (or end of block) */

    while (read_idx < input_len) {
        if (input[read_idx] == 0x00) {
            /* Finish the current block */
            output[code_idx] = code;
            code_idx = write_idx++;
            code = 1;
        } else {
            output[write_idx++] = input[read_idx];
            code++;
            if (code == 0xFF) {
                /* Block full (254 non-zero bytes) — emit and start new block */
                output[code_idx] = code;
                code_idx = write_idx++;
                code = 1;
            }
        }
        read_idx++;
    }

    /* Finish the last block */
    output[code_idx] = code;

    return write_idx;
}

size_t cobs_decode(const uint8_t *input, size_t input_len, uint8_t *output)
{
    size_t read_idx = 0;
    size_t write_idx = 0;

    while (read_idx < input_len) {
        uint8_t code = input[read_idx++];

        if (code == 0x00) {
            /* 0x00 should never appear in COBS-encoded data */
            return 0;
        }

        /* Copy (code - 1) literal bytes */
        for (uint8_t i = 1; i < code; i++) {
            if (read_idx >= input_len) {
                return 0;  /* Truncated frame */
            }
            output[write_idx++] = input[read_idx++];
        }

        /* If code < 0xFF, insert an implicit zero (unless we're at the end) */
        if (code < 0xFF && read_idx < input_len) {
            output[write_idx++] = 0x00;
        }
    }

    return write_idx;
}
