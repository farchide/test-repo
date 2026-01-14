"""
Scheduled Job Definitions

Defines job structures and trigger types for the scheduler.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
import uuid


class JobStatus(str, Enum):
    """Status of a scheduled job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class JobTrigger(ABC):
    """Base class for job triggers."""

    @abstractmethod
    def get_next_run_time(self, after: Optional[datetime] = None) -> Optional[datetime]:
        """
        Calculate the next run time.

        Args:
            after: Calculate next run after this time (defaults to now)

        Returns:
            Next run datetime or None if no more runs
        """
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize trigger to dictionary."""
        pass

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JobTrigger":
        """Deserialize trigger from dictionary."""
        trigger_type = data.get("type")
        if trigger_type == "cron":
            return CronTrigger.from_dict(data)
        elif trigger_type == "interval":
            return IntervalTrigger.from_dict(data)
        elif trigger_type == "date":
            return DateTrigger.from_dict(data)
        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")


@dataclass
class CronTrigger(JobTrigger):
    """
    Cron-based trigger.

    Supports standard cron expressions:
    - minute (0-59)
    - hour (0-23)
    - day of month (1-31)
    - month (1-12)
    - day of week (0-6, Sunday=0)

    Example:
        CronTrigger("0 0 * * *")  # Daily at midnight
        CronTrigger("*/15 * * * *")  # Every 15 minutes
        CronTrigger("0 9 * * 1-5")  # Weekdays at 9am
    """
    expression: str
    timezone: str = "UTC"

    def __post_init__(self):
        self._parse_expression()

    def _parse_expression(self) -> None:
        """Parse and validate cron expression."""
        parts = self.expression.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {self.expression}")

        self._minute = self._parse_field(parts[0], 0, 59)
        self._hour = self._parse_field(parts[1], 0, 23)
        self._day = self._parse_field(parts[2], 1, 31)
        self._month = self._parse_field(parts[3], 1, 12)
        self._weekday = self._parse_field(parts[4], 0, 6)

    def _parse_field(self, field: str, min_val: int, max_val: int) -> set:
        """Parse a cron field into a set of values."""
        values = set()

        for part in field.split(","):
            if part == "*":
                values.update(range(min_val, max_val + 1))
            elif part.startswith("*/"):
                step = int(part[2:])
                values.update(range(min_val, max_val + 1, step))
            elif "-" in part:
                start, end = map(int, part.split("-"))
                values.update(range(start, end + 1))
            else:
                values.add(int(part))

        return values

    def get_next_run_time(self, after: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate the next run time based on cron expression."""
        now = after or datetime.utcnow()
        current = now.replace(second=0, microsecond=0) + timedelta(minutes=1)

        # Search for next matching time (limit to prevent infinite loop)
        for _ in range(366 * 24 * 60):  # Max 1 year of minutes
            if (current.minute in self._minute and
                current.hour in self._hour and
                current.day in self._day and
                current.month in self._month and
                current.weekday() in self._weekday):
                return current

            current += timedelta(minutes=1)

        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "type": "cron",
            "expression": self.expression,
            "timezone": self.timezone,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CronTrigger":
        """Deserialize from dictionary."""
        return cls(
            expression=data["expression"],
            timezone=data.get("timezone", "UTC")
        )


