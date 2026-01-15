"""
SQLAlchemy Database Models

Provides ORM models for all platform entities.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import json
import uuid

# Try SQLAlchemy import
try:
    from sqlalchemy import (
        Column, String, Integer, Float, Boolean, DateTime, Text,
        ForeignKey, Table, JSON, Enum as SQLEnum, Index, UniqueConstraint
    )
    from sqlalchemy.orm import declarative_base, relationship
    from sqlalchemy.dialects.postgresql import UUID
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False

    # Create mock implementations for when SQLAlchemy is not available
    class MockBase:
        metadata = None
        pass

    def declarative_base():
        return MockBase

    # Mock column types
    def Column(*args, **kwargs):
        return None

    def String(length=None):
        return None

    def Integer():
        return None

    def Float():
        return None

    def Boolean():
        return None

    def DateTime():
        return None

    def Text():
        return None

    def ForeignKey(name):
        return None

    def Table(*args, **kwargs):
        return None

    def JSON():
        return None

    def SQLEnum(*args, **kwargs):
        return None

    def Index(*args, **kwargs):
        return None

    def UniqueConstraint(*args, **kwargs):
        return None

    def relationship(*args, **kwargs):
        return None

    UUID = None


Base = declarative_base()


# ==================== Enums ====================

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class WorkflowStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ScheduleType(str, Enum):
    CRON = "cron"
    INTERVAL = "interval"
    DATE = "date"
    MAINTENANCE_WINDOW = "maintenance_window"


class AuditAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    LOGIN = "login"
    LOGOUT = "logout"
    APPROVE = "approve"
    REJECT = "reject"


# ==================== Association Tables ====================

if SQLALCHEMY_AVAILABLE:
    user_roles = Table(
        'user_roles',
        Base.metadata,
        Column('user_id', String(36), ForeignKey('users.id')),
        Column('role_id', String(36), ForeignKey('roles.id'))
    )

    role_permissions = Table(
        'role_permissions',
        Base.metadata,
        Column('role_id', String(36), ForeignKey('roles.id')),
        Column('permission_id', String(36), ForeignKey('permissions.id'))
    )
else:
    user_roles = None
    role_permissions = None


# ==================== User & Auth Models ====================

class User(Base):
    """User account model."""
    __tablename__ = 'users'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=True)  # Null for SSO users
    full_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)

    # SSO fields
    sso_provider = Column(String(50))  # ldap, saml, oauth2
    sso_id = Column(String(255))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime)

    # Relationships
    roles = relationship("Role", secondary="user_roles", back_populates="users")
    job_executions = relationship("JobExecution", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "is_superuser": self.is_superuser,
            "roles": [r.name for r in self.roles] if self.roles else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


class Role(Base):
    """User role for RBAC."""
    __tablename__ = 'roles'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    is_system = Column(Boolean, default=False)  # Built-in roles
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    users = relationship("User", secondary="user_roles", back_populates="roles")
    permissions = relationship("Permission", secondary="role_permissions", back_populates="roles")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_system": self.is_system,
            "permissions": [p.name for p in self.permissions] if self.permissions else [],
        }


class Permission(Base):
    """Permission for RBAC."""
    __tablename__ = 'permissions'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)  # e.g., "vmware:provision"
    resource = Column(String(100), nullable=False)  # e.g., "vmware"
    action = Column(String(50), nullable=False)  # e.g., "provision"
    description = Column(Text)

    # Relationships
    roles = relationship("Role", secondary="role_permissions", back_populates="permissions")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "resource": self.resource,
            "action": self.action,
            "description": self.description,
        }


# ==================== Job & Execution Models ====================

class Job(Base):
    """Job definition model."""
    __tablename__ = 'jobs'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    module = Column(String(100), nullable=False)  # e.g., "vmware"
    action = Column(String(100), nullable=False)  # e.g., "provision_vm"
    parameters = Column(JSON, default=dict)  # Default parameters

    # Settings
    timeout = Column(Integer, default=3600)  # seconds
    retry_count = Column(Integer, default=0)
    retry_delay = Column(Integer, default=60)  # seconds
    requires_approval = Column(Boolean, default=False)

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(36), ForeignKey('users.id'))

    # Relationships
    executions = relationship("JobExecution", back_populates="job")
    schedules = relationship("Schedule", back_populates="job")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "module": self.module,
            "action": self.action,
            "parameters": self.parameters,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "requires_approval": self.requires_approval,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class JobExecution(Base):
    """Job execution history."""
    __tablename__ = 'job_executions'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey('jobs.id'), nullable=False, index=True)
    workflow_execution_id = Column(String(36), ForeignKey('workflow_executions.id'))

    # Execution details
    status = Column(String(20), default=JobStatus.PENDING.value, index=True)
    parameters = Column(JSON, default=dict)  # Runtime parameters
    result = Column(JSON)  # Execution result
    error = Column(Text)  # Error message if failed

    # Timing
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration = Column(Float)  # seconds

    # Retry tracking
    attempt = Column(Integer, default=1)

    # User who triggered
    user_id = Column(String(36), ForeignKey('users.id'))
    trigger_type = Column(String(50))  # manual, scheduled, webhook, workflow

    # Relationships
    job = relationship("Job", back_populates="executions")
    user = relationship("User", back_populates="job_executions")
    workflow_execution = relationship("WorkflowExecution", back_populates="job_executions")

    # Indexes
    __table_args__ = (
        Index('ix_job_executions_status_started', 'status', 'started_at'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "status": self.status,
            "parameters": self.parameters,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration": self.duration,
            "attempt": self.attempt,
            "trigger_type": self.trigger_type,
        }


# ==================== Workflow Models ====================

class Workflow(Base):
    """Workflow definition model."""
    __tablename__ = 'workflows'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    version = Column(Integer, default=1)

    # Workflow definition (YAML stored as JSON)
    definition = Column(JSON, nullable=False)

    # Settings
    status = Column(String(20), default=WorkflowStatus.DRAFT.value)
    timeout = Column(Integer, default=7200)  # seconds
    max_parallel = Column(Integer, default=5)  # Max parallel steps
    requires_approval = Column(Boolean, default=False)

    # Categorization
    category = Column(String(100))  # e.g., "provisioning", "patching"
    tags = Column(JSON, default=list)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(36), ForeignKey('users.id'))

    # Relationships
    executions = relationship("WorkflowExecution", back_populates="workflow")
    schedules = relationship("Schedule", back_populates="workflow")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "definition": self.definition,
            "status": self.status,
            "timeout": self.timeout,
            "category": self.category,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WorkflowExecution(Base):
    """Workflow execution history."""
    __tablename__ = 'workflow_executions'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = Column(String(36), ForeignKey('workflows.id'), nullable=False, index=True)

    # Execution details
    status = Column(String(20), default=JobStatus.PENDING.value, index=True)
    parameters = Column(JSON, default=dict)  # Input parameters
    context = Column(JSON, default=dict)  # Workflow context/state
    result = Column(JSON)  # Final result
    error = Column(Text)

    # Step tracking
    current_step = Column(String(100))
    completed_steps = Column(JSON, default=list)
    failed_steps = Column(JSON, default=list)

    # Timing
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration = Column(Float)

    # User who triggered
    user_id = Column(String(36), ForeignKey('users.id'))
    trigger_type = Column(String(50))

    # Relationships
    workflow = relationship("Workflow", back_populates="executions")
    job_executions = relationship("JobExecution", back_populates="workflow_execution")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "parameters": self.parameters,
            "current_step": self.current_step,
            "completed_steps": self.completed_steps,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration": self.duration,
        }


# ==================== Schedule Model ====================

class Schedule(Base):
    """Job/Workflow schedule model."""
    __tablename__ = 'schedules'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # What to run
    job_id = Column(String(36), ForeignKey('jobs.id'))
    workflow_id = Column(String(36), ForeignKey('workflows.id'))
    parameters = Column(JSON, default=dict)

    # Schedule configuration
    schedule_type = Column(String(20), default=ScheduleType.CRON.value)
    cron_expression = Column(String(100))  # For cron type
    interval_seconds = Column(Integer)  # For interval type
    run_date = Column(DateTime)  # For date type
    timezone = Column(String(50), default="UTC")

    # Maintenance window
    maintenance_window_start = Column(String(10))  # HH:MM
    maintenance_window_end = Column(String(10))  # HH:MM
    maintenance_days = Column(JSON)  # [0-6] for days of week

    # Control
    is_active = Column(Boolean, default=True)
    max_instances = Column(Integer, default=1)  # Concurrent runs

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_run = Column(DateTime)
    next_run = Column(DateTime)

    # Relationships
    job = relationship("Job", back_populates="schedules")
    workflow = relationship("Workflow", back_populates="schedules")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "job_id": self.job_id,
            "workflow_id": self.workflow_id,
            "schedule_type": self.schedule_type,
            "cron_expression": self.cron_expression,
            "interval_seconds": self.interval_seconds,
            "timezone": self.timezone,
            "is_active": self.is_active,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
        }


# ==================== Audit Log Model ====================

class AuditLog(Base):
    """Audit log for compliance."""
    __tablename__ = 'audit_logs'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # What happened
    action = Column(String(50), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)  # e.g., "job", "workflow"
    resource_id = Column(String(36), index=True)
    resource_name = Column(String(255))

    # Details
    old_value = Column(JSON)  # Previous state
    new_value = Column(JSON)  # New state
    details = Column(JSON)  # Additional context

    # Who and when
    user_id = Column(String(36), ForeignKey('users.id'))
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    # Indexes
    __table_args__ = (
        Index('ix_audit_logs_resource', 'resource_type', 'resource_id'),
        Index('ix_audit_logs_user_time', 'user_id', 'timestamp'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "details": self.details,
            "user_id": self.user_id,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ==================== Secret Model ====================

class Secret(Base):
    """Encrypted secret storage."""
    __tablename__ = 'secrets'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text)

    # Encrypted value (base64 encoded)
    encrypted_value = Column(Text, nullable=False)
    encryption_key_id = Column(String(100))  # Reference to key in vault

    # Metadata
    secret_type = Column(String(50))  # password, api_key, certificate, ssh_key
    expires_at = Column(DateTime)

    # Access control
    allowed_jobs = Column(JSON, default=list)  # Job IDs that can access
    allowed_workflows = Column(JSON, default=list)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_accessed = Column(DateTime)
    access_count = Column(Integer, default=0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "secret_type": self.secret_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            # Never include the actual value!
        }


# ==================== Plugin Model ====================

class Plugin(Base):
    """Installed plugin registry."""
    __tablename__ = 'plugins'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True, index=True)
    version = Column(String(50), nullable=False)
    description = Column(Text)

    # Plugin info
    author = Column(String(255))
    homepage = Column(String(500))
    repository = Column(String(500))

    # Module path
    module_path = Column(String(500), nullable=False)
    entry_point = Column(String(255))  # Main class/function

    # Dependencies
    dependencies = Column(JSON, default=list)
    python_requires = Column(String(100))

    # Status
    is_active = Column(Boolean, default=True)
    is_builtin = Column(Boolean, default=False)

    # Configuration
    config_schema = Column(JSON)  # JSON Schema for config
    config = Column(JSON, default=dict)

    # Timestamps
    installed_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "is_active": self.is_active,
            "is_builtin": self.is_builtin,
            "installed_at": self.installed_at.isoformat() if self.installed_at else None,
        }
