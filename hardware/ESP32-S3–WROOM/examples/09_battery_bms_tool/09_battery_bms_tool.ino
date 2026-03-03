/*
 * 09_battery_bms_tool.ino — Smart Battery (bq20z451) Diagnostic & Recovery Tool
 *
 * Communicates with laptop battery BMS chips over SMBus (I2C) to:
 *   - Read battery status, voltage, current, SOC, temperature
 *   - Read individual cell voltages
 *   - Detect Permanent Failure (PF) flags
 *   - Unseal the BMS and clear PF flags to recover locked-out batteries
 *
 * Designed for Apple MacBook batteries using TI bq20z451 gas gauge.
 * Tested on: A1322, A1493, A1582
 *
 * Board:   Lonely Binary ESP32-S3 WROOM (2518V5)
 * Pins:    GPIO8 (SDA), GPIO9 (SCL) — same as example 05
 * Wiring:  Battery SDA (pin 6) → GPIO8, Battery SCL (pin 4) → GPIO9
 *          Battery GND (pins 1-3) → ESP32 GND
 *          4.7kΩ pull-up from SDA to 3.3V
 *          4.7kΩ pull-up from SCL to 3.3V
 *          DO NOT connect ESP32 3.3V to battery VBAT
 *
 * Usage:   Open Serial Monitor at 115200 baud.
 *          Type commands and press Enter:
 *            scan    — Scan I2C bus for devices
 *            status  — Read full battery status
 *            cells   — Read individual cell voltages
 *            pf      — Read Permanent Failure status
 *            unseal  — Unseal the BMS (required before clearing PF)
 *            clearpf — Clear Permanent Failure flags (must unseal first)
 *            seal    — Re-seal the BMS after changes
 *            wake    — Attempt full wake sequence (unseal + clear PF + seal)
 *            help    — Show available commands
 *
 * SAFETY:  This tool modifies BMS registers. Only use on batteries you own.
 *          Incorrect commands can permanently damage the BMS.
 *          Always re-seal the BMS after making changes.
 */

#include <Wire.h>

// Smart Battery System (SBS) address
const uint8_t SBS_ADDR = 0x0B;  // 7-bit address (0x16 in 8-bit)

// SBS Standard Commands
const uint8_t CMD_MANUFACTURER_ACCESS = 0x00;
const uint8_t CMD_REMAINING_CAPACITY_ALARM = 0x01;
const uint8_t CMD_REMAINING_TIME_ALARM = 0x02;
const uint8_t CMD_BATTERY_MODE = 0x03;
const uint8_t CMD_AT_RATE = 0x04;
const uint8_t CMD_AT_RATE_TIME_TO_FULL = 0x05;
const uint8_t CMD_AT_RATE_TIME_TO_EMPTY = 0x06;
const uint8_t CMD_AT_RATE_OK = 0x07;
const uint8_t CMD_TEMPERATURE = 0x08;
const uint8_t CMD_VOLTAGE = 0x09;
const uint8_t CMD_CURRENT = 0x0A;
const uint8_t CMD_AVERAGE_CURRENT = 0x0B;
const uint8_t CMD_MAX_ERROR = 0x0C;
const uint8_t CMD_REL_STATE_OF_CHARGE = 0x0D;
const uint8_t CMD_ABS_STATE_OF_CHARGE = 0x0E;
const uint8_t CMD_REMAINING_CAPACITY = 0x0F;
const uint8_t CMD_FULL_CHARGE_CAPACITY = 0x10;
const uint8_t CMD_RUN_TIME_TO_EMPTY = 0x11;
const uint8_t CMD_AVG_TIME_TO_EMPTY = 0x12;
const uint8_t CMD_AVG_TIME_TO_FULL = 0x13;
const uint8_t CMD_CHARGING_CURRENT = 0x14;
const uint8_t CMD_CHARGING_VOLTAGE = 0x15;
const uint8_t CMD_BATTERY_STATUS = 0x16;
const uint8_t CMD_CYCLE_COUNT = 0x17;
const uint8_t CMD_DESIGN_CAPACITY = 0x18;
const uint8_t CMD_DESIGN_VOLTAGE = 0x19;
const uint8_t CMD_SPEC_INFO = 0x1A;
const uint8_t CMD_MANUFACTURE_DATE = 0x1B;
const uint8_t CMD_SERIAL_NUMBER = 0x1C;
const uint8_t CMD_MANUFACTURER_NAME = 0x20;
const uint8_t CMD_DEVICE_NAME = 0x21;
const uint8_t CMD_DEVICE_CHEMISTRY = 0x22;

// TI bq20z451 Extended Commands
const uint8_t CMD_CELL_VOLTAGE_4 = 0x3C;
const uint8_t CMD_CELL_VOLTAGE_3 = 0x3D;
const uint8_t CMD_CELL_VOLTAGE_2 = 0x3E;
const uint8_t CMD_CELL_VOLTAGE_1 = 0x3F;
const uint8_t CMD_PF_STATUS = 0x53;
const uint8_t CMD_OPERATION_STATUS = 0x54;

// bq20z451 ManufacturerAccess sub-commands
const uint16_t MA_UNSEAL_KEY1 = 0x0414;
const uint16_t MA_UNSEAL_KEY2 = 0x3672;
const uint16_t MA_FULL_ACCESS_KEY1 = 0xFFFF;
const uint16_t MA_FULL_ACCESS_KEY2 = 0xFFFF;
const uint16_t MA_PF_CLEAR_KEY1 = 0x2673;
const uint16_t MA_PF_CLEAR_KEY2 = 0x1712;
const uint16_t MA_SEAL = 0x0020;

