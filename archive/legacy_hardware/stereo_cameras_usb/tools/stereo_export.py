#!/usr/bin/env python3
"""
Stereo Camera Export Tool
Exports recorded stereo camera data to video files.

Usage:
    python3 stereo_export.py ~/stereo_capture/session1/ --format mp4
    python3 stereo_export.py ~/stereo_capture/session1/ --format mp4 --colormap jet
    python3 stereo_export.py ~/stereo_capture/session1/ --format gif --fps 10
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional, List

import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


COLORMAPS = {
    'jet': cv2.COLORMAP_JET,
    'hot': cv2.COLORMAP_HOT,
    'bone': cv2.COLORMAP_BONE,
    'rainbow': cv2.COLORMAP_RAINBOW,
    'ocean': cv2.COLORMAP_OCEAN,
    'winter': cv2.COLORMAP_WINTER,
    'spring': cv2.COLORMAP_SPRING,
    'cool': cv2.COLORMAP_COOL,
    'hsv': cv2.COLORMAP_HSV,
    'pink': cv2.COLORMAP_PINK,
    'turbo': cv2.COLORMAP_TURBO,
    'viridis': cv2.COLORMAP_VIRIDIS,
    'plasma': cv2.COLORMAP_PLASMA,
    'inferno': cv2.COLORMAP_INFERNO,
    'magma': cv2.COLORMAP_MAGMA,
}


class StereoExporter:
    """Exports recorded stereo data to video formats"""

    def __init__(self, input_dir: str, colormap: str = 'jet',
                 max_depth: float = 3.0):
        self.input_dir = Path(input_dir)
        self.colormap = COLORMAPS.get(colormap, cv2.COLORMAP_JET)
        self.max_depth = max_depth

        # Load metadata
        metadata_path = self.input_dir / 'metadata.json'
        if not metadata_path.exists():
            raise FileNotFoundError(f"No metadata.json in {input_dir}")

        with open(metadata_path) as f:
            self.metadata = json.load(f)

        self.frames = self.metadata.get('frames', [])
        self.original_fps = self.metadata.get('fps', 2.0)

        print(f"Loaded recording: {input_dir}")
        print(f"  Total frames: {len(self.frames)}")
        print(f"  Original FPS: {self.original_fps:.2f}")

    def export_video(self, output_path: str, content: str = 'depth_color',
                     fps: float = None, codec: str = 'mp4v'):
        """Export to video file"""
        fps = fps or self.original_fps
        output_path = Path(output_path)

        # Determine video writer settings
        fourcc = cv2.VideoWriter_fourcc(*codec)

        # Get first frame to determine size
        first_frame = self._load_frame_content(0, content)
        if first_frame is None:
            print(f"Error: No {content} data in recording")
            return False

        height, width = first_frame.shape[:2]

        # Create video writer
        writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
        if not writer.isOpened():
            print(f"Error: Could not create video writer for {output_path}")
            return False

        print(f"Exporting to {output_path}")
        print(f"  Resolution: {width}x{height}")
        print(f"  FPS: {fps}")
        print(f"  Content: {content}")

        # Export frames
        for i, frame_meta in enumerate(self.frames):
            frame = self._load_frame_content(i, content)
            if frame is not None:
                # Ensure frame is BGR
                if len(frame.shape) == 2:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

                writer.write(frame)

            # Progress
            if (i + 1) % 10 == 0:
                progress = ((i + 1) / len(self.frames)) * 100
                print(f"\rExporting: {i + 1}/{len(self.frames)} ({progress:.1f}%)", end='', flush=True)

        writer.release()
        print(f"\nExported to {output_path}")
        return True

    def export_composite(self, output_path: str, fps: float = None,
                         codec: str = 'mp4v', layout: str = 'horizontal'):
        """Export composite video with multiple views"""
        fps = fps or self.original_fps
        output_path = Path(output_path)

        # Load first frame of each type
        left = self._load_frame_content(0, 'left')
        right = self._load_frame_content(0, 'right')
        depth = self._load_frame_content(0, 'depth_color')

        # Determine available content
        has_left = left is not None
        has_right = right is not None
        has_depth = depth is not None

        if not any([has_left, has_right, has_depth]):
            print("Error: No image data in recording")
            return False

        # Calculate composite size
        target_height = 240
        frames_to_combine = []

        if has_left:
            scale = target_height / left.shape[0]
            frames_to_combine.append(('left', int(left.shape[1] * scale)))
        if has_right:
            scale = target_height / right.shape[0]
            frames_to_combine.append(('right', int(right.shape[1] * scale)))
        if has_depth:
            scale = target_height / depth.shape[0]
            frames_to_combine.append(('depth_color', int(depth.shape[1] * scale)))

        if layout == 'horizontal':
            total_width = sum(w for _, w in frames_to_combine)
            output_size = (total_width, target_height)
        else:
            max_width = max(w for _, w in frames_to_combine)
            output_size = (max_width, target_height * len(frames_to_combine))

        # Create video writer
        fourcc = cv2.VideoWriter_fourcc(*codec)
        writer = cv2.VideoWriter(str(output_path), fourcc, fps, output_size)
        if not writer.isOpened():
            print(f"Error: Could not create video writer for {output_path}")
            return False

        print(f"Exporting composite to {output_path}")
        print(f"  Resolution: {output_size[0]}x{output_size[1]}")
        print(f"  Layout: {layout}")

        # Export frames
        for i, frame_meta in enumerate(self.frames):
            images = []

            for content_type, target_width in frames_to_combine:
                img = self._load_frame_content(i, content_type)
                if img is not None:
                    # Convert to BGR if needed
                    if len(img.shape) == 2:
                        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

                    # Resize
                    img = cv2.resize(img, (target_width, target_height))

                    # Add label
                    cv2.putText(img, content_type.upper(), (10, 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    images.append(img)

            # Combine images
            if layout == 'horizontal':
                composite = np.hstack(images)
            else:
                composite = np.vstack(images)

            # Add timestamp
            relative_time = frame_meta.get('relative_time', 0)
            timestamp = f"T: {relative_time:.2f}s | Frame: {i + 1}/{len(self.frames)}"
            cv2.putText(composite, timestamp, (10, composite.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            writer.write(composite)

            # Progress
            if (i + 1) % 10 == 0:
                progress = ((i + 1) / len(self.frames)) * 100
                print(f"\rExporting: {i + 1}/{len(self.frames)} ({progress:.1f}%)", end='', flush=True)

        writer.release()
        print(f"\nExported to {output_path}")
        return True

    def export_gif(self, output_path: str, content: str = 'depth_color',
                   fps: float = 10, scale: float = 0.5, max_colors: int = 256):
        """Export to animated GIF"""
        try:
            from PIL import Image as PILImage
        except ImportError:
            print("Error: PIL/Pillow required for GIF export")
            print("Install with: pip install Pillow")
            return False

        output_path = Path(output_path)
        frames = []

        print(f"Exporting GIF to {output_path}")

        for i, frame_meta in enumerate(self.frames):
            frame = self._load_frame_content(i, content)
            if frame is not None:
                # Convert to RGB
                if len(frame.shape) == 2:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
                else:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Scale down
                if scale != 1.0:
                    new_size = (int(frame.shape[1] * scale), int(frame.shape[0] * scale))
                    frame = cv2.resize(frame, new_size)

                # Convert to PIL
                pil_frame = PILImage.fromarray(frame)
                frames.append(pil_frame)

            # Progress
            if (i + 1) % 10 == 0:
                progress = ((i + 1) / len(self.frames)) * 100
                print(f"\rProcessing: {i + 1}/{len(self.frames)} ({progress:.1f}%)", end='', flush=True)

        if not frames:
            print("\nError: No frames to export")
            return False

        # Save GIF
        duration = int(1000 / fps)  # ms per frame
        frames[0].save(
            str(output_path),
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=0
        )

        print(f"\nExported GIF: {output_path}")
        print(f"  Frames: {len(frames)}")
        print(f"  FPS: {fps}")
        return True

    def export_frames(self, output_dir: str, content: str = 'depth_color',
                      format: str = 'png'):
        """Export individual frames"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        print(f"Exporting frames to {output_dir}")

        exported = 0
        for i, frame_meta in enumerate(self.frames):
            frame = self._load_frame_content(i, content)
            if frame is not None:
                output_path = output_dir / f"{i:06d}.{format}"
                cv2.imwrite(str(output_path), frame)
                exported += 1

            # Progress
            if (i + 1) % 10 == 0:
                progress = ((i + 1) / len(self.frames)) * 100
                print(f"\rExporting: {i + 1}/{len(self.frames)} ({progress:.1f}%)", end='', flush=True)

        print(f"\nExported {exported} frames to {output_dir}")
        return True

    def _load_frame_content(self, index: int, content: str) -> Optional[np.ndarray]:
        """Load specific content from frame"""
        if index >= len(self.frames):
            return None

        frame_meta = self.frames[index]

        if content == 'left' and 'left' in frame_meta:
            path = self.input_dir / 'left' / frame_meta['left']
            if path.exists():
                return cv2.imread(str(path))

        elif content == 'right' and 'right' in frame_meta:
            path = self.input_dir / 'right' / frame_meta['right']
            if path.exists():
                return cv2.imread(str(path))

        elif content == 'depth' and 'depth' in frame_meta:
            path = self.input_dir / 'depth' / frame_meta['depth']
            if path.exists():
                depth_mm = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                depth = depth_mm.astype(np.float32) / 1000.0
                # Colorize depth
                depth_normalized = np.clip(depth / self.max_depth, 0, 1)
                return cv2.applyColorMap(
                    (depth_normalized * 255).astype(np.uint8),
                    self.colormap
                )

        elif content == 'depth_color' and 'depth_color' in frame_meta:
            path = self.input_dir / 'depth_color' / frame_meta['depth_color']
            if path.exists():
                return cv2.imread(str(path))

        return None


