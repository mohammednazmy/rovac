// ROVAC v3 — Iter-0 chassis skeleton
// Goal: confirm overall chassis geometry, wheel/motor placement, LIDAR recess.
// Not yet printable as-is — internal mounts (Pi, ESP32s, IMU, battery) come in Iter-1.
//
// Coordinate system:
//   Z = 0 at chassis bottom exterior (ground side; chassis floats `ground_clearance`
//       above the floor so wheels reach the ground at Z = -ground_clearance).
//   X = +forward, Y = +left  (REP-103)
//
// View modes — override with `-D '<var>=<value>'` on the openscad command line:
//   view_mode = "assembled" (default)  -- opaque, full envelope
//             | "interior"             -- chassis walls/top hidden so internals show
//             | "cutaway"              -- chassis sliced along the Y=0 plane

view_mode = "assembled";

include <parameters.scad>

// ===== Chassis structural parts =====================================

module chassis_floor() {
    difference() {
        cylinder(d=chassis_diameter, h=floor_thickness);
        // Wheel slots — wheel passes through the floor on each side
        for (sign = [-1, 1])
            translate([0, sign * wheel_track/2, floor_thickness/2])
                cube([wheel_diameter + 4, wheel_width + 4, floor_thickness + 2],
                     center=true);
        // Caster mount cutout (placeholder — final mount detailed in Iter-1)
        translate([caster_offset_x, 0, floor_thickness/2])
            cylinder(d=caster_diameter + 6, h=floor_thickness + 2, center=true);
    }
}

module chassis_wall() {
    difference() {
        cylinder(d=chassis_diameter, h=chassis_height);
        translate([0, 0, -1])
            cylinder(d=chassis_diameter - 2*wall_thickness, h=chassis_height + 2);
    }
}

module chassis_top_plate() {
    translate([0, 0, top_plate_bot_z])
        difference() {
            cylinder(d=chassis_diameter, h=ceiling_thickness);
            translate([0, 0, -1])
                cylinder(d=lidar_well_diameter, h=ceiling_thickness + 2);
        }
}

// ===== Visualization placeholders ====================================

module wheel_placeholder() {
    color([0.12, 0.12, 0.12, 0.85])
        rotate([90, 0, 0])
            cylinder(d=wheel_diameter, h=wheel_width, center=true);
}

module motor_placeholder() {
    color([0.75, 0.75, 0.78, 0.85])
        cylinder(d=motor_body_diameter, h=motor_body_length);
}

module caster_placeholder() {
    // Free-spinning rear wheel — Ø40 mm, ~12 mm wide, axis along Y
    color([0.35, 0.35, 0.35, 0.85])
        rotate([90, 0, 0])
            cylinder(d=caster_diameter, h=12, center=true);
}

module lidar_placeholder() {
    // Solid base (square) — sinks fully into chassis well
    color([0.05, 0.05, 0.05, 0.9])
        translate([-lidar_footprint/2, -lidar_footprint/2, lidar_base_z])
            cube([lidar_footprint, lidar_footprint, lidar_base_height]);
    // Optical enclosure (round, 360° rotating head) — protrudes above chassis top
    color([0.55, 0.55, 0.55, 0.7])
        translate([0, 0, lidar_optical_z])
            cylinder(d=50, h=lidar_optical_height);
    // Red dot to indicate scan-plane height
    color([0.9, 0.1, 0.1, 1.0])
        translate([0, 0, lidar_optical_z])
            cylinder(d=lidar_well_diameter + 4, h=0.3);
}

module ground_plane() {
    // Visual ground reference — large thin translucent disk
    color([0.78, 0.78, 0.82, 0.4])
        translate([0, 0, -ground_clearance - 0.5])
            cylinder(d=chassis_diameter + 80, h=0.5);
}

// ===== Indicators ====================================================

module forward_arrow() {
    // Small red wedge on top plate showing +X (forward)
    color([0.85, 0.1, 0.1, 1.0])
        translate([chassis_radius - 18, 0, chassis_height + 0.1])
            linear_extrude(1.5)
                polygon(points=[[0,-6], [10,0], [0,6]]);
}

// ===== Chassis composition (wraps each part in the right modifier) ====

module chassis_assembly() {
    if (view_mode == "cutaway") {
        // Slice chassis in half along Y=0 plane (keep Y > 0 side)
        difference() {
            color([0.92, 0.88, 0.78, 1.0]) {
                chassis_floor();
                chassis_wall();
                chassis_top_plate();
            }
            translate([-chassis_diameter, -chassis_diameter, -ground_clearance - 1])
                cube([2*chassis_diameter, chassis_diameter, chassis_height + ground_clearance + 60]);
        }
    } else if (view_mode == "interior") {
        // Floor solid; wall + top plate ghosted (% = background, semi-transparent)
        color([0.92, 0.88, 0.78, 1.0]) chassis_floor();
        %chassis_wall();
        %chassis_top_plate();
    } else {
        // assembled — opaque
        color([0.92, 0.88, 0.78, 1.0]) {
            chassis_floor();
            chassis_wall();
            chassis_top_plate();
        }
    }
}

// ===== Assembly ======================================================

chassis_assembly();

// Drive system
for (sign = [-1, 1]) {
    // Wheel at lateral midline
    translate([0, sign * wheel_track/2, wheel_center_z])
        wheel_placeholder();
    // Motor body — extends inward from wheel toward chassis center
    motor_outer_y = sign * (wheel_track/2 - wheel_width/2 - 1);
    translate([0, motor_outer_y, wheel_center_z])
        rotate([sign * 90, 0, 0])
            motor_placeholder();
}

// Caster (rear)
translate([caster_offset_x, 0, caster_diameter/2 - ground_clearance])
    caster_placeholder();

// LIDAR
lidar_placeholder();

// Forward indicator
forward_arrow();

// Ground reference plane
ground_plane();

// ===== Diagnostic echoes =============================================

echo(str("ROVAC v3 Iter-0 — chassis_height=", chassis_height,
         " mm, total_robot=", robot_total_height, " mm"));
echo(str("  wheel_center_z=", wheel_center_z,
         " mm above chassis bottom"));
echo(str("  motor inner ends at Y = ±",
         wheel_track/2 - wheel_width/2 - 1 - motor_body_length, " mm"));
echo(str("  motor strip occupies central X span ±",
         motor_body_diameter/2, " mm"));
echo(str("  bambu_p2s fit margin: ", bambu_build_volume[0] - chassis_diameter,
         " mm (positive = single-piece print fits)"));
