# ROVAC LIDAR USB Bridge - Current Setup Documentation
Backup created: 2026-01-17T16:47:01.037867
Platform: Darwin 25.0.0
Architecture: arm64

## Device Information
- Device Path: /dev/cu.wchusbserial2140
- Board: LAFVIN Nano V3.0 (ATmega328P + CH340G)
- Firmware Status: Professional enhanced
- Data Rate: Verified working

## Wiring Configuration
LIDAR Wire    Color    Nano Pin    Function
----------    -----    --------    --------
Red           Red      5V          Power (+5V)
Black         Black    GND         Ground
Orange        Orange   D2          Serial TX (LIDAR -> Nano)
Brown         Brown    D3          Serial RX (Nano -> LIDAR)

## Test Results
✅ Serial communication established
✅ Data flow confirmed
✅ Professional firmware uploaded
✅ Enhanced features verified

## Notes
- Working configuration backed up 2026-01-17T16:47:01.037867
- Ready for deployment to Raspberry Pi
- All cross-platform tools available
