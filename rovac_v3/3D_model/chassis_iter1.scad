// ROVAC v3 — Iter-1 chassis with component mounts + sensor cutouts
//
// Builds on Iter-0 by adding:
//   - Pi 5 placeholder + 4× tall standoffs (rear, above motor strip)
//   - Maker-ESP32 motor controller placeholder + 4× M4 mount inserts (front floor)
//   - ESP32 DevKitV1 sensor hub placeholder + 4× M2 mount inserts (off-axis floor)
//   - BNO055 IMU placeholder + center-post mount
//   - Battery placeholder + cradle rails
//   - LIDAR mounting standoffs hanging from top plate
//   - Cliff sensor floor cutouts (front + rear)
//   - Ultrasonic transducer windows in chassis sidewall (4 perimeter faces)
//
// Coordinate system: Z=0 at chassis bottom exterior; X=+forward, Y=+left (REP-103).
//
// View modes — override with `-D 'view_mode="..."'`:
//   "assembled"  - opaque shell, just LIDAR poking out (default)
//   "interior"   - walls/top ghosted, components visible
//   "cutaway"    - chassis sliced along Y=0 plane
//   "bottom"     - look up at chassis floor (shows wheel slots, cliff holes, caster cutout)

view_mode = "assembled";

include <parameters.scad>

// ===== Helpers =======================================================

// Round-rect "footprint" used by component placeholders
module footprint_box(fp, color_rgb=[0.7,0.7,0.7,0.85]) {
    color(color_rgb)
        translate([-fp[0]/2, -fp[1]/2, 0])
            cube([fp[0], fp[1], fp[2]]);
}

// 4 mount holes/inserts arranged in a rectangle pattern
module mount_holes(pcd, hole_d, hole_h, h_offset=0) {
    for (sx = [-1, 1]) for (sy = [-1, 1])
        translate([sx * pcd[0]/2, sy * pcd[1]/2, h_offset])
            cylinder(d=hole_d, h=hole_h);
}

// Standoff column with M-thread heat-set insert receiver
module standoff(height, outer_d=6, insert_d=heat_set_d_m25, insert_depth=5) {
    difference() {
        cylinder(d=outer_d, h=height);
        translate([0, 0, height - insert_depth + 0.01])
            cylinder(d=insert_d, h=insert_depth + 1);
    }
}

// ===== Chassis structural parts (with cutouts) =======================

module chassis_floor() {
    difference() {
        cylinder(d=chassis_diameter, h=floor_thickness);

        // Wheel slots
        for (sign = [-1, 1])
            translate([0, sign * wheel_track/2, floor_thickness/2])
                cube([wheel_diameter + 4, wheel_width + 4, floor_thickness + 2],
                     center=true);

        // Caster mount: 4× M3 screw holes for caster bracket
        // (bracket and wheel mount BELOW the floor; wheel pivots below chassis,
        //  no big floor cutout needed)
        for (sx = [-1, 1]) for (sy = [-1, 1])
            translate([caster_offset_x + sx * 15, sy * 10, floor_thickness/2])
                cylinder(d=3.4, h=floor_thickness + 2, center=true);

        // Cliff sensor through-holes (lens windows pointing down)
        translate([cliff_anchor_front[0], cliff_anchor_front[1], -1])
            cylinder(d=cliff_window_diameter, h=floor_thickness + 2);
        translate([cliff_anchor_rear[0], cliff_anchor_rear[1], -1])
            cylinder(d=cliff_window_diameter, h=floor_thickness + 2);
    }
}