// A1493/A1582: SDA=pin5→GPIO10, SCL=pin4→GPIO8
// A1322:       SDA=pin6→GPIO8,  SCL=pin4→GPIO9
const int SDA_PIN = 10;
const int SCL_PIN = 8;

String inputBuffer = "";

// --- Low-level SMBus read/write ---

int16_t readWord(uint8_t cmd, bool verbose = false) {
    Wire.beginTransmission(SBS_ADDR);
    Wire.write(cmd);
    uint8_t err = Wire.endTransmission(false);
    if (err != 0) {
        if (verbose) Serial.printf("  [read err %d on cmd 0x%02X]\n", err, cmd);
        return -1;
    }

    uint8_t got = Wire.requestFrom(SBS_ADDR, (uint8_t)2);
    if (Wire.available() < 2) {
        if (verbose) Serial.printf("  [read: got %d bytes for cmd 0x%02X, need 2]\n", Wire.available(), cmd);
        return -1;
    }

    uint8_t lo = Wire.read();
    uint8_t hi = Wire.read();
    return (int16_t)((hi << 8) | lo);
}

bool writeWord(uint8_t cmd, uint16_t value) {
    Wire.beginTransmission(SBS_ADDR);
    Wire.write(cmd);
    Wire.write(value & 0xFF);        // low byte first (SMBus)
    Wire.write((value >> 8) & 0xFF); // high byte
    uint8_t err = Wire.endTransmission();
    if (err != 0) {
        Serial.printf("  [I2C write error %d: ", err);
        if (err == 1) Serial.print("data too long");
        else if (err == 2) Serial.print("NACK on address");
        else if (err == 3) Serial.print("NACK on data");
        else if (err == 4) Serial.print("other error");
        else if (err == 5) Serial.print("timeout");
        Serial.printf(" — cmd=0x%02X val=0x%04X]\n", cmd, value);
    }
    return (err == 0);
}

String readBlock(uint8_t cmd) {
    Wire.beginTransmission(SBS_ADDR);
    Wire.write(cmd);
    uint8_t err = Wire.endTransmission(false);
    if (err != 0) return "(error)";

    Wire.requestFrom(SBS_ADDR, (uint8_t)32);
    if (Wire.available() == 0) return "(no data)";

    uint8_t len = Wire.read();
    if (len > 31) len = 31;

    String result = "";
    for (uint8_t i = 0; i < len && Wire.available(); i++) {
        char c = Wire.read();
        if (c >= 32 && c < 127) result += c;
    }
    return result;
}

// --- Command Handlers ---

// Bus recovery: toggle SCL 9 times to clear stuck slave
void busRecovery(int sdaPin, int sclPin) {
    Wire.end();
    pinMode(sclPin, OUTPUT);
    pinMode(sdaPin, INPUT_PULLUP);
    for (int i = 0; i < 9; i++) {
        digitalWrite(sclPin, LOW);
        delayMicroseconds(50);
        digitalWrite(sclPin, HIGH);
        delayMicroseconds(50);
    }
    // Send STOP condition
    pinMode(sdaPin, OUTPUT);
    digitalWrite(sdaPin, LOW);
    delayMicroseconds(50);
    digitalWrite(sclPin, HIGH);
    delayMicroseconds(50);
    digitalWrite(sdaPin, HIGH);
    delayMicroseconds(50);
}

int scanBus(int sdaPin, int sclPin, uint32_t clockHz) {
    Wire.end();
    delay(50);
    Wire.begin(sdaPin, sclPin);
    Wire.setClock(clockHz);
    delay(100);

    int found = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        uint8_t err = Wire.endTransmission();
        if (err == 0) {
            Serial.printf("    FOUND 0x%02X at %dkHz (SDA=GPIO%d, SCL=GPIO%d)",
                          addr, (int)(clockHz/1000), sdaPin, sclPin);
            if (addr == 0x0B) Serial.print(" <-- Smart Battery!");
            Serial.println();
            found++;
        }
    }
    return found;
}

void cmdScan() {
    Serial.println("\n=== I2C Bus Scan (Comprehensive) ===");

    // Pin combinations to try: {SDA, SCL}
    // GPIO8 and GPIO9 are the two connected pins
    int pinPairs[][2] = { {8, 9}, {9, 8} };
    uint32_t speeds[] = { 10000, 25000, 50000, 100000 };
    const char* speedNames[] = { "10", "25", "50", "100" };

    int totalFound = 0;

    for (int p = 0; p < 2; p++) {
        int sda = pinPairs[p][0];
        int scl = pinPairs[p][1];
        Serial.printf("\n  --- SDA=GPIO%d, SCL=GPIO%d ---\n", sda, scl);

        // Bus recovery before trying this pin pair
        busRecovery(sda, scl);
        delay(100);

        for (int s = 0; s < 4; s++) {
            Serial.printf("  Scanning at %skHz... ", speedNames[s]);
            int found = scanBus(sda, scl, speeds[s]);
            if (found == 0) {
                Serial.println("nothing");
            }
            totalFound += found;
        }
    }

    // Restore original configuration
    Wire.end();
    delay(50);
    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(100000);

    Serial.println();
    if (totalFound == 0) {
        Serial.println("  NO DEVICES FOUND on any combination!");
        Serial.println("  Possible causes:");
        Serial.println("  1. BMS in shutdown mode (cells need more charge)");
        Serial.println("  2. Pin 5 (SYS_DETECT) needs different state");
        Serial.println("  3. BMS chip is dead (blown fuse)");
        Serial.println("  4. Signal pins might be on pin 5 (try 'scan3' command)");
    } else {
        Serial.printf("  Total: %d device(s) found\n", totalFound);
    }
}

