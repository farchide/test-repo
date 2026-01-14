"""
Event Handlers

Provides handler base class and decorator for event handling.
"""

import asyncio
import functools
import inspect
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Union

from .types import Event, EventType, EventFilter


class EventHandler(ABC):
    """
    Base class for event handlers.

    Example:
    ```python
    class JobEventHandler(EventHandler):
        handles = [EventType.JOB_COMPLETED, EventType.JOB_FAILED]

        async def handle(self, event: Event) -> None:
            if event.event_type == EventType.JOB_COMPLETED:
                await self.notify_success(event)
            else:
                await self.notify_failure(event)
    ```
    """

    # Event types this handler handles
    handles: List[EventType] = []

    # Optional filter for fine-grained control
    filter: Optional[EventFilter] = None

    def __init__(self):
        self.logger = logging.getLogger(f"handler.{self.__class__.__name__}")
        self._enabled = True

    @abstractmethod
    async def handle(self, event: Event) -> None:
        """Handle an event."""
        pass

    def can_handle(self, event: Event) -> bool:
        """Check if this handler can handle an event."""
        if not self._enabled:
            return False

        if self.handles and event.event_type not in self.handles:
            return False

        if self.filter and not self.filter.matches(event):
            return False

        return True

    def enable(self) -> None:
        """Enable this handler."""
        self._enabled = True

    def disable(self) -> None:
        """Disable this handler."""
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        """Check if handler is enabled."""
        return self._enabled

    async def on_error(self, event: Event, error: Exception) -> None:
        """Called when handler raises an exception."""
        self.logger.error(f"Error handling event {event.event_id}: {error}")


class FunctionHandler(EventHandler):
    """Wrapper to convert a function to an EventHandler."""

    def __init__(
        self,
        func: Callable,
        event_types: List[EventType],
        filter: Optional[EventFilter] = None
    ):
        super().__init__()
        self._func = func
        self.handles = event_types
        self.filter = filter
        self._is_async = asyncio.iscoroutinefunction(func)

    async def handle(self, event: Event) -> None:
        """Call the wrapped function."""
        if self._is_async:
            await self._func(event)
        else:
            self._func(event)


def event_handler(
    *event_types: EventType,
    filter: Optional[EventFilter] = None
) -> Callable:
    """
    Decorator to mark a function as an event handler.

    Example:
    ```python
    @event_handler(EventType.JOB_COMPLETED, EventType.JOB_FAILED)
    async def on_job_complete(event: Event):
        print(f"Job {event.data['job_id']} finished")

    # Register with event bus
    bus.register_handler(on_job_complete)
    ```
    """
    def decorator(func: Callable) -> Callable:
        # Store handler metadata on the function
        func._event_handler = True
        func._event_types = list(event_types)
        func._event_filter = filter

        @functools.wraps(func)
        async def async_wrapper(event: Event) -> None:
            if asyncio.iscoroutinefunction(func):
                return await func(event)
            return func(event)

        # Copy metadata to wrapper
        async_wrapper._event_handler = True
        async_wrapper._event_types = list(event_types)
        async_wrapper._event_filter = filter

        return async_wrapper

    return decorator


class CompositeHandler(EventHandler):
    """Handler that delegates to multiple sub-handlers."""

    def __init__(self, handlers: Optional[List[EventHandler]] = None):
        super().__init__()
        self._handlers: List[EventHandler] = handlers or []

    def add_handler(self, handler: EventHandler) -> None:
        """Add a sub-handler."""
        self._handlers.append(handler)

    def remove_handler(self, handler: EventHandler) -> None:
        """Remove a sub-handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def handle(self, event: Event) -> None:
        """Delegate to all sub-handlers."""
        for handler in self._handlers:
            if handler.can_handle(event):
                try:
                    await handler.handle(event)
                except Exception as e:
                    await handler.on_error(event, e)


class RetryHandler(EventHandler):
    """Handler wrapper that adds retry logic."""

    def __init__(
        self,
        handler: EventHandler,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        exponential_backoff: bool = True
    ):
        super().__init__()
        self._handler = handler
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._exponential_backoff = exponential_backoff
        self.handles = handler.handles
        self.filter = handler.filter

    async def handle(self, event: Event) -> None:
        """Handle with retry logic."""
        last_error = None
        delay = self._retry_delay

        for attempt in range(self._max_retries + 1):
            try:
                await self._handler.handle(event)
                return
            except Exception as e:
                last_error = e
                self.logger.warning(
                    f"Handler failed (attempt {attempt + 1}/{self._max_retries + 1}): {e}"
                )

                if attempt < self._max_retries:
                    await asyncio.sleep(delay)
                    if self._exponential_backoff:
                        delay *= 2

        # All retries exhausted
        raise last_error


class FilteringHandler(EventHandler):
    """Handler wrapper that adds filtering logic."""

    def __init__(self, handler: EventHandler, filter: EventFilter):
        super().__init__()
        self._handler = handler
        self.filter = filter
        self.handles = handler.handles

    def can_handle(self, event: Event) -> bool:
        """Check if event passes filter."""
        return super().can_handle(event) and self._handler.can_handle(event)

    async def handle(self, event: Event) -> None:
        """Delegate to wrapped handler."""
        await self._handler.handle(event)


class LoggingHandler(EventHandler):
    """Handler that logs all events."""

    handles = []  # Handles all events

    def __init__(self, log_level: int = logging.INFO):
        super().__init__()
        self._log_level = log_level

    async def handle(self, event: Event) -> None:
        """Log the event."""
        self.logger.log(
            self._log_level,
            f"Event: {event.event_type.value} from {event.source} "
            f"[{event.event_id}] - {event.data}"
        )


class MetricsHandler(EventHandler):
    """Handler that records event metrics."""

    handles = []  # Handles all events

    def __init__(self):
        super().__init__()
        self._event_counts: Dict[str, int] = {}
        self._error_counts: Dict[str, int] = {}

    async def handle(self, event: Event) -> None:
        """Record event metrics."""
        event_type = event.event_type.value
        self._event_counts[event_type] = self._event_counts.get(event_type, 0) + 1

    async def on_error(self, event: Event, error: Exception) -> None:
        """Record error metrics."""
        await super().on_error(event, error)
        event_type = event.event_type.value
        self._error_counts[event_type] = self._error_counts.get(event_type, 0) + 1

    def get_metrics(self) -> Dict[str, Any]:
        """Get collected metrics."""
        return {
            "event_counts": dict(self._event_counts),
            "error_counts": dict(self._error_counts),
            "total_events": sum(self._event_counts.values()),
            "total_errors": sum(self._error_counts.values()),
        }