module chassis_wall() {
    difference() {
        cylinder(d=chassis_diameter, h=chassis_height);
        translate([0, 0, -1])
            cylinder(d=chassis_diameter - 2*wall_thickness, h=chassis_height + 2);

        // Ultrasonic transducer windows on 4 perimeter faces
        // Each face has 2× Ø16 mm holes at 24 mm pitch (HC-SR04 transducer pair)
        for (face = [
            [chassis_radius, 0, 0],            // front (+X)
            [-chassis_radius, 0, 180],         // rear (-X)
            [0, chassis_radius, 90],           // left (+Y)
            [0, -chassis_radius, -90]          // right (-Y)
        ]) {
            translate([face[0], face[1], us_z_center])
                rotate([0, 0, face[2]])
                    rotate([0, 90, 0])
                        for (sy = [-1, 1])
                            translate([0, sy * us_window_pitch/2, -wall_thickness])
                                cylinder(d=us_window_diameter, h=wall_thickness*3);
        }
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

// ===== Mounting structures ===========================================

// Pi 5 — 4 tall standoffs from chassis floor up to Pi mount holes
module pi5_standoffs() {
    color([0.85, 0.85, 0.88, 1.0])
        for (sx = [-1, 1]) for (sy = [-1, 1])
            translate([pi_anchor[0] + sx * pi5_mount_pcd[0]/2,
                       pi_anchor[1] + sy * pi5_mount_pcd[1]/2,
                       floor_thickness])
                standoff(height = pi_anchor[2] - floor_thickness,
                         outer_d = 6,
                         insert_d = heat_set_d_m25,
                         insert_depth = 5);
}

// Maker-ESP32 motor controller — 4 short M4 mount posts on chassis floor
module esp32_motor_mount() {
    color([0.85, 0.85, 0.88, 1.0])
        for (sx = [-1, 1]) for (sy = [-1, 1])
            translate([esp32_motor_anchor[0] + sx * esp32_motor_mount_pcd[0]/2,
                       esp32_motor_anchor[1] + sy * esp32_motor_mount_pcd[1]/2,
                       floor_thickness])
                standoff(height = 4,
                         outer_d = 8,
                         insert_d = heat_set_d_m3 + 0.6,  // M4 insert ≈ 5 mm
                         insert_depth = 4);
}

// ESP32 sensor hub — 4 small M2 posts
module esp32_sensor_mount() {
    color([0.85, 0.85, 0.88, 1.0])
        for (sx = [-1, 1]) for (sy = [-1, 1])
            translate([esp32_sensor_anchor[0] + sx * esp32_sensor_mount_pcd[0]/2,
                       esp32_sensor_anchor[1] + sy * esp32_sensor_mount_pcd[1]/2,
                       floor_thickness])
                standoff(height = 4, outer_d = 5, insert_d = 3, insert_depth = 4);
}

// IMU center post (BNO055 between motors at chassis CoG)
module imu_post() {
    color([0.85, 0.85, 0.88, 1.0])
        translate([imu_anchor[0], imu_anchor[1], floor_thickness])
            difference() {
                cylinder(d=14, h=imu_anchor[2] - floor_thickness);
                translate([0, 0, imu_anchor[2] - floor_thickness - 5])
                    cylinder(d=heat_set_d_m25, h=6);
            }
}

// Battery cradle — two longitudinal rails along the battery's long edge (X)
module battery_cradle() {
    color([0.85, 0.85, 0.88, 1.0])
        for (sy = [-1, 1])
            translate([battery_anchor[0] - battery_footprint[0]/2,
                       battery_anchor[1] + sy * (battery_footprint[1]/2 + 1.5),
                       floor_thickness])
                cube([battery_footprint[0], 3, battery_footprint[2] + 5]);
}

// LIDAR mounting standoffs — hang DOWN from top plate by recess depth
module lidar_mount() {
    color([0.85, 0.85, 0.88, 1.0])
        for (sx = [-1, 1]) for (sy = [-1, 1])
            translate([sx * lidar_mount_pcd/2, sy * lidar_mount_pcd/2, lidar_base_z])
                difference() {
                    cylinder(d=6, h=lidar_recess_depth);
                    translate([0, 0, -0.01])
                        cylinder(d=heat_set_d_m25, h=6);
                }
}

// Caster bracket — flange that mounts UNDER the chassis floor
// (4× M3 through-bolts from above clamp the bracket to the floor underside)
module caster_mount() {
    color([0.45, 0.45, 0.48, 1.0])
        translate([caster_offset_x, 0, -3])
            cylinder(d=caster_diameter + 14, h=3);
}

// ===== Component placeholders ========================================

module pi5_placeholder() {
    translate([pi_anchor[0], pi_anchor[1], pi_anchor[2]]) {
        // Pi 5 board itself (17 mm tall)
        color([0.15, 0.55, 0.25, 0.9])
            footprint_box([pi5_footprint[0], pi5_footprint[1], 17]);
        // Active cooler / heatsink stack on top (18 mm)
        color([0.4, 0.4, 0.45, 0.85])
            translate([0, 0, 17])
                footprint_box([pi5_footprint[0] - 8, pi5_footprint[1] - 6, 18]);
    }
}

module esp32_motor_placeholder() {
    translate([esp32_motor_anchor[0], esp32_motor_anchor[1],
               esp32_motor_anchor[2] + 4])  // sit on top of 4mm mount posts
        color([0.85, 0.35, 0.2, 0.95])  // brick-orange like the photo
            footprint_box(esp32_motor_footprint);
}

module esp32_sensor_placeholder() {
    translate([esp32_sensor_anchor[0], esp32_sensor_anchor[1],
               esp32_sensor_anchor[2] + 4])
        color([0.15, 0.25, 0.45, 0.95])
            footprint_box(esp32_sensor_footprint);
}

module imu_placeholder() {
    translate([imu_anchor[0], imu_anchor[1], imu_anchor[2]])
        color([0.55, 0.15, 0.15, 0.95])
            footprint_box(imu_footprint);
}

module battery_placeholder() {
    translate([battery_anchor[0], battery_anchor[1], battery_anchor[2]])
        color([0.18, 0.18, 0.2, 0.95])
            footprint_box(battery_footprint);
}

module lidar_placeholder() {
    color([0.05, 0.05, 0.05, 0.9])
        translate([-lidar_footprint/2, -lidar_footprint/2, lidar_base_z])
            cube([lidar_footprint, lidar_footprint, lidar_base_height]);
    color([0.55, 0.55, 0.55, 0.7])
        translate([0, 0, lidar_optical_z])
            cylinder(d=50, h=lidar_optical_height);
    color([0.9, 0.1, 0.1, 1.0])
        translate([0, 0, lidar_optical_z])
            cylinder(d=lidar_well_diameter + 4, h=0.3);
}

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
    color([0.35, 0.35, 0.35, 0.85])
        rotate([90, 0, 0])
            cylinder(d=caster_diameter, h=12, center=true);
}

module cliff_placeholder(anchor) {
    translate([anchor[0], anchor[1], anchor[2]])
        color([0.5, 0.3, 0.15, 0.95])
            footprint_box(cliff_footprint);
}

module ultrasonic_placeholder(face_xyz_yaw) {
    translate([face_xyz_yaw[0], face_xyz_yaw[1], us_z_center])
        rotate([0, 0, face_xyz_yaw[2]])
            translate([-us_footprint[2], -us_footprint[0]/2, -us_footprint[1]/2])
                color([0.2, 0.4, 0.65, 0.95])
                    cube([us_footprint[2], us_footprint[0], us_footprint[1]]);
}

module ground_plane() {
    color([0.78, 0.78, 0.82, 0.4])
        translate([0, 0, -ground_clearance - 0.5])
            cylinder(d=chassis_diameter + 80, h=0.5);
}

module forward_arrow() {
    color([0.85, 0.1, 0.1, 1.0])
        translate([chassis_radius - 18, 0, chassis_height + 0.1])
            linear_extrude(1.5)
                polygon(points=[[0,-6], [10,0], [0,6]]);
}

// ===== Chassis composition (view-mode aware) =========================

module chassis_assembly() {
    if (view_mode == "cutaway") {
        difference() {
            color([0.92, 0.88, 0.78, 1.0]) {
                chassis_floor();
                chassis_wall();
                chassis_top_plate();
            }
            translate([-chassis_diameter, -chassis_diameter, -ground_clearance - 1])
                cube([2*chassis_diameter, chassis_diameter,
                      chassis_height + ground_clearance + 60]);
        }
    } else if (view_mode == "interior" || view_mode == "bottom") {
        color([0.92, 0.88, 0.78, 1.0]) chassis_floor();
        %chassis_wall();
        %chassis_top_plate();
    } else {
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
    translate([0, sign * wheel_track/2, wheel_center_z])
        wheel_placeholder();
    motor_outer_y = sign * (wheel_track/2 - wheel_width/2 - 1);
    translate([0, motor_outer_y, wheel_center_z])
        rotate([sign * 90, 0, 0])
            motor_placeholder();
}

// Caster
translate([caster_offset_x, 0, caster_diameter/2 - ground_clearance])
    caster_placeholder();
caster_mount();

// LIDAR
lidar_placeholder();
lidar_mount();

// Pi 5
pi5_standoffs();
pi5_placeholder();

// ESP32 motor controller
esp32_motor_mount();
esp32_motor_placeholder();

// ESP32 sensor hub
esp32_sensor_mount();
esp32_sensor_placeholder();

// BNO055 IMU
imu_post();
imu_placeholder();

// Battery
battery_cradle();
battery_placeholder();

// Cliff sensors
cliff_placeholder(cliff_anchor_front);
cliff_placeholder(cliff_anchor_rear);

// Ultrasonics — [x, y, yaw_rotation_deg]
ultrasonic_placeholder([chassis_radius - 5, 0, 0]);             // front
ultrasonic_placeholder([-(chassis_radius - 5), 0, 180]);        // rear
ultrasonic_placeholder([0, chassis_radius - 5, 90]);            // left
ultrasonic_placeholder([0, -(chassis_radius - 5), -90]);        // right

// Top markings + ground reference
forward_arrow();
ground_plane();

// ===== Diagnostic echoes =============================================

echo(str("ROVAC v3 Iter-1 — chassis_height=", chassis_height,
         " mm, total_robot=", robot_total_height, " mm"));
echo(str("  Pi 5 stack top Z = ", pi_anchor[2] + pi5_footprint[2],
         " mm  (top plate bottom = ", top_plate_bot_z, " mm)"));
echo(str("  ESP32 motor top Z = ",
         esp32_motor_anchor[2] + 4 + esp32_motor_footprint[2], " mm"));
echo(str("  Battery top Z = ",
         battery_anchor[2] + battery_footprint[2], " mm"));
