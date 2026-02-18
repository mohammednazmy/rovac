/*
  LIDAR USB-to-UART Bridge
  This sketch turns an Arduino Nano into a USB-to-UART bridge for the XV11 LIDAR.
  
  Wiring:
  - Nano Pin 0 (RX)  <- LIDAR TX
  - Nano Pin 1 (TX)  <- LIDAR RX
  - Nano 5V          <- LIDAR 5V
  - Nano GND         <- LIDAR GND
  
  The Nano will appear as a USB serial device when plugged into the Pi.
*/

#include <SoftwareSerial.h>

// SoftwareSerial for LIDAR connection (since we're using Nano pins 2 and 3)
// Connect LIDAR TX to pin 2, LIDAR RX to pin 3
SoftwareSerial lidarSerial(2, 3); // RX, TX

void setup() {
  // Initialize serial ports
  // Serial (USB) - communicates with the host (Raspberry Pi)
  Serial.begin(115200);  // USB serial speed
  
  // SoftwareSerial (for LIDAR) - communicates with the LIDAR
  lidarSerial.begin(115200); // LIDAR operates at 115200 baud
  
  // Small delay to stabilize connections
  delay(100);
}

void loop() {
  // Forward data from LIDAR to USB (Pi)
  if (lidarSerial.available()) {
    int inByte = lidarSerial.read();
    Serial.write(inByte);
  }
  
  // Forward data from USB (Pi) to LIDAR
  if (Serial.available()) {
    int inByte = Serial.read();
    lidarSerial.write(inByte);
  }
}