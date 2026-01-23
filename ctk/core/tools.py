"""
Tool utilities for LLM tool calling.

Provides functions for working with tool definitions:
- get_ask_tools(): Get tool schemas for LLM APIs
- is_pass_through_tool(): Check if tool output goes directly to user
"""

from typing import Any, Dict, List

from .tools_registry import PASS_THROUGH_TOOLS, TOOLS_REGISTRY


def get_ask_tools(include_pass_through: bool = True) -> List[Dict[str, Any]]:
    """
    Get tool schemas for LLM to use with /ask command.

    Args:
        include_pass_through: If True, include pass_through flag in tool defs

    Returns:
        List of tool definitions
    """
    if include_pass_through:
        return TOOLS_REGISTRY
    else:
        # Remove pass_through key from tools for LLM API calls
        return [
            {k: v for k, v in tool.items() if k != "pass_through"}
            for tool in TOOLS_REGISTRY
        ]


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
