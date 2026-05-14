# Calibration Guide

Complete guide for calibrating the stereo camera system.

## Overview

Calibration consists of three phases:

1. **Stereo Calibration** - Camera intrinsics and extrinsics
2. **Rectification** - Image alignment for stereo matching
3. **Depth Correction** - Polynomial correction for systematic errors

## Prerequisites

### Equipment Needed

- 9x6 checkerboard pattern (inner corners)
- Recommended: Print on rigid board (foam core or cardboard)
- Square size: 25mm (1 inch) - measure precisely
- Good lighting (diffuse, no harsh shadows)
- Tape measure (for depth correction)

### Software Requirements

```bash
pip install opencv-python opencv-contrib-python numpy
```

## Method 1: Web UI Calibration (Recommended)

### Starting the Calibration Server

```bash
cd ~/robots/rovac/hardware/stereo_cameras
python3 calibration_ui/calibration_server.py

# Open browser to http://localhost:8000
```

### Step 1: Camera Setup

1. Verify both cameras are detected
2. Check live preview shows both camera feeds
3. Adjust camera exposure if needed (avoid overexposure)

### Step 2: Capture Calibration Images

**Guidelines for good captures:**
- Hold checkerboard at various angles (±30°)
- Move checkerboard to all corners of the frame
- Vary distance from 0.5m to 2m
- Keep checkerboard fully visible in both cameras
- Avoid motion blur - hold steady

**Capture Process:**
1. Position checkerboard
2. Wait for green outline (pattern detected)
3. Click "Capture" button
4. Repeat for 15-25 images

**Coverage Targets:**
```
┌─────────────────────────────────────┐
│  ●           ●           ●          │  Top row: 3+ images
│                                     │
│       ●           ●           ●     │  Middle: 3+ images
│                                     │
│  ●           ●           ●          │  Bottom: 3+ images
└─────────────────────────────────────┘
     Near        Mid        Far
    (0.5m)      (1m)       (2m)
```

### Step 3: Run Calibration

1. Click "Calibrate" button
2. Wait for processing (30-60 seconds)
3. Review results:
   - RMS Error < 0.5 pixels (good)
   - RMS Error < 1.0 pixels (acceptable)
   - RMS Error > 1.0 pixels (recapture needed)

### Step 4: Verify Calibration

1. Click "Test" to view rectified images
2. Check epipolar alignment:
   - Horizontal lines should align between cameras
   - Same feature should be on same row in both images

### Step 5: Save Calibration

1. Click "Save" button
2. Files saved to `calibration_data/`:
   - `stereo_calibration.json` - Camera parameters
   - `stereo_maps.npz` - Rectification maps

## Method 2: CLI Calibration

### Running Calibration Tool

```bash
python3 stereo_calibration.py
```

### Controls

| Key | Action |
|-----|--------|
| `SPACE` | Capture image pair |
| `c` | Run calibration |
| `v` | View rectified result |
| `s` | Save calibration |
| `q` | Quit |

### Capture Workflow

```
1. Position checkerboard
2. Wait for corners detected (green overlay)
3. Press SPACE to capture
4. Repeat 15-25 times
5. Press 'c' to calibrate
6. Press 'v' to verify
7. Press 's' to save
```

### Interpreting Results

```
Calibration Results:
  RMS Error: 0.45 pixels
  Baseline: 102.67 mm
  Focal Length: 1621.51 pixels
  Image Size: 640 x 480

  Camera 1 Intrinsics:
    fx: 1621.51  fy: 1623.87
    cx: 321.45   cy: 238.92

  Distortion (k1, k2, p1, p2, k3):
    [-0.0234, 0.0156, 0.0002, -0.0001, -0.0089]
```

## Depth Correction Calibration

### Why Depth Correction?

Stereo depth has systematic errors due to:
- Baseline measurement inaccuracy
- Lens distortion residuals
- SGBM algorithm characteristics

Depth correction applies a polynomial to correct these errors.

### Running Depth Correction

```bash
python3 depth_calibration_interactive.py
```

### Procedure

1. **Prepare target**: Use textured surface (checkerboard works well)
2. **Place at known distance**: Measure with tape measure
3. **Record sample**: Press key corresponding to distance

### Distance Key Mapping

| Key | Distance | Key | Distance |
|-----|----------|-----|----------|
| `1` | 0.1m | `a` | 1.1m |
| `2` | 0.2m | `b` | 1.2m |
| `3` | 0.3m | `c` | 1.3m |
| `4` | 0.4m | `d` | 1.4m |
| `5` | 0.5m | `e` | 1.5m |
| `6` | 0.6m | `f` | 1.6m |
| `7` | 0.7m | `g` | 1.7m |
| `8` | 0.8m | `h` | 1.8m |
| `9` | 0.9m | `i` | 1.9m |
| `0` | 1.0m | `j` | 2.0m |

