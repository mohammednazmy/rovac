#!/usr/bin/env python3
"""Test camera access on Pi - determines correct device IDs"""

import cv2
import time

def test_camera(device_id):
    cap = cv2.VideoCapture(device_id)
    if not cap.isOpened():
        return None
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    ret, frame = cap.read()
    cap.release()
    
    if ret and frame is not None:
        return frame.shape
    return None

print("Testing camera devices...")
for i in [0, 1, 2, 3, 4, 10]:
    result = test_camera(i)
    if result:
        print(f"  /dev/video{i}: OK - {result}")
    else:
        print(f"  /dev/video{i}: Not available or no frame")
