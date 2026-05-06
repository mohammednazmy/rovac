// ROVAC v3 — Master parameter file (audit-cleaned)
// -------------------------------------------------
// Every CAD part imports this file. Change a value here, regenerate all parts.
// See ./design_brief.md for the rationale on each value.
//
// Audit pass 2026-05-03: fixed counterbore depth, alignment pin azimuth,
// bumper inner radius, cliff anchor positions, LED/pass-through overlap,
// rib azimuth, section numbering, dead-code removal, derived-values ordering.

// ===== 1. UTILITY (must come first — used by other defaults) ===
$fn = 64;

// ===== 2. CHASSIS ENVELOPE =====================================
chassis_shape       = "round";
chassis_diameter    = 250;        // mm
chassis_radius      = chassis_diameter / 2;
chassis_height      = 95;         // mm — chassis exterior height
floor_thickness     = 3.0;
wall_thickness      = 2.4;
ceiling_thickness   = 3.0;        // RAISED from 2.4 → 3.0 mm to accommodate counterbores

bambu_build_volume  = [256, 256, 256];

// ===== 3. DRIVE SYSTEM =========================================
// Motors: Greartisan ZGB37RG17.4i / ZYTD520 (1:17.4 gear, 12V, 300 RPM no-load)

wheel_diameter      = 70;
wheel_width         = 22;
wheel_track         = 200;
wheel_offset_x      = 0;

motor_body_diameter = 37;
motor_body_length   = 71;
motor_shaft_length  = 14;
motor_shaft_diameter= 6;
// motor_mount_pcd removed — motors mount via friction-fit collar (see AS5600 mount),
// not via bolt holes through the gearbox flange. If a flange-mount design is added,
// reintroduce as motor_flange_pcd = 31.

caster_diameter     = 40;
caster_offset_x     = -90;
ground_clearance    = 15;

// Derived drive-system values
wheel_center_z      = wheel_diameter/2 - ground_clearance;

// ===== 4. LIDAR (recessed mount) ===============================
// SLAMTEC RPLIDAR C1 — solid base 23.1mm, optical enclosure 18.2mm, total 41.3mm.
// Footprint 55.6×55.6 mm. Scan plane = top of solid base = 23.1mm above LIDAR bottom.

lidar_total_height   = 41.3;
lidar_base_height    = 23.1;
lidar_optical_height = 18.2;
lidar_footprint      = 55.6;
lidar_recess_depth   = 23.1;
lidar_well_diameter  = 60;
lidar_mount_pcd      = 43;

// Derived LIDAR values
lidar_base_z        = chassis_height - lidar_recess_depth;
lidar_optical_z     = lidar_base_z + lidar_base_height;
robot_total_height  = chassis_height + lidar_optical_height;

// ===== 5. COMPONENT ANCHORS & FOOTPRINTS =======================
// Anchor = [x, y, z] in mm relative to chassis-floor-bottom-exterior.
// Footprint = [length_X, width_Y, height_Z] aligned to anchor center.
// Mount pattern = [pcd_X, pcd_Y].

// --- Raspberry Pi 5 (rear, on standoffs above motor strip; ROTATED 90°) ---
// 85×56×17 mm board + ~18 mm active cooler = 35 mm stack.
// 4× M2.5 at 58×49 mm. Long axis along Y to clear LIDAR base.
pi5_footprint         = [56, 85, 35];
pi5_mount_pcd         = [49, 58];
pi_anchor             = [-70, 0, 55];

// --- NULLLAB Maker-ESP32 motor controller (front floor) ---
// 80×57×12 mm; 4× TB67H450FNG drivers integrated. M4 LEGO-grid mount.
esp32_motor_footprint = [80, 57, 12];
esp32_motor_mount_pcd = [64, 40];
esp32_motor_anchor    = [58, 0, 3];

// --- ESP32 DevKitV1 (sensor hub; off-axis floor) ---
esp32_sensor_footprint = [55, 28, 13];
esp32_sensor_mount_pcd = [49, 22];
esp32_sensor_anchor    = [-30, 60, 3];

// --- Adafruit BNO055 IMU (#2472) ---
imu_footprint          = [27, 20, 4];
imu_mount_pcd          = [22, 15];
imu_anchor             = [0, 0, 12];

// --- Battery (rear floor) ---
battery_footprint      = [80, 40, 25];
battery_anchor         = [-65, 0, 3];

// --- Cliff sensors — moved inboard (was X=±115; would protrude past chassis) ---
cliff_footprint        = [30, 13, 7];
cliff_window_diameter  = 10;
cliff_anchor_front     = [105, 0, 3];   // moved from 115 → 105
cliff_anchor_rear      = [-105, 0, 3];

// --- Ultrasonic sensors (4× HC-SR04, perimeter) ---
us_footprint           = [45, 20, 15];
us_window_diameter     = 16;
us_window_pitch        = 24;
us_z_center            = 30;

// ===== 6. POWER SUBSYSTEM =====================================

// --- Buck converter (12V→5V 5A for Pi 5) ---
buck_footprint        = [50, 30, 15];
buck_mount_pcd        = [44, 24];
buck_anchor           = [-30, -60, 3];

// --- Master power switch ---
switch_cutout         = [21, 15];
switch_anchor_az      = 135;
switch_anchor_z       = 60;

