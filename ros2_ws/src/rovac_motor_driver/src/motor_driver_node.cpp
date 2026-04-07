/*
 * motor_driver_node.cpp — ROVAC Motor Driver ROS2 Node
 *
 * Bridges ESP32 USB serial binary protocol (COBS-framed) to ROS2 topics.
 * All publishers use reliable QoS — eliminates the need for QoS relay scripts.
 */
#include "rovac_motor_driver/motor_driver_node.hpp"
#include "cobs.h"

#include <geometry_msgs/msg/transform_stamped.hpp>
#include <cstring>
#include <cmath>

namespace rovac {

MotorDriverNode::MotorDriverNode()
    : Node("motor_driver_node")
{
    // Declare parameters
    serial_port_ = declare_parameter("serial_port", "/dev/esp32_motor");
    baud_rate_ = declare_parameter("baud_rate", 460800);
    odom_frame_ = declare_parameter("odom_frame", "odom");
    base_frame_ = declare_parameter("base_frame", "base_link");
    imu_frame_ = declare_parameter("imu_frame", "imu_link");
    publish_tf_ = declare_parameter("publish_tf", true);
    serial_rx_timeout_s_ = declare_parameter("serial_rx_timeout", 5);

    // Publishers — ALL reliable QoS (no relay scripts needed)
    auto reliable_qos = rclcpp::QoS(10).reliable();

    odom_pub_ = create_publisher<nav_msgs::msg::Odometry>("odom", reliable_qos);
    imu_pub_ = create_publisher<sensor_msgs::msg::Imu>("imu/data", reliable_qos);
    diag_pub_ = create_publisher<diagnostic_msgs::msg::DiagnosticArray>("diagnostics", reliable_qos);
    tf_broadcaster_ = std::make_unique<tf2_ros::TransformBroadcaster>(*this);

    // Subscriber
    cmd_vel_sub_ = create_subscription<geometry_msgs::msg::Twist>(
        "cmd_vel", 10,
        std::bind(&MotorDriverNode::cmd_vel_callback, this, std::placeholders::_1));

    // Reconnect timer (fires every 2s when disconnected)
    reconnect_timer_ = create_wall_timer(
        std::chrono::seconds(2),
        std::bind(&MotorDriverNode::reconnect_callback, this));

    // Initial connection attempt
    try_connect();

    // Start serial read thread
    serial_thread_ = std::thread(&MotorDriverNode::serial_read_loop, this);

    RCLCPP_INFO(get_logger(), "Motor driver node started (port=%s, baud=%d)",
                serial_port_.c_str(), baud_rate_);
}

MotorDriverNode::~MotorDriverNode()
{
    running_ = false;
    if (serial_thread_.joinable())
        serial_thread_.join();
    serial_.close();
}

// ── Connection management ──────────────────────────────

void MotorDriverNode::try_connect()
{
    if (serial_.is_open()) return;

    if (serial_.open(serial_port_, baud_rate_)) {
        auto now_ns = std::chrono::steady_clock::now().time_since_epoch().count();
        last_rx_time_ns_.store(now_ns, std::memory_order_release);
        RCLCPP_INFO(get_logger(), "Serial port opened: %s @ %d baud",
                     serial_port_.c_str(), baud_rate_);
    }
    /* Failure is silent — reconnect_callback retries every 2s */
}

void MotorDriverNode::reconnect_callback()
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

    // Serial health monitor: if port is open but no valid frames received
    // for serial_rx_timeout seconds, close and reopen the port.
    // This handles stale file descriptors after USB re-enumeration.
    auto now_ns = std::chrono::steady_clock::now().time_since_epoch().count();
    auto last_ns = last_rx_time_ns_.load(std::memory_order_acquire);
    auto elapsed_ns = now_ns - last_ns;
    if (elapsed_ns > static_cast<int64_t>(serial_rx_timeout_s_) * 1'000'000'000LL) {
        RCLCPP_WARN(get_logger(),
            "No data from ESP32 for %d seconds — closing serial for reconnect",
            serial_rx_timeout_s_);
        serial_.close();
        connected_ = false;
        // Next timer tick (2s) will call try_connect() via the !is_open() branch
    }
}

// ── Serial TX ──────────────────────────────────────────

