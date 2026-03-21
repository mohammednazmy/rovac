/*
 * motor_driver_node.hpp — ROVAC Motor Driver ROS2 Node
 *
 * Bridges the ESP32 USB serial binary protocol to ROS2 topics.
 * Publishes odom, tf, imu, diagnostics with reliable QoS.
 * Subscribes to cmd_vel and forwards to ESP32 as binary frames.
 */
#pragma once

#include <rclcpp/rclcpp.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <diagnostic_msgs/msg/diagnostic_array.hpp>
#include <tf2_ros/transform_broadcaster.h>

#include "rovac_motor_driver/serial_port.hpp"
#include "serial_protocol.h"

#include <thread>
#include <atomic>
#include <mutex>
#include <chrono>

namespace rovac {

class MotorDriverNode : public rclcpp::Node {
public:
    MotorDriverNode();
    ~MotorDriverNode() override;

private:
    // ROS2 publishers (reliable QoS)
    rclcpp::Publisher<nav_msgs::msg::Odometry>::SharedPtr odom_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr imu_pub_;
    rclcpp::Publisher<diagnostic_msgs::msg::DiagnosticArray>::SharedPtr diag_pub_;
    std::unique_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;

    // ROS2 subscriber
    rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr cmd_vel_sub_;

    // Serial port
    SerialPort serial_;
    std::thread serial_thread_;
    std::atomic<bool> running_{true};
    std::mutex write_mutex_;

    // Parameters
    std::string serial_port_;
    int baud_rate_;
    std::string odom_frame_;
    std::string base_frame_;
    std::string imu_frame_;
    bool publish_tf_;

    // Connection state
    std::atomic<bool> connected_{false};
    std::chrono::steady_clock::time_point last_rx_time_;
    rclcpp::TimerBase::SharedPtr reconnect_timer_;

    // Callbacks
    void cmd_vel_callback(const geometry_msgs::msg::Twist::SharedPtr msg);
    void reconnect_callback();

    // Serial thread
    void serial_read_loop();
    void process_frame(const uint8_t* data, size_t len);
    void send_frame(uint8_t msg_type, const void* payload, size_t payload_len);

    // Message handlers
    void handle_odom(const odom_payload_t& odom);
    void handle_imu(const imu_payload_t& imu);
    void handle_diag(const diag_payload_t& diag);
    void handle_log(const uint8_t* data, size_t len);

    // Connection management
    void try_connect();
};

}  // namespace rovac
