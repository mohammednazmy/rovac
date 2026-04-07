// ============================================
// AS5600 Encoder Mount for Greartisan GB37RG Motor
// REAR MOUNT V3 — PCB on outer face, deeper collar
// ============================================
// Collar friction-fits onto motor body. AS5600 PCB sits in a
// recessed pocket on the outer face, IC facing inward through
// center window toward the magnet. Internal shelf maintains
// air gap geometry.
//
// Motor: Greartisan GB37RG (36.2mm motor body)
// Encoder: UMLIFE AS5600 breakout (23x23mm)

// --- Motor Rear Parameters ---
motor_body_dia     = 36.2;
rear_shaft_dia     = 2;        // measured
rear_shaft_len     = 1;        // measured
rear_hub_dia       = 10;
terminal_width     = 6;
terminal_clearance = 4;

// --- AS5600 Board Parameters ---
pcb_size           = 23;
pcb_thick          = 1.6;
pcb_hole_spacing   = 20;       // measured
pcb_hole_dia       = 2.2;
pcb_clearance      = 0.5;
header_slot_width  = 12;

// --- Magnet & Air Gap ---
magnet_dia         = 6;
magnet_thick       = 2.5;
air_gap            = 1.5;

// --- Mount Parameters ---
collar_wall        = 2;
collar_depth       = 15;       // V3: increased from 10 to 15mm for better grip
collar_clearance   = 0.3;
plate_thick        = 2.5;
wire_slot_width    = 10;

// --- PCB Pocket Parameters (outer face) ---
pocket_depth       = 1.2;      // recess depth for PCB
pocket_wall        = 1.5;      // protective lip height
ic_window          = 16;       // center window for IC

// --- Calculated ---
collar_id      = motor_body_dia + collar_clearance * 2;
collar_od      = collar_id + collar_wall * 2;

ic_above_endcap = rear_shaft_len + magnet_thick + air_gap;  // 5mm

// Internal shelf height: accounts for both air gap AND pocket depression
// The pocket lowers the PCB by pocket_depth, so the shelf must be taller
// to maintain the same magnet-to-IC distance
shelf_hang     = collar_depth - ic_above_endcap + pocket_depth;  // 15-5+1.2 = 11.2mm

// Shelf window — same as IC window for magnet visibility
shelf_window   = ic_window;

plate_top_z    = collar_depth + plate_thick;
pocket_size    = pcb_size + pcb_clearance * 2;

$fn = 80;

// ============ COLLAR (motor-facing) ============

module collar() {
    difference() {
        cylinder(d=collar_od, h=collar_depth);
        
        // Inner bore
        translate([0, 0, -0.5])
            cylinder(d=collar_id, h=collar_depth + 1);
        
        // Wire slots for power terminals (opposite sides, Y axis)
        translate([-wire_slot_width/2, -collar_od/2 - 1, -0.5])
            cube([wire_slot_width, collar_wall + 2, collar_depth + 1]);
        translate([-wire_slot_width/2, collar_id/2 - 1, -0.5])
            cube([wire_slot_width, collar_wall + 2, collar_depth + 1]);
    }
}

// ============ INTERNAL SHELF (replaces V2 posts + bridges) ============

module internal_shelf() {
    // Solid disc shelf inside the collar — acts as air gap spacer
    // and structural platform. Has terminal clearance gaps on Y axis
    // (same sides as the collar wire slots) for motor power terminals.
    shelf_z = collar_depth - shelf_hang;

    // Terminal gap dimensions — must clear the brass tabs + solder + wires
    terminal_gap_width = wire_slot_width + 2;  // slightly wider than collar wire slots

    translate([0, 0, shelf_z]) {
        difference() {
            // Solid disc spanning the full collar bore
            cylinder(d=collar_id - 0.5, h=shelf_hang);

            // Center window — magnet/shaft clearance
            translate([0, 0, -0.5])
                cylinder(d=shelf_window, h=shelf_hang + 1);

            // Terminal clearance gaps on +Y and -Y sides
            // These align with the collar wire slots so terminals pass through
            translate([-terminal_gap_width/2, shelf_window/2 - 1, -0.5])
                cube([terminal_gap_width, collar_id/2, shelf_hang + 1]);
            translate([-terminal_gap_width/2, -collar_id/2, -0.5])
                cube([terminal_gap_width, collar_id/2 - shelf_window/2 + 1, shelf_hang + 1]);

            // Lightening cutouts on X axis (where there are no terminals)
            // Saves plastic while keeping structural ribs
            for (sign = [1, -1]) {
                translate([sign * (shelf_window/2 + 2), -4, -0.5])
                    cube([collar_id/2 - shelf_window/2 - 4, 8, shelf_hang - 2 + 0.5]);
            }
        }
    }
}

