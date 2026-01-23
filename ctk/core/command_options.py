"""
Command options registry for shell completion.

Defines available options for each shell command with:
- name: Option flag (e.g., "-name", "--limit")
- takes_arg: Whether the option expects a value
- desc: Short description for completion display
- enum: Optional list of allowed values (for tab completion)
- type: Expected argument type (str, int, bool)
"""

from typing import Any, Dict, List, Optional

# Command options registry
# Maps command names to their option definitions
COMMAND_OPTIONS: Dict[str, Dict[str, Any]] = {
    "find": {
        "options": [
            {
                "name": "-name",
                "takes_arg": True,
                "desc": "Match conversation title",
                "type": "str",
            },
            {
                "name": "-content",
                "takes_arg": True,
                "desc": "Match message content",
                "type": "str",
            },
            {
                "name": "-role",
                "takes_arg": True,
                "desc": "Match message role",
                "type": "str",
                "enum": ["user", "assistant", "system"],
            },
            {
                "name": "-type",
                "takes_arg": True,
                "desc": "Match entry type",
                "type": "str",
                "enum": ["conversation", "message", "directory"],
            },
            {
                "name": "-i",
                "takes_arg": False,
                "desc": "Case insensitive search",
            },
            {
                "name": "-limit",
                "takes_arg": True,
                "desc": "Maximum results",
                "type": "int",
            },
            {
                "name": "-l",
                "takes_arg": False,
                "desc": "Long format with metadata",
            },
        ],
    },
    "grep": {
        "options": [
            {
                "name": "-i",
                "takes_arg": False,
                "desc": "Case insensitive",
            },
            {
                "name": "-v",
                "takes_arg": False,
                "desc": "Invert match",
            },
            {
                "name": "-c",
                "takes_arg": False,
                "desc": "Count matches",
            },
            {
                "name": "-l",
                "takes_arg": False,
                "desc": "List matching files only",
            },
            {
                "name": "-n",
                "takes_arg": False,
                "desc": "Show line numbers",
            },
        ],
    },
    "ls": {
        "options": [
            {
                "name": "-l",
                "takes_arg": False,
                "desc": "Long format with details",
            },
            {
                "name": "-a",
                "takes_arg": False,
                "desc": "Show all (including archived)",
            },
            {
                "name": "--limit",
                "takes_arg": True,
                "desc": "Maximum results",
                "type": "int",
            },
        ],
    },
    "head": {
        "options": [
            {
                "name": "-n",
                "takes_arg": True,
                "desc": "Number of lines",
                "type": "int",
            },
        ],
    },
    "tail": {
        "options": [
            {
                "name": "-n",
                "takes_arg": True,
                "desc": "Number of lines",
                "type": "int",
            },
        ],
    },
    "tree": {
        "options": [
            {
                "name": "--depth",
                "takes_arg": True,
                "desc": "Maximum tree depth",
                "type": "int",
            },
            {
                "name": "-d",
                "takes_arg": True,
                "desc": "Maximum tree depth",
                "type": "int",
            },
        ],
    },
    "list": {
        "options": [
            {
                "name": "--starred",
                "takes_arg": False,
                "desc": "Show only starred",
            },
            {
                "name": "-s",
                "takes_arg": False,
                "desc": "Show only starred",
            },
            {
                "name": "--pinned",
                "takes_arg": False,
                "desc": "Show only pinned",
            },
            {
                "name": "-p",
                "takes_arg": False,
                "desc": "Show only pinned",
            },
            {
                "name": "--archived",
                "takes_arg": False,
                "desc": "Show only archived",
            },
            {
                "name": "-a",
                "takes_arg": False,
                "desc": "Show only archived",
            },
            {
                "name": "--limit",
                "takes_arg": True,
                "desc": "Maximum results",
                "type": "int",
            },
        ],
    },
    "export": {
        "options": [
            {
                "name": "--format",
                "takes_arg": True,
                "desc": "Export format",
                "type": "str",
                "enum": ["markdown", "json", "jsonl", "html"],
            },
            {
                "name": "-f",
                "takes_arg": True,
                "desc": "Export format",
                "type": "str",
                "enum": ["markdown", "json", "jsonl", "html"],
            },
            {
                "name": "--output",
                "takes_arg": True,
                "desc": "Output file path",
                "type": "str",
            },
            {
                "name": "-o",
                "takes_arg": True,
                "desc": "Output file path",
                "type": "str",
            },
        ],
    },
    "show": {
        "options": [
            {
                "name": "--path",
                "takes_arg": True,
                "desc": "Path selection",
                "type": "str",
                "enum": ["longest", "latest", "0", "1", "2"],
            },
            {
                "name": "-p",
                "takes_arg": True,
                "desc": "Path selection",
                "type": "str",
                "enum": ["longest", "latest", "0", "1", "2"],
            },
            {
                "name": "--no-metadata",
                "takes_arg": False,
                "desc": "Hide metadata",
            },
        ],
    },
    "tag": {
        "options": [
            {
                "name": "--remove",
                "takes_arg": False,
                "desc": "Remove tag instead of add",
            },
            {
                "name": "-r",
                "takes_arg": False,
                "desc": "Remove tag instead of add",
            },
        ],
    },
    "model": {
        "options": [
            {
                "name": "--info",
                "takes_arg": False,
                "desc": "Show detailed model info",
            },
        ],
    },
    "search": {
        "options": [
            {
                "name": "--title",
                "takes_arg": False,
                "desc": "Search titles only",
            },
            {
                "name": "--content",
                "takes_arg": False,
                "desc": "Search content only",
            },
            {
                "name": "--limit",
                "takes_arg": True,
                "desc": "Maximum results",
                "type": "int",
            },
            {
                "name": "--starred",
                "takes_arg": False,
                "desc": "Search starred only",
            },
            {
                "name": "--pinned",
                "takes_arg": False,
                "desc": "Search pinned only",
            },
        ],
    },
    "context": {
        "options": [
            {
                "name": "--as-system",
                "takes_arg": False,
                "desc": "Add as system message",
            },
        ],
    },
    "history": {
        "options": [
            {
                "name": "--max-len",
                "takes_arg": True,
                "desc": "Truncate content length",
                "type": "int",
            },
        ],
    },
    "retry": {
        "options": [
            {
                "name": "--temp",
                "takes_arg": True,
                "desc": "Temperature for retry",
                "type": "float",
            },
        ],
    },
}


def get_command_options(command: str) -> List[Dict[str, Any]]:
    """
    Get options for a command.

    Args:
        command: Command name

    Returns:
        List of option definitions, or empty list if no options
    """
    cmd_info = COMMAND_OPTIONS.get(command)
    if cmd_info:
        return cmd_info.get("options", [])
    return []


def get_option_info(command: str, option: str) -> Optional[Dict[str, Any]]:
    """
    Get info for a specific option.

    Args:
        command: Command name
        option: Option name (e.g., "-name", "--limit")

    Returns:
        Option definition dict, or None if not found
    """
    options = get_command_options(command)
    for opt in options:
        if opt["name"] == option:
            return opt
    return None


def get_option_enum_values(command: str, option: str) -> Optional[List[str]]:
    """
    Get enum values for an option if it has them.

    Args:
        command: Command name
        option: Option name

    Returns:
        List of allowed values, or None if no enum
    """
    opt_info = get_option_info(command, option)
    if opt_info:
        return opt_info.get("enum")
    return None


def has_options(command: str) -> bool:
    """Check if a command has any defined options."""
    return command in COMMAND_OPTIONS
