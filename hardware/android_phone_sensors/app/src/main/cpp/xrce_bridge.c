/*
 * XRCE-DDS JNI Bridge for ROVAC Android Phone Sensors
 *
 * Connects to the micro-ROS Agent on the Pi as an XRCE-DDS client.
 * The phone becomes a third client alongside ESP32 motor and LIDAR.
 *
 * Publishes:
 *   /phone/imu                         sensor_msgs/Imu          best-effort
 *   /phone/gps/fix                     sensor_msgs/NavSatFix    best-effort
 *   /phone/camera/image_raw/compressed sensor_msgs/CompressedImage reliable (fragmented)
 */

#include <jni.h>
#include <android/log.h>
#include <uxr/client/client.h>
#include <uxr/client/util/ping.h>
#include <ucdr/microcdr.h>
#include <string.h>
#include <stdbool.h>

#define TAG "XrceBridge"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO,  TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN,  TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

/* Stream configuration — MTU=8192, images fit in single best-effort packet */
#define RELIABLE_HISTORY    4    /* power of 2, only for entity creation */
#define RELIABLE_BUF_SIZE   (UXR_CONFIG_UDP_TRANSPORT_MTU * RELIABLE_HISTORY)
#define BE_BUF_SIZE         UXR_CONFIG_UDP_TRANSPORT_MTU

/* ── Static state ─────────────────────────────────────────────── */

static uxrUDPTransport s_transport;
static uxrSession      s_session;
static uxrStreamId     s_reliable_out;
static uxrStreamId     s_besteffort_out;
static uxrObjectId     s_dw_imu;
static uxrObjectId     s_dw_gps;
static uxrObjectId     s_dw_image;
static bool            s_connected    = false;
static bool            s_entities_ok  = false;

static uint8_t s_out_reliable_buf[RELIABLE_BUF_SIZE];
static uint8_t s_in_reliable_buf[RELIABLE_BUF_SIZE];
static uint8_t s_out_be_buf[BE_BUF_SIZE];

/* Saved connection params for reconnect */
static char    s_agent_ip[64]   = "192.168.1.200";
static char    s_agent_port[16] = "8888";
static int     s_domain_id      = 42;

/* ── Flush callback for fragmented writes ─────────────────────── */

static bool flush_callback(uxrSession* session, void* args)
{
    (void)args;
    return uxr_run_session_time(session, 100);
}

/* ── CDR size helpers ─────────────────────────────────────────── */

static uint32_t imu_cdr_size(const char* fid)
{
    uint32_t slen = (uint32_t)strlen(fid) + 1;
    uint32_t sz = 8 + 4 + slen;               /* stamp + string */
    sz += (8 - (sz % 8)) % 8;                 /* align to 8 */
    sz += 38 * 8;                              /* 38 doubles */
    return sz;
}

static uint32_t navsatfix_cdr_size(const char* fid)
{
    uint32_t slen = (uint32_t)strlen(fid) + 1;
    uint32_t sz = 8 + 4 + slen;               /* stamp + string */
    sz += 4;                                   /* NavSatStatus: int8 + pad + uint16 */
    sz += (8 - (sz % 8)) % 8;                 /* align to 8 */
    sz += 12 * 8;                              /* 12 doubles */
    sz += 1;                                   /* cov_type uint8 */
    return sz;
}

static uint32_t compressed_image_cdr_size(const char* fid, const char* fmt, uint32_t data_len)
{
    uint32_t slen1 = (uint32_t)strlen(fid) + 1;
    uint32_t slen2 = (uint32_t)strlen(fmt) + 1;
    uint32_t sz = 8 + 4 + slen1;              /* stamp + frame_id string */
    /* align to 4 for next string length prefix (strings are 4-aligned) */
    sz += (4 - (sz % 4)) % 4;
    sz += 4 + slen2;                           /* format string */
    /* align to 4 for sequence length prefix */
    sz += (4 - (sz % 4)) % 4;
    sz += 4 + data_len;                        /* uint8 sequence: len + data */
    return sz;
}

/* ── Internal: create session and streams ─────────────────────── */

