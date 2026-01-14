"""
Base Connector Classes

Provides abstract base classes and common exceptions for all infrastructure connectors.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass
from contextlib import contextmanager
import time
import logging


class ConnectionError(Exception):
    """Raised when connection to infrastructure fails."""
    pass


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class CommandExecutionError(Exception):
    """Raised when a command execution fails."""
    pass


@dataclass
class ConnectionConfig:
    """Base configuration for connections."""
    host: str
    username: str
    password: str
    port: int = 0
    timeout: int = 30
    verify_ssl: bool = True
    retry_count: int = 3
    retry_delay: float = 1.0


class BaseConnector(ABC):
    """
    Abstract base class for all infrastructure connectors.

    Provides common functionality:
    - Connection lifecycle management
    - Retry logic with exponential backoff
    - Connection pooling support
    - Metrics collection hooks
    """

    def __init__(self, config: ConnectionConfig, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._connected = False
        self._connection = None
        self._connection_time: Optional[float] = None

    @property
    def is_connected(self) -> bool:
        """Check if connector is currently connected."""
        return self._connected

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the infrastructure.

        Returns:
            True if connection successful, False otherwise.

        Raises:
            ConnectionError: If connection fails after all retries.
            AuthenticationError: If authentication fails.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection and cleanup resources."""
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the connection.

        Returns:
            Dict with status, latency, and other health metrics.
        """
        pass

    def _retry_operation(self, operation, *args, **kwargs) -> Any:
        """
        Execute an operation with retry logic and exponential backoff.

        Args:
            operation: Callable to execute
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation

        Returns:
            Result of the operation

        Raises:
            Last exception if all retries fail
        """
        last_exception = None
        delay = self.config.retry_delay

        for attempt in range(self.config.retry_count):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                self.logger.warning(
                    f"Operation failed (attempt {attempt + 1}/{self.config.retry_count}): {e}"
                )
                if attempt < self.config.retry_count - 1:
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff

        raise last_exception

    @contextmanager
    def connection_context(self):
        """
        Context manager for connection lifecycle.

        Usage:
            with connector.connection_context():
                connector.execute_command(...)
        """
        try:
            if not self._connected:
                self.connect()
            yield self
        finally:
            if self._connected:
                self.disconnect()

    def __enter__(self):
        """Enter context manager."""
        if not self._connected:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        self.disconnect()
        return False


class ConnectionPool:
    """
    Connection pool for managing multiple connections.

    Provides:
    - Connection reuse
    - Maximum connection limits
    - Automatic cleanup of stale connections
    """

    def __init__(self, connector_class, max_connections: int = 10):
        self.connector_class = connector_class
        self.max_connections = max_connections
        self._pool: Dict[str, BaseConnector] = {}
        self._in_use: Dict[str, bool] = {}
        self.logger = logging.getLogger("ConnectionPool")

    def get_connection(self, config: ConnectionConfig) -> BaseConnector:
        """
        Get a connection from the pool or create a new one.

        Args:
            config: Connection configuration

        Returns:
            Connector instance
        """
        key = f"{config.host}:{config.port}:{config.username}"

        if key in self._pool and not self._in_use.get(key, False):
            self._in_use[key] = True
            return self._pool[key]

        if len(self._pool) >= self.max_connections:
            # Remove oldest unused connection
            for k, in_use in self._in_use.items():
                if not in_use:
                    self._pool[k].disconnect()
                    del self._pool[k]
                    del self._in_use[k]
                    break

        connector = self.connector_class(config)
        connector.connect()
        self._pool[key] = connector
        self._in_use[key] = True
        return connector

    def release_connection(self, connector: BaseConnector) -> None:
        """Release a connection back to the pool."""
        for key, conn in self._pool.items():
            if conn is connector:
                self._in_use[key] = False
                break

    def close_all(self) -> None:
        """Close all connections in the pool."""
        for connector in self._pool.values():
            try:
                connector.disconnect()
            except Exception as e:
                self.logger.error(f"Error closing connection: {e}")
        self._pool.clear()
        self._in_use.clear()
