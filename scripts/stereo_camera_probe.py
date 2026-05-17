#!/usr/bin/env python3
# =============================================================================
# stereo_camera_probe.py — Image-quality tools for the ROVAC stereo cameras.
#
# Two modes:
#
#   probe  (default) — compare objective quality metrics of left vs right.
#       python3 stereo_camera_probe.py [probe] [collect_seconds]
#     Reports per-camera frame rate, brightness, contrast, per-channel color
#     balance, sharpness (variance of the Laplacian — the standard focus
#     metric), and JPEG size. Saves one frame each to /tmp for visual review.
#
#   focus — live focus readout for ONE camera, for dialing in the manual lens
#           focus by hand.
#       python3 stereo_camera_probe.py focus <left|right>
#     Shows live JPEG byte size: for a fixed scene, a sharper image carries more
#     detail and compresses to a LARGER JPEG, so size tracks focus with good
#     dynamic range — better than a Laplacian on the already-lossy stream, where
#     JPEG quantization caps the high-frequency signal. Rotate the lens slowly
#     and stop where the number peaks. Ctrl-C to finish.
#
# Needs a sourced ROS2 env (ROS_DOMAIN_ID, CycloneDDS) and the cameras running.
# =============================================================================

import io
import sys
import time

import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage

# JPEG decode — prefer OpenCV, fall back to Pillow. Import both independently;
# a missing one is simply None.
try:
    import cv2
except ImportError:
    cv2 = None
try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None


def decode(buf) -> np.ndarray:
    """Decode a JPEG byte buffer to an (H,W,3) uint8 RGB array."""
    if cv2 is not None:
        bgr = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            raise ValueError("JPEG decode failed")
        return bgr[:, :, ::-1]
    if PILImage is not None:
        return np.asarray(PILImage.open(io.BytesIO(bytes(buf))).convert("RGB"))
    raise RuntimeError("need either OpenCV (cv2) or Pillow (PIL) installed")


def save_png(path: str, rgb: np.ndarray) -> None:
    if cv2 is not None:
        cv2.imwrite(path, rgb[:, :, ::-1])
    elif PILImage is not None:
        PILImage.fromarray(rgb.astype(np.uint8)).save(path)


def laplacian_var(gray: np.ndarray) -> float:
    """Variance of the discrete Laplacian — higher = sharper / better focused."""
    lap = (gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2]
           + gray[1:-1, 2:] - 4.0 * gray[1:-1, 1:-1])
    return float(lap.var())


# --- probe mode --------------------------------------------------------------

class _Collector(Node):
    def __init__(self):
        super().__init__("stereo_camera_probe")
        self.frames: dict[str, list] = {"left": [], "right": []}
        self.sizes: dict[str, list] = {"left": [], "right": []}
        self.t0: dict[str, float] = {}
        self.t1: dict[str, float] = {}
        for side in ("left", "right"):
            self.create_subscription(
                CompressedImage, f"/stereo/{side}/image_raw/compressed",
                lambda m, s=side: self._cb(s, m), qos_profile_sensor_data)

    def _cb(self, side: str, msg: CompressedImage) -> None:
        now = time.time()
        self.t0.setdefault(side, now)
        self.t1[side] = now
        self.sizes[side].append(len(msg.data))
        if len(self.frames[side]) < 30:
            self.frames[side].append(decode(msg.data))


def run_probe(dur: float) -> None:
    rclpy.init()
    node = _Collector()
    print(f"Collecting frames for {dur:.0f}s "
          f"(decoder: {'cv2' if cv2 is not None else 'PIL'})...", file=sys.stderr)
    end = time.time() + dur
    while rclpy.ok() and time.time() < end:
        rclpy.spin_once(node, timeout_sec=0.1)

    stats: dict[str, dict] = {}
    for side in ("left", "right"):
        fr, sz = node.frames[side], node.sizes[side]
        if not fr:
            print(f"{side}: NO FRAMES RECEIVED", file=sys.stderr)
            continue
        imgs = np.stack(fr).astype(np.float64)         # (N,H,W,3) RGB
        gray = imgs.mean(axis=3)
        span = max(node.t1[side] - node.t0[side], 1e-9)
        stats[side] = {
            "frames": float(len(sz)),
            "fps": len(sz) / span,
            "brightness": gray.mean(),
            "contrast": gray.std(),
            "R": imgs[..., 0].mean(),
            "G": imgs[..., 1].mean(),
            "B": imgs[..., 2].mean(),
            "sharpness": max(laplacian_var(g) for g in gray),
            "jpeg_kb": float(np.mean(sz)) / 1024.0,
        }
        save_png(f"/tmp/stereo_{side}.png", fr[-1])

    if "left" in stats and "right" in stats:
        left, right = stats["left"], stats["right"]
        print(f"\n{'metric':<27s} {'LEFT':>13s} {'RIGHT':>13s} {'delta':>13s}")
        print("-" * 68)
        for name, key, fmt in [
            ("frames received", "frames", "{:.0f}"),
            ("effective fps", "fps", "{:.1f}"),
            ("brightness (0-255)", "brightness", "{:.1f}"),
            ("contrast (std dev)", "contrast", "{:.1f}"),
            ("red channel mean", "R", "{:.1f}"),
            ("green channel mean", "G", "{:.1f}"),
            ("blue channel mean", "B", "{:.1f}"),
            ("sharpness (Laplacian var)", "sharpness", "{:.0f}"),
            ("avg JPEG size (KB)", "jpeg_kb", "{:.1f}"),
        ]:
            lv, rv = left[key], right[key]
            print(f"{name:<27s} {fmt.format(lv):>13s} {fmt.format(rv):>13s} "
                  f"{fmt.format(rv - lv):>13s}")
        print("\nsaved: /tmp/stereo_left.png  /tmp/stereo_right.png")

    rclpy.try_shutdown()


# --- focus mode --------------------------------------------------------------

def run_focus(side: str) -> None:
    topic = f"/stereo/{side}/image_raw/compressed"
    rclpy.init()
    node = rclpy.create_node("stereo_focus_assist")
    peak = [1.0]

    def cb(msg: CompressedImage) -> None:
        kb = len(msg.data) / 1024.0
        peak[0] = max(peak[0], kb)
        filled = int(40 * min(1.0, kb / peak[0]))
        bar = "#" * filled + "-" * (40 - filled)
        sys.stdout.write(f"\r{side:>5s}  JPEG {kb:7.1f} KB   "
                         f"best {peak[0]:7.1f} KB   [{bar}]")
        sys.stdout.flush()

    node.create_subscription(CompressedImage, topic, cb, qos_profile_sensor_data)
    print(f"Live focus assist — {side.upper()} camera ({topic})")
    print("Aim at a FIXED, detailed scene. Rotate the lens barrel SLOWLY and")
    print("maximize the 'JPEG' number (bigger = sharper). Ctrl-C when done.\n")
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        print(f"\n\nBest JPEG size observed: {peak[0]:.1f} KB")
        if rclpy.ok():
            node.destroy_node()
        rclpy.try_shutdown()


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "focus":
        side = args[1] if len(args) > 1 else ""
        if side not in ("left", "right"):
            sys.exit("usage: stereo_camera_probe.py focus <left|right>")
        run_focus(side)
        return
    dur = 7.0
    for a in args:
        if a == "probe":
            continue
        try:
            dur = float(a)
        except ValueError:
            pass
    run_probe(dur)


if __name__ == "__main__":
    main()
