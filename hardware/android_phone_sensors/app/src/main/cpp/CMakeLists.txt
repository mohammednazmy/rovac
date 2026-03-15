cmake_minimum_required(VERSION 3.18)
project(xrce_bridge C)

# Pre-built Micro-XRCE-DDS Client + Micro-CDR libraries
set(XRCE_DIR ${CMAKE_SOURCE_DIR}/../../../../xrce-libs/${ANDROID_ABI})

# Import Micro-CDR (static)
add_library(microcdr STATIC IMPORTED)
set_target_properties(microcdr PROPERTIES
    IMPORTED_LOCATION ${XRCE_DIR}/lib/libmicrocdr.a
)

# Import Micro-XRCE-DDS Client (static)
add_library(microxrcedds_client STATIC IMPORTED)
set_target_properties(microxrcedds_client PROPERTIES
    IMPORTED_LOCATION ${XRCE_DIR}/lib/libmicroxrcedds_client.a
)

# Our JNI shared library
add_library(xrce_bridge SHARED
    xrce_bridge.c
)

target_include_directories(xrce_bridge PRIVATE
    ${XRCE_DIR}/include
)

# Link order matters: client depends on microcdr
target_link_libraries(xrce_bridge
    microxrcedds_client
    microcdr
    log
)
