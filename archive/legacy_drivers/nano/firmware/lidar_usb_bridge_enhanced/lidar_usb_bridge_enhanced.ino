/*
  Enhanced LIDAR USB-to-UART Bridge
  Professional version with device identification and status reporting.
  
  This sketch enhances the basic USB bridge with:
  - Device identification commands
  - Status reporting
  - Version information
  - Cross-platform compatibility improvements
  
  Wiring:
  - Nano Pin 0 (RX)  <- LIDAR TX
  - Nano Pin 1 (TX)  <- LIDAR RX
  - Nano 5V          <- LIDAR 5V
  - Nano GND         <- LIDAR GND
*/

#include <SoftwareSerial.h>

// Device identification
#define DEVICE_NAME "ROVAC_LIDAR_BRIDGE"
#define FIRMWARE_VERSION "1.2.0"
#define BAUD_RATE 115200

// SoftwareSerial for LIDAR connection
// Connect LIDAR TX to pin 2, LIDAR RX to pin 3
SoftwareSerial lidarSerial(2, 3); // RX, TX

// LED indicator pin (built-in LED)
const int ledPin = 13;
bool ledState = false;

// Command processing
String inputCommand = "";
bool commandMode = false;

// Statistics
unsigned long packetsForwarded = 0;
unsigned long bytesReceived = 0;
unsigned long startTime = 0;

void setup() {
  // Initialize pins
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, LOW);
  
  // Initialize serial ports
  // Serial (USB) - communicates with the host
  Serial.begin(BAUD_RATE);
  
  // SoftwareSerial (for LIDAR) - communicates with the LIDAR
  lidarSerial.begin(BAUD_RATE);
  
  // Initialize statistics
  startTime = millis();
  
  // Small delay to stabilize connections
  delay(1000);
  
  // Flash LED to indicate startup
  for(int i = 0; i < 3; i++) {
    digitalWrite(ledPin, HIGH);
    delay(200);
    digitalWrite(ledPin, LOW);
    delay(200);
  }
}

void loop() {
  // Handle commands from USB host
  handleHostCommands();
  
  // Forward data from LIDAR to USB (Host)
  if (lidarSerial.available()) {
    int inByte = lidarSerial.read();
    Serial.write(inByte);
    bytesReceived++;
    
    // Update statistics for significant data chunks
    if (bytesReceived % 1000 == 0) {
      packetsForwarded++;
      // Brief LED flash to indicate activity
      digitalWrite(ledPin, HIGH);
      delay(1);
      digitalWrite(ledPin, LOW);
    }
  }
  
  // Forward data from USB (Host) to LIDAR
  if (Serial.available()) {
    int inByte = Serial.read();
    lidarSerial.write(inByte);
  }
}

void handleHostCommands() {
  // Check for incoming serial data
  while (Serial.available()) {
    char c = Serial.read();
    
    // Process commands (commands start with '!')
    if (c == '!') {
      inputCommand = "";
      commandMode = true;
      continue;
    }
    
    if (commandMode) {
      if (c == '\n' || c == '\r') {
        // End of command, process it
        processCommand(inputCommand);
        inputCommand = "";
        commandMode = false;
      } else {
        inputCommand += c;
      }
    }
  }
}

void processCommand(String command) {
  command.trim();
  command.toLowerCase();
  
  if (command == "id") {
    // Device identification
    Serial.println("!DEVICE_ID:" DEVICE_NAME);
  }
  else if (command == "version") {
    // Firmware version
    Serial.println("!VERSION:" FIRMWARE_VERSION);
  }
  else if (command == "status") {
    // Current status
    unsigned long uptime = (millis() - startTime) / 1000;
    Serial.print("!STATUS:");
    Serial.print("Uptime="); Serial.print(uptime); Serial.print("s,");
    Serial.print("Bytes="); Serial.print(bytesReceived); Serial.print(",");
    Serial.print("Packets="); Serial.println(packetsForwarded);
  }
  else if (command == "baud") {
    // Report baud rate
    Serial.println("!BAUD_RATE:115200");
  }
  else if (command == "reset") {
    // Reset statistics
    bytesReceived = 0;
    packetsForwarded = 0;
    startTime = millis();
    Serial.println("!RESET_OK");
  }
  else if (command == "help") {
    // Help information
    Serial.println("!COMMANDS:id,version,status,baud,reset,help");
  }
  else {
    // Unknown command
    Serial.println("!ERROR:Unknown command");
  }
}