void MotorDriverNode::send_frame(uint8_t msg_type, const void* payload, size_t payload_len)
{
    uint8_t raw[SERIAL_PROTOCOL_MAX_FRAME];
    uint8_t encoded[SERIAL_PROTOCOL_MAX_FRAME + 3];

    size_t raw_len = serial_protocol_build_frame(raw, msg_type, payload, payload_len);
    size_t enc_len = cobs_encode(raw, raw_len, encoded);
    encoded[enc_len] = 0x00;  // Frame delimiter

    std::lock_guard<std::mutex> lock(write_mutex_);
    ssize_t ret = serial_.write(encoded, enc_len + 1);
    if (ret < 0) {
        RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 2000,
                             "Serial write failed — link may be down");
    }
}

void MotorDriverNode::cmd_vel_callback(const geometry_msgs::msg::Twist::SharedPtr msg)
{
    if (!serial_.is_open()) {
        RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 2000,
                             "cmd_vel received but serial not open");
        return;
    }

    cmd_vel_payload_t cmd;
    cmd.linear_x = static_cast<float>(msg->linear.x);
    cmd.angular_z = static_cast<float>(msg->angular.z);

    send_frame(MSG_CMD_VEL, &cmd, sizeof(cmd));

    static uint32_t cmd_count = 0;
    if (++cmd_count <= 3 || cmd_count % 100 == 0) {
        RCLCPP_INFO(get_logger(), "cmd_vel #%u: linear=%.3f angular=%.3f → serial",
                    cmd_count, cmd.linear_x, cmd.angular_z);
    }
}

// ── Serial RX ──────────────────────────────────────────

void MotorDriverNode::serial_read_loop()
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
            // Serial error — port may have been disconnected
            RCLCPP_ERROR(get_logger(), "Serial read error — closing port");
            serial_.close();
            connected_ = false;
            frame_pos = 0;
            continue;
        }
        if (n == 0) continue;  // Timeout

        for (ssize_t i = 0; i < n; i++) {
            if (byte_buf[i] == 0x00) {
                // Frame delimiter — decode accumulated bytes
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
                    frame_pos = 0;  // Overflow — resync
                }
            }
        }
    }
}

void MotorDriverNode::process_frame(const uint8_t* data, size_t len)
{
    uint8_t msg_type;
    const uint8_t* payload;
    size_t payload_len;

    if (!serial_protocol_parse_frame(data, len, &msg_type, &payload, &payload_len))
        return;  // CRC mismatch

    // Mark connection alive
    auto now_ns = std::chrono::steady_clock::now().time_since_epoch().count();
    last_rx_time_ns_.store(now_ns, std::memory_order_release);
    if (!connected_) {
        connected_ = true;
        RCLCPP_INFO(get_logger(), "ESP32 connected (receiving data)");
    }

    switch (msg_type) {
    case MSG_ODOM:
        if (payload_len == sizeof(odom_payload_t)) {
            odom_payload_t odom;
            memcpy(&odom, payload, sizeof(odom));
            handle_odom(odom);
        }
        break;
    case MSG_IMU:
        if (payload_len == sizeof(imu_payload_t)) {
            imu_payload_t imu;
            memcpy(&imu, payload, sizeof(imu));
            handle_imu(imu);
        }
        break;
    case MSG_DIAG:
        if (payload_len == sizeof(diag_payload_t)) {
            diag_payload_t diag;
            memcpy(&diag, payload, sizeof(diag));
            handle_diag(diag);
        }
        break;
    case MSG_LOG:
        handle_log(payload, payload_len);
        break;
    default:
        break;
    }
}

// ── Message handlers ───────────────────────────────────

void MotorDriverNode::handle_odom(const odom_payload_t& odom)
{
    auto msg = nav_msgs::msg::Odometry();
    msg.header.stamp = now();
    msg.header.frame_id = odom_frame_;
    msg.child_frame_id = base_frame_;

    // Pose (already in ROS frame — corrections applied on ESP32)
    msg.pose.pose.position.x = odom.x;
    msg.pose.pose.position.y = odom.y;
    msg.pose.pose.position.z = 0.0;

    // Convert yaw to quaternion
    double half_yaw = odom.yaw * 0.5;
    msg.pose.pose.orientation.x = 0.0;
    msg.pose.pose.orientation.y = 0.0;
    msg.pose.pose.orientation.z = std::sin(half_yaw);
    msg.pose.pose.orientation.w = std::cos(half_yaw);

    // Pose covariance (6x6 diagonal)
    msg.pose.covariance[0]  = odom.cov_x;    // x
    msg.pose.covariance[7]  = odom.cov_x;    // y (same as x)
    msg.pose.covariance[35] = odom.cov_yaw;  // yaw

    // Twist
    msg.twist.twist.linear.x = odom.v_linear;
    msg.twist.twist.angular.z = odom.v_angular;

    // Twist covariance
    msg.twist.covariance[0]  = 0.01;   // vx
    msg.twist.covariance[35] = 0.03;   // vyaw

    odom_pub_->publish(msg);

    // Broadcast odom → base_link TF (dynamically checked — can be disabled
    // at runtime via `ros2 param set` when EKF is publishing its own TF)
    if (get_parameter("publish_tf").as_bool()) {
        geometry_msgs::msg::TransformStamped tf;
        tf.header = msg.header;
        tf.child_frame_id = base_frame_;
        tf.transform.translation.x = odom.x;
        tf.transform.translation.y = odom.y;
        tf.transform.translation.z = 0.0;
        tf.transform.rotation = msg.pose.pose.orientation;
        tf_broadcaster_->sendTransform(tf);
    }
}

