#!/usr/bin/env python3
"""
Heat Signature Detector for ROVAC
Identifies persons, animals, fires, and other heat sources in thermal imagery
"""

import numpy as np
import cv2
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from scipy import ndimage
from thermal_camera_driver import ThermalFrame, HeatSignature


@dataclass
class DetectionConfig:
    """Configuration for heat signature detection"""

    # Temperature thresholds
    person_min_temp: float = 28.0  # Minimum human body temperature (°C)
    person_max_temp: float = 42.0  # Maximum human body temperature (°C)
    fire_min_temp: float = 100.0  # Minimum fire temperature (°C)
    animal_min_temp: float = 25.0  # Minimum animal temperature (°C)
    animal_max_temp: float = 40.0  # Maximum animal temperature (°C)

    # Size constraints
    min_person_pixels: int = 50  # Minimum pixels for person detection
    max_person_pixels: int = 5000  # Maximum pixels for person detection
    min_fire_pixels: int = 20  # Minimum pixels for fire detection
    max_fire_pixels: int = 10000  # Maximum pixels for fire detection

    # Shape analysis
    person_aspect_ratio_min: float = 0.3  # Minimum aspect ratio for person
    person_aspect_ratio_max: float = 3.0  # Maximum aspect ratio for person
    circularity_threshold: float = 0.3  # Minimum circularity for round objects

    # Detection sensitivity
    confidence_threshold: float = 0.5  # Minimum confidence for detection
    noise_reduction_kernel: int = 3  # Kernel size for noise reduction

    # Temporal filtering
    temporal_window: int = 5  # Frames to consider for persistence
    persistence_threshold: float = 0.6  # Minimum persistence for valid detection


