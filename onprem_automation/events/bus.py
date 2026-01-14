"""
Event Bus

Central hub for event publishing and subscription.
Supports async processing, prioritization, and persistence.
"""

import asyncio
import json
import logging
import queue
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Union
from pathlib import Path

from .types import Event, EventType, EventPriority, EventFilter
from .handlers import EventHandler, FunctionHandler


@dataclass
class Subscription:
    """Represents a subscription to events."""
    subscriber_id: str
    handler: EventHandler
    filter: Optional[EventFilter] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class EventQueue:
    """Priority queue for events."""

    def __init__(self, maxsize: int = 10000):
        self._queues: Dict[EventPriority, asyncio.Queue] = {
            priority: asyncio.Queue(maxsize=maxsize // 4)
            for priority in EventPriority
        }
        self._total_count = 0

    async def put(self, event: Event) -> None:
        """Add event to queue."""
        await self._queues[event.priority].put(event)
        self._total_count += 1

    async def get(self) -> Event:
        """Get highest priority event."""
        # Check queues in priority order
        for priority in reversed(list(EventPriority)):
            q = self._queues[priority]
            if not q.empty():
                self._total_count -= 1
                return await q.get()

        # If all empty, wait on normal queue
        self._total_count -= 1
        return await self._queues[EventPriority.NORMAL].get()

    def empty(self) -> bool:
        """Check if all queues are empty."""
        return all(q.empty() for q in self._queues.values())

    @property
    def size(self) -> int:
        """Get total queue size."""
        return self._total_count


class EventStore:
    """Persists events for replay and auditing."""

    def __init__(self, storage_path: Optional[str] = None):
        self._storage_path = Path(storage_path) if storage_path else None
        self._events: List[Event] = []
        self._max_memory_events = 10000
        self._logger = logging.getLogger("event.store")

        if self._storage_path:
            self._storage_path.mkdir(parents=True, exist_ok=True)

    def store(self, event: Event) -> None:
        """Store an event."""
        self._events.append(event)

        # Trim memory store
        if len(self._events) > self._max_memory_events:
            self._events = self._events[-self._max_memory_events:]

        # Persist to disk if configured
        if self._storage_path:
            self._persist_event(event)

    def _persist_event(self, event: Event) -> None:
        """Persist event to disk."""
        try:
            date_str = event.timestamp.strftime("%Y-%m-%d")
            file_path = self._storage_path / f"events_{date_str}.jsonl"

            with open(file_path, "a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        except Exception as e:
            self._logger.error(f"Failed to persist event: {e}")

    def get_events(
        self,
        event_type: Optional[EventType] = None,
        source: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Event]:
        """Query stored events."""
        results = []

        for event in reversed(self._events):
            if event_type and event.event_type != event_type:
                continue
            if source and event.source != source:
                continue
            if since and event.timestamp < since:
                continue
            if until and event.timestamp > until:
                continue

            results.append(event)
            if len(results) >= limit:
                break

        return results

    def get_by_correlation_id(self, correlation_id: str) -> List[Event]:
        """Get all events with a correlation ID."""
        return [e for e in self._events if e.correlation_id == correlation_id]

    def clear(self) -> None:
        """Clear stored events."""
        self._events.clear()


class EventBus:
    """
    Central event bus for publish-subscribe messaging.

    Example usage:
    ```python
    bus = EventBus()

    # Subscribe to events
    @event_handler(EventType.JOB_COMPLETED)
    async def on_job_complete(event: Event):
        print(f"Job completed: {event.data}")

    bus.subscribe("my-handler", on_job_complete)

    # Start processing
    await bus.start()

    # Publish events
    await bus.publish(Event(
        event_type=EventType.JOB_COMPLETED,
        source="job_executor",
        data={"job_id": "123", "status": "success"}
    ))

    # Stop processing
    await bus.stop()
    ```
    """

    def __init__(
        self,
        max_queue_size: int = 10000,
        num_workers: int = 4,
        store_events: bool = True,
        storage_path: Optional[str] = None
    ):
        self._queue = EventQueue(maxsize=max_queue_size)
        self._subscriptions: Dict[str, Subscription] = {}
        self._type_subscriptions: Dict[EventType, List[str]] = defaultdict(list)
        self._workers: List[asyncio.Task] = []
        self._num_workers = num_workers
        self._running = False
        self._logger = logging.getLogger("event.bus")

        # Event store
        self._store_events = store_events
        self._store = EventStore(storage_path) if store_events else None

        # Metrics
        self._published_count = 0
        self._processed_count = 0
        self._error_count = 0

        # Hooks
        self._before_publish: List[Callable] = []
        self._after_publish: List[Callable] = []
        self._before_handle: List[Callable] = []
        self._after_handle: List[Callable] = []

    async def start(self) -> None:
        """Start event processing workers."""
        if self._running:
            return

        self._running = True
        self._workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self._num_workers)
        ]
        self._logger.info(f"Event bus started with {self._num_workers} workers")

    async def stop(self) -> None:
        """Stop event processing."""
        self._running = False

        # Wait for queue to drain
        while not self._queue.empty():
            await asyncio.sleep(0.1)

        # Cancel workers
        for worker in self._workers:
            worker.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._logger.info("Event bus stopped")

    async def _worker(self, worker_id: int) -> None:
        """Event processing worker."""
        self._logger.debug(f"Worker {worker_id} started")

        while self._running:
            try:
                # Get next event with timeout
                try:
                    event = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                await self._process_event(event)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Worker {worker_id} error: {e}")
                self._error_count += 1

        self._logger.debug(f"Worker {worker_id} stopped")

    async def _process_event(self, event: Event) -> None:
        """Process a single event."""
        # Get matching subscriptions
        handlers = self._get_handlers_for_event(event)

        if not handlers:
            self._logger.debug(f"No handlers for event {event.event_type}")
            return

        # Before handle hooks
        for hook in self._before_handle:
            try:
                hook(event)
            except Exception as e:
                self._logger.error(f"Before handle hook error: {e}")

        # Call each handler
        for subscription in handlers:
            try:
                await subscription.handler.handle(event)
            except Exception as e:
                self._logger.error(
                    f"Handler {subscription.subscriber_id} error: {e}"
                )
                await subscription.handler.on_error(event, e)
                self._error_count += 1

        # After handle hooks
        for hook in self._after_handle:
            try:
                hook(event)
            except Exception as e:
                self._logger.error(f"After handle hook error: {e}")

        event.processed = True
        self._processed_count += 1

    def _get_handlers_for_event(self, event: Event) -> List[Subscription]:
        """Get all handlers that should process an event."""
        handlers = []

        # Get handlers subscribed to this event type
        for sub_id in self._type_subscriptions.get(event.event_type, []):
            if sub_id in self._subscriptions:
                sub = self._subscriptions[sub_id]
                if sub.handler.can_handle(event):
                    handlers.append(sub)

        # Get handlers with no type filter (catch-all)
        for sub_id in self._type_subscriptions.get(None, []):
            if sub_id in self._subscriptions:
                sub = self._subscriptions[sub_id]
                if sub.handler.can_handle(event):
                    handlers.append(sub)

        # Check target-specific handlers
        if event.target and event.target in self._subscriptions:
            handlers.append(self._subscriptions[event.target])

        return handlers

    async def publish(self, event: Event) -> str:
        """
        Publish an event to the bus.

        Args:
            event: Event to publish

        Returns:
            Event ID
        """
        # Before publish hooks
        for hook in self._before_publish:
            try:
                hook(event)
            except Exception as e:
                self._logger.error(f"Before publish hook error: {e}")

        # Store event
        if self._store:
            self._store.store(event)

        # Queue for processing
        await self._queue.put(event)
        self._published_count += 1

        # After publish hooks
        for hook in self._after_publish:
            try:
                hook(event)
            except Exception as e:
                self._logger.error(f"After publish hook error: {e}")

        self._logger.debug(f"Published event: {event.event_type} [{event.event_id}]")
        return event.event_id

    def publish_sync(self, event: Event) -> str:
        """Synchronous publish (for non-async code)."""
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Schedule in running loop
            asyncio.create_task(self.publish(event))
            return event.event_id
        else:
            return loop.run_until_complete(self.publish(event))

    async def publish_and_wait(
        self,
        event: Event,
        timeout: float = 30.0
    ) -> bool:
        """Publish and wait for processing to complete."""
        await self.publish(event)

        start = time.time()
        while not event.processed:
            if time.time() - start > timeout:
                return False
            await asyncio.sleep(0.1)

        return True

    def subscribe(
        self,
        subscriber_id: str,
        handler: Union[EventHandler, Callable],
        event_types: Optional[List[EventType]] = None,
        filter: Optional[EventFilter] = None
    ) -> None:
        """
        Subscribe to events.

        Args:
            subscriber_id: Unique subscriber identifier
            handler: EventHandler instance or callable
            event_types: Optional list of event types to subscribe to
            filter: Optional filter for fine-grained control
        """
        # Wrap callable in handler
        if not isinstance(handler, EventHandler):
            if hasattr(handler, '_event_handler'):
                # Decorated function
                event_types = event_types or handler._event_types
                filter = filter or handler._event_filter
            handler = FunctionHandler(handler, event_types or [], filter)

        subscription = Subscription(
            subscriber_id=subscriber_id,
            handler=handler,
            filter=filter
        )

        self._subscriptions[subscriber_id] = subscription

        # Index by event type
        types_to_index = event_types or handler.handles or [None]
        for event_type in types_to_index:
            if subscriber_id not in self._type_subscriptions[event_type]:
                self._type_subscriptions[event_type].append(subscriber_id)

        self._logger.info(f"Subscribed: {subscriber_id}")

    def unsubscribe(self, subscriber_id: str) -> bool:
        """Unsubscribe from events."""
        if subscriber_id not in self._subscriptions:
            return False

        # Remove from type index
        for type_subs in self._type_subscriptions.values():
            if subscriber_id in type_subs:
                type_subs.remove(subscriber_id)

        del self._subscriptions[subscriber_id]
        self._logger.info(f"Unsubscribed: {subscriber_id}")
        return True

    def register_hook(
        self,
        hook_type: str,
        callback: Callable
    ) -> None:
        """
        Register a hook callback.

        Hook types:
        - before_publish: Called before event is published
        - after_publish: Called after event is published
        - before_handle: Called before handlers process event
        - after_handle: Called after handlers process event
        """
        hooks = {
            "before_publish": self._before_publish,
            "after_publish": self._after_publish,
            "before_handle": self._before_handle,
            "after_handle": self._after_handle,
        }

        if hook_type in hooks:
            hooks[hook_type].append(callback)

    def get_subscription(self, subscriber_id: str) -> Optional[Subscription]:
        """Get subscription by ID."""
        return self._subscriptions.get(subscriber_id)

    def get_all_subscriptions(self) -> List[Subscription]:
        """Get all subscriptions."""
        return list(self._subscriptions.values())

    def get_events(self, **kwargs) -> List[Event]:
        """Query stored events."""
        if self._store:
            return self._store.get_events(**kwargs)
        return []

    def get_metrics(self) -> Dict[str, Any]:
        """Get event bus metrics."""
        return {
            "queue_size": self._queue.size,
            "published_count": self._published_count,
            "processed_count": self._processed_count,
            "error_count": self._error_count,
            "subscription_count": len(self._subscriptions),
            "worker_count": len(self._workers),
            "running": self._running,
        }

    def is_running(self) -> bool:
        """Check if bus is running."""
        return self._running


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def reset_event_bus() -> None:
    """Reset the global event bus (for testing)."""
    global _event_bus
    if _event_bus and _event_bus.is_running():
        asyncio.get_event_loop().run_until_complete(_event_bus.stop())
    _event_bus = None
