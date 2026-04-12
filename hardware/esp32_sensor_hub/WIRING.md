# ESP32 Sensor Hub — Wiring Guide

**Board**: ESP32-DevKitV1 (WROOM-32, 38-pin, CH340 USB)
**Purpose**: Near-obstacle detection + cliff/edge safety for autonomous vacuum navigation
**Replaces**: Legacy Arduino Nano "super sensor" module

## Sensors

| Sensor | Qty | Purpose | Mounting |
|--------|-----|---------|----------|
| HC-SR04 Ultrasonic | 4 | Obstacle detection | Front, rear, left, right — facing outward |
| Sharp GP2Y0A51SK0F IR | 2 | Cliff/edge detection | Front + rear — angled 30-45deg down toward floor |

---

## Parts Checklist

Gather everything before you start wiring.

**You should already have:**
- [ ] 1x ESP32-DevKitV1 (WROOM-32, 38-pin, CH340)
- [ ] 4x HC-SR04 ultrasonic sensors
- [ ] 2x Sharp GP2Y0A51SK0F IR distance sensors

**Additional parts needed:**

| Part | Qty | Purpose | Notes |
|------|-----|---------|-------|
| 1k ohm resistor (1/4W) | 4 | Voltage divider (top) | One per HC-SR04 ECHO line |
| 2.2k ohm resistor (1/4W) | 4 | Voltage divider (bottom) | One per HC-SR04 ECHO line |
| 10uF electrolytic capacitor | 2 | Sharp IR power bypass | MANDATORY — one per Sharp IR sensor |
| Micro-USB cable (data) | 1 | ESP32 to Pi connection | Must be a DATA cable, not charge-only |
| Breadboard or proto board | 1 | Component mounting | Proto board recommended for vibration resistance |
| Jumper wires (M-F, M-M) | ~25 | Sensor connections | Various lengths |

**Optional but helpful:**
- [ ] JST ZH 1.5mm 3-pin cables (for Sharp IR connectors) — or solder wires directly
- [ ] Heat shrink tubing for voltage divider joints
- [ ] Hot glue for securing connections on proto board

---

## Pin Assignment Summary

```
ESP32-DevKitV1 (38-pin) — Top View, USB port at bottom
+------------------------------------+
|           [USB / CH340]            |
|                                    |
|  3V3  o                        o  VIN
|  GND  o---[GROUND BUS]--------o  GND
|  GPIO15  o                    o  GPIO13
|  GPIO2   o  (built-in LED)    o  GPIO12
|  GPIO4   o                    o  GPIO14
|  GPIO16  o-- US Front TRIG    o  GPIO27
|  GPIO17  o-- US Rear TRIG     o  GPIO26
|  GPIO5   o                    o  GPIO25
|  GPIO18  o-- US Left TRIG     o  GPIO33 --o Sharp IR Rear (ADC)
|  GPIO19  o-- US Right TRIG    o  GPIO32 --o Sharp IR Front (ADC)
|  GPIO21  o  (reserved I2C)    o  GPIO35 --o US Rear ECHO [divider]
|  GPIO3   o  UART0 RX          o  GPIO34 --o US Front ECHO [divider]
|  GPIO1   o  UART0 TX          o  GPIO39 --o US Right ECHO [divider]
|  GPIO22  o  (reserved I2C)    o  GPIO36 --o US Left ECHO [divider]
|  GPIO23  o                     o  EN
|                                    |
|  5V  o---[5V POWER BUS]-------o  GND
+------------------------------------+

[divider] = Needs 1k + 2.2k voltage divider (5V -> 3.3V)
```

### Pin Table

| GPIO | Dir | Sensor | Function | Notes |
|------|-----|--------|----------|-------|
| **HC-SR04 Ultrasonic (4x)** | | | | |
| 16 | OUT | HC-SR04 Front | TRIG | 10us pulse to trigger measurement |
| 34 | IN | HC-SR04 Front | ECHO | Input-only pin. VOLTAGE DIVIDER REQUIRED |
| 17 | OUT | HC-SR04 Rear | TRIG | |
| 35 | IN | HC-SR04 Rear | ECHO | Input-only pin. VOLTAGE DIVIDER REQUIRED |
| 18 | OUT | HC-SR04 Left | TRIG | |
| 36 | IN | HC-SR04 Left | ECHO | Input-only pin (VP). VOLTAGE DIVIDER REQUIRED |
| 19 | OUT | HC-SR04 Right | TRIG | |
| 39 | IN | HC-SR04 Right | ECHO | Input-only pin (VN). VOLTAGE DIVIDER REQUIRED |
| **Sharp GP2Y0A51SK0F IR (2x)** | | | | |
| 32 | ADC | Sharp IR Front | Analog Vo | ADC1_CH4. No divider needed (max 2.4V) |
| 33 | ADC | Sharp IR Rear | Analog Vo | ADC1_CH5. No divider needed (max 2.4V) |
| **System** | | | | |
| 1 | TX | --- | UART0 TX | USB serial to Pi (COBS protocol). DO NOT USE |
| 3 | RX | --- | UART0 RX | USB serial to Pi (COBS protocol). DO NOT USE |
| 2 | OUT | --- | Status LED | Built-in blue LED on DevKitV1 board |
| **Reserved for future** | | | | |
| 21 | --- | --- | I2C SDA | Future expansion |
| 22 | --- | --- | I2C SCL | Future expansion |
| 4, 5, 12-15, 23, 25-27 | --- | --- | Available | Free GPIOs for future sensors |