void cmdStatus() {
    Serial.println("\n=== Battery Status ===");

    // Identity
    String mfr = readBlock(CMD_MANUFACTURER_NAME);
    String dev = readBlock(CMD_DEVICE_NAME);
    String chem = readBlock(CMD_DEVICE_CHEMISTRY);
    Serial.printf("  Manufacturer:    %s\n", mfr.c_str());
    Serial.printf("  Device Name:     %s\n", dev.c_str());
    Serial.printf("  Chemistry:       %s\n", chem.c_str());

    int16_t serial = readWord(CMD_SERIAL_NUMBER);
    if (serial >= 0) Serial.printf("  Serial Number:   %d\n", serial);

    int16_t date = readWord(CMD_MANUFACTURE_DATE);
    if (date >= 0) {
        int year = 1980 + ((date >> 9) & 0x7F);
        int month = (date >> 5) & 0x0F;
        int day = date & 0x1F;
        Serial.printf("  Manufacture Date: %04d-%02d-%02d\n", year, month, day);
    }

    // Electrical
    Serial.println("\n--- Electrical ---");
    int16_t voltage = readWord(CMD_VOLTAGE);
    if (voltage >= 0) Serial.printf("  Pack Voltage:    %d mV (%.2f V)\n", voltage, voltage / 1000.0);

    int16_t current = readWord(CMD_CURRENT);
    if (current != -1) Serial.printf("  Current:         %d mA\n", current);

    int16_t avgCurrent = readWord(CMD_AVERAGE_CURRENT);
    if (avgCurrent != -1) Serial.printf("  Avg Current:     %d mA\n", avgCurrent);

    int16_t temp = readWord(CMD_TEMPERATURE);
    if (temp >= 0) Serial.printf("  Temperature:     %.1f °C (%.1f °F)\n",
                                  (temp / 10.0) - 273.15,
                                  ((temp / 10.0) - 273.15) * 9.0/5.0 + 32.0);

    // Capacity
    Serial.println("\n--- Capacity ---");
    int16_t rsoc = readWord(CMD_REL_STATE_OF_CHARGE);
    if (rsoc >= 0) Serial.printf("  Relative SOC:    %d%%\n", rsoc);

    int16_t asoc = readWord(CMD_ABS_STATE_OF_CHARGE);
    if (asoc >= 0) Serial.printf("  Absolute SOC:    %d%%\n", asoc);

    int16_t remainCap = readWord(CMD_REMAINING_CAPACITY);
    if (remainCap >= 0) Serial.printf("  Remaining:       %d mAh\n", remainCap);

    int16_t fullCap = readWord(CMD_FULL_CHARGE_CAPACITY);
    if (fullCap >= 0) Serial.printf("  Full Charge Cap: %d mAh\n", fullCap);

    int16_t designCap = readWord(CMD_DESIGN_CAPACITY);
    if (designCap >= 0) Serial.printf("  Design Capacity: %d mAh\n", designCap);

    int16_t designVolt = readWord(CMD_DESIGN_VOLTAGE);
    if (designVolt >= 0) Serial.printf("  Design Voltage:  %d mV\n", designVolt);

    int16_t cycles = readWord(CMD_CYCLE_COUNT);
    if (cycles >= 0) Serial.printf("  Cycle Count:     %d\n", cycles);

    // Charging parameters
    Serial.println("\n--- Charging ---");
    int16_t chgCurrent = readWord(CMD_CHARGING_CURRENT);
    if (chgCurrent >= 0) Serial.printf("  Charging Current: %d mA\n", chgCurrent);

    int16_t chgVoltage = readWord(CMD_CHARGING_VOLTAGE);
    if (chgVoltage >= 0) Serial.printf("  Charging Voltage: %d mV (%.2f V)\n", chgVoltage, chgVoltage / 1000.0);

    // Battery status register
    int16_t battStatus = readWord(CMD_BATTERY_STATUS);
    if (battStatus >= 0) {
        Serial.printf("  Status Register:  0x%04X\n", (uint16_t)battStatus);
        if (battStatus & 0x0010) Serial.println("    [FD] Fully Discharged");
        if (battStatus & 0x0020) Serial.println("    [FC] Fully Charged");
        if (battStatus & 0x0040) Serial.println("    [DSG] Discharging");
        if (battStatus & 0x0080) Serial.println("    [INIT] Initialized");
        if (battStatus & 0x0100) Serial.println("    [RTA] Remaining Time Alarm");
        if (battStatus & 0x0200) Serial.println("    [RCA] Remaining Capacity Alarm");
        if (battStatus & 0x0800) Serial.println("    [TDA] Terminate Discharge Alarm");
        if (battStatus & 0x1000) Serial.println("    [OTA] Over Temperature Alarm");
        if (battStatus & 0x8000) Serial.println("    [OCA] Over Charged Alarm");
    }
}

