"""Plugin manager - handles plugin registration and discovery"""

from typing import Dict, List
from app.plugins.base import BasePlugin


class PluginManager:
    """Plugin manager - responsible for plugin registration and lookup"""

    def __init__(self):
        self._plugins: Dict[str, BasePlugin] = {}

    def register(self, plugin: BasePlugin):
        """Register a plugin"""
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> BasePlugin | None:
        """Get plugin by name"""
        return self._plugins.get(name)

    def list_plugins(self) -> List[BasePlugin]:
        """List all registered plugins"""
        return list(self._plugins.values())

    def get_by_category(self, category: str) -> List[BasePlugin]:
        """Get plugins by category"""
        return [p for p in self._plugins.values() if p.category == category]


# Global plugin manager instance
plugin_manager = PluginManager()
