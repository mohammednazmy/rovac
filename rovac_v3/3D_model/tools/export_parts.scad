// Helper: export an individual part as STL.
// Usage: openscad -D 'part="floor"' -o /tmp/floor.stl tools/export_parts.scad
// Valid parts: floor, wall, top_plate, full_chassis

use <../chassis_iter3.scad>
include <../parameters.scad>

part = "full_chassis";

if (part == "floor")
    chassis_floor();
else if (part == "wall")
    chassis_wall();
else if (part == "top_plate")
    chassis_top_plate();
else if (part == "full_chassis")
    union() { chassis_floor(); chassis_wall(); chassis_top_plate(); }
else
    echo("Unknown part: ", part);
