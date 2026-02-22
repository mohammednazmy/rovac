/*
 * 03_ble_uart_server.ino — BLE UART Service (Nordic UART)
 *
 * Creates a BLE GATT server with TX/RX characteristics that act like
 * a wireless serial port. Connect from a phone app (nRF Connect, LightBlue)
 * to send/receive text.
 *
 * Board:  Lonely Binary ESP32-S3 WROOM (2518V5)
 * Pins:   None (BLE uses internal radio)
 * Note:   BLE TX peak current is ~176 mA at 0 dBm.
 */

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

// Nordic UART Service UUIDs
#define SERVICE_UUID           "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_RX "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define CHARACTERISTIC_UUID_TX "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

BLEServer* pServer = NULL;
BLECharacteristic* pTxCharacteristic = NULL;
bool deviceConnected = false;
bool oldDeviceConnected = false;
uint32_t msgCount = 0;

class ServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) override {
        deviceConnected = true;
        Serial.println("BLE client connected");
    }
    void onDisconnect(BLEServer* pServer) override {
        deviceConnected = false;
        Serial.println("BLE client disconnected");
    }
};

class RxCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic* pCharacteristic) override {
        String rxValue = pCharacteristic->getValue();
        if (rxValue.length() > 0) {
            Serial.print("BLE RX: ");
            Serial.println(rxValue);

            // Echo back to client
            String reply = "Echo: " + rxValue;
            pTxCharacteristic->setValue(reply);
            pTxCharacteristic->notify();
        }
    }
};

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("03_ble_uart_server: Starting BLE UART...");

    BLEDevice::init("ESP32-S3-UART");

    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new ServerCallbacks());

    BLEService* pService = pServer->createService(SERVICE_UUID);

    pTxCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID_TX, BLECharacteristic::PROPERTY_NOTIFY
    );
    pTxCharacteristic->addDescriptor(new BLE2902());

    BLECharacteristic* pRxCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID_RX, BLECharacteristic::PROPERTY_WRITE
    );
    pRxCharacteristic->setCallbacks(new RxCallbacks());

    pService->start();

    BLEAdvertising* pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);
    pAdvertising->start();
    Serial.println("BLE advertising started — connect with nRF Connect or LightBlue");
}

void loop() {
    // Send a heartbeat every 5 seconds while connected
    if (deviceConnected) {
        String msg = "Heartbeat #" + String(msgCount++);
        pTxCharacteristic->setValue(msg);
        pTxCharacteristic->notify();
        delay(5000);
    }

    // Restart advertising after disconnect
    if (!deviceConnected && oldDeviceConnected) {
        delay(500);
        pServer->startAdvertising();
        Serial.println("Restarted advertising");
    }
    oldDeviceConnected = deviceConnected;

    delay(100);
}
