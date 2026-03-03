# NRF24L01+PA+LNA 2.4GHz Wireless Transceiver

## Overview

The NRF24L01+PA+LNA is a long-range 2.4 GHz wireless transceiver module. It uses SPI to communicate with a host MCU (ESP32, Arduino, Raspberry Pi, etc.) and can send/receive data at up to 2 Mbps over distances up to ~1100m line-of-sight. The "+PA+LNA" variant adds an RFX2401C amplifier chip (Power Amplifier for TX boost, Low-Noise Amplifier for RX sensitivity) and an external SMA antenna, dramatically extending range compared to the basic NRF24L01+ with its tiny PCB antenna.

**Purchase Link:** [Amazon - B00WG9HO6Q](https://www.amazon.com/dp/B00WG9HO6Q)
**Purchased:** January 24, 2026
**Quantity:** 2 (pack of 2)
**Price:** $8.49 (pack of 2)
**Status:** In inventory, not yet integrated

## Key Specifications

| Specification | Value |
|---------------|-------|
| Chip | Nordic nRF24L01+ with RFX2401C PA/LNA |
| Frequency | 2.4 GHz - 2.5 GHz ISM band (license-free) |
| Channels | 125 selectable (2400-2525 MHz, 1 MHz steps) |
| Data Rates | 250 kbps, 1 Mbps, 2 Mbps |
| Modulation | GFSK (Gaussian Frequency-Shift Keying) |
| Max TX Power | +20 dBm (PA+LNA version) |
| RX Sensitivity | -95 dBm (PA+LNA version) |
| Operating Voltage | 3.0V - 3.6V (**3.3V typical, NEVER 5V on VCC**) |
| Logic Levels | 5V-tolerant inputs (SPI pins safe with 5V MCUs) |
| Max Current | 115 mA (TX at full power) |
| Standby Current | 26 uA |
| Power-Down Current | 900 nA |
| Range (PA+LNA) | ~1100m line-of-sight, ~100-200m indoors |
| Range (basic) | ~100m line-of-sight, ~20-50m indoors |
| Interface | SPI (up to 10 MHz clock) |
| Data Pipes | 6 simultaneous RX pipes (multidrop/star network) |
| Payload Size | 1-32 bytes per packet (configurable) |
| Protocol | Enhanced ShockBurst (auto-ACK, auto-retransmit) |
| Module Size | 41mm x 15.5mm |
| Weight | 0.32 oz (9g) with antenna |
| Antenna | External SMA (2.4 GHz, included) |

## Pinout (8-Pin, 2x4 Header)

```
            ┌─────────────────────────┐
            │      NRF24L01+PA+LNA    │
            │                         │
            │  [SMA Antenna Connector]│
            │         ┌─┐            │
            │         │ │            │
            │         └─┘            │
            │                         │
            │  ┌───────────────────┐  │
            │  │ Component Side    │  │
            │  │ (chips visible)   │  │
            │  └───────────────────┘  │
            │                         │
            │   Pin Header (bottom):  │
            │                         │
            │    GND ● ○ VCC          │
            │     CE ● ○ CSN          │
            │    SCK ● ○ MOSI         │
            │   MISO ● ○ IRQ          │
            │                         │
            │   (● = left column)     │
            │   (○ = right column)    │
            │   GND pin marked with   │
            │   square pad on PCB     │
            └─────────────────────────┘
```

| Pin | Name | Direction | Description |
|-----|------|-----------|-------------|
| 1 | GND | Power | Ground (square pad marker on PCB) |
| 2 | VCC | Power | **3.3V ONLY** (3.0-3.6V) — 5V will destroy the module |
| 3 | CE | Input | Chip Enable — HIGH to activate RX or start TX |
| 4 | CSN | Input | Chip Select Not — LOW to begin SPI transaction |
| 5 | SCK | Input | SPI Clock |
| 6 | MOSI | Input | SPI Master Out → Slave In (data to module) |
| 7 | MISO | Output | SPI Master In ← Slave Out (data from module) |
| 8 | IRQ | Output | Interrupt Request (active-LOW, optional — can be left unconnected) |

## Wiring to Raspberry Pi 5 (ROVAC)

The Pi 5 has hardware SPI on its GPIO header. Use SPI0 (the default).

```
NRF24L01+PA+LNA          Raspberry Pi 5 (GPIO Header)
─────────────────         ──────────────────────────────
VCC  (pin 2)  ──────────► ** SEE POWER NOTE BELOW **
GND  (pin 1)  ──────────► Pin 6  (GND)
CE   (pin 3)  ──────────► Pin 15 (GPIO22) — configurable
CSN  (pin 4)  ──────────► Pin 24 (GPIO8 / CE0 / SPI0_CS0)
SCK  (pin 5)  ──────────► Pin 23 (GPIO11 / SPI0_SCLK)
MOSI (pin 6)  ──────────► Pin 19 (GPIO10 / SPI0_MOSI)
MISO (pin 7)  ──────────► Pin 21 (GPIO9 / SPI0_MISO)
IRQ  (pin 8)  ──────────► (optional) Pin 18 (GPIO24) or leave unconnected
```

### CRITICAL: Power Supply for PA+LNA Version

The PA+LNA version draws up to **115 mA** at full TX power. The Pi's 3.3V rail can technically supply this, but voltage droops during TX bursts cause unreliable behavior. **This is the #1 cause of "module doesn't transmit" problems** (see Amazon reviews — multiple users hit this exact issue).

**Required fix — add decoupling capacitors:**
- Solder a **10 uF electrolytic** + **100 nF ceramic** capacitor across VCC and GND, as close to the module pins as possible
- Alternatively, use an NRF24L01 adapter board (breakout with onboard 3.3V regulator + caps) that accepts 5V input

```
              10uF         100nF
Pi 3.3V ──┬──┤├──┬──┤├──┬── NRF24 VCC
           │       │       │
Pi GND  ──┴───────┴───────┴── NRF24 GND
```

### Enable SPI on Pi 5

```bash
# Check if SPI is enabled
ls /dev/spidev0.*

# If not present, enable it:
sudo raspi-config
# → Interface Options → SPI → Enable

# Or edit config directly:
echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

## Wiring to ESP32 (VSPI)

If connecting to one of the ROVAC ESP32-WROOM-32 boards:

```
NRF24L01+PA+LNA          ESP32-WROOM-32 (VSPI)
─────────────────         ─────────────────────
VCC  (pin 2)  ──────────► 3V3
GND  (pin 1)  ──────────► GND
CE   (pin 3)  ──────────► GPIO4  (configurable)
CSN  (pin 4)  ──────────► GPIO5  (VSPI SS)
SCK  (pin 5)  ──────────► GPIO18 (VSPI SCK)
MOSI (pin 6)  ──────────► GPIO23 (VSPI MOSI)
MISO (pin 7)  ──────────► GPIO19 (VSPI MISO)
IRQ  (pin 8)  ──────────► (optional) GPIO2 or leave unconnected
```

**Note:** The ESP32's 3.3V regulator can supply ~500mA, so it handles the PA+LNA version better than the Pi's rail. Still add a 10uF + 100nF cap across VCC/GND for best results.

## Wiring to ESP32-S3 (ROVAC Lonely Binary Boards)

If using one of the 3x ESP32-S3-WROOM boards (note: OPI PSRAM disables GPIO26-37):

```
NRF24L01+PA+LNA          ESP32-S3-WROOM
─────────────────         ────────────────
VCC  (pin 2)  ──────────► 3V3
GND  (pin 1)  ──────────► GND
CE   (pin 3)  ──────────► GPIO4  (configurable)
CSN  (pin 4)  ──────────► GPIO5
SCK  (pin 5)  ──────────► GPIO12
MOSI (pin 6)  ──────────► GPIO11
MISO (pin 7)  ──────────► GPIO13
IRQ  (pin 8)  ──────────► (optional) GPIO6 or leave unconnected
```

**Important:** On the ESP32-S3 with OPI PSRAM, GPIO26-37 are used by PSRAM and unavailable. Use only safe GPIOs from the pin map in `hardware/ESP32-S3-WROOM/CLAUDE.md`.

## Software Libraries

### Python (Raspberry Pi) — pyRF24

```bash
pip install pyrf24
```

```python
from pyrf24 import RF24, RF24_PA_MAX, RF24_1MBPS

radio = RF24(22, 0)  # CE=GPIO22, CSN=SPI0_CS0 (CE0)
radio.begin()
radio.setPALevel(RF24_PA_MAX)    # Full power (+20 dBm with PA+LNA)
radio.setDataRate(RF24_1MBPS)    # 1 Mbps (good balance of range vs speed)
radio.setChannel(108)             # Channel 108 (2508 MHz, less WiFi interference)
radio.openWritingPipe(b"ROVAC")   # 5-byte pipe address
radio.openReadingPipe(1, b"ROVAC")

# Transmit
radio.stopListening()
radio.write(b"Hello from Pi!")

# Receive
radio.startListening()
if radio.available():
    payload = radio.read(radio.getDynamicPayloadSize())
    print(f"Received: {payload}")
```

### Arduino/ESP32 — RF24 Library

Install via Arduino Library Manager: search "RF24" by TMRh20.

```cpp
#include <SPI.h>
#include <RF24.h>

RF24 radio(4, 5);  // CE=GPIO4, CSN=GPIO5

void setup() {
    radio.begin();
    radio.setPALevel(RF24_PA_MAX);
    radio.setDataRate(RF24_1MBPS);
    radio.setChannel(108);
    radio.openWritingPipe((const uint8_t *)"ROVAC");
    radio.openReadingPipe(1, (const uint8_t *)"ROVAC");
}
```

## How It Works

### Communication Model

The nRF24L01+ uses a **simplex** model with rapid role-switching: at any moment, each module is either a **transmitter (PTX)** or a **receiver (PRX)**. Roles can be swapped in microseconds, enabling half-duplex back-and-forth communication.

### Enhanced ShockBurst Protocol

The chip handles low-level RF reliability automatically:
1. **Auto-ACK**: Receiver sends an acknowledgment packet back to transmitter
2. **Auto-Retransmit**: If no ACK received, transmitter retries (configurable: 0-15 retries, 250us-4000us delay)
3. **CRC**: 1 or 2 byte CRC error detection on every packet
4. **Dynamic Payload**: Payload size 1-32 bytes, can vary per packet

### Multi-Node Networking (6 Pipes)

Each receiver can listen on up to 6 "pipes" simultaneously (6 different addresses). This enables star-topology networks where one central node (e.g., the Pi on the robot) talks to up to 6 remote nodes.

```
                    ┌──── Remote Node 1 (sensor)
                    │
Central Node ───────┼──── Remote Node 2 (actuator)
 (Pi on ROVAC)      │
                    ├──── Remote Node 3 (beacon)
                    │
                    └──── ... up to 6 pipes
```

### Channel Selection

125 channels available (2400-2525 MHz). WiFi uses channels 1 (2412 MHz), 6 (2437 MHz), and 11 (2462 MHz) — so **use NRF24 channels 100+ (2500+ MHz) to avoid WiFi interference**. Channel 108 (2508 MHz) is a good default.

## Use Cases for ROVAC

### 1. Emergency Stop / Wireless Kill Switch

A standalone handheld button (ESP32 + NRF24L01 + battery + button) that sends a stop command to the robot. Works even when WiFi is down because it uses a completely independent 2.4 GHz radio link. Range of ~100m+ indoors means it works from anywhere in the house.

```
[Handheld ESP32 + NRF24]  ──── 2.4GHz RF ────►  [Pi + NRF24 on ROVAC]
       │                                                │
    Button press                                   Stop motors
                                                   Kill nav stack
```

### 2. Wireless Sensor Outposts

Deploy small battery-powered sensor nodes around the environment (temperature, motion, light, gas) that report back to the robot as it drives by. No WiFi infrastructure needed.

```
[Sensor Node: Arduino Nano + NRF24 + DHT22 + battery]
       │
       └── Periodically TX: {temp, humidity, node_id}
              │
              ▼
       [ROVAC Pi + NRF24] receives, publishes to ROS2 topic
```

### 3. Inter-Robot Communication

If you build a second robot or a stationary base station, two NRF24L01 modules enable direct robot-to-robot messaging without depending on WiFi or a router. Useful for multi-robot coordination, relay messaging, or robot-to-base telemetry.

### 4. Low-Latency Remote Control Backup

A backup joystick controller that communicates via NRF24L01 instead of Bluetooth/WiFi. Faster than Bluetooth (~130us vs ~7.5ms minimum BLE interval) and works when the WiFi network is down.

### 5. Perimeter Beacons / Indoor Positioning

Place NRF24 beacon nodes at known positions. The robot can measure received signal strength (RSSI — available in the RPD register) from multiple beacons to estimate rough position. Not GPS-accurate, but useful as a supplement to SLAM.

### 6. Lightweight Telemetry Downlink

Stream compact telemetry (battery voltage, motor current, error codes) over RF to a monitoring station, independent of the main ROS2/DDS network. Good for debugging when WiFi/DDS is misbehaving.

## Comparison with Other Wireless Options

| Feature | NRF24L01+PA+LNA | WiFi (ESP32) | Bluetooth (ESP32) | LoRa |
|---------|-----------------|--------------|-------------------|------|
| Range (LOS) | ~1100m | ~100m | ~30m | ~10km |
| Data Rate | 250kbps-2Mbps | 72Mbps | 2Mbps | 0.3-50kbps |
| Latency | ~130us | ~1-10ms | ~7.5ms | ~100ms+ |
| Power (TX) | 115mA | 240mA | 130mA | 120mA |
| Power (sleep) | 900nA | 10uA | N/A | 1uA |
| Infrastructure | None (P2P) | Router needed | Pairing | None (P2P) |
| Protocol | Proprietary | TCP/IP | BT stack | LoRaWAN |
| Packet Size | 32 bytes max | MTU 1500 | 244 bytes | 256 bytes |
| Cost | ~$4/module | Built into ESP32 | Built into ESP32 | ~$15/module |
| Best For | Control, sensors | Bulk data, video | Controllers, audio | Ultra-long range |

## Important Warnings

1. **NEVER connect VCC to 5V** — the nRF24L01+ is a 3.3V chip. 5V on VCC will destroy it. (The SPI *logic* pins are 5V-tolerant, but VCC is not.)

2. **Decoupling capacitors are mandatory** for the PA+LNA version. Without them, the module will receive fine but fail to transmit (the PA draws current spikes that cause voltage droops). 10uF electrolytic + 100nF ceramic across VCC/GND.

3. **Same settings on both ends**: Channel, data rate, PA level, pipe address, and payload size must match between transmitter and receiver or communication silently fails.

4. **WiFi interference**: Channels 0-80 overlap with common WiFi channels. Use channel 100+ to stay clear.

5. **SPI bus sharing**: If other SPI devices share the bus (SD card, display, etc.), ensure proper CS/CSN management. The NRF24 CSN must go HIGH when not in use.

## Package Contents

- 2x NRF24L01+PA+LNA transceiver modules
- 2x 2.4 GHz SMA antennas (screw-on)

## Resources

- [nRF24L01+ Datasheet (Nordic Semi)](https://www.nordicsemi.com/Products/nRF24L01)
- [Last Minute Engineers — nRF24L01 In-Depth Guide](https://lastminuteengineers.com/nrf24l01-arduino-wireless-communication/)
- [Components101 — nRF24L01 Pinout & Features](https://components101.com/wireless/nrf24l01-pinout-features-datasheet)
- [pyRF24 — Python Library for Raspberry Pi](https://nrf24.github.io/pyRF24/)
- [RF24 Arduino Library (TMRh20)](https://github.com/nRF24/RF24)
- [RF24 Pi 5 Compatibility Discussion](https://github.com/nRF24/RF24/issues/1040)
- [Hackster.io — nRF24L01 + Raspberry Pi](https://www.hackster.io/Wirekraken/connecting-an-nrf24l01-to-raspberry-pi-9c0a57)
