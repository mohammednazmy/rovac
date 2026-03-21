/*
 * main.cpp — ROVAC Motor Driver Node entry point
 */
#include <rclcpp/rclcpp.hpp>
#include "rovac_motor_driver/motor_driver_node.hpp"

int main(int argc, char** argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<rovac::MotorDriverNode>();
    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
