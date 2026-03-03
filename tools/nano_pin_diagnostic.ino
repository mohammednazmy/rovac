/*
 * Nano Pin Connectivity Test v3
 *
 * Reads D2-D5 plus D6-D9 plus A0-A5 to find where encoder wires actually go.
 * Prints ALL pin states so we can find the encoders wherever they may be.
 *
 * Also: if you disconnect one encoder wire and reconnect it, the pin
 * that changes is the one that wire is connected to.
 */

const int dPins[] = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12};
const int numDPins = 11;
const int aPins[] = {A0, A1, A2, A3, A4, A5};
const int numAPins = 6;

unsigned long transitions[11] = {0};
int prevD[11] = {0};
unsigned long lastPrint = 0;

void setup() {
  Serial.begin(115200);
  pinMode(13, OUTPUT);

  for (int i = 0; i < 5; i++) {
    digitalWrite(13, HIGH); delay(50);
    digitalWrite(13, LOW); delay(50);
  }

  delay(200);
  Serial.println();
  Serial.println(F("=== PIN CONNECTIVITY TEST v3 ==="));
  Serial.println(F("Reading ALL digital and analog pins"));
  Serial.println(F("Spin a wheel by hand to find which pin responds"));
  Serial.println();

  for (int i = 0; i < numDPins; i++) {
    pinMode(dPins[i], INPUT_PULLUP);
    prevD[i] = digitalRead(dPins[i]);
  }
  for (int i = 0; i < numAPins; i++) {
    pinMode(aPins[i], INPUT_PULLUP);
  }
}

void loop() {
  // Track transitions on all digital pins
  for (int i = 0; i < numDPins; i++) {
    int val = digitalRead(dPins[i]);
    if (val != prevD[i]) {
      transitions[i]++;
      prevD[i] = val;
    }
  }

  unsigned long now = millis();
  if (now - lastPrint >= 500) {
    lastPrint = now;

    // Digital pins D2-D12
    Serial.print(F("D:"));
    for (int i = 0; i < numDPins; i++) {
      Serial.print(F(" D"));
      Serial.print(dPins[i]);
      Serial.print('=');
      Serial.print(digitalRead(dPins[i]) ? '1' : '0');
    }

    // Edge counts (only non-zero)
    bool anyEdge = false;
    for (int i = 0; i < numDPins; i++) {
      if (transitions[i] > 0) {
        if (!anyEdge) { Serial.print(F(" | EDGES:")); anyEdge = true; }
        Serial.print(F(" D"));
        Serial.print(dPins[i]);
        Serial.print('=');
        Serial.print(transitions[i]);
      }
    }

    // Analog pins A0-A5 (raw ADC 0-1023)
    Serial.print(F(" | A:"));
    for (int i = 0; i < numAPins; i++) {
      Serial.print(F(" A"));
      Serial.print(i);
      Serial.print('=');
      Serial.print(analogRead(aPins[i]));
    }

    Serial.println();
    digitalWrite(13, !digitalRead(13));
  }
}