### Best Practices

**Sample Distribution:**
```
                        ← More samples here
   ├────┬────┬────┬────┬────┬────┬────┬────┤
   0.5  0.6  0.7  0.8  0.9  1.0  1.1  1.2m
```

- Focus on 0.7m - 1.2m range (typical operating range)
- Minimum 6 samples for good polynomial fit
- Ensure ROI Valid > 40% before capturing

**Quality Indicators:**
- `ROI Valid %`: Percentage of valid depth in center region
- `Measured`: Average depth in center region
- `Target`: Your measured distance

### Controls

| Key | Action |
|-----|--------|
| `1-9, 0` | Record sample at distance |
| `a-j` | Record sample at 1.1m-2.0m |
| `u` | Undo last sample |
| `r` | Reset all samples |
| `q` | Save and quit |

### Interpreting Results

```
Depth Correction Calibration Results:
  Polynomial: y = 0.0 + 1.05x - 0.02x² + 0.001x³
  RMSE: 0.008m (8mm)
  Valid Range: 0.65m - 10.0m
  Samples: 12

  Before Correction:
    0.70m actual → 0.68m measured (error: -20mm)
    1.00m actual → 0.97m measured (error: -30mm)

  After Correction:
    0.70m actual → 0.70m corrected (error: 0mm)
    1.00m actual → 1.00m corrected (error: -2mm)
```

## Verification

### Testing Depth Accuracy

```bash
python3 stereo_depth_calibrated.py
```

1. Enable depth correction (press `c`)
2. Place object at known distance
3. Point crosshair at object
4. Compare displayed depth to measured distance

### Expected Accuracy

| Distance | Expected Error |
|----------|----------------|
| 0.7m | ±10mm |
| 1.0m | ±15mm |
| 1.5m | ±25mm |
| 2.0m | ±40mm |

### Troubleshooting Poor Accuracy

**High RMS Error (> 1.0 pixel):**
- Recapture images with better coverage
- Check for motion blur
- Ensure checkerboard is flat
- Improve lighting

**Depth consistently wrong:**
- Verify baseline measurement
- Check camera device mapping (left/right swap)
- Recalibrate depth correction

**Noisy depth:**
- Enable WLS filter
- Increase block size
- Improve surface texture

## Recalibration Schedule

### When to Recalibrate

- After physical camera adjustment
- After USB port changes
- After significant temperature changes
- If depth accuracy degrades

### Quick Verification

```bash
# Check current calibration
python3 stereo_depth_calibrated.py

# Verify at known distances:
# - 0.5m: Error < 10mm
# - 1.0m: Error < 20mm
# - 2.0m: Error < 50mm
```

## Calibration Files

### File Locations

```
calibration_data/
├── stereo_calibration.json     # Camera matrices
├── stereo_maps.npz             # Rectification maps
├── depth_correction.json       # Depth polynomial
├── left/                       # Left calibration images
│   ├── 00.png
│   └── ...
└── right/                      # Right calibration images
    ├── 00.png
    └── ...
```

### Backing Up Calibration

```bash
# Create backup
cp -r calibration_data calibration_data_backup_$(date +%Y%m%d)

# Restore backup
cp -r calibration_data_backup_YYYYMMDD/* calibration_data/
```

### Transferring Calibration

```bash
# To Pi
scp -r calibration_data/ pi@192.168.1.200:~/robots/rovac/hardware/stereo_cameras/

# From Pi
scp -r pi@192.168.1.200:~/robots/rovac/hardware/stereo_cameras/calibration_data/ ./
```

## Advanced Topics

### Camera Matrix Explained

```
K = [fx  0  cx]
    [0  fy  cy]
    [0   0   1]

fx, fy = Focal lengths (pixels)
cx, cy = Principal point (image center)
```

### Distortion Model

Radial distortion: `k1, k2, k3`
Tangential distortion: `p1, p2`

```
x' = x(1 + k1*r² + k2*r⁴ + k3*r⁶) + 2*p1*x*y + p2*(r² + 2*x²)
y' = y(1 + k1*r² + k2*r⁴ + k3*r⁶) + p1*(r² + 2*y²) + 2*p2*x*y
```

### Baseline Calculation

The baseline is calculated from the translation vector:
```
baseline = ||T|| = sqrt(Tx² + Ty² + Tz²)
```

For our configuration: ~102.67mm

### Depth Formula

```
depth = (baseline × focal_length) / disparity

With our calibration:
depth_meters = (102.67mm × 1621.51px) / disparity / 1000
depth_meters = 166,419 / disparity
```

### Minimum Detectable Depth

```
min_depth = (baseline × focal_length) / max_disparity

With 256 disparities:
min_depth = 166,419 / 256 = 0.65m
```
