"""
Prometheus Metrics Collector

Provides metrics collection and exposition for monitoring:
- Action execution counts and durations
- Error rates
- Module health status
- System resource usage
"""

from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import time
import threading
import logging

# Try to import prometheus_client
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, Info,
        CollectorRegistry, generate_latest,
        CONTENT_TYPE_LATEST, start_http_server
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    Counter = None
    Histogram = None
    Gauge = None


# Singleton instance
_metrics_collector: Optional["MetricsCollector"] = None


def get_metrics_collector() -> "MetricsCollector":
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def _reset_metrics_collector() -> None:
    """Reset the global metrics collector instance (for testing)."""
    global _metrics_collector
    _metrics_collector = None


@dataclass
class MetricData:
    """In-memory metric storage for when prometheus_client is not available."""
    name: str
    type: str  # counter, gauge, histogram
    labels: Dict[str, str] = field(default_factory=dict)
    value: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    histogram_buckets: List[float] = field(default_factory=list)


class MetricsCollector:
    """
    Prometheus metrics collector for automation framework.

    Provides:
    - Counter for action executions
    - Histogram for action durations
    - Gauge for module health
    - Info for system information

    Can work with or without prometheus_client installed:
    - With prometheus_client: Full Prometheus integration
    - Without: In-memory metrics with /metrics text output
    """

    # Default histogram buckets for action duration (in seconds)
    DEFAULT_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, float("inf"))

    def __init__(self, prefix: str = "onprem_automation"):
        self.prefix = prefix
        self.logger = logging.getLogger("metrics")
        self._lock = threading.Lock()

        if PROMETHEUS_AVAILABLE:
            self._init_prometheus_metrics()
        else:
            self._init_fallback_metrics()

        self._server_started = False

    def _init_prometheus_metrics(self) -> None:
        """Initialize Prometheus metrics."""
        self.registry = CollectorRegistry()

        # Action execution counter
        self.action_total = Counter(
            f"{self.prefix}_action_total",
            "Total number of automation actions executed",
            ["module", "action", "status"],
            registry=self.registry
        )

        # Action duration histogram
        self.action_duration = Histogram(
            f"{self.prefix}_action_duration_seconds",
            "Duration of automation actions in seconds",
            ["module", "action"],
            buckets=self.DEFAULT_BUCKETS,
            registry=self.registry
        )

        # Module health gauge
        self.module_health = Gauge(
            f"{self.prefix}_module_health",
            "Health status of automation modules (1=healthy, 0=unhealthy)",
            ["module"],
            registry=self.registry
        )

        # Active connections gauge
        self.active_connections = Gauge(
            f"{self.prefix}_active_connections",
            "Number of active infrastructure connections",
            ["type"],  # vmware, network, ssh, winrm, etc.
            registry=self.registry
        )

        # Errors counter
        self.errors_total = Counter(
            f"{self.prefix}_errors_total",
            "Total number of errors",
            ["module", "error_type"],
            registry=self.registry
        )

        # ITSM integration metrics
        self.itsm_requests_total = Counter(
            f"{self.prefix}_itsm_requests_total",
            "Total ITSM integration requests",
            ["integration", "operation", "status"],
            registry=self.registry
        )

        # System info
        self.system_info = Info(
            f"{self.prefix}_system",
            "Automation system information",
            registry=self.registry
        )
        self.system_info.info({
            "version": "1.0.0",
            "python_version": "3.x"
        })

    def _init_fallback_metrics(self) -> None:
        """Initialize fallback in-memory metrics."""
        self._metrics: Dict[str, MetricData] = {}

    # ==================== Recording Methods ====================

    def record_action(
        self,
        module: str,
        action: str,
        status: str,
        duration: float = None
    ) -> None:
        """
        Record an action execution.

        Args:
            module: Module name
            action: Action name
            status: success or error
            duration: Execution duration in seconds
        """
        with self._lock:
            if PROMETHEUS_AVAILABLE:
                self.action_total.labels(
                    module=module,
                    action=action,
                    status=status
                ).inc()

                if duration is not None:
                    self.action_duration.labels(
                        module=module,
                        action=action
                    ).observe(duration)
            else:
                # Fallback: store in memory
                key = f"action_total_{module}_{action}_{status}"
                if key not in self._metrics:
                    self._metrics[key] = MetricData(
                        name="action_total",
                        type="counter",
                        labels={"module": module, "action": action, "status": status}
                    )
                self._metrics[key].value += 1
                self._metrics[key].timestamp = datetime.utcnow()

                if duration is not None:
                    dur_key = f"action_duration_{module}_{action}"
                    if dur_key not in self._metrics:
                        self._metrics[dur_key] = MetricData(
                            name="action_duration",
                            type="histogram",
                            labels={"module": module, "action": action}
                        )
                    # For fallback, just track last duration
                    self._metrics[dur_key].value = duration

    def record_error(
        self,
        module: str,
        error_type: str
    ) -> None:
        """Record an error occurrence."""
        with self._lock:
            if PROMETHEUS_AVAILABLE:
                self.errors_total.labels(
                    module=module,
                    error_type=error_type
                ).inc()
            else:
                key = f"errors_{module}_{error_type}"
                if key not in self._metrics:
                    self._metrics[key] = MetricData(
                        name="errors_total",
                        type="counter",
                        labels={"module": module, "error_type": error_type}
                    )
                self._metrics[key].value += 1

    def set_module_health(self, module: str, healthy: bool) -> None:
        """Set module health status."""
        with self._lock:
            if PROMETHEUS_AVAILABLE:
                self.module_health.labels(module=module).set(1 if healthy else 0)
            else:
                key = f"module_health_{module}"
                self._metrics[key] = MetricData(
                    name="module_health",
                    type="gauge",
                    labels={"module": module},
                    value=1.0 if healthy else 0.0
                )

    def set_active_connections(self, connection_type: str, count: int) -> None:
        """Set number of active connections."""
        with self._lock:
            if PROMETHEUS_AVAILABLE:
                self.active_connections.labels(type=connection_type).set(count)
            else:
                key = f"active_connections_{connection_type}"
                self._metrics[key] = MetricData(
                    name="active_connections",
                    type="gauge",
                    labels={"type": connection_type},
                    value=float(count)
                )

    def record_itsm_request(
        self,
        integration: str,
        operation: str,
        status: str
    ) -> None:
        """Record an ITSM integration request."""
        with self._lock:
            if PROMETHEUS_AVAILABLE:
                self.itsm_requests_total.labels(
                    integration=integration,
                    operation=operation,
                    status=status
                ).inc()
            else:
                key = f"itsm_{integration}_{operation}_{status}"
                if key not in self._metrics:
                    self._metrics[key] = MetricData(
                        name="itsm_requests_total",
                        type="counter",
                        labels={
                            "integration": integration,
                            "operation": operation,
                            "status": status
                        }
                    )
                self._metrics[key].value += 1

    def record_gauge(
        self,
        module: str,
        name: str,
        value: float
    ) -> None:
        """Record a gauge metric value."""
        with self._lock:
            key = f"{module}_{name}"
            if not PROMETHEUS_AVAILABLE:
                self._metrics[key] = MetricData(
                    name=name,
                    type="gauge",
                    labels={"module": module},
                    value=value
                )

    def get_metrics(self) -> Dict[str, Any]:
        """Get all recorded metrics as a dictionary."""
        with self._lock:
            if PROMETHEUS_AVAILABLE:
                return {"prometheus_available": True}
            else:
                return {
                    k: {"value": v.value, "type": v.type, "labels": v.labels}
                    for k, v in self._metrics.items()
                }

    # ==================== Exposition Methods ====================

    def get_metrics_text(self) -> str:
        """
        Get metrics in Prometheus text format.

        Returns:
            Prometheus exposition format text
        """
        if PROMETHEUS_AVAILABLE:
            return generate_latest(self.registry).decode("utf-8")
        else:
            return self._generate_fallback_metrics()

    def _generate_fallback_metrics(self) -> str:
        """Generate Prometheus-style text output from fallback metrics."""
        lines = []
        timestamp_ms = int(time.time() * 1000)

        for key, metric in self._metrics.items():
            # Build label string
            label_str = ",".join(
                f'{k}="{v}"' for k, v in metric.labels.items()
            )
            if label_str:
                label_str = "{" + label_str + "}"

            # Add HELP and TYPE for first occurrence
            metric_name = f"{self.prefix}_{metric.name}"

            if metric.type == "counter":
                lines.append(f"# TYPE {metric_name} counter")
            elif metric.type == "gauge":
                lines.append(f"# TYPE {metric_name} gauge")
            elif metric.type == "histogram":
                lines.append(f"# TYPE {metric_name} histogram")

            lines.append(f"{metric_name}{label_str} {metric.value}")

        return "\n".join(lines) + "\n"

    def start_http_server(self, port: int = 9090, addr: str = "") -> None:
        """
        Start HTTP server for metrics exposition.

        Args:
            port: Port to listen on
            addr: Address to bind to (empty for all interfaces)
        """
        if self._server_started:
            self.logger.warning("Metrics server already started")
            return

        if PROMETHEUS_AVAILABLE:
            start_http_server(port, addr, registry=self.registry)
            self.logger.info(f"Prometheus metrics server started on port {port}")
        else:
            # Start simple HTTP server for fallback
            self._start_fallback_server(port, addr)

        self._server_started = True

    def _start_fallback_server(self, port: int, addr: str) -> None:
        """Start a simple HTTP server for metrics when prometheus_client is not available."""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import threading

        collector = self

        class MetricsHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/metrics":
                    content = collector.get_metrics_text()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                    self.send_header("Content-Length", len(content))
                    self.end_headers()
                    self.wfile.write(content.encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress logging

        server = HTTPServer((addr, port), MetricsHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.logger.info(f"Fallback metrics server started on port {port}")

    # ==================== Context Manager for Timing ====================

    class ActionTimer:
        """Context manager for timing actions."""

        def __init__(self, collector: "MetricsCollector", module: str, action: str):
            self.collector = collector
            self.module = module
            self.action = action
            self.start_time = None
            self.status = "success"

        def __enter__(self):
            self.start_time = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = time.time() - self.start_time
            if exc_type is not None:
                self.status = "error"
                self.collector.record_error(self.module, exc_type.__name__)
            self.collector.record_action(
                self.module,
                self.action,
                self.status,
                duration
            )
            return False  # Don't suppress exceptions

        def set_failed(self):
            """Mark the action as failed."""
            self.status = "error"

    def time_action(self, module: str, action: str) -> "ActionTimer":
        """
        Get a context manager for timing an action.

        Usage:
            with metrics.time_action("vmware", "provision_vm") as timer:
                result = do_something()
                if result["status"] == "error":
                    timer.set_failed()
        """
        return self.ActionTimer(self, module, action)

    # ==================== Summary Methods ====================

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all metrics."""
        with self._lock:
            if PROMETHEUS_AVAILABLE:
                # For prometheus, we'd need to query the registry
                # For now, return basic info
                return {
                    "prometheus_available": True,
                    "server_started": self._server_started,
                }
            else:
                return {
                    "prometheus_available": False,
                    "server_started": self._server_started,
                    "metrics_count": len(self._metrics),
                    "metrics": {
                        k: {"value": v.value, "type": v.type}
                        for k, v in self._metrics.items()
                    }
                }