void cmdCells() {
    Serial.println("\n=== Cell Voltages ===");

    int16_t cell1 = readWord(CMD_CELL_VOLTAGE_1);
    int16_t cell2 = readWord(CMD_CELL_VOLTAGE_2);
    int16_t cell3 = readWord(CMD_CELL_VOLTAGE_3);
    int16_t cell4 = readWord(CMD_CELL_VOLTAGE_4);

    if (cell1 >= 0) Serial.printf("  Cell 1: %d mV (%.3f V)\n", cell1, cell1 / 1000.0);
    if (cell2 >= 0) Serial.printf("  Cell 2: %d mV (%.3f V)\n", cell2, cell2 / 1000.0);
    if (cell3 >= 0) Serial.printf("  Cell 3: %d mV (%.3f V)\n", cell3, cell3 / 1000.0);
    if (cell4 >= 0 && cell4 > 0) Serial.printf("  Cell 4: %d mV (%.3f V)\n", cell4, cell4 / 1000.0);

    if (cell1 >= 0 && cell2 >= 0 && cell3 >= 0) {
        int16_t maxV = max(cell1, max(cell2, cell3));
        int16_t minV = min(cell1, min(cell2, cell3));
        Serial.printf("  Imbalance: %d mV (max - min)\n", maxV - minV);
        if (maxV - minV > 200) {
            Serial.println("  WARNING: Cell imbalance > 200mV — cells are significantly unbalanced");
        } else if (maxV - minV > 50) {
            Serial.println("  NOTE: Moderate imbalance — balance charging recommended");
        } else {
            Serial.println("  OK: Cells are well balanced");
        }
    }
}

void cmdPFStatus() {
    Serial.println("\n=== Permanent Failure Status ===");

    int16_t pfStatus = readWord(CMD_PF_STATUS, true);
    if (pfStatus < 0) {
        Serial.println("  Could not read PFStatus (BMS may be sealed or unpowered)");
        return;
    }

    Serial.printf("  PFStatus Register: 0x%04X\n", (uint16_t)pfStatus);

    if (pfStatus == 0) {
        Serial.println("  No Permanent Failure flags set — PF is NOT the problem");
    } else {
        Serial.println("  PERMANENT FAILURE FLAGS DETECTED:");
        if (pfStatus & 0x0001) Serial.println("    [SUV]  Safety Under Voltage");
        if (pfStatus & 0x0002) Serial.println("    [SOV]  Safety Over Voltage");
        if (pfStatus & 0x0004) Serial.println("    [SOT]  Safety Over Temperature (charge)");
        if (pfStatus & 0x0008) Serial.println("    [SOTF] Safety Over Temperature (FET)");
        if (pfStatus & 0x0010) Serial.println("    [SOC]  Safety Over Current (charge)");
        if (pfStatus & 0x0020) Serial.println("    [SOCD] Safety Over Current (discharge)");
        if (pfStatus & 0x0040) Serial.println("    [AFE]  AFE Communication Failure");
        if (pfStatus & 0x0080) Serial.println("    [OPEN] Open Thermistor");
        if (pfStatus & 0x0100) Serial.println("    [FUSE] Chemical Fuse Blown");
        if (pfStatus & 0x0200) Serial.println("    [VIMR] Voltage Imbalance at Rest");
        if (pfStatus & 0x0400) Serial.println("    [VIMA] Voltage Imbalance Active");
        if (pfStatus & 0x0800) Serial.println("    [QIM]  Charge Imbalance");
        if (pfStatus & 0x1000) Serial.println("    [CB]   Cell Balancing Error");
        if (pfStatus & 0x2000) Serial.println("    [IMP]  Impedance Failure");
        if (pfStatus & 0x4000) Serial.println("    [CTO]  Capacity Timeout");
        if (pfStatus & 0x8000) Serial.println("    [PCHG] Pre-charge Timeout");

        if (pfStatus & 0x0100) {
            Serial.println("\n  *** FUSE FLAG SET — chemical fuse may be blown ***");
            Serial.println("  If fuse is physically blown, battery cannot be recovered");
            Serial.println("  If fuse is intact, clearing PF may restore operation");
        }

        Serial.println("\n  To attempt recovery: type 'wake' to run full wake sequence");
    }

    // Also read Operation Status
    int16_t opStatus = readWord(CMD_OPERATION_STATUS);
    if (opStatus >= 0) {
        Serial.printf("\n  OperationStatus: 0x%04X\n", (uint16_t)opStatus);
        if (opStatus & 0x0001) Serial.println("    [PRES] Battery Present");
        if (opStatus & 0x0002) Serial.println("    [DSG]  Discharge FET ON");
        if (opStatus & 0x0004) Serial.println("    [CHG]  Charge FET ON");
        if (opStatus & 0x0010) Serial.println("    [XDSGI] Discharge Disabled");
        if (opStatus & 0x0020) Serial.println("    [XCHGI] Charge Disabled");
        if (opStatus & 0x0200) Serial.println("    [PCHG] Pre-charge FET ON");
        if (opStatus & 0x4000) Serial.println("    [SS]   Sealed State");
        if (opStatus & 0x8000) Serial.println("    [FAS]  Full Access State");

        bool chgFET = opStatus & 0x0004;
        bool dsgFET = opStatus & 0x0002;
        Serial.printf("\n  Charge FET: %s | Discharge FET: %s\n",
                      chgFET ? "ON (closed)" : "OFF (open)",
                      dsgFET ? "ON (closed)" : "OFF (open)");

        if (!chgFET && !dsgFET) {
            Serial.println("  Both FETs are OPEN — this is why the battery reads 0V on the terminals");
        }
    }
}