**Total GPIOs used**: 12 of 20+ available (built-in LED + 4 TRIG + 4 ECHO + 2 ADC + UART0)

---

## Step-by-Step Wiring Instructions

### Step 1: Set Up the Power Rails

Connect power from the ESP32 board to your breadboard/protoboard power rails.

```
ESP32 5V pin  ------>  5V power rail (red)
ESP32 GND pin ------>  GND rail (blue/black)
```

Both GND pins on the ESP32 board connect to the same ground internally — use whichever is more convenient. The 5V pin provides USB power (up to ~500mA from Pi USB port).

**Power budget (well within USB limits):**

| Component | Voltage | Max Current |
|-----------|---------|-------------|
| ESP32 (WiFi off) | 3.3V (internal) | 50 mA |
| 4x HC-SR04 | 5V | 60 mA (4 x 15 mA) |
| 2x Sharp IR | 5V | 44 mA (2 x 22 mA) |
| **Total from 5V rail** | | **~154 mA** |

---

### Step 2: Build the 4 Voltage Dividers

**This is the most critical step.** The HC-SR04 ECHO pins output 5V. The ESP32 GPIO pins are rated for 3.3V max. Without voltage dividers, you WILL damage the ESP32.

Build this circuit 4 times (one per HC-SR04):

```
                    1k ohm
HC-SR04 ECHO o----[####]----+---- ESP32 GPIO (input)
                            |
                         [####] 2.2k ohm
                            |
                           GND
```

