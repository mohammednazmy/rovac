/*
 * serial_protocol.h — ROVAC USB Serial Binary Protocol
 *
 * Shared between ESP32 firmware and Pi C++ ROS2 driver.
 * C-compatible (no C++ features in the core definitions).
 *
 * Frame format (COBS-encoded):
 *   [COBS-encoded block] [0x00 delimiter]
 *
 *   Decoded block = [msg_type:u8] [payload:N bytes] [crc16:u16 LE]
 *   CRC-16/CCITT computed over [msg_type, payload] (excludes CRC bytes)
 *
 * All multi-byte fields are little-endian (native on ESP32 and ARM).
 * All floats are IEEE 754 single-precision (32-bit).
 */
#ifndef SERIAL_PROTOCOL_H
#define SERIAL_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ── Protocol constants ─────────────────────────────────── */

#define SERIAL_PROTOCOL_VERSION     1
#define SERIAL_PROTOCOL_BAUD        460800
#define SERIAL_PROTOCOL_MAX_FRAME   256   /* Max COBS-encoded frame size */

/* ── Message type IDs ───────────────────────────────────── */

/* Pi → ESP32 commands (0x01–0x0F) */
#define MSG_CMD_VEL         0x01    /* Velocity command */
#define MSG_CMD_ESTOP       0x02    /* Emergency stop (brake) */
#define MSG_CMD_RESET_ODOM  0x03    /* Reset odometry to zero */

/* ESP32 → Pi data (0x10–0x1F) */
#define MSG_ODOM            0x10    /* Odometry (20 Hz) */
#define MSG_IMU             0x11    /* IMU data (20 Hz) */
#define MSG_DIAG            0x12    /* Diagnostics (1 Hz) */

/* ESP32 → Pi debug (0xF0+) */
#define MSG_LOG             0xF0    /* Log string (null-terminated) */

/* ── Payload structs (packed, little-endian) ────────────── */

typedef struct __attribute__((packed)) {
    float linear_x;     /* m/s, ROS convention (+X = forward) */
    float angular_z;    /* rad/s, ROS convention (+Z = CCW) */
} cmd_vel_payload_t;
/* Size: 8 bytes */

typedef struct __attribute__((packed)) {
    uint64_t timestamp_us;  /* ESP32 microseconds since boot */
    float x;                /* meters, ROS frame */
    float y;                /* meters, ROS frame */
    float yaw;              /* radians */
    float v_linear;         /* m/s */
    float v_angular;        /* rad/s */
    float cov_x;            /* position covariance (diagonal) */
    float cov_yaw;          /* yaw covariance (diagonal) */
} odom_payload_t;
/* Size: 36 bytes */

typedef struct __attribute__((packed)) {
    uint64_t timestamp_us;  /* ESP32 microseconds since boot */
    float qw, qx, qy, qz;  /* orientation quaternion (BNO055 NDOF) */
    float gx, gy, gz;       /* angular velocity rad/s (gyroscope) */
    float ax, ay, az;        /* linear acceleration m/s^2 (gravity removed) */
} imu_payload_t;
/* Size: 48 bytes */

typedef struct __attribute__((packed)) {
    int8_t   wifi_rssi;      /* dBm (0 if WiFi disabled) */
    uint32_t heap_free;      /* bytes */
    uint8_t  pid_active;     /* 1 = running, 0 = idle */
    float    v_left;         /* measured left wheel velocity m/s */
    float    v_right;        /* measured right wheel velocity m/s */
    uint32_t odom_count;     /* total odometry updates since boot */
    int8_t   imu_cal_sys;    /* BNO055 calibration 0-3, -1 if invalid */
    int8_t   imu_cal_gyro;
    int8_t   imu_cal_accel;
    int8_t   imu_cal_mag;
} diag_payload_t;
/* Size: 22 bytes */

/* ── CRC-16/CCITT ───────────────────────────────────────── */

/*
 * Compute CRC-16/CCITT over a byte buffer.
 * Polynomial: 0x1021, Init: 0xFFFF, No final XOR.
 */
static inline uint16_t serial_protocol_crc16(const uint8_t *data, size_t len)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int j = 0; j < 8; j++) {
            if (crc & 0x8000)
                crc = (crc << 1) ^ 0x1021;
            else
                crc = crc << 1;
        }
    }
    return crc;
}

/* ── Frame helpers ──────────────────────────────────────── */

/*
 * Build a raw (pre-COBS) frame: [msg_type] [payload...] [crc16_lo] [crc16_hi]
 * Returns total frame length (1 + payload_len + 2).
 * Caller must ensure `out` has at least (payload_len + 3) bytes.
 */
static inline size_t serial_protocol_build_frame(
    uint8_t *out, uint8_t msg_type,
    const void *payload, size_t payload_len)
{
    out[0] = msg_type;
    if (payload_len > 0) {
        const uint8_t *p = (const uint8_t *)payload;
        for (size_t i = 0; i < payload_len; i++)
            out[1 + i] = p[i];
    }
    size_t crc_len = 1 + payload_len;
    uint16_t crc = serial_protocol_crc16(out, crc_len);
    out[crc_len]     = (uint8_t)(crc & 0xFF);
    out[crc_len + 1] = (uint8_t)(crc >> 8);
    return crc_len + 2;
}

/*
 * Validate a decoded frame: check CRC, extract msg_type and payload pointer.
 * frame_len = total decoded length (msg_type + payload + 2 CRC bytes).
 * On success: *msg_type set, *payload points into frame, *payload_len set.
 * Returns 1 on success, 0 on CRC mismatch or frame too short.
 */
static inline int serial_protocol_parse_frame(
    const uint8_t *frame, size_t frame_len,
    uint8_t *msg_type, const uint8_t **payload, size_t *payload_len)
{
    if (frame_len < 3) return 0;  /* min: 1 type + 0 payload + 2 CRC */

    size_t data_len = frame_len - 2;  /* everything except CRC */
    uint16_t expected = serial_protocol_crc16(frame, data_len);
    uint16_t received = (uint16_t)frame[data_len] | ((uint16_t)frame[data_len + 1] << 8);

    if (expected != received) return 0;

    *msg_type = frame[0];
    *payload = frame + 1;
    *payload_len = data_len - 1;
    return 1;
}

#ifdef __cplusplus
}
#endif

#endif /* SERIAL_PROTOCOL_H */
