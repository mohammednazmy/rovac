/*
 * test_protocol.c — Quick verification of serial protocol + COBS
 *
 * Build: gcc -o test_protocol test_protocol.c cobs.c -I. && ./test_protocol
 */
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "serial_protocol.h"
#include "cobs.h"

static void print_hex(const char *label, const uint8_t *data, size_t len)
{
    printf("%s (%zu bytes): ", label, len);
    for (size_t i = 0; i < len; i++)
        printf("%02X ", data[i]);
    printf("\n");
}

static void test_cobs_roundtrip(void)
{
    printf("=== COBS Round-trip ===\n");

    /* Test 1: Simple data (no zeros) */
    {
        uint8_t input[] = {0x11, 0x22, 0x33};
        uint8_t encoded[8], decoded[8];
        size_t enc_len = cobs_encode(input, sizeof(input), encoded);
        size_t dec_len = cobs_decode(encoded, enc_len, decoded);
        assert(dec_len == sizeof(input));
        assert(memcmp(input, decoded, dec_len) == 0);
        printf("  [PASS] Simple data (no zeros)\n");
    }

    /* Test 2: Data with zeros */
    {
        uint8_t input[] = {0x11, 0x00, 0x00, 0x22};
        uint8_t encoded[8], decoded[8];
        size_t enc_len = cobs_encode(input, sizeof(input), encoded);
        /* Verify no 0x00 in encoded output */
        for (size_t i = 0; i < enc_len; i++)
            assert(encoded[i] != 0x00);
        size_t dec_len = cobs_decode(encoded, enc_len, decoded);
        assert(dec_len == sizeof(input));
        assert(memcmp(input, decoded, dec_len) == 0);
        printf("  [PASS] Data with embedded zeros\n");
    }

    /* Test 3: Empty data */
    {
        uint8_t encoded[4], decoded[4];
        size_t enc_len = cobs_encode(NULL, 0, encoded);
        size_t dec_len = cobs_decode(encoded, enc_len, decoded);
        assert(dec_len == 0);
        printf("  [PASS] Empty data\n");
    }

    /* Test 4: All zeros */
    {
        uint8_t input[] = {0x00, 0x00, 0x00};
        uint8_t encoded[8], decoded[8];
        size_t enc_len = cobs_encode(input, sizeof(input), encoded);
        for (size_t i = 0; i < enc_len; i++)
            assert(encoded[i] != 0x00);
        size_t dec_len = cobs_decode(encoded, enc_len, decoded);
        assert(dec_len == sizeof(input));
        assert(memcmp(input, decoded, dec_len) == 0);
        printf("  [PASS] All zeros\n");
    }

    /* Test 5: 254 non-zero bytes (COBS block boundary) */
    {
        uint8_t input[254], encoded[260], decoded[260];
        for (int i = 0; i < 254; i++) input[i] = (uint8_t)(i + 1);
        size_t enc_len = cobs_encode(input, 254, encoded);
        for (size_t i = 0; i < enc_len; i++)
            assert(encoded[i] != 0x00);
        size_t dec_len = cobs_decode(encoded, enc_len, decoded);
        assert(dec_len == 254);
        assert(memcmp(input, decoded, 254) == 0);
        printf("  [PASS] 254 non-zero bytes (block boundary)\n");
    }
}

static void test_crc16(void)
{
    printf("=== CRC-16/CCITT ===\n");

    /* Known test vector: "123456789" → 0x29B1 */
    uint8_t data[] = "123456789";
    uint16_t crc = serial_protocol_crc16(data, 9);
    assert(crc == 0x29B1);
    printf("  [PASS] Known vector '123456789' = 0x%04X\n", crc);

    /* Empty data → 0xFFFF (init value) */
    uint16_t crc_empty = serial_protocol_crc16(NULL, 0);
    assert(crc_empty == 0xFFFF);
    printf("  [PASS] Empty data = 0x%04X\n", crc_empty);
}

static void test_odom_frame(void)
{
    printf("=== Odom Frame Build + Parse ===\n");

    /* Build an odom payload */
    odom_payload_t odom = {
        .timestamp_us = 1234567890ULL,
        .x = 1.23f, .y = -0.45f, .yaw = 0.78f,
        .v_linear = 0.15f, .v_angular = -0.02f,
        .cov_x = 0.01f, .cov_yaw = 0.03f,
    };

    /* Build raw frame */
    uint8_t raw[64];
    size_t raw_len = serial_protocol_build_frame(raw, MSG_ODOM, &odom, sizeof(odom));
    print_hex("  Raw frame", raw, raw_len);

    /* COBS-encode */
    uint8_t encoded[80];
    size_t enc_len = cobs_encode(raw, raw_len, encoded);
    /* Verify no 0x00 in encoded */
    for (size_t i = 0; i < enc_len; i++)
        assert(encoded[i] != 0x00);
    print_hex("  COBS-encoded", encoded, enc_len);

    /* COBS-decode */
    uint8_t decoded[80];
    size_t dec_len = cobs_decode(encoded, enc_len, decoded);
    assert(dec_len == raw_len);
    assert(memcmp(raw, decoded, raw_len) == 0);

    /* Parse frame */
    uint8_t msg_type;
    const uint8_t *payload;
    size_t payload_len;
    int ok = serial_protocol_parse_frame(decoded, dec_len, &msg_type, &payload, &payload_len);
    assert(ok == 1);
    assert(msg_type == MSG_ODOM);
    assert(payload_len == sizeof(odom_payload_t));

    /* Verify payload content */
    const odom_payload_t *parsed = (const odom_payload_t *)payload;
    assert(parsed->timestamp_us == 1234567890ULL);
    assert(parsed->x == 1.23f);
    assert(parsed->v_linear == 0.15f);
    printf("  [PASS] Odom build → encode → decode → parse\n");
}

