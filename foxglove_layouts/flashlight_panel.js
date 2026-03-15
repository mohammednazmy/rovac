// Foxglove User Script Panel — Flashlight Toggle Button
//
// Setup:
// 1. Add a "User Script" panel in Foxglove
// 2. Paste this entire script into the panel
// 3. Click the button to toggle the flashlight

// Output topic
export const outputs = ["/phone/flashlight"];
export const inputs = [];

let isOn = false;

export default function script(event, ctx) {
  // This runs on each tick — we use ctx.callAction to render UI
}
