/*
 * 02_wifi_station.ino — WiFi Station (Client) Connection
 *
 * Connects to a WiFi network, prints IP/RSSI, and monitors connection.
 * Automatically reconnects if the connection drops.
 *
 * Board:  Lonely Binary ESP32-S3 WROOM (2518V5)
 * Pins:   None (WiFi uses internal RF, no GPIO needed)
 * Note:   ADC2 (GPIO11-20) cannot be used while WiFi is active.
 */

#include <WiFi.h>

const char* ssid     = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("02_wifi_station: Connecting to WiFi...");

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);

    int timeout = 20;
    while (WiFi.status() != WL_CONNECTED && timeout > 0) {
        delay(1000);
        Serial.print(".");
        timeout--;
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("WiFi connected!");
        Serial.print("  IP:   "); Serial.println(WiFi.localIP());
        Serial.print("  RSSI: "); Serial.print(WiFi.RSSI()); Serial.println(" dBm");
        Serial.print("  MAC:  "); Serial.println(WiFi.macAddress());
    } else {
        Serial.println("WiFi connection FAILED. Check SSID/password.");
    }
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi lost — reconnecting...");
        WiFi.reconnect();
        delay(5000);
        return;
    }

    Serial.printf("OK — IP: %s, RSSI: %d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
    delay(10000);
}