class HeatSignatureDetector:
    """Detects heat signatures in thermal imagery"""

    def __init__(self, config: DetectionConfig = None):
        self.config = config or DetectionConfig()
        self.previous_detections: List[HeatSignature] = []
        self.detection_history: Dict[int, List[HeatSignature]] = {}
        self.object_counter = 0

        print("🌡️ Heat Signature Detector initialized")
        print(
            f"   Person detection range: {self.config.person_min_temp}°C - {self.config.person_max_temp}°C"
        )
        print(f"   Fire detection threshold: >{self.config.fire_min_temp}°C")
        print(
            f"   Animal detection range: {self.config.animal_min_temp}°C - {self.config.animal_max_temp}°C"
        )

    def detect_signatures(self, frame: ThermalFrame) -> List[HeatSignature]:
        """Detect heat signatures in thermal frame"""
        signatures = []

        # Preprocess thermal data
        processed_data = self._preprocess_thermal_data(frame.temperature_data)

        # Detect different types of signatures
        person_signatures = self._detect_persons(processed_data, frame)
        fire_signatures = self._detect_fires(processed_data, frame)
        animal_signatures = self._detect_animals(processed_data, frame)

        # Combine all signatures
        signatures.extend(person_signatures)
        signatures.extend(fire_signatures)
        signatures.extend(animal_signatures)

        # Apply temporal filtering
        filtered_signatures = self._apply_temporal_filtering(signatures)

        # Update detection history
        self.previous_detections = filtered_signatures

        return filtered_signatures

    def _preprocess_thermal_data(self, temp_data: np.ndarray) -> np.ndarray:
        """Preprocess thermal data for detection"""
        # Normalize temperature data to 0-255 range for OpenCV
        temp_min = temp_data.min()
        temp_max = temp_data.max()

        if temp_max > temp_min:
            normalized = ((temp_data - temp_min) / (temp_max - temp_min) * 255).astype(
                np.uint8
            )
        else:
            normalized = np.zeros_like(temp_data, dtype=np.uint8)

        # Apply noise reduction
        kernel_size = self.config.noise_reduction_kernel
        if kernel_size > 1:
            kernel = np.ones((kernel_size, kernel_size), np.uint8)
            normalized = cv2.morphologyEx(normalized, cv2.MORPH_OPEN, kernel)

        return normalized

    def _detect_persons(
        self, processed_data: np.ndarray, frame: ThermalFrame
    ) -> List[HeatSignature]:
        """Detect human heat signatures"""
        persons = []

        # Create mask for human body temperature range
        temp_mask = np.logical_and(
            frame.temperature_data >= self.config.person_min_temp,
            frame.temperature_data <= self.config.person_max_temp,
        )

        # Convert to binary image
        binary_mask = (temp_mask * 255).astype(np.uint8)

        # Find contours
        contours, _ = cv2.findContours(
            binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Analyze each contour
        for contour in contours:
            area = cv2.contourArea(contour)

            # Check area constraints
            if (
                area < self.config.min_person_pixels
                or area > self.config.max_person_pixels
            ):
                continue

            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)
            center_x = (x + w / 2) / frame.width
            center_y = (y + h / 2) / frame.height

            # Calculate aspect ratio
            aspect_ratio = w / h if h > 0 else 0

            # Check aspect ratio constraints
            if not (
                self.config.person_aspect_ratio_min
                <= aspect_ratio
                <= self.config.person_aspect_ratio_max
            ):
                continue

            # Calculate peak temperature in region
            region_temp = frame.temperature_data[y : y + h, x : x + w]
            peak_temp = np.max(region_temp) if region_temp.size > 0 else 0

            # Calculate confidence based on multiple factors
            temp_confidence = self._calculate_temperature_confidence(
                peak_temp, "person"
            )
            size_confidence = self._calculate_size_confidence(area, "person")
            shape_confidence = self._calculate_shape_confidence(aspect_ratio, "person")

            # Combined confidence
            confidence = (temp_confidence + size_confidence + shape_confidence) / 3.0

            # Create heat signature if confidence is high enough
            if confidence >= self.config.confidence_threshold:
                signature = HeatSignature(
                    center_x=center_x,
                    center_y=center_y,
                    temperature=peak_temp,
                    area_pixels=int(area),
                    signature_type="person",
                    confidence=min(1.0, confidence),
                )
                persons.append(signature)

        return persons

    def _detect_fires(
        self, processed_data: np.ndarray, frame: ThermalFrame
    ) -> List[HeatSignature]:
        """Detect fire heat signatures"""
        fires = []

        # Create mask for high temperature regions
        fire_mask = frame.temperature_data >= self.config.fire_min_temp

        # Convert to binary image
        binary_mask = (fire_mask * 255).astype(np.uint8)

        # Find contours
        contours, _ = cv2.findContours(
            binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Analyze each contour
        for contour in contours:
            area = cv2.contourArea(contour)

            # Check minimum area
            if area < self.config.min_fire_pixels:
                continue

            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)
            center_x = (x + w / 2) / frame.width
            center_y = (y + h / 2) / frame.height

            # Calculate peak temperature in region
            region_temp = frame.temperature_data[y : y + h, x : x + w]
            peak_temp = np.max(region_temp) if region_temp.size > 0 else 0

            # Calculate confidence (higher temp = higher confidence for fires)
            temp_confidence = min(1.0, (peak_temp - self.config.fire_min_temp) / 100.0)
            size_confidence = min(1.0, area / self.config.max_fire_pixels)
            confidence = (temp_confidence + size_confidence) / 2.0

            # Create heat signature
            if confidence >= self.config.confidence_threshold:
                signature = HeatSignature(
                    center_x=center_x,
                    center_y=center_y,
                    temperature=peak_temp,
                    area_pixels=int(area),
                    signature_type="fire",
                    confidence=min(1.0, confidence),
                )
                fires.append(signature)

        return fires

    def _detect_animals(
        self, processed_data: np.ndarray, frame: ThermalFrame
    ) -> List[HeatSignature]:
        """Detect animal heat signatures"""
        animals = []

        # Create mask for animal body temperature range
        temp_mask = np.logical_and(
            frame.temperature_data >= self.config.animal_min_temp,
            frame.temperature_data <= self.config.animal_max_temp,
        )

        # Exclude human temperature range to avoid duplicates
        human_mask = np.logical_not(
            np.logical_and(
                frame.temperature_data >= self.config.person_min_temp,
                frame.temperature_data <= self.config.person_max_temp,
            )
        )

        # Combine masks
        animal_mask = np.logical_and(temp_mask, human_mask)

        # Convert to binary image
        binary_mask = (animal_mask * 255).astype(np.uint8)

        # Find contours
        contours, _ = cv2.findContours(
            binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Analyze each contour
        for contour in contours:
            area = cv2.contourArea(contour)

            # Check area constraints (animals are typically smaller than humans)
            if area < 20 or area > self.config.min_person_pixels:
                continue

            # Get bounding rectangle
            x, y, w, h = cv2.boundingRect(contour)
            center_x = (x + w / 2) / frame.width
            center_y = (y + h / 2) / frame.height

            # Calculate peak temperature in region
            region_temp = frame.temperature_data[y : y + h, x : x + w]
            peak_temp = np.max(region_temp) if region_temp.size > 0 else 0

            # Calculate confidence
            temp_confidence = self._calculate_temperature_confidence(
                peak_temp, "animal"
            )
            size_confidence = self._calculate_size_confidence(area, "animal")
            confidence = (temp_confidence + size_confidence) / 2.0

            # Create heat signature if confidence is high enough
            if confidence >= self.config.confidence_threshold:
                signature = HeatSignature(
                    center_x=center_x,
                    center_y=center_y,
                    temperature=peak_temp,
                    area_pixels=int(area),
                    signature_type="animal",
                    confidence=min(1.0, confidence),
                )
                animals.append(signature)

        return animals

    def _calculate_temperature_confidence(
        self, temperature: float, signature_type: str
    ) -> float:
        """Calculate confidence based on temperature"""
        if signature_type == "person":
            if (
                self.config.person_min_temp
                <= temperature
                <= self.config.person_max_temp
            ):
                # Higher confidence for temperatures closer to average human body temp (37°C)
                ideal_temp = 37.0
                deviation = abs(temperature - ideal_temp)
                return max(
                    0.0, 1.0 - (deviation / 15.0)
                )  # 15°C range for full confidence
            else:
                return 0.0
        elif signature_type == "animal":
            if (
                self.config.animal_min_temp
                <= temperature
                <= self.config.animal_max_temp
            ):
                # Similar approach for animals
                ideal_temp = 37.0
                deviation = abs(temperature - ideal_temp)
                return max(0.0, 1.0 - (deviation / 20.0))  # 20°C range for animals
            else:
                return 0.0
        else:  # Default case
            return 0.5

    def _calculate_size_confidence(self, area: float, signature_type: str) -> float:
        """Calculate confidence based on size"""
        if signature_type == "person":
            # Linear interpolation between min and max person sizes
            if area < self.config.min_person_pixels:
                return 0.0
            elif area > self.config.max_person_pixels:
                return 0.0
            else:
                # Peak confidence at mid-range
                mid_point = (
                    self.config.min_person_pixels + self.config.max_person_pixels
                ) / 2
                if area <= mid_point:
                    return (area - self.config.min_person_pixels) / (
                        mid_point - self.config.min_person_pixels
                    )
                else:
                    return 1.0 - (area - mid_point) / (
                        self.config.max_person_pixels - mid_point
                    )
        elif signature_type == "animal":
            # Animals are smaller
            if area < 20:
                return 0.0
            elif area > self.config.min_person_pixels:
                return 0.0
            else:
                return 1.0 - (area / self.config.min_person_pixels)
        else:
            return 0.5

    def _calculate_shape_confidence(
        self, aspect_ratio: float, signature_type: str
    ) -> float:
        """Calculate confidence based on shape"""
        if signature_type == "person":
            if (
                self.config.person_aspect_ratio_min
                <= aspect_ratio
                <= self.config.person_aspect_ratio_max
            ):
                # Higher confidence for aspect ratios closer to 1.0 (square-ish)
                deviation = abs(aspect_ratio - 1.0)
                return max(0.0, 1.0 - (deviation / 2.0))
            else:
                return 0.0
        else:
            return 0.5

    def _apply_temporal_filtering(
        self, current_detections: List[HeatSignature]
    ) -> List[HeatSignature]:
        """Apply temporal filtering to reduce false positives"""
        if not self.previous_detections:
            return current_detections

        filtered_detections = []

        # For each current detection, check if similar detections existed recently
        for current in current_detections:
            # Find similar previous detections
            similar_detections = []
            for prev in self.previous_detections:
                # Check spatial proximity (within 10% of frame)
                distance = np.sqrt(
                    (current.center_x - prev.center_x) ** 2
                    + (current.center_y - prev.center_y) ** 2
                )
                if distance < 0.1 and current.signature_type == prev.signature_type:
                    similar_detections.append(prev)

            # If similar detections exist, boost confidence
            if similar_detections:
                # Average confidence with persistence bonus
                avg_confidence = np.mean([d.confidence for d in similar_detections])
                current.confidence = min(
                    1.0, (current.confidence + avg_confidence) / 2.0 + 0.1
                )

            # Only keep detections that meet persistence threshold
            if current.confidence >= self.config.persistence_threshold:
                filtered_detections.append(current)

        return filtered_detections

    def visualize_detections(
        self, frame: ThermalFrame, detections: List[HeatSignature]
    ) -> np.ndarray:
        """Create visualization of thermal frame with detections"""
        # Normalize temperature data for display
        temp_data = frame.temperature_data
        temp_min = temp_data.min()
        temp_max = temp_data.max()

        if temp_max > temp_min:
            normalized = ((temp_data - temp_min) / (temp_max - temp_min) * 255).astype(
                np.uint8
            )
        else:
            normalized = np.zeros_like(temp_data, dtype=np.uint8)

        # Convert to color image (pseudo-color thermal)
        colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)

        # Draw detections
        height, width = colored.shape[:2]

        for detection in detections:
            # Convert normalized coordinates to pixel coordinates
            x = int(detection.center_x * width)
            y = int(detection.center_y * height)

            # Draw circle around detection
            radius = max(5, int(np.sqrt(detection.area_pixels / np.pi)))
            color = self._get_detection_color(detection.signature_type)

            cv2.circle(colored, (x, y), radius, color, 2)

            # Draw label
            label = f"{detection.signature_type}: {detection.temperature:.1f}°C"
            confidence_text = f"Conf: {detection.confidence:.2f}"

            cv2.putText(
                colored,
                label,
                (x - 50, y - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                color,
                1,
            )
            cv2.putText(
                colored,
                confidence_text,
                (x - 50, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                color,
                1,
            )

        return colored

    def _get_detection_color(self, signature_type: str) -> Tuple[int, int, int]:
        """Get color for detection type"""
        colors = {
            "person": (0, 255, 0),  # Green
            "fire": (0, 0, 255),  # Red
            "animal": (255, 255, 0),  # Cyan
            "vehicle": (255, 0, 0),  # Blue
            "default": (128, 128, 128),  # Gray
        }
        return colors.get(signature_type, colors["default"])

    def get_detection_statistics(
        self, detections: List[HeatSignature]
    ) -> Dict[str, int]:
        """Get statistics about detections"""
        stats = {}
        for detection in detections:
            signature_type = detection.signature_type
            stats[signature_type] = stats.get(signature_type, 0) + 1
        return stats


# Example usage
def main():
    """Example usage of heat signature detector"""
    print("🌡️ ROVAC Heat Signature Detector Demo")
    print("=" * 40)

    # Create detector
    detector = HeatSignatureDetector()

    # Create sample thermal frame (normally from camera)
    from thermal_camera_driver import ThermalFrame
    import time

    # Create sample temperature data
    temp_data = np.random.normal(25.0, 5.0, (120, 160))  # Room temp with variation
    raw_data = np.random.randint(0, 65535, (120, 160), dtype=np.uint16)

    # Add some hot spots
    temp_data[50:70, 70:90] = 37.0  # Person-like temperature
    temp_data[30:40, 120:130] = 150.0  # Fire-like temperature

    frame = ThermalFrame(
        temperature_data=temp_data,
        raw_data=raw_data,
        timestamp=time.time(),
        width=160,
        height=120,
    )

    # Detect signatures
    detections = detector.detect_signatures(frame)

    print(f"📊 Detected {len(detections)} heat signatures:")
    for i, detection in enumerate(detections):
        print(
            f"   {i + 1}. {detection.signature_type} at ({detection.center_x:.2f}, {detection.center_y:.2f}) "
            f"- {detection.temperature:.1f}°C (conf: {detection.confidence:.2f})"
        )

    # Get statistics
    stats = detector.get_detection_statistics(detections)
    print(f"\n📈 Detection Statistics: {stats}")

    # Create visualization
    visualization = detector.visualize_detections(frame, detections)
    print(f"🎨 Visualization created: {visualization.shape}")


if __name__ == "__main__":
    main()
