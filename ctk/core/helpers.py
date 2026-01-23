"""
Shared helper functions for CLI and TUI.

This module re-exports functions from focused modules for backwards compatibility.
New code should import directly from the specific modules:

- ctk.core.formatting: format_conversations_table
- ctk.core.db_helpers: list_conversations_helper, search_conversations_helper
- ctk.core.prompts: generate_cli_prompt_from_argparse, generate_tui_prompt_from_help,
                    get_ctk_system_prompt, get_ctk_system_prompt_no_tools
- ctk.core.tools: get_ask_tools, is_pass_through_tool
- ctk.core.tools_registry: TOOLS_REGISTRY, PASS_THROUGH_TOOLS
- ctk.core.conversation_display: show_conversation_helper
"""

# Re-export formatting functions
from .formatting import format_conversations_table

# Re-export database helper functions
from .db_helpers import list_conversations_helper, search_conversations_helper

# Re-export prompt generators
from .prompts import (
    generate_cli_prompt_from_argparse,
    generate_tui_prompt_from_help,
    get_ctk_system_prompt,
    get_ctk_system_prompt_no_tools,
)

# Re-export tool utilities
from .tools import get_ask_tools, is_pass_through_tool
from .tools_registry import PASS_THROUGH_TOOLS, TOOLS_REGISTRY

# Re-export conversation display helper
from .conversation_display import show_conversation_helper

# For explicit backwards compatibility, expose all public names
__all__ = [
    # Formatting
    "format_conversations_table",
    # DB helpers
    "list_conversations_helper",
    "search_conversations_helper",
    # Prompts
    "generate_cli_prompt_from_argparse",
    "generate_tui_prompt_from_help",
    "get_ctk_system_prompt",
    "get_ctk_system_prompt_no_tools",
    # Tools
    "get_ask_tools",
    "is_pass_through_tool",
    "PASS_THROUGH_TOOLS",
    "TOOLS_REGISTRY",
    # Display
    "show_conversation_helper",
]