**How it works:** The two resistors form a voltage divider that scales 5V down to:
`5V x 2.2k / (1k + 2.2k) = 3.44V` (safe for ESP32's 3.3V-tolerant inputs)

**Build tips:**
- Twist the resistor leads together at the junction point and solder if using proto board
- Keep the wires short — long wires on the ECHO line can pick up noise
- Each divider's GND connects to the common ground rail

**Divider-to-pin mapping:**

| Divider # | HC-SR04 Position | ESP32 ECHO GPIO |
|-----------|-----------------|-----------------|
| 1 | Front | GPIO34 |
| 2 | Rear | GPIO35 |
| 3 | Left | GPIO36 |
| 4 | Right | GPIO39 |

---

### Step 3: Wire the HC-SR04 Ultrasonic Sensors (x4)

Each HC-SR04 has 4 pins: VCC, TRIG, ECHO, GND.

Wire each sensor as follows:

| HC-SR04 Pin | Connects To |
|-------------|-------------|
| VCC | 5V power rail |
| TRIG | ESP32 GPIO directly (see table below) |
| ECHO | Through voltage divider (Step 2) to ESP32 GPIO |
| GND | GND rail |

**Complete wiring table:**

| Sensor | VCC | TRIG | ECHO (through divider!) | GND |
|--------|-----|------|-------------------------|-----|
| **Front** | 5V rail | GPIO16 | 1k+2.2k divider -> GPIO34 | GND rail |
| **Rear** | 5V rail | GPIO17 | 1k+2.2k divider -> GPIO35 | GND rail |
| **Left** | 5V rail | GPIO18 | 1k+2.2k divider -> GPIO36 | GND rail |
| **Right** | 5V rail | GPIO19 | 1k+2.2k divider -> GPIO39 | GND rail |

**IMPORTANT**: Do NOT connect ECHO directly to ESP32. Always go through the voltage divider.

---

### Step 4: Wire the Sharp IR Cliff Sensors (x2)

The Sharp GP2Y0A51SK0F has a 3-pin JST ZH (1.5mm pitch) connector. The max output voltage is ~2.4V, which is safely below the ESP32's 3.3V ADC limit, so NO voltage divider is needed.

**Connector pinout (looking at the sensor from the front, left to right):**

| Pin | Wire Color | Function | Connects To |
|-----|------------|----------|-------------|
| 1 | Red | VCC (5V) | 5V power rail |
| 2 | Black | GND | GND rail |
| 3 | Yellow/White | Vo (analog) | ESP32 GPIO directly |

**Wiring table:**

| Sensor | VCC (Red) | GND (Black) | Vo (Yellow) |
|--------|-----------|-------------|-------------|
| **Front cliff** | 5V rail | GND rail | GPIO32 |
| **Rear cliff** | 5V rail | GND rail | GPIO33 |

**MANDATORY: Add a 10uF capacitor per sensor.**
The Sharp IR draws current in short, high-amplitude pulses (when firing the IR LED). Without a bypass cap, this destabilizes the 5V rail and corrupts readings from other sensors.

```
            10uF electrolytic cap
5V rail ----||( + )----+---- Red wire (VCC) to sensor
                       |
GND rail ----( - )-----+---- Black wire (GND) to sensor

Place the capacitor as close to each sensor as possible.
The (+) leg goes to 5V, the (-) leg goes to GND.
```

**Connector note:** The JST ZH is 1.5mm pitch — this is NOT the common 2.0mm JST PH connector. You may need specific JST ZH cables, or solder wires directly to the sensor's solder pads.

---

### Step 5: Verify Before Powering On

**DO NOT plug in the USB cable until you verify all of these:**

- [ ] **No ECHO pins are connected directly to ESP32** — all 4 go through voltage dividers
- [ ] **Voltage divider orientation is correct** — 1k from ECHO, then junction to ESP32 GPIO, then 2.2k to GND (not reversed)
- [ ] **No shorts between 5V and GND rails** — visually inspect, or test with multimeter in continuity mode
- [ ] **No shorts between adjacent GPIO pins** — especially the closely-spaced ECHO/ADC pins on the right side of the board
- [ ] **10uF caps installed on both Sharp IR sensors** — polarity correct (+ to 5V, - to GND)
- [ ] **All GNDs connected** — ESP32 GND, all sensor GNDs, all voltage divider GNDs must share a common ground
- [ ] **TRIG wires go to the correct GPIOs** — GPIO16=Front, GPIO17=Rear, GPIO18=Left, GPIO19=Right
- [ ] **ECHO dividers go to the correct GPIOs** — GPIO34=Front, GPIO35=Rear, GPIO36=Left, GPIO39=Right
- [ ] **Sharp IR Vo wires go to correct GPIOs** — GPIO32=Front cliff, GPIO33=Rear cliff
- [ ] **USB cable is a DATA cable** — some cheap micro-USB cables are charge-only (no data lines). If the ESP32 doesn't show up as a serial device on the Pi, try a different cable

---

## Complete Wiring Diagram

```
                              ESP32-DevKitV1
                         +-----------------------+
                         |      [USB to Pi]      |
                         |                       |
                    3V3  |o                     o|  VIN
                    GND  |o        GND BUS     o|  GND
                         |o  GPIO15            o|  GPIO13
         (status LED) <--|o  GPIO2             o|  GPIO12
                         |o  GPIO4             o|  GPIO14
  US Front TRIG  ------->|o  GPIO16            o|  GPIO27
  US Rear TRIG   ------->|o  GPIO17            o|  GPIO26
                         |o  GPIO5             o|  GPIO25
  US Left TRIG   ------->|o  GPIO18            o|  GPIO33  |<------- Sharp IR Rear Vo
  US Right TRIG  ------->|o  GPIO19            o|  GPIO32  |<------- Sharp IR Front Vo
                         |o  GPIO21            o|  GPIO35  |<--[div] US Rear ECHO
                         |o  GPIO3 (UART RX)   o|  GPIO34  |<--[div] US Front ECHO
                         |o  GPIO1 (UART TX)   o|  GPIO39  |<--[div] US Right ECHO
                         |o  GPIO22            o|  GPIO36  |<--[div] US Left ECHO
                         |o  GPIO23            o|  EN
                         |                       |
                    5V   |o        GND BUS     o|  GND
                         +-----------------------+

[div] = through 1k + 2.2k voltage divider to GND


    POWER WIRING:
    =============
    ESP32 5V pin ----> 5V Rail ---+--- HC-SR04 Front VCC
                                  +--- HC-SR04 Rear VCC
                                  +--- HC-SR04 Left VCC
                                  +--- HC-SR04 Right VCC
                                  +--- Sharp IR Front VCC (through 10uF cap)
                                  +--- Sharp IR Rear VCC (through 10uF cap)

    ESP32 GND pin ---> GND Rail --+--- All HC-SR04 GND pins (x4)
                                  +--- Sharp IR Front GND
                                  +--- Sharp IR Rear GND
                                  +--- All voltage divider bottom legs (x4)


    VOLTAGE DIVIDER DETAIL (build x4):
    ===================================

    HC-SR04       1k ohm        ESP32 GPIO
    ECHO o------[####]-----+-----o (34, 35, 36, or 39)
                           |
                        [####] 2.2k ohm
                           |
                          GND rail
```

---

## Physical Mounting

```
                    FRONT OF ROBOT
        +-------------------------------+
        |                               |
        |     [HC-SR04 Front]           |  <- Center front edge, facing forward
        |     [Sharp IR Front]          |  <- Below front HC-SR04, angled 30-45 deg
        |          |                    |     down toward floor
        |          v (sees floor        |
        |            ~5-10cm ahead)     |
        |                               |
   [HC-SR04  <-                 ->  HC-SR04
     Left]                        Right]
        |                               |
        |          ^ (sees floor        |
        |          |  ~5-10cm behind)   |
        |     [Sharp IR Rear]           |  <- Below rear HC-SR04, angled 30-45 deg
        |     [HC-SR04 Rear]            |  <- Center rear edge, facing backward
        |                               |
        +-------------------------------+
                    REAR OF ROBOT

   ESP32 DevKitV1: Mount inside chassis or on top deck
                   USB port accessible (toward rear preferred for cable routing)
```

**HC-SR04 mounting tips:**
- Mount with both "eyes" (transducers) horizontal and facing outward
- The beam is a ~30 degree cone — don't aim them at the floor or ceiling
- Keep the front edges of the transducers flush with the robot body if possible

**Sharp IR cliff sensor mounting tips:**
- Angle downward 30-45 degrees so the sensor "sees" the floor 5-10cm ahead of (or behind) the robot
- At typical mounting height (~10-20mm above floor level), the 2-15cm range covers the ground detection zone perfectly
- Normal floor reading: ~1.0-1.5V (corresponds to 3-5cm distance to floor)
- Cliff detected: voltage drops below ~0.3V (no surface within 15cm)
- The sensor's IR LED/detector baseline should run perpendicular to the robot's direction of travel for best accuracy

---

## USB Setup on Pi (After Wiring Is Complete)

When you plug the ESP32 into the Pi via USB, you need to set up a udev rule so it gets a stable device name. Both the motor ESP32 and sensor ESP32 use CH340 chips (same vendor:product ID `1a86:7523`), so we distinguish them by serial number.

**Step 1: Find the CH340 serial number**
```bash
# On the Pi, with the sensor ESP32 plugged in:
# First find which /dev/ttyUSBx it got assigned:
ls -la /dev/ttyUSB*

# Then get its serial number:
udevadm info -a /dev/ttyUSBx | grep serial
# Look for the ATTRS{serial}== line
```

**Step 2: Add udev rule**
```bash
# Add to /etc/udev/rules.d/99-rovac-esp32.rules on the Pi:
# (The motor ESP32 rule should already exist)

# Sensor Hub ESP32
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", \
  ATTRS{serial}=="<SENSOR_HUB_SERIAL>", SYMLINK+="esp32_sensor", MODE="0666"
```

**Step 3: Reload udev**
```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
# Verify:
ls -la /dev/esp32_sensor
```

After this, the sensor ESP32 will always appear as `/dev/esp32_sensor` regardless of plug order.

---

## Sensor Specifications Quick Reference

### HC-SR04 Ultrasonic
| Spec | Value |
|------|-------|
| Range | 2 cm to 400 cm |
| Practical range (obstacle avoidance) | 2 cm to 50 cm |
| Accuracy | ~3 mm |
| Beam angle | ~30 degree cone |
| Update rate | ~10 Hz (sequential 4-sensor cycle) |
| Trigger | 10 us HIGH pulse |
| Distance formula | `distance_cm = echo_duration_us / 58.3` |
| Current draw | 15 mA per sensor at 5V |

### Sharp GP2Y0A51SK0F IR
| Spec | Value |
|------|-------|
| Range | 2 cm to 15 cm |
| Output | Analog voltage: ~2.4V at 2cm, ~0.3V at 15cm |
| Update rate | ~60 Hz (16.5ms measurement cycle) |
| Conversion | `distance_cm = 1 / (a * voltage + b)` (calibrate per sensor) |
| Cliff detection | Floor present: 1.0-1.5V / Cliff (>15cm): <0.3V |
| Current draw | 12 mA avg, 22 mA max at 5V |
| CRITICAL | 10uF bypass cap MANDATORY on each sensor |
