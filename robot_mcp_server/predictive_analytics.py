#!/usr/bin/env python3
"""
Predictive Analytics for ROVAC
Maintenance forecasting and performance prediction
"""

import numpy as np
import json
import time
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from collections import deque, defaultdict
import statistics


@dataclass
class SensorReading:
    """Single sensor reading with timestamp"""

    sensor_name: str
    value: float
    timestamp: float
    unit: str


@dataclass
class SystemMetrics:
    """System performance metrics"""

    cpu_usage: float
    memory_usage: float
    network_traffic: float
    disk_usage: float
    temperature: float
    timestamp: float


@dataclass
class ComponentHealth:
    """Health status of a robot component"""

    component_name: str
    health_score: float  # 0.0 - 1.0
    last_maintenance: float  # timestamp
    predicted_failure: float  # timestamp of predicted failure
    maintenance_recommendation: str
    metrics_history: List[float]


class PredictiveAnalyticsEngine:
    """Predictive analytics engine for maintenance and performance"""

    def __init__(self):
        self.sensor_history = defaultdict(deque)
        self.system_metrics_history = deque(maxlen=1000)
        self.component_health = {}
        self.prediction_models = {}
        self.anomaly_detectors = {}
        self.performance_trends = {}

        # Initialize component health tracking
        component_names = [
            "motors",
            "sensors",
            "lidar",
            "imu",
            "camera",
            "battery",
            "controller",
        ]
        for name in component_names:
            self.component_health[name] = ComponentHealth(
                component_name=name,
                health_score=1.0,
                last_maintenance=time.time(),
                predicted_failure=time.time() + 86400 * 365,  # 1 year default
                maintenance_recommendation="No action required",
                metrics_history=[],
            )

        # Initialize prediction models (simplified for simulation)
        self._initialize_models()

        print("🔮 Predictive Analytics Engine initialized")
        print(f"   Tracking {len(component_names)} components")
        print("   Ready for maintenance forecasting")

    def _initialize_models(self):
        """Initialize prediction models"""
        # Simple linear regression models for each component
        for component in self.component_health.keys():
            self.prediction_models[component] = {
                "slope": np.random.normal(0, 0.001),  # Degradation rate
                "intercept": 1.0,  # Initial health score
                "noise": 0.05,  # Model uncertainty
            }

        # Anomaly detection thresholds
        self.anomaly_detectors = {
            "cpu_usage": {"mean": 30.0, "std": 15.0, "threshold": 2.0},
            "memory_usage": {"mean": 50.0, "std": 20.0, "threshold": 2.0},
            "temperature": {"mean": 45.0, "std": 10.0, "threshold": 2.5},
            "network_traffic": {"mean": 1000.0, "std": 500.0, "threshold": 3.0},
        }

    def add_sensor_reading(self, reading: SensorReading):
        """Add sensor reading to history"""
        self.sensor_history[reading.sensor_name].append(reading)

        # Keep only recent readings (last 1000)
        if len(self.sensor_history[reading.sensor_name]) > 1000:
            self.sensor_history[reading.sensor_name].popleft()

        # Update component health based on sensor data
        self._update_component_health(reading)

    def add_system_metrics(self, metrics: SystemMetrics):
        """Add system metrics to history"""
        self.system_metrics_history.append(metrics)

        # Check for anomalies
        self._detect_anomalies(metrics)

        # Update performance trends
        self._update_performance_trends(metrics)

    def _update_component_health(self, reading: SensorReading):
        """Update component health based on sensor reading"""
        # Map sensor names to components
        sensor_to_component = {
            "motor_temperature": "motors",
            "motor_current": "motors",
            "lidar_quality": "lidar",
            "imu_drift": "imu",
            "camera_fps": "camera",
            "battery_voltage": "battery",
            "controller_latency": "controller",
        }

        component_name = sensor_to_component.get(reading.sensor_name)
        if component_name:
            component = self.component_health[component_name]

            # Update metrics history
            component.metrics_history.append(reading.value)
            if len(component.metrics_history) > 100:
                component.metrics_history.pop(0)

            # Update health score based on reading
            if "temperature" in reading.sensor_name:
                # Higher temperature = lower health
                health_impact = max(0.0, 1.0 - (reading.value - 40.0) / 20.0)
            elif "quality" in reading.sensor_name:
                # Quality reading directly affects health
                health_impact = reading.value / 100.0
            elif "latency" in reading.sensor_name:
                # Higher latency = lower health
                health_impact = max(0.0, 1.0 - reading.value / 1000.0)
            else:
                # Default: assume 0-100 scale where higher is better
                health_impact = min(1.0, reading.value / 100.0)

            # Smooth update of health score
            component.health_score = component.health_score * 0.9 + health_impact * 0.1

            # Predict failure time
            self._predict_failure_time(component)

    def _predict_failure_time(self, component: ComponentHealth):
        """Predict component failure time using simple model"""
        if len(component.metrics_history) < 10:
            return

        # Simple linear degradation model
        recent_values = (
            component.metrics_history[-20:]
            if len(component.metrics_history) >= 20
            else component.metrics_history
        )
        if len(recent_values) < 3:
            return

        # Calculate trend
        x = np.arange(len(recent_values))
        y = np.array(recent_values)

        # Linear regression
        if len(x) > 1:
            slope, intercept = np.polyfit(x, y, 1)

            # Predict when health will drop below 0.3 (failure threshold)
            if slope < 0 and component.health_score > 0.3:
                time_to_failure = (0.3 - component.health_score) / slope
                if time_to_failure > 0:
                    component.predicted_failure = (
                        time.time() + time_to_failure * 3600
                    )  # Convert to seconds

                    # Set maintenance recommendation
                    days_until_failure = time_to_failure / 24.0
                    if days_until_failure < 1:
                        component.maintenance_recommendation = (
                            "Immediate maintenance required"
                        )
                    elif days_until_failure < 7:
                        component.maintenance_recommendation = (
                            "Schedule maintenance within 1 week"
                        )
                    elif days_until_failure < 30:
                        component.maintenance_recommendation = (
                            "Plan maintenance within 1 month"
                        )
                    else:
                        component.maintenance_recommendation = "No action required"
            else:
                component.predicted_failure = time.time() + 86400 * 365  # 1 year
                component.maintenance_recommendation = "No action required"

    def _detect_anomalies(self, metrics: SystemMetrics):
        """Detect system anomalies"""
        for metric_name, detector in self.anomaly_detectors.items():
            metric_value = getattr(metrics, metric_name, None)
            if metric_value is not None:
                # Z-score anomaly detection
                z_score = abs(metric_value - detector["mean"]) / detector["std"]
                if z_score > detector["threshold"]:
                    print(
                        f"⚠️  ANOMALY DETECTED: {metric_name} = {metric_value:.2f} (z-score: {z_score:.2f})"
                    )

                    # Update detector statistics
                    detector["mean"] = detector["mean"] * 0.99 + metric_value * 0.01
                    detector["std"] = (
                        detector["std"] * 0.99
                        + abs(metric_value - detector["mean"]) * 0.01
                    )

    def _update_performance_trends(self, metrics: SystemMetrics):
        """Update performance trend analysis"""
        # Add current metrics to trends
        for attr in ["cpu_usage", "memory_usage", "network_traffic", "temperature"]:
            value = getattr(metrics, attr)
            if attr not in self.performance_trends:
                self.performance_trends[attr] = deque(maxlen=100)
            self.performance_trends[attr].append(value)

    def get_component_health_report(self) -> Dict[str, Any]:
        """Generate component health report"""
        report = {}
        current_time = time.time()

        for name, component in self.component_health.items():
            days_until_failure = (component.predicted_failure - current_time) / 86400

            report[name] = {
                "health_score": round(component.health_score, 3),
                "days_until_failure": round(max(0, days_until_failure), 1),
                "maintenance_recommendation": component.maintenance_recommendation,
                "last_maintenance_days_ago": round(
                    (current_time - component.last_maintenance) / 86400, 1
                ),
                "recent_trend": self._calculate_trend(component.metrics_history),
            }

        return report

    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction from values"""
        if len(values) < 3:
            return "stable"

        recent_values = values[-10:] if len(values) >= 10 else values
        if len(recent_values) < 2:
            return "stable"

        # Simple trend calculation
        first_half = sum(recent_values[: len(recent_values) // 2]) / (
            len(recent_values) // 2
        )
        second_half = sum(recent_values[len(recent_values) // 2 :]) / (
            len(recent_values) - len(recent_values) // 2
        )

        diff = second_half - first_half

        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "degrading"
        else:
            return "stable"

    def get_system_performance_report(self) -> Dict[str, Any]:
        """Generate system performance report"""
        if not self.system_metrics_history:
            return {"status": "No data available"}

        latest = self.system_metrics_history[-1]
        recent_metrics = list(self.system_metrics_history)[-50:]  # Last 50 readings

        # Calculate statistics
        stats = {}
        for attr in ["cpu_usage", "memory_usage", "network_traffic", "temperature"]:
            values = [getattr(m, attr) for m in recent_metrics]
            stats[attr] = {
                "current": getattr(latest, attr),
                "average": round(statistics.mean(values), 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "std_dev": round(statistics.stdev(values) if len(values) > 1 else 0, 2),
                "trend": self._calculate_metric_trend(values),
            }

        return {
            "timestamp": latest.timestamp,
            "metrics": stats,
            "total_readings": len(self.system_metrics_history),
            "performance_status": self._assess_performance_status(stats),
        }

    def _calculate_metric_trend(self, values: List[float]) -> str:
        """Calculate trend for metric values"""
        if len(values) < 3:
            return "stable"

        # Linear regression for trend
        x = np.arange(len(values))
        slope, _ = np.polyfit(x, values, 1)

        if slope > 0.5:
            return "increasing"
        elif slope < -0.5:
            return "decreasing"
        else:
            return "stable"

    def _assess_performance_status(self, stats: Dict[str, Any]) -> str:
        """Assess overall system performance status"""
        issues = 0

        # Check for critical thresholds
        if stats["cpu_usage"]["current"] > 80:
            issues += 2
        elif stats["cpu_usage"]["current"] > 60:
            issues += 1

        if stats["memory_usage"]["current"] > 85:
            issues += 2
        elif stats["memory_usage"]["current"] > 70:
            issues += 1

        if stats["temperature"]["current"] > 70:
            issues += 2
        elif stats["temperature"]["current"] > 60:
            issues += 1

        if issues >= 4:
            return "critical"
        elif issues >= 2:
            return "warning"
        else:
            return "normal"

    def simulate_data_collection(self, duration_seconds: int = 60):
        """Simulate data collection for testing"""
        print(f"🧪 Simulating {duration_seconds} seconds of data collection...")

        start_time = time.time()
        current_time = start_time

        while (current_time - start_time) < duration_seconds:
            # Simulate sensor readings
            sensors = [
                ("motor_temperature", np.random.normal(45, 5), "°C"),
                ("lidar_quality", np.random.normal(95, 3), "%"),
                ("battery_voltage", np.random.normal(12.0, 0.2), "V"),
                ("controller_latency", np.random.normal(50, 10), "ms"),
            ]

            for sensor_name, value, unit in sensors:
                reading = SensorReading(sensor_name, value, current_time, unit)
                self.add_sensor_reading(reading)

            # Simulate system metrics
            metrics = SystemMetrics(
                cpu_usage=np.random.normal(30, 10),
                memory_usage=np.random.normal(50, 15),
                network_traffic=np.random.normal(1000, 300),
                disk_usage=np.random.normal(60, 10),
                temperature=np.random.normal(45, 5),
                timestamp=current_time,
            )
            self.add_system_metrics(metrics)

            # Wait a bit
            time.sleep(0.1)
            current_time = time.time()

        print("✅ Data collection simulation completed!")


# Example usage
def main():
    """Example usage of predictive analytics engine"""
    print("🔮 ROVAC Predictive Analytics Engine")
    print("=" * 40)

    # Initialize engine
    analytics = PredictiveAnalyticsEngine()

    # Simulate data collection
    analytics.simulate_data_collection(duration_seconds=30)

    # Generate reports
    print("\n📋 Component Health Report:")
    health_report = analytics.get_component_health_report()
    for component, data in health_report.items():
        print(
            f"   {component}: {data['health_score']:.2f} health, {data['days_until_failure']:.1f} days until maintenance"
        )

    print("\n📊 System Performance Report:")
    perf_report = analytics.get_system_performance_report()
    if "metrics" in perf_report:
        metrics = perf_report["metrics"]
        print(f"   Status: {perf_report['performance_status']}")
        print(
            f"   CPU: {metrics['cpu_usage']['current']:.1f}% (avg: {metrics['cpu_usage']['average']:.1f}%)"
        )
        print(
            f"   Memory: {metrics['memory_usage']['current']:.1f}% (avg: {metrics['memory_usage']['average']:.1f}%)"
        )
        print(
            f"   Temperature: {metrics['temperature']['current']:.1f}°C (avg: {metrics['temperature']['average']:.1f}°C)"
        )


if __name__ == "__main__":
    main()
