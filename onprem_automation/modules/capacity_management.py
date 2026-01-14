"""
Capacity Management Module
Automates storage and compute capacity monitoring, forecasting, and planning.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta
import statistics

from ..core.engine import AutomationModule
from ..core.config import Config
from ..core.logger import get_logger


class ResourceType(Enum):
    """Resource types for capacity management."""
    STORAGE = "storage"
    COMPUTE = "compute"
    MEMORY = "memory"
    NETWORK = "network"


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class CapacityMetric:
    """Capacity metric data point."""
    resource_type: ResourceType
    resource_name: str
    timestamp: datetime
    total_capacity: float
    used_capacity: float
    unit: str  # GB, TB, vCPU, etc.

    @property
    def utilization_percent(self) -> float:
        if self.total_capacity == 0:
            return 0.0
        return (self.used_capacity / self.total_capacity) * 100

    @property
    def available_capacity(self) -> float:
        return self.total_capacity - self.used_capacity


@dataclass
class CapacityForecast:
    """Capacity forecast result."""
    resource_name: str
    current_utilization: float
    forecasted_utilization: float
    days_until_threshold: Optional[int]
    growth_rate_per_day: float
    confidence: float
    recommendations: List[str]


class MetricsCollector:
    """
    Collects capacity metrics from various sources.
    Supports VMware, storage arrays, and custom data sources.
    """

    def __init__(self):
        self.logger = get_logger("capacity.collector")
        self._metrics_history: Dict[str, List[CapacityMetric]] = {}

    def collect_vmware_metrics(self, vcenter_client) -> List[CapacityMetric]:
        """Collect compute and storage metrics from VMware."""
        metrics = []

        # In production, query vCenter API for:
        # - Cluster CPU usage
        # - Cluster memory usage
        # - Datastore capacity
        # - Host resources

        # Example mock data
        metrics.append(CapacityMetric(
            resource_type=ResourceType.COMPUTE,
            resource_name="Production-Cluster",
            timestamp=datetime.now(),
            total_capacity=384,  # vCPUs
            used_capacity=256,
            unit="vCPU"
        ))

        metrics.append(CapacityMetric(
            resource_type=ResourceType.MEMORY,
            resource_name="Production-Cluster",
            timestamp=datetime.now(),
            total_capacity=1536,  # GB
            used_capacity=1024,
            unit="GB"
        ))

        return metrics

    def collect_storage_metrics(self, storage_array) -> List[CapacityMetric]:
        """Collect metrics from storage arrays."""
        metrics = []

        # In production, query storage array API (NetApp, Pure, EMC, etc.)

        metrics.append(CapacityMetric(
            resource_type=ResourceType.STORAGE,
            resource_name="NetApp-FAS8200",
            timestamp=datetime.now(),
            total_capacity=100,  # TB
            used_capacity=72,
            unit="TB"
        ))

        return metrics

    def store_metric(self, metric: CapacityMetric) -> None:
        """Store metric for historical analysis."""
        key = f"{metric.resource_type.value}:{metric.resource_name}"
        if key not in self._metrics_history:
            self._metrics_history[key] = []
        self._metrics_history[key].append(metric)

    def get_history(
        self,
        resource_type: ResourceType,
        resource_name: str,
        days: int = 30
    ) -> List[CapacityMetric]:
        """Get historical metrics for a resource."""
        key = f"{resource_type.value}:{resource_name}"
        history = self._metrics_history.get(key, [])

        cutoff = datetime.now() - timedelta(days=days)
        return [m for m in history if m.timestamp >= cutoff]


class CapacityForecaster:
    """
    Forecasting engine for capacity planning.
    Uses statistical methods to predict future capacity needs.
    """

    def __init__(self):
        self.logger = get_logger("capacity.forecaster")

    def linear_forecast(
        self,
        metrics: List[CapacityMetric],
        forecast_days: int = 90
    ) -> CapacityForecast:
        """
        Simple linear regression forecast.
        Good for steady, predictable growth patterns.
        """
        if len(metrics) < 2:
            return None

        # Extract utilization values
        utilizations = [m.utilization_percent for m in metrics]

        # Calculate growth rate (simple linear approximation)
        daily_growth = (utilizations[-1] - utilizations[0]) / len(utilizations)

        # Forecast future utilization
        current = utilizations[-1]
        forecasted = current + (daily_growth * forecast_days)

        # Calculate days until threshold (e.g., 85%)
        threshold = 85
        if daily_growth > 0:
            days_until = int((threshold - current) / daily_growth) if current < threshold else 0
        else:
            days_until = None  # Not approaching threshold

        recommendations = []
        if forecasted > 90:
            recommendations.append("CRITICAL: Projected to exceed 90% capacity")
            recommendations.append("Consider adding storage/compute resources")
        elif forecasted > 75:
            recommendations.append("WARNING: Projected to exceed 75% capacity")
            recommendations.append("Plan capacity expansion within next quarter")

        return CapacityForecast(
            resource_name=metrics[-1].resource_name if metrics else "",
            current_utilization=current,
            forecasted_utilization=min(forecasted, 100),
            days_until_threshold=days_until,
            growth_rate_per_day=daily_growth,
            confidence=0.85,  # Simplified confidence
            recommendations=recommendations
        )

    def moving_average_forecast(
        self,
        metrics: List[CapacityMetric],
        window: int = 7,
        forecast_days: int = 90
    ) -> CapacityForecast:
        """
        Moving average based forecast.
        Smooths out short-term fluctuations.
        """
        if len(metrics) < window:
            return self.linear_forecast(metrics, forecast_days)

        utilizations = [m.utilization_percent for m in metrics]

        # Calculate moving averages
        moving_avgs = []
        for i in range(len(utilizations) - window + 1):
            avg = statistics.mean(utilizations[i:i + window])
            moving_avgs.append(avg)

        # Use moving average trend for forecast
        if len(moving_avgs) >= 2:
            trend = (moving_avgs[-1] - moving_avgs[0]) / len(moving_avgs)
        else:
            trend = 0

        current = utilizations[-1]
        forecasted = current + (trend * forecast_days)

        return CapacityForecast(
            resource_name=metrics[-1].resource_name if metrics else "",
            current_utilization=current,
            forecasted_utilization=min(forecasted, 100),
            days_until_threshold=None,
            growth_rate_per_day=trend,
            confidence=0.80,
            recommendations=[]
        )


class CapacityManagementModule(AutomationModule):
    """
    Capacity management automation module.
    Monitors, analyzes, and forecasts storage and compute capacity.
    """

    name = "capacity"
    description = "Storage and compute capacity management and forecasting"

    def __init__(self, config: Config, logger=None):
        super().__init__(config, logger)
        self.collector = MetricsCollector()
        self.forecaster = CapacityForecaster()

    def validate_config(self) -> bool:
        """Validate capacity configuration."""
        return True

    def health_check(self) -> Dict[str, Any]:
        """Check capacity monitoring system health."""
        return {
            "status": "ok",
            "module": self.name,
            "thresholds": {
                "storage_warning": self.config.capacity.storage_threshold_warning,
                "storage_critical": self.config.capacity.storage_threshold_critical,
                "compute_warning": self.config.capacity.compute_threshold_warning,
                "compute_critical": self.config.capacity.compute_threshold_critical
            }
        }

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Execute capacity management action."""
        actions = {
            "get_current_capacity": self._get_current_capacity,
            "get_capacity_trend": self._get_capacity_trend,
            "forecast_capacity": self._forecast_capacity,
            "check_thresholds": self._check_thresholds,
            "generate_capacity_report": self._generate_capacity_report,
            "get_recommendations": self._get_recommendations,
            "list_storage_arrays": self._list_storage_arrays,
            "list_datastores": self._list_datastores,
            "list_clusters": self._list_clusters,
            "analyze_vm_rightsizing": self._analyze_vm_rightsizing,
            "identify_orphaned_resources": self._identify_orphaned_resources,
        }

        if action not in actions:
            return {
                "status": "error",
                "message": f"Unknown action: {action}. Available: {list(actions.keys())}"
            }

        return await actions[action](**kwargs)

    async def _get_current_capacity(
        self,
        resource_type: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get current capacity utilization across all monitored resources.

        Args:
            resource_type: Filter by type (storage, compute, memory)
        """
        self.logger.info(f"Getting current capacity (type={resource_type})")

        # In production, collect real metrics
        capacity_data = {
            "storage": [
                {
                    "name": "Production-Datastore-01",
                    "total_tb": 50,
                    "used_tb": 38.5,
                    "free_tb": 11.5,
                    "utilization_pct": 77,
                    "status": "warning"
                },
                {
                    "name": "Production-Datastore-02",
                    "total_tb": 50,
                    "used_tb": 32.0,
                    "free_tb": 18.0,
                    "utilization_pct": 64,
                    "status": "ok"
                },
                {
                    "name": "NetApp-SAN-LUN01",
                    "total_tb": 100,
                    "used_tb": 72.0,
                    "free_tb": 28.0,
                    "utilization_pct": 72,
                    "status": "ok"
                },
            ],
            "compute": [
                {
                    "name": "Production-Cluster",
                    "total_vcpu": 384,
                    "used_vcpu": 312,
                    "utilization_pct": 81.25,
                    "status": "warning"
                },
                {
                    "name": "Development-Cluster",
                    "total_vcpu": 192,
                    "used_vcpu": 96,
                    "utilization_pct": 50,
                    "status": "ok"
                },
            ],
            "memory": [
                {
                    "name": "Production-Cluster",
                    "total_gb": 1536,
                    "used_gb": 1228,
                    "utilization_pct": 79.95,
                    "status": "warning"
                },
                {
                    "name": "Development-Cluster",
                    "total_gb": 768,
                    "used_gb": 384,
                    "utilization_pct": 50,
                    "status": "ok"
                },
            ]
        }

        if resource_type:
            capacity_data = {resource_type: capacity_data.get(resource_type, [])}

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "capacity": capacity_data
        }

    async def _get_capacity_trend(
        self,
        resource_name: str,
        days: int = 30,
        **kwargs
    ) -> Dict[str, Any]:
        """Get historical capacity trend for a resource."""
        self.logger.info(f"Getting capacity trend for {resource_name} ({days} days)")

        # In production, query metrics database
        trend_data = {
            "resource_name": resource_name,
            "period_days": days,
            "data_points": [
                {"date": "2024-01-01", "utilization_pct": 68},
                {"date": "2024-01-08", "utilization_pct": 70},
                {"date": "2024-01-15", "utilization_pct": 72},
                {"date": "2024-01-22", "utilization_pct": 74},
                {"date": "2024-01-29", "utilization_pct": 77},
            ],
            "trend": "increasing",
            "average_daily_growth": 0.3,
            "min_utilization": 68,
            "max_utilization": 77,
            "average_utilization": 72.2
        }

        return {"status": "success", "trend": trend_data}

    async def _forecast_capacity(
        self,
        resource_name: str,
        forecast_days: int = 90,
        method: str = "linear",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Forecast future capacity utilization.

        Args:
            resource_name: Resource to forecast
            forecast_days: Number of days to forecast
            method: Forecast method (linear, moving_average)
        """
        self.logger.info(f"Forecasting capacity for {resource_name} ({forecast_days} days)")

        # Get historical data
        # In production, this would come from metrics database

        # Mock historical metrics
        mock_metrics = []
        base_util = 65
        for i in range(30):
            mock_metrics.append(CapacityMetric(
                resource_type=ResourceType.STORAGE,
                resource_name=resource_name,
                timestamp=datetime.now() - timedelta(days=30 - i),
                total_capacity=100,
                used_capacity=base_util + (i * 0.4),
                unit="TB"
            ))

        if method == "linear":
            forecast = self.forecaster.linear_forecast(mock_metrics, forecast_days)
        else:
            forecast = self.forecaster.moving_average_forecast(mock_metrics, forecast_days=forecast_days)

        forecast_result = {
            "resource_name": resource_name,
            "current_utilization_pct": forecast.current_utilization,
            "forecasted_utilization_pct": forecast.forecasted_utilization,
            "forecast_days": forecast_days,
            "days_until_warning_threshold": forecast.days_until_threshold,
            "growth_rate_per_day_pct": forecast.growth_rate_per_day,
            "confidence": forecast.confidence,
            "recommendations": forecast.recommendations,
            "forecast_date": (datetime.now() + timedelta(days=forecast_days)).isoformat()
        }

        return {"status": "success", "forecast": forecast_result}

    async def _check_thresholds(self, **kwargs) -> Dict[str, Any]:
        """Check all resources against configured thresholds."""
        self.logger.info("Checking capacity thresholds")

        alerts = []

        # Check storage
        storage_warning = self.config.capacity.storage_threshold_warning
        storage_critical = self.config.capacity.storage_threshold_critical

        # Mock check results
        resources = [
            {"name": "Production-Datastore-01", "type": "storage", "utilization": 77},
            {"name": "Production-Cluster", "type": "compute", "utilization": 81},
            {"name": "Production-Cluster-Memory", "type": "memory", "utilization": 80},
        ]

        compute_warning = self.config.capacity.compute_threshold_warning
        compute_critical = self.config.capacity.compute_threshold_critical

        for resource in resources:
            util = resource["utilization"]

            if resource["type"] == "storage":
                warning_thresh = storage_warning
                critical_thresh = storage_critical
            else:
                warning_thresh = compute_warning
                critical_thresh = compute_critical

            if util >= critical_thresh:
                severity = AlertSeverity.CRITICAL
            elif util >= warning_thresh:
                severity = AlertSeverity.WARNING
            else:
                continue

            alerts.append({
                "resource": resource["name"],
                "type": resource["type"],
                "utilization_pct": util,
                "threshold_pct": warning_thresh if severity == AlertSeverity.WARNING else critical_thresh,
                "severity": severity.value,
                "message": f"{resource['name']} at {util}% utilization"
            })

        return {
            "status": "success",
            "alerts": alerts,
            "total_alerts": len(alerts),
            "critical_count": len([a for a in alerts if a["severity"] == "critical"]),
            "warning_count": len([a for a in alerts if a["severity"] == "warning"])
        }

    async def _generate_capacity_report(
        self,
        report_type: str = "summary",
        include_forecast: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate comprehensive capacity report."""
        self.logger.info(f"Generating {report_type} capacity report")

        report = {
            "report_type": report_type,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_storage_tb": 200,
                "used_storage_tb": 142.5,
                "storage_utilization_pct": 71.25,
                "total_compute_vcpu": 576,
                "used_compute_vcpu": 408,
                "compute_utilization_pct": 70.83,
                "total_memory_gb": 2304,
                "used_memory_gb": 1612,
                "memory_utilization_pct": 69.97
            },
            "by_cluster": [
                {
                    "name": "Production-Cluster",
                    "hosts": 8,
                    "vms": 145,
                    "cpu_pct": 81,
                    "memory_pct": 80,
                    "storage_pct": 77
                },
                {
                    "name": "Development-Cluster",
                    "hosts": 4,
                    "vms": 62,
                    "cpu_pct": 50,
                    "memory_pct": 50,
                    "storage_pct": 64
                }
            ],
            "alerts_summary": {
                "critical": 0,
                "warning": 3,
                "total": 3
            }
        }

        if include_forecast:
            report["forecast_90_days"] = {
                "storage_utilization_pct": 83,
                "compute_utilization_pct": 88,
                "memory_utilization_pct": 85,
                "capacity_recommendations": [
                    "Consider adding compute capacity to Production-Cluster within 60 days",
                    "Monitor storage growth on Production-Datastore-01"
                ]
            }

        return {"status": "success", "report": report}

    async def _get_recommendations(self, **kwargs) -> Dict[str, Any]:
        """Get capacity optimization recommendations."""
        self.logger.info("Generating capacity recommendations")

        recommendations = [
            {
                "priority": "high",
                "category": "compute",
                "resource": "Production-Cluster",
                "recommendation": "Add 2 hosts to cluster to maintain 25% headroom",
                "estimated_runway_days": 45,
                "estimated_cost": "$50,000"
            },
            {
                "priority": "medium",
                "category": "storage",
                "resource": "Production-Datastore-01",
                "recommendation": "Expand datastore by 20TB or migrate VMs",
                "estimated_runway_days": 90,
                "estimated_cost": "$15,000"
            },
            {
                "priority": "low",
                "category": "optimization",
                "resource": "Multiple VMs",
                "recommendation": "Right-size 23 over-provisioned VMs to reclaim 48 vCPU and 192GB RAM",
                "estimated_runway_days": None,
                "estimated_cost": "$0"
            }
        ]

        return {"status": "success", "recommendations": recommendations}

    async def _list_storage_arrays(self, **kwargs) -> Dict[str, Any]:
        """List all monitored storage arrays."""
        arrays = [
            {
                "name": "NetApp-FAS8200-01",
                "type": "NetApp",
                "model": "FAS8200",
                "total_capacity_tb": 100,
                "used_capacity_tb": 72,
                "utilization_pct": 72,
                "health": "healthy"
            },
            {
                "name": "PureStorage-FA-01",
                "type": "Pure Storage",
                "model": "FlashArray//X50",
                "total_capacity_tb": 50,
                "used_capacity_tb": 32,
                "utilization_pct": 64,
                "health": "healthy"
            }
        ]

        return {"status": "success", "storage_arrays": arrays}

    async def _list_datastores(self, **kwargs) -> Dict[str, Any]:
        """List all VMware datastores."""
        datastores = [
            {
                "name": "Production-Datastore-01",
                "type": "VMFS",
                "capacity_tb": 50,
                "free_tb": 11.5,
                "vms": 45,
                "accessible": True
            },
            {
                "name": "Production-Datastore-02",
                "type": "VMFS",
                "capacity_tb": 50,
                "free_tb": 18,
                "vms": 38,
                "accessible": True
            },
            {
                "name": "NFS-Datastore-01",
                "type": "NFS",
                "capacity_tb": 100,
                "free_tb": 42,
                "vms": 62,
                "accessible": True
            }
        ]

        return {"status": "success", "datastores": datastores}

    async def _list_clusters(self, **kwargs) -> Dict[str, Any]:
        """List all compute clusters."""
        clusters = [
            {
                "name": "Production-Cluster",
                "hosts": 8,
                "vms": 145,
                "total_cpu_ghz": 576,
                "used_cpu_ghz": 467,
                "total_memory_gb": 1536,
                "used_memory_gb": 1228,
                "ha_enabled": True,
                "drs_enabled": True
            },
            {
                "name": "Development-Cluster",
                "hosts": 4,
                "vms": 62,
                "total_cpu_ghz": 288,
                "used_cpu_ghz": 144,
                "total_memory_gb": 768,
                "used_memory_gb": 384,
                "ha_enabled": True,
                "drs_enabled": True
            }
        ]

        return {"status": "success", "clusters": clusters}

    async def _analyze_vm_rightsizing(
        self,
        cluster: Optional[str] = None,
        threshold_pct: int = 20,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Analyze VMs for rightsizing opportunities.
        Identifies over-provisioned and under-utilized VMs.
        """
        self.logger.info(f"Analyzing VM rightsizing (threshold={threshold_pct}%)")

        # In production, analyze actual VM metrics
        over_provisioned = [
            {
                "vm_name": "app-server-01",
                "current_vcpu": 8,
                "recommended_vcpu": 4,
                "avg_cpu_usage_pct": 12,
                "current_memory_gb": 32,
                "recommended_memory_gb": 16,
                "avg_memory_usage_pct": 35
            },
            {
                "vm_name": "web-server-05",
                "current_vcpu": 4,
                "recommended_vcpu": 2,
                "avg_cpu_usage_pct": 8,
                "current_memory_gb": 16,
                "recommended_memory_gb": 8,
                "avg_memory_usage_pct": 25
            }
        ]

        total_reclaim_vcpu = sum(vm["current_vcpu"] - vm["recommended_vcpu"] for vm in over_provisioned)
        total_reclaim_memory = sum(vm["current_memory_gb"] - vm["recommended_memory_gb"] for vm in over_provisioned)

        return {
            "status": "success",
            "analysis": {
                "vms_analyzed": 207,
                "over_provisioned_count": len(over_provisioned),
                "potential_vcpu_reclaim": total_reclaim_vcpu,
                "potential_memory_reclaim_gb": total_reclaim_memory,
                "over_provisioned_vms": over_provisioned
            }
        }

    async def _identify_orphaned_resources(self, **kwargs) -> Dict[str, Any]:
        """Identify orphaned VMDKs, snapshots, and unused resources."""
        self.logger.info("Identifying orphaned resources")

        orphaned = {
            "orphaned_vmdks": [
                {"path": "[Datastore-01] old-vm/disk1.vmdk", "size_gb": 50},
                {"path": "[Datastore-02] deleted-vm/disk1.vmdk", "size_gb": 100}
            ],
            "stale_snapshots": [
                {"vm": "test-vm-01", "snapshot": "before-update", "age_days": 45, "size_gb": 25},
                {"vm": "dev-server-03", "snapshot": "backup-snap", "age_days": 30, "size_gb": 15}
            ],
            "powered_off_vms": [
                {"name": "old-app-server", "powered_off_days": 60, "size_gb": 80},
                {"name": "test-vm-archived", "powered_off_days": 90, "size_gb": 40}
            ],
            "total_reclaimable_gb": 310
        }

        return {"status": "success", "orphaned_resources": orphaned}