@dataclass
class IntervalTrigger(JobTrigger):
    """
    Interval-based trigger.

    Example:
        IntervalTrigger(minutes=30)  # Every 30 minutes
        IntervalTrigger(hours=2)  # Every 2 hours
        IntervalTrigger(days=1, hours=12)  # Every 1.5 days
    """
    weeks: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    def __post_init__(self):
        self._interval = timedelta(
            weeks=self.weeks,
            days=self.days,
            hours=self.hours,
            minutes=self.minutes,
            seconds=self.seconds
        )
        if self._interval.total_seconds() <= 0:
            raise ValueError("Interval must be positive")

    def get_next_run_time(self, after: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate the next run time based on interval."""
        now = after or datetime.utcnow()
        start = self.start_time or now

        if now < start:
            next_time = start
        else:
            # Calculate how many intervals have passed
            elapsed = now - start
            intervals_passed = int(elapsed.total_seconds() / self._interval.total_seconds())
            next_time = start + self._interval * (intervals_passed + 1)

        # Check end time
        if self.end_time and next_time > self.end_time:
            return None

        return next_time

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "type": "interval",
            "weeks": self.weeks,
            "days": self.days,
            "hours": self.hours,
            "minutes": self.minutes,
            "seconds": self.seconds,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntervalTrigger":
        """Deserialize from dictionary."""
        start_time = data.get("start_time")
        end_time = data.get("end_time")

        return cls(
            weeks=data.get("weeks", 0),
            days=data.get("days", 0),
            hours=data.get("hours", 0),
            minutes=data.get("minutes", 0),
            seconds=data.get("seconds", 0),
            start_time=datetime.fromisoformat(start_time) if start_time else None,
            end_time=datetime.fromisoformat(end_time) if end_time else None,
        )


@dataclass
class DateTrigger(JobTrigger):
    """
    One-time date trigger.

    Example:
        DateTrigger(run_at=datetime(2024, 1, 15, 10, 0))  # Run once at specific time
    """
    run_at: datetime

    def get_next_run_time(self, after: Optional[datetime] = None) -> Optional[datetime]:
        """Get the scheduled run time if not yet passed."""
        now = after or datetime.utcnow()
        if self.run_at > now:
            return self.run_at
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "type": "date",
            "run_at": self.run_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DateTrigger":
        """Deserialize from dictionary."""
        return cls(run_at=datetime.fromisoformat(data["run_at"]))


@dataclass
class ScheduledJob:
    """
    Represents a scheduled job.

    Example:
    ```python
    job = ScheduledJob(
        name="daily-backup",
        trigger=CronTrigger("0 2 * * *"),
        action="backup",
        module="backup_validation",
        params={"target": "production"}
    )
    ```
    """
    name: str
    trigger: JobTrigger
    action: str
    module: str

    # Optional configuration
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    # Execution settings
    timeout: int = 3600  # seconds
    max_retries: int = 3
    retry_delay: int = 60  # seconds
    coalesce: bool = True  # Combine missed runs
    max_instances: int = 1  # Max concurrent instances

    # State
    status: JobStatus = JobStatus.PENDING
    next_run_time: Optional[datetime] = None
    last_run_time: Optional[datetime] = None
    last_result: Optional[Dict[str, Any]] = None
    run_count: int = 0
    error_count: int = 0

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    enabled: bool = True

    def __post_init__(self):
        if not self.next_run_time:
            self.next_run_time = self.trigger.get_next_run_time()

    def calculate_next_run(self) -> Optional[datetime]:
        """Calculate and update next run time."""
        self.next_run_time = self.trigger.get_next_run_time()
        return self.next_run_time

    def record_run(self, success: bool, result: Optional[Dict[str, Any]] = None) -> None:
        """Record a job execution."""
        self.last_run_time = datetime.utcnow()
        self.last_result = result
        self.run_count += 1

        if success:
            self.status = JobStatus.COMPLETED
        else:
            self.error_count += 1
            self.status = JobStatus.FAILED

        # Schedule next run
        self.calculate_next_run()

    def pause(self) -> None:
        """Pause the job."""
        self.status = JobStatus.PAUSED
        self.enabled = False

    def resume(self) -> None:
        """Resume a paused job."""
        self.status = JobStatus.PENDING
        self.enabled = True
        self.calculate_next_run()

    def cancel(self) -> None:
        """Cancel the job."""
        self.status = JobStatus.CANCELLED
        self.enabled = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger": self.trigger.to_dict(),
            "action": self.action,
            "module": self.module,
            "params": self.params,
            "tags": self.tags,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "coalesce": self.coalesce,
            "max_instances": self.max_instances,
            "status": self.status.value,
            "next_run_time": self.next_run_time.isoformat() if self.next_run_time else None,
            "last_run_time": self.last_run_time.isoformat() if self.last_run_time else None,
            "last_result": self.last_result,
            "run_count": self.run_count,
            "error_count": self.error_count,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledJob":
        """Deserialize from dictionary."""
        trigger = JobTrigger.from_dict(data["trigger"])

        next_run = data.get("next_run_time")
        last_run = data.get("last_run_time")
        created = data.get("created_at")

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data["name"],
            description=data.get("description", ""),
            trigger=trigger,
            action=data["action"],
            module=data["module"],
            params=data.get("params", {}),
            tags=data.get("tags", []),
            timeout=data.get("timeout", 3600),
            max_retries=data.get("max_retries", 3),
            retry_delay=data.get("retry_delay", 60),
            coalesce=data.get("coalesce", True),
            max_instances=data.get("max_instances", 1),
            status=JobStatus(data.get("status", "pending")),
            next_run_time=datetime.fromisoformat(next_run) if next_run else None,
            last_run_time=datetime.fromisoformat(last_run) if last_run else None,
            last_result=data.get("last_result"),
            run_count=data.get("run_count", 0),
            error_count=data.get("error_count", 0),
            created_at=datetime.fromisoformat(created) if created else datetime.utcnow(),
            created_by=data.get("created_by"),
            enabled=data.get("enabled", True),
        )
