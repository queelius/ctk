"""
Tool utilities for LLM tool calling.

Provides functions for working with tool definitions:
- get_ask_tools(): Get tool schemas for LLM APIs
- is_pass_through_tool(): Check if tool output goes directly to user
"""

from typing import Any, Dict, List

from .tools_registry import (PASS_THROUGH_TOOLS, TOOLS_REGISTRY,
                              all_tools as _provider_tools)


def get_ask_tools(include_pass_through: bool = True) -> List[Dict[str, Any]]:
    """Get tool schemas for the LLM.

    Pulls from the provider registry (``tools_registry.iter_providers``)
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


def is_pass_through_tool(tool_name: str) -> bool:
    """
    Check if a tool is a pass-through tool.

    Pass-through tools have their output sent directly to the user,
    rather than being processed by the LLM first.

    Args:
        tool_name: Name of the tool to check

    Returns:
        True if tool output goes directly to user
    """
    return tool_name in PASS_THROUGH_TOOLS
