/*
 * sensor_driver_node.hpp — ROVAC Sensor Hub ROS2 Driver
 *
 * Bridges the ESP32 sensor hub USB serial binary protocol to ROS2 topics.
 * Publishes Range messages for 4x ultrasonic + 2x cliff sensors,
 * Bool for cliff detection, and DiagnosticArray for sensor health.
 */
#pragma once

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/range.hpp>
#include <std_msgs/msg/bool.hpp>
#include <diagnostic_msgs/msg/diagnostic_array.hpp>

#include "rovac_sensor_driver/serial_port.hpp"
#include "serial_protocol.h"

#include <thread>
#include <atomic>
#include <mutex>

namespace rovac {

class SensorDriverNode : public rclcpp::Node {
public:
    SensorDriverNode();
    ~SensorDriverNode() override;

private:
    // Ultrasonic publishers (sensor_msgs/Range)
    rclcpp::Publisher<sensor_msgs::msg::Range>::SharedPtr us_front_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Range>::SharedPtr us_rear_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Range>::SharedPtr us_left_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Range>::SharedPtr us_right_pub_;

    // Cliff publishers (sensor_msgs/Range + Bool)
    rclcpp::Publisher<sensor_msgs::msg::Range>::SharedPtr cliff_front_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Range>::SharedPtr cliff_rear_pub_;
    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr cliff_detected_pub_;

    // Diagnostics
    rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr diag_pub_;

    // Serial port
    SerialPort serial_;
    std::thread serial_thread_;
    std::atomic<bool> running_{true};

    // Parameters
    std::string serial_port_;
    int baud_rate_;
    int serial_rx_timeout_s_;

    // Connection state
    std::atomic<bool> connected_{false};
    std::atomic<int64_t> last_rx_time_ns_{0};
    rclcpp::TimerBase::SharedPtr reconnect_timer_;
    std::atomic<uint32_t> reconnect_count_{0};

    // Callbacks
    void reconnect_callback();

    // Serial thread
    void serial_read_loop();
    void process_frame(const uint8_t* data, size_t len);

    // Message handlers
    void handle_sensor_data(const sensor_data_payload_t& sensor);
    void handle_sensor_diag(const sensor_diag_payload_t& diag);
    void handle_log(const uint8_t* data, size_t len);

    // Connection management
    void try_connect();

    // Helpers
    sensor_msgs::msg::Range make_ultrasonic_msg(
        const std::string& frame_id, float distance_m);
    sensor_msgs::msg::Range make_cliff_msg(
        const std::string& frame_id, float distance_m);
};

}  // namespace rovac
