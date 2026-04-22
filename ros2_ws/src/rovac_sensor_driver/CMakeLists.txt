cmake_minimum_required(VERSION 3.8)
project(rovac_sensor_driver)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(diagnostic_msgs REQUIRED)

# Shared protocol (C code from common/)
add_library(sensor_serial_protocol STATIC
  ${CMAKE_CURRENT_SOURCE_DIR}/../../../common/cobs.c
)
target_include_directories(sensor_serial_protocol PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/../../../common
)

# Sensor driver node
add_executable(sensor_driver_node
  src/main.cpp
  src/sensor_driver_node.cpp
  src/serial_port.cpp
)

target_include_directories(sensor_driver_node PRIVATE
  include
  ${CMAKE_CURRENT_SOURCE_DIR}/../../../common
)

target_link_libraries(sensor_driver_node sensor_serial_protocol)

ament_target_dependencies(sensor_driver_node
  rclcpp
  sensor_msgs
  std_msgs
  diagnostic_msgs
)

install(TARGETS sensor_driver_node
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY config/
  DESTINATION share/${PROJECT_NAME}/config
)

ament_package()
