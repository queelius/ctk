"""
Tool utilities for LLM tool calling.

Provides functions for working with tool definitions:
- get_ask_tools(): Get tool schemas for LLM APIs
- is_pass_through_tool(): Check if tool output goes directly to user
- pass_through_tools(): The derived set of pass-through tool names
"""

from typing import Any, Dict, List, Set

# Importing builtin_tools for its side effect: it registers the
# ``ctk.builtin`` provider with tools_registry at import time. Without this,
# a caller that imports only ``ctk.core.tools`` (rather than going through
# the TUI's _register_builtin_providers) would see an empty registry.
import ctk.core.builtin_tools  # noqa: F401  (import for side effect)
from .tools_registry import all_tools as _provider_tools


def get_ask_tools(include_pass_through: bool = True) -> List[Dict[str, Any]]:
    """Get tool schemas for the LLM.

    Pulls from the provider registry (``tools_registry.all_tools``)
    so that any provider registered after import — for example the
    ``ctk.network`` virtual MCP — is automatically included.

    Args:
        include_pass_through: If True, include pass_through flag in tool defs

    Returns:
        List of tool definitions
    """
    tools = _provider_tools()
    if include_pass_through:
        return tools
    # Remove pass_through key from tools for LLM API calls.
    return [{k: v for k, v in tool.items() if k != "pass_through"} for tool in tools]


def pass_through_tools() -> Set[str]:
    """The set of tool names whose output goes directly to the user.

    Derived from the registered tools' ``pass_through`` flag rather than
    a hardcoded list, so a provider that marks a tool pass-through needs
    no edit here.
    """
    return {t["name"] for t in _provider_tools() if t.get("pass_through")}


def is_pass_through_tool(tool_name: str) -> bool:
    """
    Check if a tool is a pass-through tool.

    Pass-through tools have their output sent directly to the user,
    rather than being processed by the LLM first. Membership is derived
    from the live registry (``pass_through_tools``) at call time.

    Args:
        tool_name: Name of the tool to check

    Returns:
        True if tool output goes directly to user
    """
    return tool_name in pass_through_tools()
