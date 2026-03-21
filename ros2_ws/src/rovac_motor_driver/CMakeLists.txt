cmake_minimum_required(VERSION 3.8)
project(rovac_motor_driver)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)
find_package(tf2_ros REQUIRED)

# Shared protocol (C code from common/)
add_library(serial_protocol STATIC
  ${CMAKE_CURRENT_SOURCE_DIR}/../../../common/cobs.c
)
target_include_directories(serial_protocol PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/../../../common
)

# Motor driver node
add_executable(motor_driver_node
  src/main.cpp
  src/motor_driver_node.cpp
  src/serial_port.cpp
)

target_include_directories(motor_driver_node PRIVATE
  include
  ${CMAKE_CURRENT_SOURCE_DIR}/../../../common
)

target_link_libraries(motor_driver_node serial_protocol)

ament_target_dependencies(motor_driver_node
  rclcpp
  nav_msgs
  geometry_msgs
  sensor_msgs
  diagnostic_msgs
  tf2_ros
)

install(TARGETS motor_driver_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY config/
  DESTINATION share/${PROJECT_NAME}/config
)

ament_package()
