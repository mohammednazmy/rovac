/*
 * sensor_driver_node.cpp — ROVAC Sensor Hub ROS2 Driver
 *
 * Bridges ESP32 sensor hub USB serial binary protocol (COBS-framed) to ROS2.
 *
 * Published topics:
 *   /sensors/ultrasonic/front  (sensor_msgs/Range)  10 Hz
 *   /sensors/ultrasonic/rear   (sensor_msgs/Range)  10 Hz
 *   /sensors/ultrasonic/left   (sensor_msgs/Range)  10 Hz
 *   /sensors/ultrasonic/right  (sensor_msgs/Range)  10 Hz
 *   /sensors/cliff/front       (sensor_msgs/Range)  10 Hz
 *   /sensors/cliff/rear        (sensor_msgs/Range)  10 Hz
 *   /sensors/cliff/detected    (std_msgs/Bool)      10 Hz
 *   /diagnostics               (DiagnosticArray)     1 Hz
 */
#include "rovac_sensor_driver/sensor_driver_node.hpp"
#include "cobs.h"

#include <cstring>
#include <cmath>

namespace rovac {

SensorDriverNode::SensorDriverNode()
    : Node("sensor_driver_node")
{
    // Declare parameters
    serial_port_ = declare_parameter("serial_port", "/dev/esp32_sensor");
    baud_rate_ = declare_parameter("baud_rate", 460800);
    serial_rx_timeout_s_ = declare_parameter("serial_rx_timeout", 5);

    // Publishers — all reliable QoS
    auto reliable_qos = rclcpp::QoS(10).reliable();

    us_front_pub_ = create_publisher<sensor_msgs::msg::Range>(
        "sensors/ultrasonic/front", reliable_qos);
    us_rear_pub_ = create_publisher<sensor_msgs::msg::Range>(
        "sensors/ultrasonic/rear", reliable_qos);
    us_left_pub_ = create_publisher<sensor_msgs::msg::Range>(
        "sensors/ultrasonic/left", reliable_qos);
    us_right_pub_ = create_publisher<sensor_msgs::msg::Range>(
        "sensors/ultrasonic/right", reliable_qos);

    cliff_front_pub_ = create_publisher<sensor_msgs::msg::Range>(
        "sensors/cliff/front", reliable_qos);
    cliff_rear_pub_ = create_publisher<sensor_msgs::msg::Range>(
        "sensors/cliff/rear", reliable_qos);
    cliff_detected_pub_ = create_publisher<std_msgs::msg::Bool>(
        "sensors/cliff/detected", reliable_qos);

    diag_pub_ = create_publisher<diagnostic_msgs::msg::DiagnosticArray>(
        "diagnostics", reliable_qos);

    // Reconnect timer (fires every 2s)
    reconnect_timer_ = create_wall_timer(
        std::chrono::seconds(2),
        std::bind(&SensorDriverNode::reconnect_callback, this));

    // Initial connection attempt
    try_connect();

    // Start serial read thread
    serial_thread_ = std::thread(&SensorDriverNode::serial_read_loop, this);

    RCLCPP_INFO(get_logger(), "Sensor driver node started (port=%s, baud=%d)",
                serial_port_.c_str(), baud_rate_);
}

SensorDriverNode::~SensorDriverNode()
{
    running_ = false;
    if (serial_thread_.joinable())
        serial_thread_.join();
    serial_.close();
}

// ── Connection management ──────────────────────────────

void SensorDriverNode::try_connect()
{
    if (serial_.is_open()) return;

    if (serial_.open(serial_port_, baud_rate_)) {
        auto now_ns = std::chrono::steady_clock::now().time_since_epoch().count();
        last_rx_time_ns_.store(now_ns, std::memory_order_release);
        RCLCPP_INFO(get_logger(), "Serial port opened: %s @ %d baud",
                    serial_port_.c_str(), baud_rate_);
    }
}

void SensorDriverNode::reconnect_callback()
{
    if (!serial_.is_open()) {
        try_connect();
        if (serial_.is_open()) {
            reconnect_count_++;
            RCLCPP_INFO(get_logger(), "Reconnected to %s (reconnect #%u)",
                        serial_port_.c_str(), reconnect_count_.load());
        }
        return;
    }

    // Serial health monitor: close stale connections
    auto now_ns = std::chrono::steady_clock::now().time_since_epoch().count();
    auto last_ns = last_rx_time_ns_.load(std::memory_order_acquire);
    auto elapsed_ns = now_ns - last_ns;
    if (elapsed_ns > static_cast<int64_t>(serial_rx_timeout_s_) * 1'000'000'000LL) {
        RCLCPP_WARN(get_logger(),
            "No data from sensor ESP32 for %d seconds — closing for reconnect",
            serial_rx_timeout_s_);
        serial_.close();
        connected_ = false;
    }
}

// ── Serial RX ──────────────────────────────────────────

void SensorDriverNode::serial_read_loop()
{
    uint8_t byte_buf[64];
    uint8_t frame_buf[SERIAL_PROTOCOL_MAX_FRAME];
    size_t frame_pos = 0;
    uint8_t decoded[SERIAL_PROTOCOL_MAX_FRAME];

    while (running_) {
        if (!serial_.is_open()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
            continue;
        }

        ssize_t n = serial_.read(byte_buf, sizeof(byte_buf), 100);
        if (n < 0) {
            RCLCPP_ERROR(get_logger(), "Serial read error — closing port");
            serial_.close();
            connected_ = false;
            frame_pos = 0;
            continue;
        }
        if (n == 0) continue;

        for (ssize_t i = 0; i < n; i++) {
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

void SensorDriverNode::process_frame(const uint8_t* data, size_t len)
{
    uint8_t msg_type;
    const uint8_t* payload;
    size_t payload_len;

    if (!serial_protocol_parse_frame(data, len, &msg_type, &payload, &payload_len))
        return;

    // Mark connection alive
    auto now_ns = std::chrono::steady_clock::now().time_since_epoch().count();
    last_rx_time_ns_.store(now_ns, std::memory_order_release);
    if (!connected_) {
        connected_ = true;
        RCLCPP_INFO(get_logger(), "Sensor ESP32 connected (receiving data)");
    }

    switch (msg_type) {
    case MSG_SENSOR_DATA:
        if (payload_len == sizeof(sensor_data_payload_t)) {
            sensor_data_payload_t sensor;
            memcpy(&sensor, payload, sizeof(sensor));
            handle_sensor_data(sensor);
        }
        break;
    case MSG_SENSOR_DIAG:
        if (payload_len == sizeof(sensor_diag_payload_t)) {
            sensor_diag_payload_t diag;
            memcpy(&diag, payload, sizeof(diag));
            handle_sensor_diag(diag);
        }
        break;
    case MSG_LOG:
        handle_log(payload, payload_len);
        break;
    default:
        break;
    }
}

// ── Message helpers ────────────────────────────────────

sensor_msgs::msg::Range SensorDriverNode::make_ultrasonic_msg(
    const std::string& frame_id, float distance_m)
{
    auto msg = sensor_msgs::msg::Range();
    msg.header.stamp = now();
    msg.header.frame_id = frame_id;
    msg.radiation_type = sensor_msgs::msg::Range::ULTRASOUND;
    msg.field_of_view = 0.5236f;  // 30 degrees in radians
    msg.min_range = 0.02f;        // 2 cm
    msg.max_range = 4.0f;         // 4 m
    msg.range = (distance_m > 0.0f) ? distance_m
                                     : std::numeric_limits<float>::infinity();
    return msg;
}

sensor_msgs::msg::Range SensorDriverNode::make_cliff_msg(
    const std::string& frame_id, float distance_m)
{
    auto msg = sensor_msgs::msg::Range();
    msg.header.stamp = now();
    msg.header.frame_id = frame_id;
    msg.radiation_type = sensor_msgs::msg::Range::INFRARED;
    msg.field_of_view = 0.0436f;  // ~2.5 degrees (narrow IR beam)
    msg.min_range = 0.02f;        // 2 cm
    msg.max_range = 0.15f;        // 15 cm
    msg.range = (distance_m > 0.0f) ? distance_m
                                     : std::numeric_limits<float>::infinity();
    return msg;
}

// ── Message handlers ───────────────────────────────────

void SensorDriverNode::handle_sensor_data(const sensor_data_payload_t& sensor)
{
    // Publish 4x ultrasonic Range messages
    us_front_pub_->publish(make_ultrasonic_msg("us_front_link", sensor.us_front_m));
    us_rear_pub_->publish(make_ultrasonic_msg("us_rear_link", sensor.us_rear_m));
    us_left_pub_->publish(make_ultrasonic_msg("us_left_link", sensor.us_left_m));
    us_right_pub_->publish(make_ultrasonic_msg("us_right_link", sensor.us_right_m));

    // Publish 2x cliff Range messages
    cliff_front_pub_->publish(make_cliff_msg("cliff_front_link", sensor.cliff_front_m));
    cliff_rear_pub_->publish(make_cliff_msg("cliff_rear_link", sensor.cliff_rear_m));

    // Publish cliff detection Bool
    auto cliff_msg = std_msgs::msg::Bool();
    cliff_msg.data = (sensor.cliff_detected != 0);
    cliff_detected_pub_->publish(cliff_msg);
}

void SensorDriverNode::handle_sensor_diag(const sensor_diag_payload_t& diag)
{
    auto msg = diagnostic_msgs::msg::DiagnosticArray();
    msg.header.stamp = now();

    diagnostic_msgs::msg::DiagnosticStatus status;
    status.name = "ROVAC Sensor Hub";
    status.hardware_id = "esp32_sensor_hub";

    // Determine overall status
    bool all_us_ok = (diag.us_ok == 0x0F);
    bool all_cliff_ok = (diag.cliff_ok == 0x03);
    if (all_us_ok && all_cliff_ok) {
        status.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
        status.message = "All sensors OK";
    } else if (all_cliff_ok) {
        status.level = diagnostic_msgs::msg::DiagnosticStatus::WARN;
        status.message = "Some ultrasonic sensors not reading";
    } else {
        status.level = diagnostic_msgs::msg::DiagnosticStatus::ERROR;
        status.message = "Cliff sensor failure";
    }

    auto kv = [](const std::string& key, const std::string& val) {
        diagnostic_msgs::msg::KeyValue kv;
        kv.key = key;
        kv.value = val;
        return kv;
    };

    const char* us_names[] = {"front", "rear", "left", "right"};
    for (int i = 0; i < 4; i++) {
        status.values.push_back(kv(
            std::string("us_") + us_names[i],
            (diag.us_ok & (1 << i)) ? "OK" : "FAIL"));
    }
    status.values.push_back(kv("cliff_front", (diag.cliff_ok & 0x01) ? "OK" : "FAIL"));
    status.values.push_back(kv("cliff_rear", (diag.cliff_ok & 0x02) ? "OK" : "FAIL"));
    status.values.push_back(kv("heap_free", std::to_string(diag.heap_free)));
    status.values.push_back(kv("read_cycles", std::to_string(diag.read_count)));
    status.values.push_back(kv("transport", "usb_serial"));
    status.values.push_back(kv("reconnects", std::to_string(reconnect_count_.load())));

    msg.status.push_back(status);
    diag_pub_->publish(msg);
}

void SensorDriverNode::handle_log(const uint8_t* data, size_t len)
{
    if (len == 0) return;
    std::string log_msg(reinterpret_cast<const char*>(data), len);
    if (!log_msg.empty() && log_msg.back() == '\0')
        log_msg.pop_back();
    if (!log_msg.empty())
        RCLCPP_INFO(get_logger(), "[ESP32] %s", log_msg.c_str());
}

}  // namespace rovac
