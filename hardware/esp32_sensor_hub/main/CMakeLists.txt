idf_component_register(
    SRCS
        "main.c"
        "sensor_serial.c"
        "ultrasonic.c"
        "cliff_sensor.c"
        "../../../common/cobs.c"
    INCLUDE_DIRS "." "../../../common"
    REQUIRES
        driver
        esp_timer
        esp_adc
)