static bool create_session_internal(void)
{
    if (!uxr_init_udp_transport(&s_transport, UXR_IPv4, s_agent_ip, s_agent_port)) {
        LOGE("UDP transport failed → %s:%s", s_agent_ip, s_agent_port);
        return false;
    }
    LOGI("UDP transport → %s:%s", s_agent_ip, s_agent_port);

    /* Unique client key — different from ESP32 motor and LIDAR */
    uxr_init_session(&s_session, &s_transport.comm, 0xAD010001);

    if (!uxr_create_session(&s_session)) {
        LOGE("Session creation failed");
        uxr_close_udp_transport(&s_transport);
        return false;
    }

    /* Streams */
    s_reliable_out = uxr_create_output_reliable_stream(
        &s_session, s_out_reliable_buf, RELIABLE_BUF_SIZE, RELIABLE_HISTORY);
    uxr_create_input_reliable_stream(
        &s_session, s_in_reliable_buf, RELIABLE_BUF_SIZE, RELIABLE_HISTORY);
    s_besteffort_out = uxr_create_output_best_effort_stream(
        &s_session, s_out_be_buf, BE_BUF_SIZE);

    /* Time sync with Agent */
    uxr_sync_session(&s_session, 1000);

    s_connected = true;
    LOGI("Session created, domain %d", s_domain_id);
    return true;
}

/* ── Internal: create all XRCE entities ──────────────────────── */

static bool create_entities_internal(bool with_camera)
{
    if (!s_connected) return false;

    uxrQoS_t qos_be = {
        .durability  = UXR_DURABILITY_VOLATILE,
        .reliability = UXR_RELIABILITY_BEST_EFFORT,
        .history     = UXR_HISTORY_KEEP_LAST,
        .depth       = 1
    };
    uxrQoS_t qos_rel = {
        .durability  = UXR_DURABILITY_VOLATILE,
        .reliability = UXR_RELIABILITY_RELIABLE,
        .history     = UXR_HISTORY_KEEP_LAST,
        .depth       = 1
    };

    /* Participant — domain 42 */
    uxrObjectId participant = uxr_object_id(0x01, UXR_PARTICIPANT_ID);
    uint16_t r0 = uxr_buffer_create_participant_bin(
        &s_session, s_reliable_out, participant,
        (uint16_t)s_domain_id, "android_phone", UXR_REPLACE);

    /* Publisher (shared) */
    uxrObjectId pub = uxr_object_id(0x01, UXR_PUBLISHER_ID);
    uint16_t r1 = uxr_buffer_create_publisher_bin(
        &s_session, s_reliable_out, pub, participant, UXR_REPLACE);

    /* IMU */
    uxrObjectId t_imu = uxr_object_id(0x01, UXR_TOPIC_ID);
    uint16_t r2 = uxr_buffer_create_topic_bin(
        &s_session, s_reliable_out, t_imu, participant,
        "rt/phone/imu", "sensor_msgs::msg::dds_::Imu_", UXR_REPLACE);
    s_dw_imu = uxr_object_id(0x01, UXR_DATAWRITER_ID);
    uint16_t r3 = uxr_buffer_create_datawriter_bin(
        &s_session, s_reliable_out, s_dw_imu, pub, t_imu, qos_be, UXR_REPLACE);

    /* NavSatFix */
    uxrObjectId t_gps = uxr_object_id(0x02, UXR_TOPIC_ID);
    uint16_t r4 = uxr_buffer_create_topic_bin(
        &s_session, s_reliable_out, t_gps, participant,
        "rt/phone/gps/fix", "sensor_msgs::msg::dds_::NavSatFix_", UXR_REPLACE);
    s_dw_gps = uxr_object_id(0x02, UXR_DATAWRITER_ID);
    uint16_t r5 = uxr_buffer_create_datawriter_bin(
        &s_session, s_reliable_out, s_dw_gps, pub, t_gps, qos_be, UXR_REPLACE);

    int n_reqs = 6;
    uint8_t  status[8];
    uint16_t reqs[8] = { r0, r1, r2, r3, r4, r5, 0, 0 };

    /* CompressedImage (reliable for fragmentation) */
    if (with_camera) {
        uxrObjectId t_img = uxr_object_id(0x03, UXR_TOPIC_ID);
        reqs[6] = uxr_buffer_create_topic_bin(
            &s_session, s_reliable_out, t_img, participant,
            "rt/phone/camera/image_raw/compressed",
            "sensor_msgs::msg::dds_::CompressedImage_", UXR_REPLACE);
        s_dw_image = uxr_object_id(0x03, UXR_DATAWRITER_ID);
        reqs[7] = uxr_buffer_create_datawriter_bin(
            &s_session, s_reliable_out, s_dw_image, pub, t_img, qos_be, UXR_REPLACE);
        n_reqs = 8;
    }

    if (!uxr_run_session_until_all_status(&s_session, 3000, reqs, status, (size_t)n_reqs)) {
        LOGE("Entity creation failed: %d %d %d %d %d %d %d %d",
             status[0], status[1], status[2], status[3],
             status[4], status[5], status[6], status[7]);
        return false;
    }

    s_entities_ok = true;
    LOGI("Publishers created (camera=%s)", with_camera ? "yes" : "no");
    return true;
}