def main():
    parser = argparse.ArgumentParser(description='Export recorded stereo camera data')
    parser.add_argument('input', help='Input directory with recorded data')
    parser.add_argument('--output', '-o', help='Output file path')
    parser.add_argument('--format', '-f', choices=['mp4', 'avi', 'gif', 'frames'],
                        default='mp4', help='Output format (default: mp4)')
    parser.add_argument('--content', '-c', choices=['left', 'right', 'depth', 'depth_color', 'composite'],
                        default='depth_color', help='Content to export (default: depth_color)')
    parser.add_argument('--fps', type=float, help='Output FPS (default: original)')
    parser.add_argument('--colormap', choices=list(COLORMAPS.keys()),
                        default='jet', help='Colormap for depth (default: jet)')
    parser.add_argument('--max-depth', type=float, default=3.0,
                        help='Maximum depth for colorization (default: 3.0m)')
    parser.add_argument('--scale', type=float, default=1.0,
                        help='Scale factor for output (default: 1.0)')
    parser.add_argument('--layout', choices=['horizontal', 'vertical'],
                        default='horizontal', help='Layout for composite (default: horizontal)')

    args = parser.parse_args()

    if not HAS_CV2:
        print("Error: OpenCV is required for export")
        return 1

    if not Path(args.input).exists():
        print(f"Error: Input directory not found: {args.input}")
        return 1

    # Create exporter
    exporter = StereoExporter(args.input, colormap=args.colormap, max_depth=args.max_depth)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        input_name = Path(args.input).name
        if args.format == 'frames':
            output_path = str(Path(args.input).parent / f"{input_name}_{args.content}_frames")
        elif args.format == 'gif':
            output_path = str(Path(args.input).parent / f"{input_name}_{args.content}.gif")
        else:
            output_path = str(Path(args.input).parent / f"{input_name}_{args.content}.{args.format}")

    # Export based on format
    if args.format == 'gif':
        return 0 if exporter.export_gif(output_path, content=args.content,
                                         fps=args.fps or 10, scale=args.scale) else 1
    elif args.format == 'frames':
        return 0 if exporter.export_frames(output_path, content=args.content) else 1
    elif args.content == 'composite':
        codec = 'mp4v' if args.format == 'mp4' else 'XVID'
        return 0 if exporter.export_composite(output_path, fps=args.fps,
                                               codec=codec, layout=args.layout) else 1
    else:
        codec = 'mp4v' if args.format == 'mp4' else 'XVID'
        return 0 if exporter.export_video(output_path, content=args.content,
                                           fps=args.fps, codec=codec) else 1


if __name__ == '__main__':
    sys.exit(main())
