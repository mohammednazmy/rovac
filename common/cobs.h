/*
 * cobs.h — Consistent Overhead Byte Stuffing (COBS)
 *
 * COBS encodes a byte buffer so that 0x00 never appears in the output.
 * Frames are delimited by a 0x00 byte after the encoded block.
 *
 * Properties:
 *   - Output never contains 0x00 (unambiguous frame delimiter)
 *   - Overhead: at most 1 byte per 254 input bytes + 1
 *   - Deterministic: same input always produces same output
 *
 * Usage:
 *   Encode: cobs_encode(raw, raw_len, encoded)  → encoded_len
 *           Then append 0x00 delimiter and transmit.
 *   Decode: Receive bytes until 0x00, then:
 *           cobs_decode(encoded, encoded_len, decoded) → decoded_len
 */
#ifndef COBS_H
#define COBS_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * COBS-encode `input` (length `input_len`) into `output`.
 * `output` must have at least (input_len + input_len/254 + 1) bytes.
 * Returns the encoded length (excluding the 0x00 delimiter).
 */
size_t cobs_encode(const uint8_t *input, size_t input_len, uint8_t *output);

/*
 * COBS-decode `input` (length `input_len`) into `output`.
 * `input` must NOT include the trailing 0x00 delimiter.
 * `output` must have at least `input_len` bytes.
 * Returns the decoded length, or 0 on error.
 */
size_t cobs_decode(const uint8_t *input, size_t input_len, uint8_t *output);

#ifdef __cplusplus
}
#endif

#endif /* COBS_H */