void cmdUnseal() {
    Serial.println("\n=== Unsealing BMS ===");

    // Verify device is present first
    Wire.beginTransmission(SBS_ADDR);
    uint8_t check = Wire.endTransmission();
    if (check != 0) {
        Serial.printf("  BMS not responding (error %d). Is charger connected?\n", check);
        return;
    }
    Serial.println("  BMS present at 0x0B. Sending unseal keys...");

    Serial.println("  Sending unseal keys (TI default: 0x0414, 0x3672)...");

    delay(200);
    bool ok1 = writeWord(CMD_MANUFACTURER_ACCESS, MA_UNSEAL_KEY1);
    delay(200);
    bool ok2 = writeWord(CMD_MANUFACTURER_ACCESS, MA_UNSEAL_KEY2);
    delay(200);

    if (ok1 && ok2) {
        Serial.println("  Unseal keys sent.");
    } else {
        Serial.println("  ERROR: Failed to send unseal keys");
        return;
    }

    // Send Full Access keys
    Serial.println("  Sending Full Access keys (0xFFFF, 0xFFFF)...");
    delay(50);
    bool ok3 = writeWord(CMD_MANUFACTURER_ACCESS, MA_FULL_ACCESS_KEY1);
    delay(50);
    bool ok4 = writeWord(CMD_MANUFACTURER_ACCESS, MA_FULL_ACCESS_KEY2);
    delay(100);

    if (ok3 && ok4) {
        Serial.println("  Full Access keys sent.");
    } else {
        Serial.println("  ERROR: Failed to send Full Access keys");
    }

    // Verify
    int16_t opStatus = readWord(CMD_OPERATION_STATUS);
    if (opStatus >= 0) {
        bool sealed = opStatus & 0x4000;
        bool fullAccess = opStatus & 0x8000;
        Serial.printf("  OperationStatus: 0x%04X\n", (uint16_t)opStatus);
        Serial.printf("  Sealed: %s | Full Access: %s\n",
                      sealed ? "YES (unseal FAILED)" : "NO (unsealed OK)",
                      fullAccess ? "YES (full access OK)" : "NO");
    }
}

void cmdClearPF() {
    Serial.println("\n=== Clearing Permanent Failure Flags ===");
    Serial.println("  WARNING: Only do this if you understand the implications!");
    Serial.println("  Sending PF clear keys (0x2673, 0x1712)...");

    delay(100);
    bool ok1 = writeWord(CMD_MANUFACTURER_ACCESS, MA_PF_CLEAR_KEY1);
    delay(50);
    bool ok2 = writeWord(CMD_MANUFACTURER_ACCESS, MA_PF_CLEAR_KEY2);
    delay(500);

    if (ok1 && ok2) {
        Serial.println("  PF clear keys sent. Reading PFStatus...");
        delay(200);
        int16_t pfStatus = readWord(CMD_PF_STATUS);
        if (pfStatus >= 0) {
            Serial.printf("  PFStatus: 0x%04X\n", (uint16_t)pfStatus);
            if (pfStatus == 0) {
                Serial.println("  SUCCESS: All PF flags cleared!");
            } else {
                Serial.println("  Some PF flags remain — may need power cycle or physical issue");
            }
        }
    } else {
        Serial.println("  ERROR: Failed to send PF clear keys");
        Serial.println("  Make sure BMS is unsealed first (type 'unseal')");
    }
}

void cmdSeal() {
    Serial.println("\n=== Re-sealing BMS ===");
    bool ok = writeWord(CMD_MANUFACTURER_ACCESS, MA_SEAL);
    delay(100);
    if (ok) {
        Serial.println("  Seal command sent.");
        int16_t opStatus = readWord(CMD_OPERATION_STATUS);
        if (opStatus >= 0) {
            bool sealed = opStatus & 0x4000;
            Serial.printf("  Sealed: %s\n", sealed ? "YES (sealed OK)" : "NO (seal may need power cycle)");
        }
    } else {
        Serial.println("  ERROR: Failed to send seal command");
    }
}