static void test_cmd_vel_frame(void)
{
    printf("=== CMD_VEL Frame ===\n");

    cmd_vel_payload_t cmd = { .linear_x = 0.15f, .angular_z = -0.5f };

    uint8_t raw[16];
    size_t raw_len = serial_protocol_build_frame(raw, MSG_CMD_VEL, &cmd, sizeof(cmd));

    uint8_t encoded[24];
    size_t enc_len = cobs_encode(raw, raw_len, encoded);

    uint8_t decoded[24];
    size_t dec_len = cobs_decode(encoded, enc_len, decoded);

    uint8_t msg_type;
    const uint8_t *payload;
    size_t payload_len;
    int ok = serial_protocol_parse_frame(decoded, dec_len, &msg_type, &payload, &payload_len);
    assert(ok == 1);
    assert(msg_type == MSG_CMD_VEL);
    assert(payload_len == sizeof(cmd_vel_payload_t));

    const cmd_vel_payload_t *parsed = (const cmd_vel_payload_t *)payload;
    assert(parsed->linear_x == 0.15f);
    assert(parsed->angular_z == -0.5f);
    printf("  [PASS] CMD_VEL build → encode → decode → parse\n");

    /* Print frame sizes for bandwidth estimation */
    printf("  Raw: %zu bytes, COBS-encoded: %zu bytes (+ 1 delimiter)\n", raw_len, enc_len);
}

static void test_estop_frame(void)
{
    printf("=== ESTOP Frame (empty payload) ===\n");

    uint8_t raw[8];
    size_t raw_len = serial_protocol_build_frame(raw, MSG_CMD_ESTOP, NULL, 0);
    assert(raw_len == 3);  /* 1 type + 0 payload + 2 CRC */

    uint8_t encoded[8];
    size_t enc_len = cobs_encode(raw, raw_len, encoded);

    uint8_t decoded[8];
    size_t dec_len = cobs_decode(encoded, enc_len, decoded);

    uint8_t msg_type;
    const uint8_t *payload;
    size_t payload_len;
    int ok = serial_protocol_parse_frame(decoded, dec_len, &msg_type, &payload, &payload_len);
    assert(ok == 1);
    assert(msg_type == MSG_CMD_ESTOP);
    assert(payload_len == 0);
    printf("  [PASS] ESTOP (empty payload)\n");
}

static void test_crc_corruption(void)
{
    printf("=== CRC Corruption Detection ===\n");

    cmd_vel_payload_t cmd = { .linear_x = 0.1f, .angular_z = 0.0f };
    uint8_t raw[16];
    size_t raw_len = serial_protocol_build_frame(raw, MSG_CMD_VEL, &cmd, sizeof(cmd));

    /* Corrupt one byte in the payload */
    raw[2] ^= 0x01;

    uint8_t msg_type;
    const uint8_t *payload;
    size_t payload_len;
    int ok = serial_protocol_parse_frame(raw, raw_len, &msg_type, &payload, &payload_len);
    assert(ok == 0);  /* CRC should fail */
    printf("  [PASS] Corrupted frame rejected by CRC\n");
}

static void print_frame_sizes(void)
{
    printf("\n=== Frame Size Summary ===\n");
    printf("  CMD_VEL:  payload=%zu, raw=%zu, COBS~%zu + delim\n",
           sizeof(cmd_vel_payload_t), sizeof(cmd_vel_payload_t) + 3, sizeof(cmd_vel_payload_t) + 5);
    printf("  ODOM:     payload=%zu, raw=%zu, COBS~%zu + delim\n",
           sizeof(odom_payload_t), sizeof(odom_payload_t) + 3, sizeof(odom_payload_t) + 5);
    printf("  IMU:      payload=%zu, raw=%zu, COBS~%zu + delim\n",
           sizeof(imu_payload_t), sizeof(imu_payload_t) + 3, sizeof(imu_payload_t) + 5);
    printf("  DIAG:     payload=%zu, raw=%zu, COBS~%zu + delim\n",
           sizeof(diag_payload_t), sizeof(diag_payload_t) + 3, sizeof(diag_payload_t) + 5);
    printf("  ESTOP:    payload=0, raw=3, COBS~4 + delim\n");
}

int main(void)
{
    printf("ROVAC Serial Protocol Test Suite\n");
    printf("================================\n\n");

    test_cobs_roundtrip();
    printf("\n");
    test_crc16();
    printf("\n");
    test_odom_frame();
    printf("\n");
    test_cmd_vel_frame();
    printf("\n");
    test_estop_frame();
    printf("\n");
    test_crc_corruption();

    print_frame_sizes();

    printf("\n================================\n");
    printf("All tests PASSED!\n");
    return 0;
}