// --- Charging port (DC barrel jack) ---
charge_port_d         = 12;
charge_port_az        = -135;
charge_port_z         = 60;

// ===== 7. SERVICE ACCESS (top plate fasteners + features) =====

// 8× M3 fasteners around chassis wall top → top plate
top_plate_fastener_count    = 8;
top_plate_fastener_pcd_r    = chassis_radius - wall_thickness/2 - 2;
top_plate_fastener_first_az = 22.5;
top_plate_boss_d            = 8;
top_plate_boss_h            = 3;
top_plate_screw_d           = 3.4;        // M3 clearance through-hole
top_plate_counterbore_d     = 6.5;        // M3 socket-cap counterbore
top_plate_counterbore_depth = 1.5;        // FIXED 2.5 → 1.5 (was > ceiling_thickness)
top_plate_insert_depth      = 5;

// Top plate ventilation grid (over Pi 5 active cooler at X=-70)
vent_slot_grid_count_x      = 5;
vent_slot_grid_count_y      = 3;
vent_slot_size              = [4, 18];
vent_slot_pitch_x           = 9;
vent_slot_pitch_y           = 22;

// Stiffening ribs (azimuths chosen to clear vents at X=-70 and LIDAR mounts at 45° pcd)
top_plate_rib_azimuths      = [30, 150, 210, 330];   // FIXED was 0/90/180/270 (vent collision)
top_plate_rib_width         = 4;
top_plate_rib_height        = 8;

// Top plate accessibility
finger_grip_azimuths        = [90, -90];
finger_grip_size            = [25, 6];

status_led_slot_position    = [-100, 0];
status_led_slot_size        = [30, 4];

// Cable pass-through — MOVED from (-90, 0) to clear LED slot footprint
cable_passthrough_position  = [-110, 20];
cable_passthrough_d         = 12;

// Top plate alignment pin — MOVED from -22.5° to 0° (was at same azimuth as fastener boss)
top_plate_alignment_pin_r   = chassis_radius - wall_thickness/2 - 2;
top_plate_alignment_pin_az  = 0;
top_plate_alignment_pin_d   = 4;
top_plate_alignment_pin_h   = 6;

// ===== 8. BUMPER + COLLISION DETECTION ========================

// 8 microswitches around full perimeter
microswitch_count           = 8;
microswitch_azimuths        = [22.5, 67.5, 112.5, 157.5,
                               -22.5, -67.5, -112.5, -157.5];
microswitch_z               = 25;
microswitch_pad_size        = [16, 12, 2];   // [width_tangent, height_z, depth_radial]
microswitch_screw_pcd       = 10;
microswitch_protrusion      = 9;

// Bumper LED indicator
bumper_led_az               = 0;
bumper_led_size             = [40, 5];

// Bumper geometry (radial clearance must accept microswitch protrusion + travel)
bumper_radial_clearance     = microswitch_protrusion + 4;   // = 13 mm (FIXED was 1.5)
bumper_thickness            = 4;
bumper_height               = 30;
bumper_z_bottom             = 10;
bumper_travel               = 4;

// Bumper hook ledge on chassis exterior (NEW — gives snap hooks something to grab)
bumper_hook_ledge_z         = bumper_z_bottom + 4 + (bumper_height - 8)/2;
bumper_hook_ledge_h         = 3;            // mm vertical extent of ledge
bumper_hook_ledge_protrude  = 1.5;          // mm radial protrusion of ledge

// ===== 9. CABLE MANAGEMENT ====================================

cable_channel_width         = 12;
cable_channel_height        = 5;
cable_channel_thickness     = 1.5;
cable_tie_post_height       = 8;

// Perimeter ring channel for ultrasonic + cliff sensor wiring
perimeter_channel_offset    = 8;
perimeter_channel_height    = 5;

// ===== 10. PRINT SPLITTING ====================================
split_strategy      = "none";
joint_type          = "lap";
joint_count         = 4;
joint_clearance     = 0.2;

// ===== 11. PRINT TOLERANCES + ITER-3 FEATURES =================

slip_fit_clearance  = 0.2;
press_fit_clearance = 0.05;
heat_set_d_m3       = 4.2;
heat_set_d_m25      = 3.6;
heat_set_d_m2       = 3.0;
heat_set_d_m4       = 5.0;
chamfer_size        = 0.5;

// Battery hold-down strap (NEW — simple cross-bar over battery)
battery_strap_thickness     = 2.5;
battery_strap_width         = 12;

// Cliff sensor mounting bracket
cliff_bracket_height        = 8;
cliff_bracket_screw_pcd     = 18;
cliff_bracket_d             = 14;

// Flat panel-mount bosses (switch + charging port)
// AUDIT-2 fix: depth reduced from 4 → 3 mm so chassis OD stays ≤ 256 mm
panel_boss_size             = [25, 25, 3];   // [width_tangent, height_z, depth_radial]

// Sidewall reinforcement near ultrasonic windows
us_reinforcement_size       = [60, 40];
us_reinforcement_thickness  = 2;

// Wheel set-screw boss
wheel_setscrew_boss_d       = 10;
wheel_setscrew_boss_h       = 4;

// Print orientation label
orient_label_depth          = 0.6;
orient_label_size           = 6;

// Derived top-plate values (computed last so all dependencies resolved)
top_plate_bot_z     = chassis_height - ceiling_thickness;
