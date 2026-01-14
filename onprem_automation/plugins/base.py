"""
Plugin Base Classes

Defines the interface for plugins:
- Module plugins (add new automation modules)
- Connector plugins (add new infrastructure connectors)
- Integration plugins (add new ITSM/notification integrations)
- Auth plugins (add new authentication providers)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type
from dataclasses import dataclass, field
from enum import Enum
import logging


class PluginType(str, Enum):
    MODULE = "module"
    CONNECTOR = "connector"
    INTEGRATION = "integration"
    AUTH = "auth"
    NOTIFICATION = "notification"
    WEBHOOK = "webhook"


@dataclass
class PluginMetadata:
    """Plugin metadata definition."""
    name: str
    version: str
    description: str = ""
    author: str = ""
    homepage: str = ""
    license: str = ""
    plugin_type: PluginType = PluginType.MODULE

    # Dependencies
    requires: List[str] = field(default_factory=list)  # Other plugins
    python_requires: str = ">=3.8"
    pip_requires: List[str] = field(default_factory=list)

    # Configuration
    config_schema: Dict[str, Any] = field(default_factory=dict)

    # Capabilities
    provides_actions: List[str] = field(default_factory=list)
    provides_connectors: List[str] = field(default_factory=list)


class PluginBase(ABC):
    """
    Base class for all plugins.

    Example plugin:
    ```python
    class MyPlugin(PluginBase):
        metadata = PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My custom plugin",
            plugin_type=PluginType.MODULE,
        )

        def initialize(self, config: dict) -> bool:
            self.api_key = config.get("api_key")
            return True

        def get_actions(self) -> dict:
            return {
                "my_action": self.my_action,
            }

        async def my_action(self, **kwargs) -> dict:
            return {"status": "success"}
    ```
    """

    metadata: PluginMetadata = None

    def __init__(self):
        self.logger = logging.getLogger(f"plugin.{self.metadata.name if self.metadata else 'unknown'}")
        self._initialized = False
        self._config = {}

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        Initialize the plugin with configuration.

        Args:
            config: Plugin configuration

        Returns:
            True if initialization successful
        """
        pass

    def shutdown(self) -> None:
        """Cleanup plugin resources."""
        pass

    def health_check(self) -> Dict[str, Any]:
        """Check plugin health."""
        return {
            "status": "healthy" if self._initialized else "uninitialized",
            "name": self.metadata.name if self.metadata else "unknown",
            "version": self.metadata.version if self.metadata else "0.0.0",
        }

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate configuration against schema.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        schema = self.metadata.config_schema if self.metadata else {}

        for field_name, field_schema in schema.get("properties", {}).items():
            if field_schema.get("required") and field_name not in config:
                errors.append(f"Missing required field: {field_name}")

        return errors


class ModulePlugin(PluginBase):
    """Base class for module plugins."""

    def get_actions(self) -> Dict[str, callable]:
        """
        Get available actions.

        Returns:
            Dictionary of action_name -> async function
        """
        return {}

    async def execute(self, action: str, **kwargs) -> Dict[str, Any]:
        """Execute an action."""
        actions = self.get_actions()
        if action not in actions:
            return {"status": "error", "error": f"Unknown action: {action}"}

        return await actions[action](**kwargs)


class ConnectorPlugin(PluginBase):
    """Base class for connector plugins."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected."""
        pass


class IntegrationPlugin(PluginBase):
    """Base class for integration plugins (ITSM, notifications)."""

    @abstractmethod
    async def send(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Send event to integration."""
        pass


class AuthPlugin(PluginBase):
    """Base class for authentication plugins."""

    @abstractmethod
    async def authenticate(self, credentials: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Authenticate user.

        Args:
            credentials: Login credentials

        Returns:
            User info if authenticated, None otherwise
        """
        pass

    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        pass