void cmdWake() {
    Serial.println("\n========================================");
    Serial.println("  FULL WAKE SEQUENCE");
    Serial.println("========================================\n");

    // Step 1: Scan
    Serial.println("[1/6] Scanning for BMS...");
    Wire.beginTransmission(SBS_ADDR);
    if (Wire.endTransmission() != 0) {
        Serial.println("  BMS not responding at 0x0B!");
        Serial.println("  The BMS IC may not have enough power.");
        Serial.println("  Try the body-diode NiMH trickle charge first.");
        return;
    }
    Serial.println("  BMS found at 0x0B\n");

    // Step 2: Read current state
    Serial.println("[2/6] Reading battery state...");
    int16_t voltage = readWord(CMD_VOLTAGE);
    int16_t pfStatus = readWord(CMD_PF_STATUS);
    int16_t opStatus = readWord(CMD_OPERATION_STATUS);

    if (voltage >= 0) Serial.printf("  Voltage: %d mV\n", voltage);
    if (pfStatus >= 0) Serial.printf("  PFStatus: 0x%04X\n", (uint16_t)pfStatus);
    if (opStatus >= 0) Serial.printf("  OpStatus: 0x%04X\n", (uint16_t)opStatus);

    bool hasPF = (pfStatus > 0);
    bool fetsOpen = opStatus >= 0 && !(opStatus & 0x0002) && !(opStatus & 0x0004);

    if (!hasPF && !fetsOpen) {
        Serial.println("\n  Battery appears OK — no PF flags, FETs should be on");
        Serial.println("  Try the SYS_DETECT trick or measure voltage again");
        return;
    }

    if (hasPF) {
        Serial.printf("\n  PF flags detected (0x%04X) — attempting clear...\n", (uint16_t)pfStatus);
    } else {
        Serial.println("\n  No PF flags but FETs are open — attempting unseal + reset...");
    }

    // Step 3: Unseal
    Serial.println("\n[3/6] Unsealing BMS...");
    delay(5000);  // Wait 5 seconds with no SMBus activity first
    writeWord(CMD_MANUFACTURER_ACCESS, MA_UNSEAL_KEY1);
    delay(50);
    writeWord(CMD_MANUFACTURER_ACCESS, MA_UNSEAL_KEY2);
    delay(100);
    writeWord(CMD_MANUFACTURER_ACCESS, MA_FULL_ACCESS_KEY1);
    delay(50);
    writeWord(CMD_MANUFACTURER_ACCESS, MA_FULL_ACCESS_KEY2);
    delay(200);

    opStatus = readWord(CMD_OPERATION_STATUS);
    bool sealed = (opStatus >= 0) && (opStatus & 0x4000);
    Serial.printf("  Sealed: %s\n", sealed ? "YES (unseal failed — keys may be custom)" : "NO (unsealed OK)");

    if (sealed) {
        Serial.println("  Cannot proceed without unsealing. Apple may have changed the keys.");
        Serial.println("  Try alternative keys or use a professional tool (MBRT/NLBA1).");
        return;
    }

    // Step 4: Clear PF
    Serial.println("\n[4/6] Clearing Permanent Failure flags...");
    writeWord(CMD_MANUFACTURER_ACCESS, MA_PF_CLEAR_KEY1);
    delay(50);
    writeWord(CMD_MANUFACTURER_ACCESS, MA_PF_CLEAR_KEY2);
    delay(500);

    pfStatus = readWord(CMD_PF_STATUS);
    Serial.printf("  PFStatus after clear: 0x%04X\n", (uint16_t)pfStatus);
    if (pfStatus == 0) {
        Serial.println("  PF flags cleared successfully!");
    } else {
        Serial.println("  Some flags remain — may indicate physical damage");
    }

    // Step 5: Re-seal
    Serial.println("\n[5/6] Re-sealing BMS...");
    writeWord(CMD_MANUFACTURER_ACCESS, MA_SEAL);
    delay(200);
    Serial.println("  Seal command sent.");

    // Step 6: Final check
    Serial.println("\n[6/6] Final status check...");
    delay(500);
    voltage = readWord(CMD_VOLTAGE);
    opStatus = readWord(CMD_OPERATION_STATUS);
    pfStatus = readWord(CMD_PF_STATUS);

    Serial.println("\n========================================");
    Serial.println("  RESULTS");
    Serial.println("========================================");
    if (voltage >= 0) Serial.printf("  Voltage:  %d mV (%.2f V)\n", voltage, voltage / 1000.0);
    if (pfStatus >= 0) Serial.printf("  PFStatus: 0x%04X %s\n", (uint16_t)pfStatus,
                                      pfStatus == 0 ? "(clean)" : "(flags remain)");
    if (opStatus >= 0) {
        bool chgFET = opStatus & 0x0004;
        bool dsgFET = opStatus & 0x0002;
        Serial.printf("  Charge FET: %s\n", chgFET ? "ON" : "OFF");
        Serial.printf("  Discharge FET: %s\n", dsgFET ? "ON" : "OFF");

        if (chgFET || dsgFET) {
            Serial.println("\n  SUCCESS! FETs are now ON — battery should output voltage!");
            Serial.println("  Disconnect ESP32 and measure with multimeter.");
            Serial.println("  Then charge with B6 V2: LiPo, 3S, 1.0A");
        } else {
            Serial.println("\n  FETs still off. Possible causes:");
            Serial.println("  - BMS needs a power cycle (disconnect and reconnect cell voltage)");
            Serial.println("  - Cell voltage too low for BMS to enable FETs");
            Serial.println("  - Physical fuse blown");
            Serial.println("  Try the body-diode NiMH trickle charge, then run 'wake' again.");
        }
    }
}

