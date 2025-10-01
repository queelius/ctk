"""Core components of the Conversation Toolkit"""

from .plugin import PluginRegistry

# Create global registry instance
registry = PluginRegistry()

__all__ = ['registry', 'PluginRegistry']