"""
Metrics Decorators

Provides decorators for automatic metrics collection on functions and methods.
"""

import functools
import time
import asyncio
from typing import Callable, Any

from .collector import get_metrics_collector


def track_action(module: str, action: str = None):
    """
    Decorator to track action execution metrics.

    Args:
        module: Module name for the metric
        action: Action name (uses function name if not provided)

    Usage:
        @track_action("vmware", "provision_vm")
        async def provision_vm(self, name, template):
            ...

        @track_action("network")  # Uses function name as action
        def create_vlan(self, vlan_id, name):
            ...
    """
    def decorator(func: Callable) -> Callable:
        action_name = action or func.__name__

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                metrics = get_metrics_collector()
                start_time = time.time()
                status = "success"

                try:
                    result = await func(*args, **kwargs)

                    # Check if result indicates failure
                    if isinstance(result, dict):
                        if result.get("status") == "error":
                            status = "error"

                    return result
                except Exception as e:
                    status = "error"
                    metrics.record_error(module, type(e).__name__)
                    raise
                finally:
                    duration = time.time() - start_time
                    metrics.record_action(module, action_name, status, duration)

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                metrics = get_metrics_collector()
                start_time = time.time()
                status = "success"

                try:
                    result = func(*args, **kwargs)

                    # Check if result indicates failure
                    if isinstance(result, dict):
                        if result.get("status") == "error":
                            status = "error"

                    return result
                except Exception as e:
                    status = "error"
                    metrics.record_error(module, type(e).__name__)
                    raise
                finally:
                    duration = time.time() - start_time
                    metrics.record_action(module, action_name, status, duration)

            return sync_wrapper

    return decorator


def track_duration(module: str, operation: str = None):
    """
    Decorator to track operation duration (histogram only, no success/failure).

    Args:
        module: Module name
        operation: Operation name (uses function name if not provided)

    Usage:
        @track_duration("backup", "verification")
        def verify_backup(self, backup_id):
            ...
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation or func.__name__

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                metrics = get_metrics_collector()
                start_time = time.time()

                try:
                    return await func(*args, **kwargs)
                finally:
                    duration = time.time() - start_time
                    metrics.record_action(module, op_name, "completed", duration)

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                metrics = get_metrics_collector()
                start_time = time.time()

                try:
                    return func(*args, **kwargs)
                finally:
                    duration = time.time() - start_time
                    metrics.record_action(module, op_name, "completed", duration)

            return sync_wrapper

    return decorator


def track_itsm(integration: str, operation: str = None):
    """
    Decorator to track ITSM integration calls.

    Args:
        integration: Integration name (servicenow, jira, pagerduty)
        operation: Operation name (uses function name if not provided)

    Usage:
        @track_itsm("servicenow", "create_incident")
        def create_incident(self, title, description):
            ...
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation or func.__name__

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                metrics = get_metrics_collector()
                status = "success"

                try:
                    result = await func(*args, **kwargs)

                    if isinstance(result, dict):
                        if result.get("status") == "error":
                            status = "error"

                    return result
                except Exception:
                    status = "error"
                    raise
                finally:
                    metrics.record_itsm_request(integration, op_name, status)

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                metrics = get_metrics_collector()
                status = "success"

                try:
                    result = func(*args, **kwargs)

                    if isinstance(result, dict):
                        if result.get("status") == "error":
                            status = "error"

                    return result
                except Exception:
                    status = "error"
                    raise
                finally:
                    metrics.record_itsm_request(integration, op_name, status)

            return sync_wrapper

    return decorator


class MetricsContext:
    """
    Context manager for tracking metrics with custom logic.

    Usage:
        with MetricsContext("vmware", "bulk_provision") as ctx:
            for vm in vms:
                result = provision_vm(vm)
                if result["status"] == "error":
                    ctx.record_error("provision_failed")
            ctx.set_status("success")
    """

    def __init__(self, module: str, operation: str):
        self.module = module
        self.operation = operation
        self.metrics = get_metrics_collector()
        self.start_time = None
        self._status = "success"
        self._errors = []

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        if exc_type is not None:
            self._status = "error"
            self.metrics.record_error(self.module, exc_type.__name__)

        self.metrics.record_action(
            self.module,
            self.operation,
            self._status,
            duration
        )

        # Record any accumulated errors
        for error_type in self._errors:
            self.metrics.record_error(self.module, error_type)

        return False

    def set_status(self, status: str) -> None:
        """Set the final status (success/error)."""
        self._status = status

    def record_error(self, error_type: str) -> None:
        """Record an error that occurred during the operation."""
        self._errors.append(error_type)
        self._status = "error"
