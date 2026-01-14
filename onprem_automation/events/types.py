"""
Event Types

Defines event types and structures for the event system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import uuid


class EventPriority(int, Enum):
    """Event priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EventType(str, Enum):
    """Standard event types."""
    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"

    # Job events
    JOB_CREATED = "job.created"
    JOB_STARTED = "job.started"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_CANCELLED = "job.cancelled"
    JOB_PROGRESS = "job.progress"

    # Workflow events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_STEP_STARTED = "workflow.step.started"
    WORKFLOW_STEP_COMPLETED = "workflow.step.completed"
    WORKFLOW_STEP_FAILED = "workflow.step.failed"
    WORKFLOW_APPROVAL_REQUIRED = "workflow.approval.required"
    WORKFLOW_APPROVED = "workflow.approved"
    WORKFLOW_REJECTED = "workflow.rejected"

    # Infrastructure events
    VM_CREATED = "infrastructure.vm.created"
    VM_STARTED = "infrastructure.vm.started"
    VM_STOPPED = "infrastructure.vm.stopped"
    VM_DELETED = "infrastructure.vm.deleted"
    SERVER_CONNECTED = "infrastructure.server.connected"
    SERVER_DISCONNECTED = "infrastructure.server.disconnected"
    NETWORK_CHANGE = "infrastructure.network.change"

    # Connector events
    CONNECTOR_CONNECTED = "connector.connected"
    CONNECTOR_DISCONNECTED = "connector.disconnected"
    CONNECTOR_ERROR = "connector.error"

    # ITSM events
    INCIDENT_CREATED = "itsm.incident.created"
    INCIDENT_UPDATED = "itsm.incident.updated"
    INCIDENT_RESOLVED = "itsm.incident.resolved"
    CHANGE_CREATED = "itsm.change.created"
    CHANGE_APPROVED = "itsm.change.approved"
    CHANGE_IMPLEMENTED = "itsm.change.implemented"

    # Alert events
    ALERT_TRIGGERED = "alert.triggered"
    ALERT_ACKNOWLEDGED = "alert.acknowledged"
    ALERT_RESOLVED = "alert.resolved"

    # Security events
    AUTH_SUCCESS = "security.auth.success"
    AUTH_FAILURE = "security.auth.failure"
    PERMISSION_DENIED = "security.permission.denied"
    SECRET_ACCESSED = "security.secret.accessed"

    # Plugin events
    PLUGIN_LOADED = "plugin.loaded"
    PLUGIN_UNLOADED = "plugin.unloaded"
    PLUGIN_ERROR = "plugin.error"

    # Custom events
    CUSTOM = "custom"


@dataclass
class Event:
    """
    Base event structure.

    Example:
    ```python
    event = Event(
        event_type=EventType.JOB_COMPLETED,
        source="job_executor",
        data={"job_id": "123", "result": "success"}
    )
    ```
    """
    event_type: EventType
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL

    # Metadata
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None

    # Routing
    target: Optional[str] = None  # Specific target handler
    tags: list = field(default_factory=list)

    # Processing state
    processed: bool = False
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value if isinstance(self.event_type, EventType) else self.event_type,
            "source": self.source,
            "data": self.data,
            "priority": self.priority.value if isinstance(self.priority, EventPriority) else self.priority,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "target": self.target,
            "tags": self.tags,
            "processed": self.processed,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create event from dictionary."""
        event_type = data.get("event_type", EventType.CUSTOM)
        if isinstance(event_type, str):
            try:
                event_type = EventType(event_type)
            except ValueError:
                event_type = EventType.CUSTOM

        priority = data.get("priority", EventPriority.NORMAL)
        if isinstance(priority, int):
            priority = EventPriority(priority)

        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.utcnow()

        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            event_type=event_type,
            source=data.get("source", "unknown"),
            data=data.get("data", {}),
            priority=priority,
            timestamp=timestamp,
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            target=data.get("target"),
            tags=data.get("tags", []),
            processed=data.get("processed", False),
            retry_count=data.get("retry_count", 0),
        )

    def create_child(self, event_type: EventType, **data) -> "Event":
        """Create a child event with correlation."""
        return Event(
            event_type=event_type,
            source=self.source,
            data=data,
            priority=self.priority,
            correlation_id=self.correlation_id or self.event_id,
            causation_id=self.event_id,
        )


@dataclass
class EventFilter:
    """Filter for subscribing to specific events."""
    event_types: Optional[list] = None
    sources: Optional[list] = None
    tags: Optional[list] = None
    min_priority: Optional[EventPriority] = None

    def matches(self, event: Event) -> bool:
        """Check if an event matches this filter."""
        if self.event_types and event.event_type not in self.event_types:
            return False
        if self.sources and event.source not in self.sources:
            return False
        if self.tags and not any(t in event.tags for t in self.tags):
            return False
        if self.min_priority and event.priority.value < self.min_priority.value:
            return False
        return True
