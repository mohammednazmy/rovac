#!/usr/bin/env python3
"""Quick test of OpenCV mouse callback on macOS"""
import cv2
import numpy as np

mouse_state = {'x': 0, 'y': 0, 'clicks': 0}

def mouse_callback(event, x, y, flags, param):
    mouse_state['x'] = x
    mouse_state['y'] = y
    if event == cv2.EVENT_LBUTTONDOWN:
        mouse_state['clicks'] += 1
        print(f"CLICK #{mouse_state['clicks']} at ({x}, {y})")

# Create window and set callback
cv2.namedWindow("Mouse Test")
cv2.setMouseCallback("Mouse Test", mouse_callback)

print("Move mouse and click in the window. Press 'q' to quit.")

while True:
    # Create a simple image
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    img[:] = (50, 50, 50)
    
    # Draw mouse position
    mx, my = mouse_state['x'], mouse_state['y']
    cv2.circle(img, (mx, my), 10, (0, 255, 0), -1)
    cv2.putText(img, f"Mouse: ({mx}, {my})", (10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(img, f"Clicks: {mouse_state['clicks']}", (10, 60),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(img, "Click anywhere - should see green dot follow mouse", (10, 380),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
    
    cv2.imshow("Mouse Test", img)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cv2.destroyAllWindows()
print("Done")