void cmdDiag() {
    Serial.println("\n=== Full Diagnostic (unseal + read all) ===");

    // Check presence
    Wire.beginTransmission(SBS_ADDR);
    if (Wire.endTransmission() != 0) {
        Serial.println("  BMS not responding!");
        return;
    }
    Serial.println("  BMS found at 0x0B");

    // Unseal
    Serial.println("  Unsealing...");
    writeWord(CMD_MANUFACTURER_ACCESS, MA_UNSEAL_KEY1);
    delay(200);
    writeWord(CMD_MANUFACTURER_ACCESS, MA_UNSEAL_KEY2);
    delay(200);
    writeWord(CMD_MANUFACTURER_ACCESS, MA_FULL_ACCESS_KEY1);
    delay(200);
    writeWord(CMD_MANUFACTURER_ACCESS, MA_FULL_ACCESS_KEY2);
    delay(500);

    // Now immediately read everything at slow clock
    Serial.println("\n  --- Standard SBS Registers ---");
    int16_t v;
    v = readWord(0x09); if (v>=0) Serial.printf("  Voltage:     %d mV\n", v);
    v = readWord(0x0A); if (v!=-1) Serial.printf("  Current:     %d mA\n", v);
    v = readWord(0x0D); if (v>=0) Serial.printf("  RelSOC:      %d%%\n", v);
    v = readWord(0x0F); if (v>=0) Serial.printf("  RemainCap:   %d mAh\n", v);
    v = readWord(0x10); if (v>=0) Serial.printf("  FullCap:     %d mAh\n", v);
    v = readWord(0x17); if (v>=0) Serial.printf("  Cycles:      %d\n", v);

    Serial.println("\n  --- Extended Registers ---");
    v = readWord(0x3F, true); if (v>=0) Serial.printf("  Cell 1:      %d mV\n", v);
    v = readWord(0x3E, true); if (v>=0) Serial.printf("  Cell 2:      %d mV\n", v);
    v = readWord(0x3D, true); if (v>=0) Serial.printf("  Cell 3:      %d mV\n", v);

    Serial.println("\n  --- Safety & Status ---");
    v = readWord(0x50, true); Serial.printf("  SafetyAlert:  0x%04X %s\n", (uint16_t)v, v==0?"(clean)":"(FLAGS!)");
    v = readWord(0x51, true); Serial.printf("  SafetyStatus: 0x%04X %s\n", (uint16_t)v, v==0?"(clean)":"(FLAGS!)");
    v = readWord(0x53, true); Serial.printf("  PFStatus:     0x%04X %s\n", (uint16_t)v, v==0?"(clean)":"(FLAGS!)");
    v = readWord(0x54, true);
    if (v >= 0) {
        Serial.printf("  OpStatus:     0x%04X\n", (uint16_t)v);
        Serial.printf("    CHG FET:  %s\n", (v & 0x0004) ? "ON" : "OFF");
        Serial.printf("    DSG FET:  %s\n", (v & 0x0002) ? "ON" : "OFF");
        Serial.printf("    Sealed:   %s\n", (v & 0x4000) ? "YES" : "NO");
        Serial.printf("    FullAccs: %s\n", (v & 0x8000) ? "YES" : "NO");
    }

    // Try to force FETs on via ManufacturerAccess
    Serial.println("\n  --- Attempting to enable FETs ---");
    Serial.println("  Sending CHG FET toggle (0x0021)...");
    writeWord(CMD_MANUFACTURER_ACCESS, 0x0021);
    delay(200);
    Serial.println("  Sending DSG FET toggle (0x0022)...");
    writeWord(CMD_MANUFACTURER_ACCESS, 0x0022);
    delay(200);
    Serial.println("  Sending Clear Shutdown (0x0097)...");
    writeWord(CMD_MANUFACTURER_ACCESS, 0x0097);
    delay(500);

    // Re-read operation status
    v = readWord(0x54, true);
    if (v >= 0) {
        Serial.printf("\n  OpStatus NOW: 0x%04X\n", (uint16_t)v);
        Serial.printf("    CHG FET:  %s\n", (v & 0x0004) ? "ON" : "OFF");
        Serial.printf("    DSG FET:  %s\n", (v & 0x0002) ? "ON" : "OFF");
    }

    // Re-seal
    Serial.println("\n  Re-sealing BMS...");
    writeWord(CMD_MANUFACTURER_ACCESS, MA_SEAL);
    delay(200);

    Wire.setClock(100000);
    Serial.println("  Done. Check battery voltage with multimeter!");
}

void cmdReset() {
    Serial.println("\n=== BMS Device Reset ===");
    Serial.println("  This resets the gas gauge to clear latched safety flags.");

    // Check presence
    Wire.beginTransmission(SBS_ADDR);
    if (Wire.endTransmission() != 0) {
        Serial.println("  BMS not responding!");
        return;
    }

    // Read current safety status
    int16_t ss = readWord(0x51);
    Serial.printf("  SafetyStatus before: 0x%04X\n", (uint16_t)ss);
    if (ss == 0) {
        Serial.println("  No safety flags — reset not needed.");
        return;
    }

    // Decode safety flags
    if (ss & 0x0002) Serial.println("    [COV]  Cell Over Voltage (latched)");
    if (ss & 0x0004) Serial.println("    [OCC]  Overcurrent Charge (latched)");
    if (ss & 0x0008) Serial.println("    [OCD]  Overcurrent Discharge (latched)");
    if (ss & 0x0001) Serial.println("    [CUV]  Cell Under Voltage");
    if (ss & 0x0010) Serial.println("    [OTC]  Over Temperature Charge");
    if (ss & 0x0020) Serial.println("    [OTD]  Over Temperature Discharge");
    if (ss & 0x2000) Serial.println("    [Bit13] Charge-related flag");

    // Unseal + Full Access
    Serial.println("\n  Unsealing...");
    writeWord(CMD_MANUFACTURER_ACCESS, MA_UNSEAL_KEY1);
    delay(200);
    writeWord(CMD_MANUFACTURER_ACCESS, MA_UNSEAL_KEY2);
    delay(200);
    writeWord(CMD_MANUFACTURER_ACCESS, MA_FULL_ACCESS_KEY1);
    delay(200);
    writeWord(CMD_MANUFACTURER_ACCESS, MA_FULL_ACCESS_KEY2);
    delay(500);

    // Method 1: Device Reset (ManufacturerAccess 0x0002)
    Serial.println("  Sending Device Reset (0x0002)...");
    writeWord(CMD_MANUFACTURER_ACCESS, 0x0002);
    Serial.println("  Waiting 5 seconds for gauge to restart...");
    delay(5000);

    // Re-check - device should have rebooted
    Wire.beginTransmission(SBS_ADDR);
    uint8_t err = Wire.endTransmission();
    if (err != 0) {
        Serial.printf("  BMS not responding after reset (error %d)\n", err);
        Serial.println("  This is normal — BMS may need charger reconnected to wake up");
        Serial.println("  STOP the charger, wait 5 sec, restart it, then type 'status'");
        return;
    }

    // Read safety status after reset
    ss = readWord(0x51);
    Serial.printf("\n  SafetyStatus after reset: 0x%04X", (uint16_t)ss);
    if (ss == 0) {
        Serial.println(" — CLEARED!");
    } else {
        Serial.println(" — flags remain");
        // Method 2: Try FET control sub-command
        Serial.println("  Trying FET Control (0x0012)...");
        writeWord(CMD_MANUFACTURER_ACCESS, 0x0012);
        delay(500);
        Serial.println("  Trying CHG FET (0x0021) + DSG FET (0x0022)...");
        writeWord(CMD_MANUFACTURER_ACCESS, 0x0021);
        delay(200);
        writeWord(CMD_MANUFACTURER_ACCESS, 0x0022);
        delay(200);
    }

    // Read operation status
    int16_t op = readWord(0x54);
    if (op >= 0) {
        Serial.printf("  OpStatus: 0x%04X\n", (uint16_t)op);
        Serial.printf("    CHG FET: %s\n", (op & 0x0004) ? "ON" : "OFF");
        Serial.printf("    DSG FET: %s\n", (op & 0x0002) ? "ON" : "OFF");
    }

    // Re-seal
    Serial.println("  Re-sealing...");
    writeWord(CMD_MANUFACTURER_ACCESS, MA_SEAL);
    delay(200);

    Serial.println("\n  Done! Check battery voltage with multimeter.");
    Serial.println("  If still 0.07V, try: STOP charger → wait 10 sec → measure again");
}

