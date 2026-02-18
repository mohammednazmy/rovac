// XV11 LIDAR to USB Bridge
// Reads data from XV11 LIDAR and forwards it to USB serial
// Uses SoftwareSerial for LIDAR connection

#include <SoftwareSerial.h>

#define LIDAR_BAUD 115200
#define USB_BAUD 115200

// LIDAR connections on Arduino Uno
// Connect LIDAR TX to Arduino pin 2 (RX)
// Connect LIDAR RX to Arduino pin 3 (TX)
#define LIDAR_RX_PIN 2
#define LIDAR_TX_PIN 3

// Create software serial for LIDAR
SoftwareSerial lidarSerial(LIDAR_RX_PIN, LIDAR_TX_PIN);

void setup() {
  // Initialize serial communications
  Serial.begin(USB_BAUD);        // USB serial to computer/Raspberry Pi
  lidarSerial.begin(LIDAR_BAUD);  // Software serial to LIDAR
  
  // Wait a moment for connections to stabilize
  delay(1000);
}

void loop() {
  // Bridge data bidirectionally between LIDAR and USB
  
  // Forward data from LIDAR to USB (Pi)
  if (lidarSerial.available()) {
    Serial.write(lidarSerial.read());
  }
  
  // Forward data from USB (Pi) to LIDAR
  if (Serial.available()) {
    lidarSerial.write(Serial.read());
  }
}