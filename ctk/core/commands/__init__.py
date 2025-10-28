"""
Shell command handlers

This package contains command handlers for the shell mode interface.
Commands are organized by category:
- navigation.py: cd, ls, pwd
- unix.py: cat, head, tail, echo, grep
- file_ops.py: ln, cp, mv, rm, mkdir
- database.py: star, pin, archive, title, search, show
- llm.py: chat, complete, model
- system.py: config, help, exit, clear
"""

from typing import Dict, Callable, List
from ctk.core.command_dispatcher import CommandResult


def get_all_commands() -> Dict[str, Callable]:
    """
    Get all registered command handlers

    Returns:
        Dictionary mapping command names to handler functions
    """
    handlers = {}

    # Import and register commands from each module
    try:
        from ctk.core.commands.unix import register_commands as register_unix
        handlers.update(register_unix())
    except ImportError:
        pass

    try:
        from ctk.core.commands.navigation import register_commands as register_navigation
        handlers.update(register_navigation())
    except ImportError:
        pass

    try:
        from ctk.core.commands.database import register_commands as register_database
        handlers.update(register_database())
    except ImportError:
        pass

    try:
        from ctk.core.commands.system import register_commands as register_system
        handlers.update(register_system())
    except ImportError:
        pass

    return handlers
