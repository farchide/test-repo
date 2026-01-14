"""
Tests for metrics collection module.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import time

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_metrics_collector_singleton(self):
        """Test that get_metrics_collector returns singleton."""
        from onprem_automation.metrics.collector import (
            get_metrics_collector,
            _reset_metrics_collector
        )

        # Reset to start fresh
        _reset_metrics_collector()

        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()

        assert collector1 is collector2

    def test_metrics_collector_initialization(self):
        """Test MetricsCollector initialization."""
        from onprem_automation.metrics.collector import (
            MetricsCollector,
            _reset_metrics_collector
        )

        _reset_metrics_collector()

        collector = MetricsCollector(prefix="test_app")
        assert collector.prefix == "test_app"

    def test_record_action(self):
        """Test recording an action metric."""
        from onprem_automation.metrics.collector import (
            MetricsCollector,
            _reset_metrics_collector
        )

        _reset_metrics_collector()

        collector = MetricsCollector(prefix="test")
        # Should not raise
        collector.record_action("vmware", "provision_vm", "success", 5.5)

    def test_record_error(self):
        """Test recording an error metric."""
        from onprem_automation.metrics.collector import (
            MetricsCollector,
            _reset_metrics_collector
        )

        _reset_metrics_collector()

        collector = MetricsCollector(prefix="test")
        # Should not raise
        collector.record_error("network", "ConnectionError")

    def test_record_gauge(self):
        """Test recording a gauge metric."""
        from onprem_automation.metrics.collector import (
            MetricsCollector,
            _reset_metrics_collector
        )

        _reset_metrics_collector()

        collector = MetricsCollector(prefix="test")
        # Should not raise
        collector.record_gauge("capacity", "storage_used", 75.5)

    def test_record_itsm_request(self):
        """Test recording ITSM request metric."""
        from onprem_automation.metrics.collector import (
            MetricsCollector,
            _reset_metrics_collector
        )

        _reset_metrics_collector()

        collector = MetricsCollector(prefix="test")
        # Should not raise
        collector.record_itsm_request("servicenow", "create_incident", "success")

    def test_get_metrics(self):
        """Test getting all metrics."""
        from onprem_automation.metrics.collector import (
            MetricsCollector,
            _reset_metrics_collector
        )

        _reset_metrics_collector()

        collector = MetricsCollector(prefix="test")
        collector.record_action("test", "action", "success", 1.0)

        metrics = collector.get_metrics()
        assert isinstance(metrics, dict)


class TestMetricsDecorators:
    """Tests for metrics decorators."""

    def test_track_action_decorator_sync(self):
        """Test track_action decorator on sync function."""
        from onprem_automation.metrics.decorators import track_action
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        @track_action("test_module", "test_action")
        def test_function():
            return {"status": "success", "data": "test"}

        result = test_function()
        assert result["status"] == "success"

    def test_track_action_decorator_with_error(self):
        """Test track_action decorator records errors."""
        from onprem_automation.metrics.decorators import track_action
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        @track_action("test_module", "failing_action")
        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_function()

    def test_track_action_decorator_uses_function_name(self):
        """Test track_action uses function name if action not provided."""
        from onprem_automation.metrics.decorators import track_action
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        @track_action("test_module")
        def my_test_function():
            return {"status": "success"}

        result = my_test_function()
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_track_action_decorator_async(self):
        """Test track_action decorator on async function."""
        from onprem_automation.metrics.decorators import track_action
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        @track_action("test_module", "async_action")
        async def async_test_function():
            return {"status": "success", "data": "async_test"}

        result = await async_test_function()
        assert result["status"] == "success"

    def test_track_duration_decorator_sync(self):
        """Test track_duration decorator on sync function."""
        from onprem_automation.metrics.decorators import track_duration
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        @track_duration("backup", "verification")
        def verify_backup():
            time.sleep(0.01)  # Small delay
            return {"verified": True}

        result = verify_backup()
        assert result["verified"] is True

    @pytest.mark.asyncio
    async def test_track_duration_decorator_async(self):
        """Test track_duration decorator on async function."""
        import asyncio
        from onprem_automation.metrics.decorators import track_duration
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        @track_duration("backup", "async_verify")
        async def async_verify():
            await asyncio.sleep(0.01)
            return {"verified": True}

        result = await async_verify()
        assert result["verified"] is True

    def test_track_itsm_decorator_sync(self):
        """Test track_itsm decorator on sync function."""
        from onprem_automation.metrics.decorators import track_itsm
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        @track_itsm("servicenow", "create_incident")
        def create_incident():
            return {"status": "success", "sys_id": "INC123"}

        result = create_incident()
        assert result["status"] == "success"

    def test_track_itsm_decorator_error_status(self):
        """Test track_itsm decorator detects error status in result."""
        from onprem_automation.metrics.decorators import track_itsm
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        @track_itsm("jira", "create_issue")
        def create_issue_failed():
            return {"status": "error", "message": "Project not found"}

        result = create_issue_failed()
        assert result["status"] == "error"


class TestMetricsContext:
    """Tests for MetricsContext context manager."""

    def test_metrics_context_success(self):
        """Test MetricsContext with successful operation."""
        from onprem_automation.metrics.decorators import MetricsContext
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        with MetricsContext("vmware", "bulk_provision") as ctx:
            # Simulate work
            pass

        # Context should complete without error

    def test_metrics_context_with_error(self):
        """Test MetricsContext records errors."""
        from onprem_automation.metrics.decorators import MetricsContext
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        with pytest.raises(ValueError):
            with MetricsContext("vmware", "failing_op") as ctx:
                raise ValueError("Test error")

    def test_metrics_context_set_status(self):
        """Test MetricsContext status setting."""
        from onprem_automation.metrics.decorators import MetricsContext
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        with MetricsContext("vmware", "operation") as ctx:
            ctx.set_status("success")

    def test_metrics_context_record_error(self):
        """Test MetricsContext error recording."""
        from onprem_automation.metrics.decorators import MetricsContext
        from onprem_automation.metrics.collector import _reset_metrics_collector

        _reset_metrics_collector()

        with MetricsContext("vmware", "operation") as ctx:
            ctx.record_error("provision_failed")
            ctx.record_error("network_error")


class TestMetricsImports:
    """Tests for metrics module imports."""

    def test_metrics_package_imports(self):
        """Test that metrics package exports correct symbols."""
        from onprem_automation.metrics import (
            MetricsCollector,
            get_metrics_collector,
            _reset_metrics_collector,
            track_action,
            track_duration,
            track_itsm,
            MetricsContext
        )

        # All should be importable
        assert MetricsCollector is not None
        assert get_metrics_collector is not None
        assert track_action is not None
        assert track_duration is not None
        assert track_itsm is not None
        assert MetricsContext is not None

    def test_collector_module_exports(self):
        """Test collector module exports."""
        from onprem_automation.metrics.collector import (
            MetricsCollector,
            get_metrics_collector,
            _reset_metrics_collector
        )

        assert MetricsCollector is not None
        assert callable(get_metrics_collector)
        assert callable(_reset_metrics_collector)

    def test_decorators_module_exports(self):
        """Test decorators module exports."""
        from onprem_automation.metrics.decorators import (
            track_action,
            track_duration,
            track_itsm,
            MetricsContext
        )

        assert callable(track_action)
        assert callable(track_duration)
        assert callable(track_itsm)
        assert MetricsContext is not None


class TestMetricsWithPrometheus:
    """Tests for Prometheus integration (when available)."""

    def test_metrics_creation(self):
        """Test metrics creation."""
        from onprem_automation.metrics.collector import (
            MetricsCollector,
            _reset_metrics_collector
        )

        _reset_metrics_collector()

        # This should work even if prometheus_client is mocked
        collector = MetricsCollector(prefix="prom_test")
        assert collector.prefix == "prom_test"

    def test_metrics_work_without_prometheus(self):
        """Test metrics work without Prometheus client."""
        from onprem_automation.metrics.collector import (
            MetricsCollector,
            _reset_metrics_collector
        )

        _reset_metrics_collector()

        # Should work even without prometheus_client
        collector = MetricsCollector(prefix="no_prom")
        collector.record_action("test", "action", "success", 1.0)
        collector.record_error("test", "TestError")
        collector.record_gauge("test", "value", 42.0)

        # Should not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