/* ── Internal: tear down ─────────────────────────────────────── */

static void disconnect_internal(void)
{
    if (s_connected) {
        uxr_delete_session(&s_session);
        uxr_close_udp_transport(&s_transport);
        s_connected = false;
        s_entities_ok = false;
        LOGI("Disconnected from Agent");
    }
}

/* ═══════════════════════════════════════════════════════════════
 *  JNI EXPORTS
 * ═══════════════════════════════════════════════════════════════ */

/* ── connect ──────────────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_com_rovac_phonesensors_XrceBridge_connect(
    JNIEnv* env, jobject thiz,
    jstring ip_j, jstring port_j, jint domain)
{
    const char* ip   = (*env)->GetStringUTFChars(env, ip_j, NULL);
    const char* port = (*env)->GetStringUTFChars(env, port_j, NULL);

    /* Save for reconnect */
    strncpy(s_agent_ip,   ip,   sizeof(s_agent_ip)   - 1);
    strncpy(s_agent_port, port, sizeof(s_agent_port) - 1);
    s_domain_id = (int)domain;

    (*env)->ReleaseStringUTFChars(env, ip_j, ip);
    (*env)->ReleaseStringUTFChars(env, port_j, port);

    return create_session_internal() ? JNI_TRUE : JNI_FALSE;
}

/* ── createPublishers ─────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_com_rovac_phonesensors_XrceBridge_createPublishers(
    JNIEnv* env, jobject thiz, jboolean withCamera)
{
    return create_entities_internal(withCamera) ? JNI_TRUE : JNI_FALSE;
}

/* ── publishImu ───────────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_com_rovac_phonesensors_XrceBridge_publishImu(
    JNIEnv* env, jobject thiz,
    jint sec, jint nsec, jstring fid_j,
    jdouble ox, jdouble oy, jdouble oz, jdouble ow,
    jdouble avx, jdouble avy, jdouble avz,
    jdouble lax, jdouble lay, jdouble laz)
{
    if (!s_entities_ok) return JNI_FALSE;

    const char* fid = (*env)->GetStringUTFChars(env, fid_j, NULL);
    uint32_t size = imu_cdr_size(fid);

    ucdrBuffer ub;
    uxr_prepare_output_stream(&s_session, s_besteffort_out, s_dw_imu, &ub, size);

    ucdr_serialize_int32_t(&ub, sec);
    ucdr_serialize_uint32_t(&ub, (uint32_t)nsec);
    ucdr_serialize_string(&ub, fid);

    ucdr_serialize_double(&ub, ox);
    ucdr_serialize_double(&ub, oy);
    ucdr_serialize_double(&ub, oz);
    ucdr_serialize_double(&ub, ow);
    double z9[9] = {0};
    ucdr_serialize_array_double(&ub, z9, 9);

    ucdr_serialize_double(&ub, avx);
    ucdr_serialize_double(&ub, avy);
    ucdr_serialize_double(&ub, avz);
    ucdr_serialize_array_double(&ub, z9, 9);

    ucdr_serialize_double(&ub, lax);
    ucdr_serialize_double(&ub, lay);
    ucdr_serialize_double(&ub, laz);
    ucdr_serialize_array_double(&ub, z9, 9);

    (*env)->ReleaseStringUTFChars(env, fid_j, fid);
    /* Non-blocking flush — just send, don't wait for anything */
    uxr_flash_output_streams(&s_session);
    return JNI_TRUE;
}