void MotorDriverNode::handle_imu(const imu_payload_t& imu)
{
    auto msg = sensor_msgs::msg::Imu();
    msg.header.stamp = now();
    msg.header.frame_id = imu_frame_;

    // Orientation (BNO055 NDOF fusion quaternion)
    msg.orientation.w = imu.qw;
    msg.orientation.x = imu.qx;
    msg.orientation.y = imu.qy;
    msg.orientation.z = imu.qz;

    // Orientation covariance (BNO055 ±3° heading = ~0.003 rad² variance)
    msg.orientation_covariance[0] = 0.003;
    msg.orientation_covariance[4] = 0.003;
    msg.orientation_covariance[8] = 0.003;

    // Angular velocity (gyroscope, rad/s)
    msg.angular_velocity.x = imu.gx;
    msg.angular_velocity.y = imu.gy;
    msg.angular_velocity.z = imu.gz;

    // Gyro noise variance ~6e-6 rad²/s²
    msg.angular_velocity_covariance[0] = 6e-6;
    msg.angular_velocity_covariance[4] = 6e-6;
    msg.angular_velocity_covariance[8] = 6e-6;

    // Linear acceleration (gravity removed, m/s²)
    msg.linear_acceleration.x = imu.ax;
    msg.linear_acceleration.y = imu.ay;
    msg.linear_acceleration.z = imu.az;

    // Accel noise variance ~2.5e-4 m²/s⁴
    msg.linear_acceleration_covariance[0] = 2.5e-4;
    msg.linear_acceleration_covariance[4] = 2.5e-4;
    msg.linear_acceleration_covariance[8] = 2.5e-4;

    imu_pub_->publish(msg);
}

void MotorDriverNode::handle_diag(const diag_payload_t& diag)
{
    auto msg = diagnostic_msgs::msg::DiagnosticArray();
    msg.header.stamp = now();

    diagnostic_msgs::msg::DiagnosticStatus status;
    status.level = diagnostic_msgs::msg::DiagnosticStatus::OK;
    status.name = "ROVAC Motor Serial";
    status.hardware_id = "esp32_motor_serial";
    status.message = diag.pid_active ? "Running" : "PID idle";

    auto kv = [](const std::string& key, const std::string& val) {
        diagnostic_msgs::msg::KeyValue kv;
        kv.key = key;
        kv.value = val;
        return kv;
    };

    status.values.push_back(kv("heap_free", std::to_string(diag.heap_free)));
    status.values.push_back(kv("pid_active", diag.pid_active ? "true" : "false"));
    status.values.push_back(kv("v_left", std::to_string(diag.v_left)));
    status.values.push_back(kv("v_right", std::to_string(diag.v_right)));
    status.values.push_back(kv("odom_updates", std::to_string(diag.odom_count)));
    status.values.push_back(kv("imu_cal_sys", std::to_string(diag.imu_cal_sys)));
    status.values.push_back(kv("imu_cal_gyro", std::to_string(diag.imu_cal_gyro)));
    status.values.push_back(kv("imu_cal_accel", std::to_string(diag.imu_cal_accel)));
    status.values.push_back(kv("imu_cal_mag", std::to_string(diag.imu_cal_mag)));
    status.values.push_back(kv("transport", "usb_serial"));
    status.values.push_back(kv("reconnects", std::to_string(reconnect_count_.load())));

    msg.status.push_back(status);
    diag_pub_->publish(msg);
}

void MotorDriverNode::handle_log(const uint8_t* data, size_t len)
{
    if (len == 0) return;
    // Ensure null-terminated
    std::string log_msg(reinterpret_cast<const char*>(data), len);
    // Remove trailing null if present
    if (!log_msg.empty() && log_msg.back() == '\0')
        log_msg.pop_back();
    if (!log_msg.empty())
        RCLCPP_INFO(get_logger(), "[ESP32] %s", log_msg.c_str());
}

}  // namespace rovac
