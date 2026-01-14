"""
Plugin System

Provides extensibility through:
- Hot-loadable plugins
- Plugin discovery
- Dependency management
- Configuration management
"""

from .base import (
    PluginBase,
    PluginMetadata,
    PluginType,
    ModulePlugin,
    ConnectorPlugin,
    IntegrationPlugin,
    AuthPlugin,
)
from .manager import (
    PluginManager,
    PluginInfo,
    PluginRegistry,
    get_plugin_manager,
    reset_plugin_manager,
)

__all__ = [
    # Base classes
    "PluginBase",
    "PluginMetadata",
    "PluginType",
    "ModulePlugin",
    "ConnectorPlugin",
    "IntegrationPlugin",
    "AuthPlugin",
    # Manager
    "PluginManager",
    "PluginInfo",
    "PluginRegistry",
    "get_plugin_manager",
    "reset_plugin_manager",
]
