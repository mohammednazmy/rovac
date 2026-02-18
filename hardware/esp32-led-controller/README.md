# ESP32 Blue LED Strip Controller

Control a 12V blue SMD 3528 LED strip via WiFi, Bluetooth, and USB Serial.

## Components Required

| Component | Quantity | Notes |
|-----------|----------|-------|
| ESP32-WROOM-32 (38-pin) | 1 | Your dev board |
| IRLZ44N or IRLB8721 | 1 | Logic-level N-channel MOSFET |
| 1kΩ resistor | 1 | Gate resistor (1/4W) |
| 12V DC power supply | 1 | 2A minimum for 5m strip |
| Blue LED strip (SMD 3528) | 1 | 5m, 300 LEDs |
| Breadboard + jumper wires | - | For prototyping |

## Wiring Diagram

```
                            12V Power Supply
                           ┌───────┴───────┐
                           │  (+)     (-)  │
                           │   │       │   │
                           └───┼───────┼───┘
                               │       │
         ┌─────────────────────┘       │
         │                             │
         │  ┌──────────────────────────┼──────────────────────┐
         │  │                          │                      │
         │  │     BLUE LED STRIP       │                      │
         │  │     (SMD 3528)           │                      │
         │  │                          │                      │
         │  │  (+12V)───────┐    (-)───┼──┐                   │
         │  │  (Red wire)   │  (White) │  │                   │
         │  └───────────────┼──────────┼──┼───────────────────┘
         │                  │          │  │
         └──────────────────┘          │  │
                                       │  │
                                       │  │ LED Strip (-)
                                       │  │
                                       │  ▼
                                       │  ┌─────────────┐
                                       │  │   DRAIN     │
                                       │  │             │
                                       │  │   MOSFET    │◄── IRLZ44N or IRLB8721
                                       │  │  (TO-220)   │
                                       │  │             │
                                       │  │ GATE SOURCE │
                                       │  └──┬──────┬───┘
                                       │     │      │
                                       │     │      │
                                       │   1kΩ      │
                                       │     │      │
                                       │     │      │
    ┌──────────────────────────────────┼─────┼──────┼─────────────────────────────┐
    │                                  │     │      │                             │
    │        ESP32 Dev Board           │     │      │                             │
    │                                  │     │      │                             │
    │   ┌─────────────────────────┐    │     │      │    ┌─────────────────────┐  │
    │   │                         │    │     │      │    │                     │  │
    │   │ 3V3              GPIO23 │    │     │      │    │ GND                 │──┼──┐
    │   │ EN               GPIO22 │    │     │      │    │ GPIO23              │  │  │
    │   │ VP               TX0    │    │     │      │    │ GPIO22              │  │  │
    │   │ VN               RX0    │    │     │      │    │ TX0                 │  │  │
    │   │ D34              GPIO21 │    │     │      │    │ RX0                 │  │  │
    │   │ D35              GND    │    │     │      │    │ GPIO21              │  │  │
    │   │ D32              GPIO19 │    │     │      │    │ GND ────────────────┼──┼──┤
    │   │ D33              GPIO18 │    │     │      │    │ GPIO19              │  │  │
    │   │ D25              GPIO5  │    │     │      │    │ GPIO18              │  │  │
    │   │ D26              GPIO17 │    │     │      │    │ GPIO5               │  │  │
    │   │ D27              GPIO16 │────┼─────┘      │    │ GPIO17              │  │  │
    │   │ D14              GPIO4  │    │            │    │ GPIO16 ─────────────┼──┼──┼── To 1kΩ
    │   │ D12              GPIO0  │    │            │    │ GPIO4               │  │  │
    │   │ GND              GPIO2  │    │            │    │ GPIO0               │  │  │
    │   │ D13              GPIO15 │    │            │    │ GPIO2               │  │  │
    │   │ D9               D8     │    │            │    │ GPIO15              │  │  │
    │   │ D10              D7     │    │            │    │                     │  │  │
    │   │ D11              D6     │    │            │    │                     │  │  │
    │   │ VIN              ───────│    │            │    │                     │  │  │
    │   │                         │    │            │    │                     │  │  │
    │   └─────────────────────────┘    │            │    └─────────────────────┘  │  │
    │              │                   │            │                             │  │
    │              │                   │            │                             │  │
    │           [USB]                  │            │                             │  │
    │              │                   │            │                             │  │
    └──────────────┼───────────────────┼────────────┼─────────────────────────────┘  │
                   │                   │            │                                │
                   │                   │            └──────────────┬─────────────────┘
                   ▼                   │                           │
            To Computer                │                           │
            (Programming               │                           │
             & Serial)                 │                           │
                                       │                           │
                                       └───────────┬───────────────┘
                                                   │
                                                   │
                                              COMMON GND
                                        (All grounds connected)
```

