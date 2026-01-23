"""
Shell command handlers

This package contains command handlers for the shell mode interface.
Commands are organized by category:
- navigation.py: cd, ls, pwd
- unix.py: cat, head, tail, echo, grep
- search.py: find
- visualization.py: tree, paths, show
- organization.py: star, pin, archive, title, delete, duplicate, tag
- chat.py: chat, complete, say
- settings.py: set, get
- database.py: save, load, search, list (TUI database operations)
- llm.py: temp, model, models, regenerate, retry, stream
- session.py: clear, new-chat, system, context, user, stats
- tree_nav.py: fork, branch, merge, goto-*, where, alternatives
"""

from typing import Callable, Dict

from ctk.core.command_dispatcher import CommandResult

# Export commonly used items
__all__ = [
    "CommandResult",
    "create_navigation_commands",
    "create_unix_commands",
    "create_visualization_commands",
    "create_organization_commands",
    "create_search_commands",
    "create_chat_commands",
    "create_settings_commands",
    "create_database_commands",
    "create_llm_commands",
    "create_session_commands",
    "create_tree_nav_commands",
]

# Lazy imports for command factories
def create_navigation_commands(*args, **kwargs):
    from .navigation import create_navigation_commands as _create
    return _create(*args, **kwargs)

def create_unix_commands(*args, **kwargs):
    from .unix import create_unix_commands as _create
    return _create(*args, **kwargs)

def create_visualization_commands(*args, **kwargs):
    from .visualization import create_visualization_commands as _create
    return _create(*args, **kwargs)

def create_organization_commands(*args, **kwargs):
    from .organization import create_organization_commands as _create
    return _create(*args, **kwargs)

def create_search_commands(*args, **kwargs):
    from .search import create_search_commands as _create
    return _create(*args, **kwargs)

def create_chat_commands(*args, **kwargs):
    from .chat import create_chat_commands as _create
    return _create(*args, **kwargs)

def create_settings_commands(*args, **kwargs):
    from .settings import create_settings_commands as _create
    return _create(*args, **kwargs)

def create_database_commands(*args, **kwargs):
    from .database import create_database_commands as _create
    return _create(*args, **kwargs)

def create_llm_commands(*args, **kwargs):
    from .llm import create_llm_commands as _create
    return _create(*args, **kwargs)

def create_session_commands(*args, **kwargs):
    from .session import create_session_commands as _create
    return _create(*args, **kwargs)

def create_tree_nav_commands(*args, **kwargs):
    from .tree_nav import create_tree_nav_commands as _create
    return _create(*args, **kwargs)
