"""
Database Session Management

Provides session management for SQLAlchemy with support for:
- SQLite (development)
- PostgreSQL (production)
- Connection pooling
- Async support
"""

from typing import Optional, Generator
from contextlib import contextmanager
import os
import logging

# Try SQLAlchemy import
try:
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker, Session
    from sqlalchemy.pool import QueuePool
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    Session = None

from .models import Base

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine = None
_SessionLocal = None


def get_database_url() -> str:
    """
    Get database URL from environment or config.

    Supports:
    - DATABASE_URL environment variable
    - SQLite default for development
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        # Handle Heroku-style postgres:// -> postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    # Default to SQLite for development
    data_dir = os.environ.get("DATA_DIR", "/tmp/onprem_automation")
    os.makedirs(data_dir, exist_ok=True)
    return f"sqlite:///{data_dir}/automation.db"


def get_engine(database_url: Optional[str] = None, echo: bool = False):
    """
    Get or create SQLAlchemy engine.

    Args:
        database_url: Database connection URL
        echo: Enable SQL logging

    Returns:
        SQLAlchemy Engine
    """
    global _engine

    if not SQLALCHEMY_AVAILABLE:
        raise RuntimeError("SQLAlchemy is not installed. Run: pip install sqlalchemy")

    if _engine is not None:
        return _engine

    url = database_url or get_database_url()

    # Configure engine based on database type
    if url.startswith("sqlite"):
        _engine = create_engine(
            url,
            echo=echo,
            connect_args={"check_same_thread": False},  # SQLite specific
        )

        # Enable foreign keys for SQLite
        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    else:
        # PostgreSQL or other database
        _engine = create_engine(
            url,
            echo=echo,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections
            pool_recycle=3600,  # Recycle connections after 1 hour
        )

    logger.info(f"Database engine created: {url.split('@')[-1] if '@' in url else url}")
    return _engine


def get_session_factory(engine=None):
    """Get or create session factory."""
    global _SessionLocal

    if _SessionLocal is not None:
        return _SessionLocal

    if engine is None:
        engine = get_engine()

    _SessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    return _SessionLocal


def get_session() -> Generator[Session, None, None]:
    """
    Get database session (dependency injection pattern).

    Usage:
        with get_session() as session:
            users = session.query(User).all()

    Or as FastAPI dependency:
        @app.get("/users")
        def get_users(db: Session = Depends(get_session)):
            return db.query(User).all()
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def DatabaseSession():
    """
    Context manager for database sessions.

    Usage:
        with DatabaseSession() as session:
            user = session.query(User).first()
            session.add(new_job)
            session.commit()
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(database_url: Optional[str] = None, drop_all: bool = False):
    """
    Initialize database schema.

    Args:
        database_url: Optional database URL
        drop_all: Drop all tables first (for testing)
    """
    engine = get_engine(database_url)

    if drop_all:
        logger.warning("Dropping all database tables!")
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized")

    # Create default data
    _create_default_data()


def _create_default_data():
    """Create default roles, permissions, and admin user."""
    from .models import Role, Permission, User
    import hashlib

    with DatabaseSession() as session:
        # Check if already initialized
        if session.query(Role).filter_by(name="admin").first():
            return

        # Create default permissions
        resources = ["job", "workflow", "schedule", "user", "role", "secret", "plugin", "audit"]
        actions = ["create", "read", "update", "delete", "execute"]

        all_permissions = []
        for resource in resources:
            for action in actions:
                perm = Permission(
                    name=f"{resource}:{action}",
                    resource=resource,
                    action=action,
                    description=f"Can {action} {resource}s"
                )
                session.add(perm)
                all_permissions.append(perm)

        # Create admin role with all permissions
        admin_role = Role(
            name="admin",
            description="Full system administrator",
            is_system=True,
        )
        admin_role.permissions = all_permissions
        session.add(admin_role)

        # Create operator role
        operator_perms = [p for p in all_permissions if p.action in ["read", "execute"]]
        operator_role = Role(
            name="operator",
            description="Can view and execute jobs",
            is_system=True,
        )
        operator_role.permissions = operator_perms
        session.add(operator_role)

        # Create viewer role
        viewer_perms = [p for p in all_permissions if p.action == "read"]
        viewer_role = Role(
            name="viewer",
            description="Read-only access",
            is_system=True,
        )
        viewer_role.permissions = viewer_perms
        session.add(viewer_role)

        # Create default admin user
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin")
        admin_user = User(
            username="admin",
            email="admin@localhost",
            password_hash=hashlib.sha256(admin_password.encode()).hexdigest(),
            full_name="System Administrator",
            is_superuser=True,
            is_active=True,
        )
        admin_user.roles = [admin_role]
        session.add(admin_user)

        logger.info("Default roles and admin user created")


def reset_db():
    """Reset database (for testing)."""
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None


# Health check
def check_db_health() -> dict:
    """Check database health."""
    try:
        with DatabaseSession() as session:
            session.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}