## MOSFET Pinout (IRLZ44N / IRLB8721)

```
      Front View (text facing you)
      ┌─────────────────┐
      │                 │
      │    IRLZ44N      │
      │                 │
      └────┬──┬──┬──────┘
           │  │  │
           │  │  │
           G  D  S
           │  │  │
         Gate │  Source
              │
            Drain

  Pin 1 (G) - Gate   -> Connect to ESP32 GPIO16 via 1kΩ resistor
  Pin 2 (D) - Drain  -> Connect to LED strip negative (-)
  Pin 3 (S) - Source -> Connect to common GND
```

## Step-by-Step Wiring Instructions

### Step 1: Prepare the Breadboard
1. Place the MOSFET on the breadboard with pins in separate rows
2. The flat side with text should face you

### Step 2: Wire the MOSFET
```
ESP32 GPIO16 ──[1kΩ]──► MOSFET Gate (left pin)
ESP32 GND ─────────────► MOSFET Source (right pin)
LED Strip (-) ─────────► MOSFET Drain (middle pin)
```

### Step 3: Wire the Power
```
12V Supply (+) ────────► LED Strip (+) (red wire)
12V Supply (-) ────────► Common GND rail
ESP32 GND ─────────────► Common GND rail
MOSFET Source ─────────► Common GND rail
```

### Step 4: Connect ESP32
```
ESP32 USB ─────────────► Computer (for programming and serial)
```

## Connection Summary Table

| From | To | Wire Color (suggested) |
|------|-----|------------------------|
| 12V Supply (+) | LED Strip (+) | Red |
| 12V Supply (-) | GND rail | Black |
| LED Strip (-) | MOSFET Drain | White |
| MOSFET Source | GND rail | Black |
| MOSFET Gate | 1kΩ resistor | Yellow |
| 1kΩ resistor | ESP32 GPIO16 | Yellow |
| ESP32 GND | GND rail | Black |

## Important Notes

1. **Common Ground**: All grounds (12V supply, ESP32, MOSFET source) MUST be connected together
2. **Do NOT connect 12V to ESP32**: The ESP32 runs on 5V (USB) or 3.3V
3. **MOSFET orientation**: Make sure Gate-Drain-Source pins are correctly identified
4. **Power sequencing**: Connect the LED strip power AFTER wiring is complete
5. **Heat sink**: For continuous full-brightness operation, add a small heatsink to the MOSFET

## Control Methods

### WiFi (Web Interface)
- Connect to the same WiFi network ("Hurry")
- Open browser to http://<ESP32_IP>
- Use the slider or ON/OFF buttons

### WiFi (HTTP API)
```bash
curl http://<ESP32_IP>/on              # Turn on (100%)
curl http://<ESP32_IP>/off             # Turn off
curl "http://<ESP32_IP>/brightness?value=50"  # Set to 50%
curl http://<ESP32_IP>/status          # Get JSON status
```

### Bluetooth
1. Pair phone/computer with "LED_Controller"
2. Use a Bluetooth terminal app
3. Send commands: `on`, `off`, `b 50`, `status`

### USB Serial
```bash
screen /dev/cu.usbserial-0001 115200
# Then type: on, off, b 50, status, help
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| LED doesn't light | Check 12V power supply is on; verify MOSFET wiring |
| LED always on | Gate and Drain might be swapped; check MOSFET orientation |
| No WiFi connection | Verify SSID/password; check serial output for errors |
| ESP32 won't program | Hold BOOT button while uploading; check USB cable |
| Dim LED at 100% | Check 12V supply can deliver enough current (2A+) |

## Files

- `led_strip_controller.ino` - Main Arduino sketch
- `README.md` - This file