void cmdScan3() {
    Serial.println("\n=== 3-Pin Scan (requires pin 5 on GPIO10) ===");
    Serial.println("  Disconnect pin 5 from GND, connect to ESP32 GPIO10");
    Serial.println("  Add 4.7k pull-up from GPIO10 to 3.3V");
    Serial.println("  Trying all 6 combinations of 3 pins...\n");

    int pins[] = { 8, 9, 10 };
    const char* pinLabels[] = { "GPIO8", "GPIO9", "GPIO10" };
    uint32_t speeds[] = { 25000, 100000 };
    int totalFound = 0;

    for (int i = 0; i < 3; i++) {
        for (int j = 0; j < 3; j++) {
            if (i == j) continue;
            int sda = pins[i];
            int scl = pins[j];
            // Determine which unused pin to set as input (not interfere)
            for (int k = 0; k < 3; k++) {
                if (k != i && k != j) {
                    pinMode(pins[k], INPUT);  // float unused pin
                }
            }

            Serial.printf("  SDA=%s SCL=%s: ", pinLabels[i], pinLabels[j]);

            busRecovery(sda, scl);
            delay(50);

            bool foundAny = false;
            for (int s = 0; s < 2; s++) {
                int found = scanBus(sda, scl, speeds[s]);
                if (found > 0) {
                    foundAny = true;
                    totalFound += found;
                }
            }
            if (!foundAny) Serial.println("nothing");
        }
    }

    // Restore original
    Wire.end();
    delay(50);
    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(100000);

    if (totalFound == 0) {
        Serial.println("\n  Still nothing on any combination.");
        Serial.println("  BMS is likely dead or in deep shutdown.");
    }
}

void printHelp() {
    Serial.println("\n=== Battery BMS Tool — Commands ===");
    Serial.println("  scan    — Comprehensive scan (both pin orientations, 4 speeds)");
    Serial.println("  scan3   — Try ALL 3 signal pins (connect pin 5 to GPIO10 first)");
    Serial.println("  status  — Full battery status (voltage, capacity, cycles, temp)");
    Serial.println("  cells   — Individual cell voltages");
    Serial.println("  pf      — Read Permanent Failure flags");
    Serial.println("  unseal  — Unseal BMS for register access");
    Serial.println("  clearpf — Clear Permanent Failure flags");
    Serial.println("  seal    — Re-seal BMS (always do this when done)");
    Serial.println("  wake    — Full auto-recovery (scan → unseal → clear PF → seal)");
    Serial.println("  help    — Show this help");
    Serial.println();
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    Wire.begin(SDA_PIN, SCL_PIN);
    Wire.setClock(100000);  // 100 kHz — SMBus standard speed

    Serial.println("==========================================");
    Serial.println(" Battery BMS Tool (bq20z451)");
    Serial.println(" ESP32-S3 WROOM — GPIO8 SDA, GPIO9 SCL");
    Serial.println("==========================================");
    Serial.println();
    Serial.println("Wiring check:");
    Serial.printf("  SDA: GPIO%d → Battery pin 6 (+ 4.7k pull-up to 3.3V)\n", SDA_PIN);
    Serial.printf("  SCL: GPIO%d → Battery pin 4 (+ 4.7k pull-up to 3.3V)\n", SCL_PIN);
    Serial.println("  GND: ESP32 GND → Battery pins 1-3");
    Serial.println();

    // Quick scan at configured pins only (no bus recovery)
    Serial.println("Scanning for BMS at 0x0B...");
    Wire.beginTransmission(SBS_ADDR);
    uint8_t err = Wire.endTransmission();
    if (err == 0) {
        Serial.println("  FOUND bq20z451 at 0x0B!");
    } else {
        Serial.printf("  Not found (error %d). Type 'scan' for comprehensive search.\n", err);
    }
    Serial.println();
    printHelp();
}

void loop() {
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            inputBuffer.trim();
            inputBuffer.toLowerCase();

            if (inputBuffer == "scan")         cmdScan();
            else if (inputBuffer == "scan3")   cmdScan3();
            else if (inputBuffer == "diag")    cmdDiag();
            else if (inputBuffer == "reset")   cmdReset();
            else if (inputBuffer == "status")  cmdStatus();
            else if (inputBuffer == "cells")   cmdCells();
            else if (inputBuffer == "pf")      cmdPFStatus();
            else if (inputBuffer == "unseal")  cmdUnseal();
            else if (inputBuffer == "clearpf") cmdClearPF();
            else if (inputBuffer == "seal")    cmdSeal();
            else if (inputBuffer == "wake")    cmdWake();
            else if (inputBuffer == "help")    printHelp();
            else if (inputBuffer.length() > 0) {
                Serial.printf("Unknown command: '%s' — type 'help' for options\n", inputBuffer.c_str());
            }

            inputBuffer = "";
            Serial.print("\n> ");
        } else {
            inputBuffer += c;
        }
    }
}
