/*
  Professional ROVAC LIDAR USB Bridge
  Enhanced firmware with device identification and professional features
  
  Features:
  - Device identification (!id)
  - Firmware version (!version)  
  - Real-time status (!status)
  - Baud rate reporting (!baud)
  - Statistics reset (!reset)
  - Help system (!help)
  - LED status indication
  - Professional-grade communication
  
  Wiring:
  - Nano Pin 2 (RX)  <- LIDAR TX
  - Nano Pin 3 (TX)  -> LIDAR RX  
  - Nano 5V          <- LIDAR 5V
  - Nano GND         <- LIDAR GND
*/

#include <SoftwareSerial.h>

// Device identification
#define DEVICE_NAME "ROVAC_LIDAR_BRIDGE"
#define FIRMWARE_VERSION "2.0.0"
#define BAUD_RATE 115200

// LED pin for status indication
const int LED_PIN = 13;

// SoftwareSerial for LIDAR connection
SoftwareSerial lidarSerial(2, 3); // RX, TX (LIDAR connection)

// Statistics
unsigned long packetsForwarded = 0;
unsigned long bytesForwarded = 0;
unsigned long startTime = 0;
unsigned long lastActivity = 0;

// Command buffer
#define CMD_BUFFER_SIZE 64
char commandBuffer[CMD_BUFFER_SIZE];
int commandIndex = 0;

// Forward declarations
void processCommand(char* command);
void flashLED(int count, int duration);

void setup() {
  // Initialize LED
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  
  // Initialize serial communications
  Serial.begin(BAUD_RATE);      // USB serial (to host computer)
  lidarSerial.begin(BAUD_RATE);  // LIDAR serial (to LIDAR device)
  
  // Initialize statistics
  startTime = millis();
  lastActivity = millis();
  
  // Small delay for stabilization
  delay(1000);
  
  // Flash LED to indicate startup
  flashLED(3, 100);
  
  // Send startup notification
  Serial.println("!ROVAC_LIDAR_BRIDGE_READY");
  Serial.println("!Send !help for available commands");
}

void loop() {
  // Handle LED status indication
  static unsigned long lastBlink = 0;
  static bool ledState = false;
  
  unsigned long currentTime = millis();
  
  // Blink LED periodically to show device is active
  if (currentTime - lastBlink > 1000) {
    ledState = !ledState;
    digitalWrite(LED_PIN, ledState);
    lastBlink = currentTime;
  }
  
  // Process commands from USB host
  static char commandBuffer[CMD_BUFFER_SIZE];
  static int commandIndex = 0;
  
  // Check for incoming commands from USB host
  while (Serial.available()) {
    char c = Serial.read();
    
    // Command mode - commands start with '!'
    if (c == '!') {
      commandIndex = 0;
      continue;
    }
    
    // Process command characters
    if (commandIndex >= 0) {
      if (c == '\n' || c == '\r') {
        // End of command - process it
        if (commandIndex > 0) {
          commandBuffer[commandIndex] = '\0';
          processCommand(commandBuffer);
        }
        commandIndex = -1; // Reset command processing
      } else if (commandIndex < CMD_BUFFER_SIZE - 1) {
        commandBuffer[commandIndex++] = tolower(c);
      }
    }
  }
  
  // Forward data from LIDAR to USB host
  if (lidarSerial.available()) {
    int inByte = lidarSerial.read();
    Serial.write(inByte);
    bytesForwarded++;
    lastActivity = millis();
    
    // Update packet counter periodically
    if (bytesForwarded % 1000 == 0) {
      packetsForwarded++;
    }
  }
  
  // Forward data from USB host to LIDAR
  // Only forward if we're not in the middle of processing a command
  if (commandIndex < 0 && Serial.available()) {
    int inByte = Serial.read();
    lidarSerial.write(inByte);
    lastActivity = millis();
  }
}

void processCommand(char* command) {
  // Process different commands
  if (strcmp(command, "id") == 0) {
    Serial.print("!DEVICE_ID:");
    Serial.println(DEVICE_NAME);
  }
  else if (strcmp(command, "version") == 0) {
    Serial.print("!VERSION:");
    Serial.println(FIRMWARE_VERSION);
  }
  else if (strcmp(command, "status") == 0) {
    unsigned long uptime = (millis() - startTime) / 1000;
    unsigned long idleTime = (millis() - lastActivity) / 1000;
    Serial.print("!STATUS:Uptime=");
    Serial.print(uptime);
    Serial.print("s,Bytes=");
    Serial.print(bytesForwarded);
    Serial.print(",Packets=");
    Serial.print(packetsForwarded);
    Serial.print(",Idle=");
    Serial.println(idleTime);
  }
  else if (strcmp(command, "baud") == 0) {
    Serial.print("!BAUD_RATE:");
    Serial.println(BAUD_RATE);
  }
  else if (strcmp(command, "reset") == 0) {
    packetsForwarded = 0;
    bytesForwarded = 0;
    startTime = millis();
    lastActivity = millis();
    Serial.println("!STATISTICS_RESET");
  }
  else if (strcmp(command, "help") == 0) {
    Serial.println("!AVAILABLE_COMMANDS:!id,!version,!status,!baud,!reset,!help");
  }
  else {
    Serial.print("!UNKNOWN_COMMAND:");
    Serial.println(command);
  }
}

void flashLED(int count, int duration) {
  // Flash LED multiple times
  for (int i = 0; i < count; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(duration);
    digitalWrite(LED_PIN, LOW);
    delay(duration);
  }
}