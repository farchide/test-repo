"""
Database Package

Provides SQLAlchemy-based persistence for:
- Jobs and executions
- Workflows and templates
- Users and permissions
- Audit logs
- Schedules
"""

from .models import (
    Base,
    Job,
    JobExecution,
    Workflow,
    WorkflowExecution,
    Schedule,
    AuditLog,
    User,
    Role,
    Permission,
    Secret,
    Plugin,
)
from .session import (
    get_engine,
    get_session,
    init_db,
    DatabaseSession,
)

__all__ = [
    # Models
    "Base",
    "Job",
    "JobExecution",
    "Workflow",
    "WorkflowExecution",
    "Schedule",
    "AuditLog",
    "User",
    "Role",
    "Permission",
    "Secret",
    "Plugin",
    # Session
    "get_engine",
    "get_session",
    "init_db",
    "DatabaseSession",
]
