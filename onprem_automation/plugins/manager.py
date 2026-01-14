"""
Plugin Manager

Handles plugin discovery, loading, and lifecycle management.
Supports hot-reload and dependency resolution.
"""

import importlib
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Set
from dataclasses import dataclass, field
import json
import hashlib

from .base import PluginBase, PluginMetadata, PluginType


@dataclass
class PluginInfo:
    """Information about a loaded plugin."""
    name: str
    version: str
    plugin_type: PluginType
    module_path: str
    instance: Optional[PluginBase] = None
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    file_hash: str = ""
    dependencies_met: bool = True
    load_error: Optional[str] = None


class PluginRegistry:
    """Registry for managing plugin metadata and instances."""

    def __init__(self):
        self._plugins: Dict[str, PluginInfo] = {}
        self._by_type: Dict[PluginType, List[str]] = {pt: [] for pt in PluginType}
        self._logger = logging.getLogger("plugin.registry")

    def register(self, info: PluginInfo) -> None:
        """Register a plugin."""
        self._plugins[info.name] = info
        if info.name not in self._by_type[info.plugin_type]:
            self._by_type[info.plugin_type].append(info.name)
        self._logger.info(f"Registered plugin: {info.name} v{info.version}")

    def unregister(self, name: str) -> Optional[PluginInfo]:
        """Unregister a plugin."""
        if name in self._plugins:
            info = self._plugins.pop(name)
            if name in self._by_type[info.plugin_type]:
                self._by_type[info.plugin_type].remove(name)
            self._logger.info(f"Unregistered plugin: {name}")
            return info
        return None

    def get(self, name: str) -> Optional[PluginInfo]:
        """Get plugin info by name."""
        return self._plugins.get(name)

    def get_by_type(self, plugin_type: PluginType) -> List[PluginInfo]:
        """Get all plugins of a specific type."""
        return [self._plugins[name] for name in self._by_type[plugin_type]
                if name in self._plugins]

    def get_all(self) -> List[PluginInfo]:
        """Get all registered plugins."""
        return list(self._plugins.values())

    def has(self, name: str) -> bool:
        """Check if a plugin is registered."""
        return name in self._plugins


