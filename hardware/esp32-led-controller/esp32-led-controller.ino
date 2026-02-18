// LED Strip Controller for ESP32
// Control via WiFi, Bluetooth, and USB Serial
// For single-color (blue) SMD 3528 LED strip

#include <WiFi.h>
#include <WebServer.h>
#include <BluetoothSerial.h>

// ========== CONFIGURATION ==========
const char* WIFI_SSID = "Hurry";
const char* WIFI_PASSWORD = "Gaza@2023";
const char* DEVICE_NAME = "LED_Controller";

// PWM Configuration
const int LED_PIN = 16;           // GPIO16 controls MOSFET gate
const int PWM_FREQ = 5000;        // 5 kHz PWM frequency
const int PWM_RESOLUTION = 8;     // 8-bit (0-255)

// ========== GLOBALS ==========
WebServer server(80);
BluetoothSerial SerialBT;
int brightness = 0;               // 0-255
bool ledOn = false;

// ========== HTML INTERFACE ==========
const char* HTML_PAGE = R"rawliteral(
<!DOCTYPE html>
<html>
<head>
  <title>LED Controller</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: Arial; text-align: center; margin: 50px; background: #1a1a2e; color: #fff; }
    h1 { color: #4da6ff; }
    .btn { padding: 20px 40px; font-size: 20px; margin: 10px; border: none; border-radius: 10px; cursor: pointer; }
    .on { background: #4CAF50; color: white; }
    .off { background: #f44336; color: white; }
    input[type=range] { width: 80%; height: 30px; margin: 20px; accent-color: #4da6ff; }
    .status { font-size: 24px; margin: 20px; }
    .info { font-size: 14px; color: #888; margin-top: 40px; }
  </style>
</head>
<body>
  <h1>Blue LED Strip Controller</h1>
  <div class="status">Brightness: <span id="val">0</span>%</div>
  <input type="range" id="slider" min="0" max="100" value="0" oninput="updateSlider(this.value)">
  <br>
  <button class="btn on" onclick="sendCmd('on')">ON (100%)</button>
  <button class="btn off" onclick="sendCmd('off')">OFF</button>
  <div class="info">
    Also available via Bluetooth ("LED_Controller") or USB Serial (115200 baud)
  </div>
  <script>
    function sendCmd(cmd) { fetch('/' + cmd); updateStatus(); }
    function updateSlider(val) {
      document.getElementById('val').innerHTML = val;
      fetch('/brightness?value=' + val);
    }
    function updateStatus() {
      fetch('/status').then(r => r.json()).then(d => {
        document.getElementById('val').innerHTML = Math.round(d.brightness / 2.55);
        document.getElementById('slider').value = Math.round(d.brightness / 2.55);
      });
    }
    setInterval(updateStatus, 2000);
  </script>
</body>
</html>
)rawliteral";

// ========== LED CONTROL ==========
void setLED(int value) {
  brightness = constrain(value, 0, 255);
  ledcWrite(LED_PIN, brightness);  // ESP32 Core 3.x uses pin directly
  ledOn = (brightness > 0);
}

// ========== WIFI HANDLERS ==========
void handleRoot() {
  server.send(200, "text/html", HTML_PAGE);
}

void handleOn() {
  setLED(255);
  server.send(200, "text/plain", "LED ON");
  Serial.println("WiFi: LED ON");
}

void handleOff() {
  setLED(0);
  server.send(200, "text/plain", "LED OFF");
  Serial.println("WiFi: LED OFF");
}

void handleBrightness() {
  if (server.hasArg("value")) {
    int percent = server.arg("value").toInt();
    int pwmValue = map(percent, 0, 100, 0, 255);
    setLED(pwmValue);
    server.send(200, "text/plain", "Brightness: " + String(percent) + "%");
    Serial.printf("WiFi: Brightness %d%%\n", percent);
  } else {
    server.send(400, "text/plain", "Missing value parameter");
  }
}

void handleStatus() {
  String json = "{\"brightness\":" + String(brightness) + ",\"on\":" + (ledOn ? "true" : "false") + "}";
  server.send(200, "application/json", json);
}

// ========== COMMAND PARSER ==========
void processCommand(String cmd, String source) {
  cmd.trim();
  cmd.toLowerCase();

  String response = "";

  if (cmd == "on") {
    setLED(255);
    response = "LED ON (100%)";
  }
  else if (cmd == "off") {
    setLED(0);
    response = "LED OFF";
  }
  else if (cmd.startsWith("brightness ") || cmd.startsWith("b ")) {
    int value = cmd.substring(cmd.indexOf(' ') + 1).toInt();
    value = constrain(value, 0, 100);
    int pwmValue = map(value, 0, 100, 0, 255);
    setLED(pwmValue);
    response = "Brightness: " + String(value) + "%";
  }
  else if (cmd == "status" || cmd == "s") {
    response = "LED: " + String(ledOn ? "ON" : "OFF") +
               ", Brightness: " + String(map(brightness, 0, 255, 0, 100)) + "%" +
               ", IP: " + WiFi.localIP().toString();
  }
  else if (cmd == "help" || cmd == "h" || cmd == "?") {
    response = "Commands:\n"
               "  on          - Turn LED on (100%)\n"
               "  off         - Turn LED off\n"
               "  b <0-100>   - Set brightness %\n"
               "  status      - Show current status\n"
               "  help        - Show this help";
  }
  else {
    response = "Unknown command. Type 'help' for commands.";
  }

  Serial.printf("[%s] %s -> %s\n", source.c_str(), cmd.c_str(), response.c_str());

  if (source == "BT") {
    SerialBT.println(response);
  }
}

// ========== SETUP ==========
void setup() {
  // USB Serial
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n========================================");
  Serial.println("   Blue LED Strip Controller v1.0");
  Serial.println("========================================");

  // PWM Setup for LED control (ESP32 Core 3.x API)
  ledcAttach(LED_PIN, PWM_FREQ, PWM_RESOLUTION);
  setLED(0);
  Serial.println("[OK] PWM initialized on GPIO16");

  // Bluetooth Serial
  if (SerialBT.begin(DEVICE_NAME)) {
    Serial.printf("[OK] Bluetooth: %s\n", DEVICE_NAME);
  } else {
    Serial.println("[FAIL] Bluetooth init failed");
  }

  // WiFi Connection
  Serial.printf("[..] Connecting to WiFi '%s'", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[OK] WiFi connected!\n");
    Serial.printf("[OK] Web interface: http://%s\n", WiFi.localIP().toString().c_str());

    // Web server routes
    server.on("/", handleRoot);
    server.on("/on", handleOn);
    server.on("/off", handleOff);
    server.on("/brightness", handleBrightness);
    server.on("/status", handleStatus);
    server.begin();
    Serial.println("[OK] Web server started");
  } else {
    Serial.println("\n[WARN] WiFi connection failed");
    Serial.println("[INFO] Bluetooth and USB Serial still available");
  }

  Serial.println("========================================");
  Serial.println("Ready! Type 'help' for commands.");
  Serial.println("========================================\n");
}

// ========== MAIN LOOP ==========
void loop() {
  // Handle WiFi web clients
  if (WiFi.status() == WL_CONNECTED) {
    server.handleClient();
  }

  // Handle Bluetooth commands
  if (SerialBT.available()) {
    String cmd = SerialBT.readStringUntil('\n');
    processCommand(cmd, "BT");
  }

  // Handle USB Serial commands
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    processCommand(cmd, "USB");
  }

  delay(10);
}