module grip_bumps() {
    bump_h = 0.4;
    bump_w = 4;
    bump_len = collar_depth - 2;
    
    for (angle = [60, 150, 240, 330]) {
        rotate([0, 0, angle])
        translate([collar_id/2 - bump_h, -bump_w/2, 1])
            cube([bump_h, bump_w, bump_len]);
    }
}

// ============ PLATE WITH WINDOW ============

module plate_with_window() {
    translate([0, 0, collar_depth]) {
        difference() {
            cylinder(d=collar_od, h=plate_thick);
            translate([0, 0, -0.5])
                cylinder(d=ic_window, h=plate_thick + 1);
        }
    }
}

// ============ PCB POCKET (outer face) ============

module pcb_pocket() {
    pocket_z = plate_top_z;
    lip_z = pocket_z + pocket_depth;
    half_pocket = pocket_size / 2;
    half_collar = collar_od / 2;
    
    // 1. Pocket floor ring (PCB rests on this)
    translate([0, 0, pocket_z])
    difference() {
        cylinder(d=collar_od, h=pocket_depth);
        translate([0, 0, -0.5])
            cylinder(d=ic_window, h=pocket_depth + 1);
    }
    
    // 2. Protective lip with header slots
    translate([0, 0, lip_z]) {
        difference() {
            cylinder(d=collar_od, h=pocket_wall);
            
            // Square pocket interior
            translate([-half_pocket, -half_pocket, -0.5])
                cube([pocket_size, pocket_size, pocket_wall + 1]);
            
            // Header slot on +X side (DIR, SCL, SDA, GPO)
            translate([half_pocket - 1, -header_slot_width/2, -0.5])
                cube([half_collar, header_slot_width, pocket_wall + 1]);
            
            // Header slot on -X side (VCC, OUT, GND)
            translate([-half_collar - 1, -header_slot_width/2, -0.5])
                cube([half_collar, header_slot_width, pocket_wall + 1]);
        }
    }
    
    // 3. M2 screw bosses in pocket floor
    hs = pcb_hole_spacing / 2;
    for (pos = [[hs,hs], [-hs,hs], [-hs,-hs], [hs,-hs]]) {
        translate([pos[0], pos[1], pocket_z]) {
            difference() {
                cylinder(d=4.5, h=pocket_depth);
                translate([0, 0, -plate_thick - 0.5])
                    cylinder(d=1.8, h=plate_thick + pocket_depth + 1);
            }
        }
    }
}

// ============ GHOST PARTS ============

module motor_ghost() {
    color("silver", 0.15) {
        translate([0, 0, -30])
            cylinder(d=motor_body_dia, h=30 + collar_depth);
        cylinder(d=motor_body_dia, h=1);
        cylinder(d=rear_hub_dia, h=2);
        cylinder(d=rear_shaft_dia, h=rear_shaft_len);
    }
    color("gray", 0.3)
        translate([0, 0, rear_shaft_len])
            cylinder(d=magnet_dia, h=magnet_thick);
}

module pcb_ghost_v3() {
    pcb_z = plate_top_z;
    color("green", 0.3)
        translate([-pcb_size/2, -pcb_size/2, pcb_z])
            cube([pcb_size, pcb_size, pcb_thick]);
    color("gold", 0.4) {
        translate([pcb_size/2 - 1, -6, pcb_z + pcb_thick])
            cube([2, 12, 8]);
        translate([-pcb_size/2 - 1, -4, pcb_z + pcb_thick])
            cube([2, 8, 8]);
    }
}

// ============ ASSEMBLY ============

module rear_mount_v3() {
    collar();
    grip_bumps();
    internal_shelf();
    plate_with_window();
    pcb_pocket();
}

rear_mount_v3();

// Uncomment for assembly context:
// motor_ghost();
// pcb_ghost_v3();
