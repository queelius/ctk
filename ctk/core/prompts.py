"""
System prompt generators for LLM interactions.

Contains functions that generate context-aware system prompts for:
- CLI commands (argparse-based)
- TUI commands (help-dict based)
- CTK shell mode (with and without tools)
"""

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from .database import ConversationDB


def generate_cli_prompt_from_argparse(parser) -> str:
    """
    Generate a system prompt for LLM from argparse subparsers.

    Args:
        parser: The main ArgumentParser with subparsers

    Returns:
        System prompt describing available CTK operations
    """
    prompt = """You are a helpful assistant for CTK (Conversation Toolkit), a tool for managing and analyzing conversation data.

The user will ask questions or request operations in natural language. Your job is to understand their intent and call the appropriate tool functions to fulfill their request.

Available CTK Operations:

"""

    # Extract subparser information
    if hasattr(parser, "_subparsers") and parser._subparsers is not None:
        for action in parser._subparsers._group_actions:
            if hasattr(action, "choices"):
                for cmd_name, cmd_parser in action.choices.items():
                    # Skip some commands that don't make sense for ask
                    if cmd_name in ["chat", "ask"]:
                        continue

                    prompt += f"\n**{cmd_name}**: {cmd_parser.description or cmd_parser.format_help().split('\\n')[0]}\n"

                    # Add key arguments
                    args_info = []
                    for arg_action in cmd_parser._actions:
                        if arg_action.dest not in ["help", "db"]:
                            arg_name = (
                                "/".join(arg_action.option_strings)
                                if arg_action.option_strings
                                else arg_action.dest
                            )
                            arg_help = arg_action.help or ""
                            args_info.append(f"  - {arg_name}: {arg_help}")

                    if args_info:
                        prompt += "\n".join(args_info) + "\n"

    prompt += """

When the user asks a question:
1. Determine which operation(s) would best answer their request
2. Call the appropriate tool function(s) with the right parameters
3. Present the results in a clear, helpful way

Be concise and focus on what the user asked for."""

    return prompt


def generate_tui_prompt_from_help(command_help: Dict[str, Dict[str, Any]]) -> str:
    """
    Generate a system prompt for LLM from TUI COMMAND_HELP dictionary.

    Args:
        command_help: Dictionary mapping command names to help info

    Returns:
        System prompt describing available TUI commands
    """
    prompt = """You are a helpful assistant within the CTK chat TUI (Text User Interface).

The user will ask questions or request operations in natural language. Your job is to understand their intent and call the appropriate tool functions to execute TUI commands.

Available TUI Commands:

"""

    for cmd_name, help_info in command_help.items():
        # Skip help command itself
        if cmd_name == "help":
            continue

        prompt += f"\n**/{cmd_name}**: {help_info.get('desc', '')}\n"
        prompt += f"  Usage: {help_info.get('usage', '')}\n"

        if "details" in help_info:
            prompt += f"  Details: {help_info['details']}\n"

        if "examples" in help_info and help_info["examples"]:
            prompt += f"  Examples: {', '.join(help_info['examples'][:2])}\n"

    prompt += """

When the user asks a question:
1. Determine which command(s) would best fulfill their request
2. Call the appropriate tool function(s) with the right parameters
3. Present the results in a clear, helpful way

Important notes:
- The user is currently in an interactive chat session
- Commands like /load, /save, /tag affect the currently loaded conversation
- Use /search or /list to find conversations
- Be concise and focus on what the user asked for"""

    return prompt


def get_ctk_system_prompt(db: "ConversationDB", current_path: str = "/") -> str:
    """
    Generate a context-aware system prompt for CTK shell mode.

    Args:
        db: Database instance to get stats from
        current_path: Current VFS path

    Returns:
        System prompt string
    """
    # Get database stats
    try:
        stats = db.get_statistics()
        total_convs = stats.get("total_conversations", 0)
        total_msgs = stats.get("total_messages", 0)

        # Get counts for starred, pinned, archived
        starred_count = len(db.list_conversations(starred=True, limit=None))
        pinned_count = len(db.list_conversations(pinned=True, limit=None))
        archived_count = len(db.list_conversations(archived=True, limit=None))

        # Get top sources
        sources = stats.get("by_source", {})
        source_summary = (
            ", ".join(f"{k}: {v}" for k, v in list(sources.items())[:3])
            if sources
            else "none"
        )

    except Exception:
        total_convs = 0
        total_msgs = 0
        starred_count = 0
        pinned_count = 0
        archived_count = 0
        source_summary = "unknown"

    prompt = f"""You help users explore their conversation history.

Database: {total_convs} conversations, {total_msgs} messages ({starred_count} starred, {pinned_count} pinned)
Location: {current_path}

Tools:
- search_conversations: Search by query or filter
- get_conversation: View a conversation by ID
- get_statistics: Database stats

Search results are numbered [1], [2], etc. When user says "show 1" or "open 2", use the ID from that numbered result with get_conversation.

USE TOOLS for data queries. Never fabricate data."""

    return prompt


def get_ctk_system_prompt_no_tools(
    db: "ConversationDB", current_path: str = "/"
) -> str:
    """
    Generate a simpler system prompt for CTK when tools are disabled.

    Args:
        db: Database instance to get stats from
        current_path: Current VFS path

    Returns:
        System prompt string (no tool instructions)
    """
    # Get database stats
    try:
        stats = db.get_statistics()
        total_convs = stats.get("total_conversations", 0)
        total_msgs = stats.get("total_messages", 0)

        # Get counts for starred, pinned, archived
        starred_count = len(db.list_conversations(starred=True, limit=None))
        pinned_count = len(db.list_conversations(pinned=True, limit=None))

        # Get top sources
        sources = stats.get("by_source", {})
        source_summary = (
            ", ".join(f"{k}: {v}" for k, v in list(sources.items())[:3])
            if sources
            else "none"
        )

    except Exception:
        total_convs = 0
        total_msgs = 0
        starred_count = 0
        pinned_count = 0
        source_summary = "unknown"

    prompt = f"""You help users explore their conversation history in CTK.

Database: {total_convs} conversations, {total_msgs} messages
Location: {current_path}

You cannot search or view conversations directly. Guide users to type shell commands:
- `find -content "topic"` to search
- `show <id>` to view a conversation
- `ls /starred` to list starred items
- `cd <id>` to navigate into a conversation
- `help` for all commands

Never make up conversation IDs or content - you don't have access to the data."""

    return prompt
