"""
Metrics Package

Provides Prometheus metrics collection and exposition:
- Action metrics (counts, durations, errors)
- Module health metrics
- System metrics
"""

from .collector import MetricsCollector, get_metrics_collector, _reset_metrics_collector
from .decorators import track_action, track_duration, track_itsm, MetricsContext

__all__ = [
    "MetricsCollector",
    "get_metrics_collector",
    "_reset_metrics_collector",
    "track_action",
    "track_duration",
    "track_itsm",
    "MetricsContext",
]