/* ── publishNavSatFix ─────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_com_rovac_phonesensors_XrceBridge_publishNavSatFix(
    JNIEnv* env, jobject thiz,
    jint sec, jint nsec, jstring fid_j,
    jint nav_status, jint service,
    jdouble lat, jdouble lon, jdouble alt,
    jint cov_type)
{
    if (!s_entities_ok) return JNI_FALSE;

    const char* fid = (*env)->GetStringUTFChars(env, fid_j, NULL);
    uint32_t size = navsatfix_cdr_size(fid);

    ucdrBuffer ub;
    uxr_prepare_output_stream(&s_session, s_besteffort_out, s_dw_gps, &ub, size);

    ucdr_serialize_int32_t(&ub, sec);
    ucdr_serialize_uint32_t(&ub, (uint32_t)nsec);
    ucdr_serialize_string(&ub, fid);

    ucdr_serialize_int8_t(&ub, (int8_t)nav_status);
    ucdr_serialize_uint16_t(&ub, (uint16_t)service);

    ucdr_serialize_double(&ub, lat);
    ucdr_serialize_double(&ub, lon);
    ucdr_serialize_double(&ub, alt);
    double z9[9] = {0};
    ucdr_serialize_array_double(&ub, z9, 9);
    ucdr_serialize_uint8_t(&ub, (uint8_t)cov_type);

    (*env)->ReleaseStringUTFChars(env, fid_j, fid);
    uxr_flash_output_streams(&s_session);
    return JNI_TRUE;
}

/* ── publishCompressedImage ───────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_com_rovac_phonesensors_XrceBridge_publishCompressedImage(
    JNIEnv* env, jobject thiz,
    jint sec, jint nsec, jstring fid_j,
    jstring fmt_j, jbyteArray data_j)
{
    if (!s_entities_ok) return JNI_FALSE;

    const char* fid = (*env)->GetStringUTFChars(env, fid_j, NULL);
    const char* fmt = (*env)->GetStringUTFChars(env, fmt_j, NULL);
    jsize data_len  = (*env)->GetArrayLength(env, data_j);
    jbyte* data     = (*env)->GetByteArrayElements(env, data_j, NULL);

    uint32_t size = compressed_image_cdr_size(fid, fmt, (uint32_t)data_len);

    /* Skip if image + header exceeds MTU (best-effort can't fragment) */
    if (size > UXR_CONFIG_UDP_TRANSPORT_MTU - 100) {
        LOGW("Image too large for MTU: %u bytes CDR, max ~%d", size,
             UXR_CONFIG_UDP_TRANSPORT_MTU - 100);
        (*env)->ReleaseByteArrayElements(env, data_j, data, JNI_ABORT);
        (*env)->ReleaseStringUTFChars(env, fmt_j, fmt);
        (*env)->ReleaseStringUTFChars(env, fid_j, fid);
        return JNI_FALSE;
    }

    ucdrBuffer ub;
    uxr_prepare_output_stream(&s_session, s_besteffort_out, s_dw_image, &ub, size);

    /* Header */
    ucdr_serialize_int32_t(&ub, sec);
    ucdr_serialize_uint32_t(&ub, (uint32_t)nsec);
    ucdr_serialize_string(&ub, fid);

    /* format string */
    ucdr_serialize_string(&ub, fmt);

    /* data sequence (uint32 length + bytes) */
    ucdr_serialize_sequence_uint8_t(&ub, (const uint8_t*)data, (uint32_t)data_len);

    (*env)->ReleaseByteArrayElements(env, data_j, data, JNI_ABORT);
    (*env)->ReleaseStringUTFChars(env, fmt_j, fmt);
    (*env)->ReleaseStringUTFChars(env, fid_j, fid);

    uxr_flash_output_streams(&s_session);
    return JNI_TRUE;
}

/* ── ping ─────────────────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_com_rovac_phonesensors_XrceBridge_ping(
    JNIEnv* env, jobject thiz, jint timeout_ms)
{
    if (!s_connected) return JNI_FALSE;
    return uxr_ping_agent_session(&s_session, (int)timeout_ms, 1)
           ? JNI_TRUE : JNI_FALSE;
}

/* ── reconnect ────────────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_com_rovac_phonesensors_XrceBridge_reconnect(
    JNIEnv* env, jobject thiz, jboolean withCamera)
{
    LOGW("Reconnecting to %s:%s ...", s_agent_ip, s_agent_port);
    disconnect_internal();

    if (!create_session_internal()) return JNI_FALSE;
    if (!create_entities_internal(withCamera)) {
        disconnect_internal();
        return JNI_FALSE;
    }
    LOGI("Reconnected successfully");
    return JNI_TRUE;
}

/* ── spin ─────────────────────────────────────────────────────── */

JNIEXPORT void JNICALL
Java_com_rovac_phonesensors_XrceBridge_spin(
    JNIEnv* env, jobject thiz, jint timeout_ms)
{
    if (s_connected) {
        uxr_run_session_time(&s_session, (int)timeout_ms);
    }
}

/* ── disconnect ───────────────────────────────────────────────── */

JNIEXPORT void JNICALL
Java_com_rovac_phonesensors_XrceBridge_disconnect(
    JNIEnv* env, jobject thiz)
{
    disconnect_internal();
}

/* ── isConnected ──────────────────────────────────────────────── */

JNIEXPORT jboolean JNICALL
Java_com_rovac_phonesensors_XrceBridge_isConnected(
    JNIEnv* env, jobject thiz)
{
    return s_connected ? JNI_TRUE : JNI_FALSE;
}
