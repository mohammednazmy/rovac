/*
 * main.cpp — ROVAC Sensor Driver Node entry point
 */
#include <rclcpp/rclcpp.hpp>
#include "rovac_sensor_driver/sensor_driver_node.hpp"

int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<rovac::SensorDriverNode>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