class PluginLoader:
    """Handles loading plugins from various sources."""

    def __init__(self):
        self._logger = logging.getLogger("plugin.loader")

    def load_from_path(self, path: Path) -> Optional[Type[PluginBase]]:
        """Load a plugin class from a file path."""
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugin_{path.stem}",
                path
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

                # Find plugin class
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and
                        issubclass(attr, PluginBase) and
                        attr is not PluginBase and
                        hasattr(attr, 'metadata') and
                        attr.metadata is not None):
                        return attr

            self._logger.warning(f"No plugin class found in {path}")
            return None
        except Exception as e:
            self._logger.error(f"Failed to load plugin from {path}: {e}")
            return None

    def load_from_module(self, module_name: str) -> Optional[Type[PluginBase]]:
        """Load a plugin class from a module name."""
        try:
            module = importlib.import_module(module_name)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, PluginBase) and
                    attr is not PluginBase and
                    hasattr(attr, 'metadata') and
                    attr.metadata is not None):
                    return attr

            self._logger.warning(f"No plugin class found in module {module_name}")
            return None
        except Exception as e:
            self._logger.error(f"Failed to load plugin from module {module_name}: {e}")
            return None

    def get_file_hash(self, path: Path) -> str:
        """Get hash of a plugin file for change detection."""
        try:
            with open(path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""


class DependencyResolver:
    """Resolves plugin dependencies."""

    def __init__(self, registry: PluginRegistry):
        self._registry = registry
        self._logger = logging.getLogger("plugin.deps")

    def check_dependencies(self, metadata: PluginMetadata) -> tuple[bool, List[str]]:
        """
        Check if all dependencies are met.

        Returns:
            Tuple of (all_met, missing_deps)
        """
        missing = []

        for dep in metadata.requires:
            if not self._registry.has(dep):
                missing.append(dep)

        return len(missing) == 0, missing

    def get_load_order(self, plugins: List[PluginMetadata]) -> List[PluginMetadata]:
        """
        Get plugins in dependency-resolved order.
        Uses topological sort.
        """
        # Build dependency graph
        graph: Dict[str, Set[str]] = {}
        name_to_meta: Dict[str, PluginMetadata] = {}

        for meta in plugins:
            graph[meta.name] = set(meta.requires)
            name_to_meta[meta.name] = meta

        # Topological sort
        result = []
        visited = set()
        temp_visited = set()

        def visit(name: str) -> bool:
            if name in temp_visited:
                self._logger.error(f"Circular dependency detected at {name}")
                return False
            if name in visited:
                return True

            temp_visited.add(name)

            if name in graph:
                for dep in graph[name]:
                    if dep in graph:  # Only visit deps that are being loaded
                        if not visit(dep):
                            return False

            temp_visited.remove(name)
            visited.add(name)

            if name in name_to_meta:
                result.append(name_to_meta[name])

            return True

        for name in graph:
            if name not in visited:
                if not visit(name):
                    return []  # Circular dependency

        return result


class PluginManager:
    """
    Main plugin manager for discovery, loading, and lifecycle management.

    Example usage:
    ```python
    manager = PluginManager()

    # Discover and load plugins
    manager.discover_plugins("/path/to/plugins")
    manager.load_all()

    # Get specific plugin
    plugin = manager.get_plugin("my-plugin")

    # Execute plugin action
    result = await plugin.instance.execute("action_name", arg1="value")

    # Hot reload changed plugins
    manager.reload_changed()
    ```
    """

    def __init__(self, plugin_dirs: Optional[List[str]] = None):
        self._registry = PluginRegistry()
        self._loader = PluginLoader()
        self._resolver = DependencyResolver(self._registry)
        self._plugin_dirs = plugin_dirs or []
        self._logger = logging.getLogger("plugin.manager")
        self._hooks: Dict[str, List[callable]] = {}

    @property
    def registry(self) -> PluginRegistry:
        """Get the plugin registry."""
        return self._registry

    def add_plugin_directory(self, path: str) -> None:
        """Add a directory to search for plugins."""
        if path not in self._plugin_dirs:
            self._plugin_dirs.append(path)
            self._logger.info(f"Added plugin directory: {path}")

    def discover_plugins(self, path: Optional[str] = None) -> List[PluginInfo]:
        """
        Discover plugins in directories.

        Args:
            path: Optional specific path to search

        Returns:
            List of discovered plugin info
        """
        discovered = []
        search_paths = [path] if path else self._plugin_dirs

        for search_path in search_paths:
            p = Path(search_path)
            if not p.exists():
                self._logger.warning(f"Plugin directory not found: {search_path}")
                continue

            # Search for Python files
            for py_file in p.glob("**/*.py"):
                if py_file.name.startswith("_"):
                    continue

                plugin_class = self._loader.load_from_path(py_file)
                if plugin_class and plugin_class.metadata:
                    info = PluginInfo(
                        name=plugin_class.metadata.name,
                        version=plugin_class.metadata.version,
                        plugin_type=plugin_class.metadata.plugin_type,
                        module_path=str(py_file),
                        file_hash=self._loader.get_file_hash(py_file)
                    )
                    discovered.append(info)
                    self._logger.info(f"Discovered plugin: {info.name}")

        return discovered

    def load_plugin(
        self,
        name_or_path: str,
        config: Optional[Dict[str, Any]] = None
    ) -> Optional[PluginBase]:
        """
        Load a single plugin.

        Args:
            name_or_path: Plugin name, module path, or file path
            config: Optional configuration for the plugin

        Returns:
            Plugin instance or None if failed
        """
        config = config or {}

        # Determine if it's a path or module name
        if os.path.exists(name_or_path):
            path = Path(name_or_path)
            plugin_class = self._loader.load_from_path(path)
            module_path = str(path)
            file_hash = self._loader.get_file_hash(path)
        else:
            plugin_class = self._loader.load_from_module(name_or_path)
            module_path = name_or_path
            file_hash = ""

        if not plugin_class or not plugin_class.metadata:
            return None

        metadata = plugin_class.metadata

        # Check dependencies
        deps_met, missing = self._resolver.check_dependencies(metadata)
        if not deps_met:
            self._logger.error(
                f"Plugin {metadata.name} missing dependencies: {missing}"
            )
            info = PluginInfo(
                name=metadata.name,
                version=metadata.version,
                plugin_type=metadata.plugin_type,
                module_path=module_path,
                enabled=False,
                dependencies_met=False,
                load_error=f"Missing dependencies: {missing}"
            )
            self._registry.register(info)
            return None

        # Create and initialize instance
        try:
            instance = plugin_class()

            # Validate config
            errors = instance.validate_config(config)
            if errors:
                self._logger.warning(
                    f"Plugin {metadata.name} config warnings: {errors}"
                )

            # Initialize
            if not instance.initialize(config):
                raise RuntimeError("Plugin initialization returned False")

            instance._initialized = True
            instance._config = config

            info = PluginInfo(
                name=metadata.name,
                version=metadata.version,
                plugin_type=metadata.plugin_type,
                module_path=module_path,
                instance=instance,
                enabled=True,
                config=config,
                file_hash=file_hash,
                dependencies_met=True
            )

            self._registry.register(info)
            self._trigger_hook("plugin_loaded", info)

            self._logger.info(f"Loaded plugin: {metadata.name} v{metadata.version}")
            return instance

        except Exception as e:
            self._logger.error(f"Failed to initialize plugin {metadata.name}: {e}")
            info = PluginInfo(
                name=metadata.name,
                version=metadata.version,
                plugin_type=metadata.plugin_type,
                module_path=module_path,
                enabled=False,
                load_error=str(e)
            )
            self._registry.register(info)
            return None

    def load_all(self, configs: Optional[Dict[str, Dict[str, Any]]] = None) -> int:
        """
        Load all discovered plugins.

        Args:
            configs: Optional dict of plugin_name -> config

        Returns:
            Number of successfully loaded plugins
        """
        configs = configs or {}
        loaded = 0

        # Discover all plugins first
        all_discovered = []
        for path in self._plugin_dirs:
            all_discovered.extend(self.discover_plugins(path))

        # Get load order based on dependencies
        # For now, just load in discovery order
        for info in all_discovered:
            if not self._registry.has(info.name):
                config = configs.get(info.name, {})
                if self.load_plugin(info.module_path, config):
                    loaded += 1

        self._logger.info(f"Loaded {loaded} plugins")
        return loaded

    def unload_plugin(self, name: str) -> bool:
        """
        Unload a plugin.

        Args:
            name: Plugin name

        Returns:
            True if unloaded successfully
        """
        info = self._registry.get(name)
        if not info:
            return False

        try:
            if info.instance:
                info.instance.shutdown()

            self._registry.unregister(name)
            self._trigger_hook("plugin_unloaded", info)

            self._logger.info(f"Unloaded plugin: {name}")
            return True

        except Exception as e:
            self._logger.error(f"Error unloading plugin {name}: {e}")
            return False

    def reload_plugin(self, name: str) -> Optional[PluginBase]:
        """
        Reload a plugin (unload then load).

        Args:
            name: Plugin name

        Returns:
            New plugin instance or None
        """
        info = self._registry.get(name)
        if not info:
            return None

        config = info.config
        module_path = info.module_path

        self.unload_plugin(name)

        # Clear module cache
        for mod_name in list(sys.modules.keys()):
            if f"plugin_{Path(module_path).stem}" in mod_name:
                del sys.modules[mod_name]

        return self.load_plugin(module_path, config)

    def reload_changed(self) -> List[str]:
        """
        Reload plugins that have changed on disk.

        Returns:
            List of reloaded plugin names
        """
        reloaded = []

        for info in self._registry.get_all():
            if info.module_path and os.path.exists(info.module_path):
                current_hash = self._loader.get_file_hash(Path(info.module_path))
                if current_hash != info.file_hash:
                    self._logger.info(f"Plugin {info.name} changed, reloading...")
                    if self.reload_plugin(info.name):
                        reloaded.append(info.name)

        return reloaded

    def get_plugin(self, name: str) -> Optional[PluginInfo]:
        """Get plugin info by name."""
        return self._registry.get(name)

    def get_plugins_by_type(self, plugin_type: PluginType) -> List[PluginInfo]:
        """Get all plugins of a specific type."""
        return self._registry.get_by_type(plugin_type)

    def get_all_plugins(self) -> List[PluginInfo]:
        """Get all loaded plugins."""
        return self._registry.get_all()

    def get_enabled_plugins(self) -> List[PluginInfo]:
        """Get all enabled plugins."""
        return [p for p in self._registry.get_all() if p.enabled]

    def enable_plugin(self, name: str) -> bool:
        """Enable a disabled plugin."""
        info = self._registry.get(name)
        if info and not info.enabled:
            # Re-initialize if needed
            if info.instance and not info.instance._initialized:
                if info.instance.initialize(info.config):
                    info.instance._initialized = True
                    info.enabled = True
                    return True
            elif info.instance:
                info.enabled = True
                return True
        return False

    def disable_plugin(self, name: str) -> bool:
        """Disable a plugin without unloading."""
        info = self._registry.get(name)
        if info and info.enabled:
            info.enabled = False
            if info.instance:
                info.instance._initialized = False
            return True
        return False

    def register_hook(self, event: str, callback: callable) -> None:
        """Register a callback for plugin events."""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)

    def _trigger_hook(self, event: str, *args, **kwargs) -> None:
        """Trigger registered callbacks for an event."""
        for callback in self._hooks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                self._logger.error(f"Hook {event} callback error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get overall plugin system status."""
        plugins = self._registry.get_all()
        return {
            "total_plugins": len(plugins),
            "enabled_plugins": len([p for p in plugins if p.enabled]),
            "disabled_plugins": len([p for p in plugins if not p.enabled]),
            "by_type": {
                pt.value: len(self._registry.get_by_type(pt))
                for pt in PluginType
            },
            "plugins": [
                {
                    "name": p.name,
                    "version": p.version,
                    "type": p.plugin_type.value,
                    "enabled": p.enabled,
                    "error": p.load_error
                }
                for p in plugins
            ]
        }

    def export_config(self) -> Dict[str, Any]:
        """Export all plugin configurations."""
        return {
            p.name: p.config
            for p in self._registry.get_all()
            if p.config
        }

    def import_config(self, configs: Dict[str, Dict[str, Any]]) -> None:
        """Import plugin configurations and reload affected plugins."""
        for name, config in configs.items():
            info = self._registry.get(name)
            if info:
                info.config = config
                self.reload_plugin(name)


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the global plugin manager instance."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager


def reset_plugin_manager() -> None:
    """Reset the global plugin manager (for testing)."""
    global _plugin_manager
    if _plugin_manager:
        for info in _plugin_manager.get_all_plugins():
            _plugin_manager.unload_plugin(info.name)
    _plugin_manager = None
