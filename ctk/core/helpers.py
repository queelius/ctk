"""
Shared helper functions for CLI and TUI
"""

import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from .database import ConversationDB


def format_conversations_table(conversations: List, show_message_count: bool = False, console=None):
    """
    Format conversations as a Rich table.

    Args:
        conversations: List of conversation objects/dicts
        show_message_count: Whether to show message count column
        console: Optional Console instance (creates new one if not provided)
    """
    from rich.console import Console
    from rich.table import Table

    if console is None:
        console = Console()

    # Create table
    table = Table(title=f"[bold cyan]{len(conversations)} conversation(s) found[/bold cyan]",
                 show_header=True, header_style="bold magenta", border_style="cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("ID", style="cyan", width=10)
    table.add_column("Title", style="white", width=50)
    if show_message_count:
        table.add_column("Msgs", style="blue", width=6)
    else:
        table.add_column("Model", style="blue", width=20)
    table.add_column("Updated", style="green", width=20)
    table.add_column("Tags", style="yellow")

    for i, conv in enumerate(conversations, 1):
        # Get dict representation
        conv_dict = conv.to_dict() if hasattr(conv, 'to_dict') else conv

        # Build flags
        flags = ""
        if conv_dict.get('pinned_at'):
            flags += "📌 "
        if conv_dict.get('starred_at'):
            flags += "⭐ "
        if conv_dict.get('archived_at'):
            flags += "📦 "

        title = conv_dict.get('title') or 'Untitled'
        if len(title) > 47:
            title = title[:47] + '...'
        title_with_flags = f"{flags}{title}" if flags else title

        updated = conv_dict.get('updated_at') or 'Unknown'
        if len(updated) > 19:
            updated = updated[:19]

        # Build tags display
        tags_display = ""
        if conv_dict.get('tags'):
            tags_display = ", ".join(conv_dict['tags'][:3])
            if len(conv_dict['tags']) > 3:
                tags_display += f" +{len(conv_dict['tags']) - 3}"

        # Build middle column (msgs or model)
        if show_message_count:
            middle_col = str(conv_dict.get('message_count', 0))
        else:
            model = conv_dict.get('model') or 'Unknown'
            if len(model) > 17:
                model = model[:17] + '...'
            middle_col = model

        table.add_row(
            str(i),
            conv_dict['id'][:8] + "...",
            title_with_flags,
            middle_col,
            updated,
            tags_display
        )

    console.print(table)


def list_conversations_helper(
    db: ConversationDB,
    limit: Optional[int] = None,
    json_output: bool = False,
    archived: bool = False,
    starred: bool = False,
    pinned: bool = False,
    include_archived: bool = False,
    source: Optional[str] = None,
    project: Optional[str] = None,
    model: Optional[str] = None,
    tags: Optional[str] = None
) -> int:
    """
    List conversations with filtering

    Args:
        db: Database instance
        limit: Maximum results
        json_output: Output as JSON
        archived: Show only archived
        starred: Show only starred
        pinned: Show only pinned
        include_archived: Include archived in results
        source: Filter by source
        project: Filter by project
        model: Filter by model
        tags: Comma-separated tags

    Returns:
        0 on success, 1 on error
    """
    # Build filter args
    filter_args = {
        'limit': limit,
        'source': source,
        'project': project,
        'model': model,
        'include_archived': include_archived,
    }

    # Handle tags
    if tags:
        filter_args['tags'] = [t.strip() for t in tags.split(',')]

    # Handle archive/star/pin flags
    if archived:
        filter_args['archived'] = True
    if starred:
        filter_args['starred'] = True
    if pinned:
        filter_args['pinned'] = True

    conversations = db.list_conversations(**filter_args)

    if not conversations:
        print("No conversations found")
        return 0

    # Display format
    if json_output:
        # Convert to dicts
        conv_dicts = [c.to_dict() if hasattr(c, 'to_dict') else c for c in conversations]
        print(json.dumps(conv_dicts, indent=2, default=str))
    else:
        format_conversations_table(conversations, show_message_count=False)

    return 0


def search_conversations_helper(
    db: ConversationDB,
    query: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    title_only: bool = False,
    content_only: bool = False,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    source: Optional[str] = None,
    project: Optional[str] = None,
    model: Optional[str] = None,
    tags: Optional[str] = None,
    min_messages: Optional[int] = None,
    max_messages: Optional[int] = None,
    has_branches: bool = False,
    archived: bool = False,
    starred: bool = False,
    pinned: bool = False,
    include_archived: bool = False,
    order_by: str = 'updated_at',
    ascending: bool = False,
    output_format: str = 'table'
) -> int:
    """
    Search conversations with filtering

    Args:
        db: Database instance
        query: Search query text
        limit: Maximum results
        offset: Skip N results
        title_only: Search only titles
        content_only: Search only content
        date_from: Created after date
        date_to: Created before date
        source: Filter by source
        project: Filter by project
        model: Filter by model
        tags: Comma-separated tags
        min_messages: Minimum message count
        max_messages: Maximum message count
        has_branches: Filter branching conversations
        archived: Show only archived
        starred: Show only starred
        pinned: Show only pinned
        include_archived: Include archived in results
        order_by: Sort field
        ascending: Sort direction
        output_format: 'table', 'json', or 'csv'

    Returns:
        0 on success, 1 on error
    """
    # Parse tags
    tags_list = tags.split(',') if tags else None

    # Build search args
    search_args = {
        'query_text': query,
        'limit': limit,
        'offset': offset,
        'title_only': title_only,
        'content_only': content_only,
        'date_from': date_from,
        'date_to': date_to,
        'source': source,
        'project': project,
        'model': model,
        'tags': tags_list,
        'min_messages': min_messages,
        'max_messages': max_messages,
        'has_branches': has_branches,
        'order_by': order_by,
        'ascending': ascending,
        'include_archived': include_archived,
    }

    # Handle archive/star/pin flags
    if archived:
        search_args['archived'] = True
    if starred:
        search_args['starred'] = True
    if pinned:
        search_args['pinned'] = True

    results = db.search_conversations(**search_args)

    if not results:
        print("No conversations found matching criteria")
        return 0

    # Display results
    if output_format == 'json':
        conv_dicts = [c.to_dict() if hasattr(c, 'to_dict') else c for c in results]
        print(json.dumps(conv_dicts, indent=2, default=str))
    elif output_format == 'csv':
        print("ID,Title,Messages,Source,Model,Created,Updated")
        for conv in results:
            conv_dict = conv.to_dict() if hasattr(conv, 'to_dict') else conv
            print(f"{conv_dict['id']},{conv_dict.get('title', 'Untitled')},{conv_dict.get('message_count', 0)},"
                  f"{conv_dict.get('source', '')},{conv_dict.get('model', '')},"
                  f"{conv_dict.get('created_at', '')},{conv_dict.get('updated_at', '')}")
    else:  # default table format
        format_conversations_table(results, show_message_count=True)

    return 0


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
    if hasattr(parser, '_subparsers') and parser._subparsers is not None:
        for action in parser._subparsers._group_actions:
            if hasattr(action, 'choices'):
                for cmd_name, cmd_parser in action.choices.items():
                    # Skip some commands that don't make sense for ask
                    if cmd_name in ['chat', 'ask']:
                        continue

                    prompt += f"\n**{cmd_name}**: {cmd_parser.description or cmd_parser.format_help().split('\\n')[0]}\n"

                    # Add key arguments
                    args_info = []
                    for arg_action in cmd_parser._actions:
                        if arg_action.dest not in ['help', 'db']:
                            arg_name = '/'.join(arg_action.option_strings) if arg_action.option_strings else arg_action.dest
                            arg_help = arg_action.help or ''
                            args_info.append(f"  - {arg_name}: {arg_help}")

                    if args_info:
                        prompt += '\n'.join(args_info) + '\n'

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
        if cmd_name == 'help':
            continue

        prompt += f"\n**/{cmd_name}**: {help_info.get('desc', '')}\n"
        prompt += f"  Usage: {help_info.get('usage', '')}\n"

        if 'details' in help_info:
            prompt += f"  Details: {help_info['details']}\n"

        if 'examples' in help_info and help_info['examples']:
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


def get_ask_tools() -> List[Dict[str, Any]]:
    """
    Define tool schemas for LLM to use with /ask command.

    Returns:
        List of tool definitions
    """
    return [
        {
            "name": "search_conversations",
            "description": """Search and filter conversations in the database.

DO NOT USE THIS TOOL FOR: greetings (hi, hello), chitchat, general questions.

USE THIS TOOL WHEN user explicitly asks to find/search/list conversations.

IMPORTANT: After showing results, suggest shell commands like `show <id>` or `cd <id>` - NEVER mention this tool's name to users.

EXAMPLES:
- "find conversations about python" → {"query": "python"}
- "show me starred conversations" → {"starred": true}
- "list recent conversations" → {"limit": 10}

RULE: Only include starred/pinned/archived if user explicitly mentions them.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional search query text (searches titles and message content). Omit for listing without search."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return"
                    },
                    "source": {
                        "type": "string",
                        "description": "Filter by source (e.g., 'openai', 'anthropic')"
                    },
                    "project": {
                        "type": "string",
                        "description": "Filter by project name"
                    },
                    "model": {
                        "type": "string",
                        "description": "Filter by model name"
                    },
                    "starred": {
                        "type": "boolean",
                        "description": "Set to true to show ONLY starred conversations. Omit this parameter completely unless user explicitly mentions 'starred'."
                    },
                    "pinned": {
                        "type": "boolean",
                        "description": "Set to true to show ONLY pinned conversations. Omit this parameter completely unless user explicitly mentions 'pinned'."
                    },
                    "archived": {
                        "type": "boolean",
                        "description": "Set to true to show ONLY archived conversations. Omit this parameter completely unless user explicitly mentions 'archived'."
                    },
                    "tags": {
                        "type": "string",
                        "description": "Comma-separated tags to filter by"
                    }
                },
                "required": []
            }
        },
        {
            "name": "get_conversation",
            "description": """Get details of a specific conversation by its ID.

DO NOT USE THIS TOOL FOR: greetings, chitchat, or questions that don't mention a specific conversation ID.

USE THIS TOOL WHEN: user provides a conversation ID and wants details about it.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID"
                    },
                    "show_messages": {
                        "type": "boolean",
                        "description": "Include message content (default: false)"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "get_statistics",
            "description": """Get database statistics (counts, sources, models).

DO NOT USE THIS TOOL FOR: greetings, chitchat, or general questions.

USE THIS TOOL WHEN: user asks "how many conversations", "what are the stats", "show statistics".""",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "execute_shell_command",
            "description": """Execute a CTK shell command (cd, ls, find, cat, tree, star, etc.).

DO NOT USE THIS TOOL FOR: greetings, chitchat, or general questions.

USE THIS TOOL WHEN: user wants to navigate (cd, ls), view content (cat, tree), or organize (star, pin, archive).

Commands: cd, ls, pwd, find, cat, tree, paths, star, unstar, pin, unpin, archive, unarchive, title, show""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute (e.g., 'ls /starred', 'find -name python')"
                    }
                },
                "required": ["command"]
            }
        },
        {
            "name": "star_conversation",
            "description": """Star a conversation to mark it as important.

USE THIS TOOL WHEN: user says "star this", "mark as important", "favorite this conversation".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID to star"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "unstar_conversation",
            "description": """Remove star from a conversation.

USE THIS TOOL WHEN: user says "unstar this", "remove from favorites".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID to unstar"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "pin_conversation",
            "description": """Pin a conversation to keep it at the top.

USE THIS TOOL WHEN: user says "pin this", "keep at top".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID to pin"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "unpin_conversation",
            "description": """Remove pin from a conversation.

USE THIS TOOL WHEN: user says "unpin this".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID to unpin"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "archive_conversation",
            "description": """Archive a conversation to hide it from default listings.

USE THIS TOOL WHEN: user says "archive this", "hide this conversation".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID to archive"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "unarchive_conversation",
            "description": """Unarchive a conversation to make it visible again.

USE THIS TOOL WHEN: user says "unarchive this", "restore this conversation".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID to unarchive"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "rename_conversation",
            "description": """Rename a conversation by setting its title.

USE THIS TOOL WHEN: user says "rename this to...", "change title to...", "call this...".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID to rename"
                    },
                    "title": {
                        "type": "string",
                        "description": "New title for the conversation"
                    }
                },
                "required": ["conversation_id", "title"]
            }
        },
        {
            "name": "show_conversation_content",
            "description": """Show the full content of a conversation.

USE THIS TOOL WHEN: user says "show me the conversation", "display the chat", "what was said in...".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID to show"
                    },
                    "path_selection": {
                        "type": "string",
                        "description": "Which path to show: 'longest' (default), 'latest', or a path number like '0', '1'"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "show_conversation_tree",
            "description": """Show the tree structure of a conversation (useful for branching conversations).

USE THIS TOOL WHEN: user says "show the tree", "show branches", "conversation structure".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "delete_conversation",
            "description": """Delete a conversation from the database. This is IRREVERSIBLE.

USE THIS TOOL WHEN: user explicitly says "delete this conversation", "remove this chat".

IMPORTANT: Ask for confirmation before deleting.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID to delete"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "tag_conversation",
            "description": """Add tags to a conversation for categorization.

USE THIS TOOL WHEN: user says "tag this as...", "add tag...", "categorize as...".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to add to the conversation"
                    }
                },
                "required": ["conversation_id", "tags"]
            }
        },
        {
            "name": "list_tags",
            "description": """List all tags in the database with counts.

USE THIS TOOL WHEN: user says "show all tags", "what tags exist", "list tags".""",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "remove_tag",
            "description": """Remove a tag from a conversation.

USE THIS TOOL WHEN: user says "remove tag", "untag", "delete tag from...".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID"
                    },
                    "tag": {
                        "type": "string",
                        "description": "Tag to remove"
                    }
                },
                "required": ["conversation_id", "tag"]
            }
        },
        {
            "name": "list_sources",
            "description": """List all conversation sources (openai, anthropic, etc.) with counts.

USE THIS TOOL WHEN: user says "what sources", "show sources", "where are conversations from".""",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "list_models",
            "description": """List all models used in conversations with counts.

USE THIS TOOL WHEN: user says "what models", "show models", "which models were used".""",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "export_conversation",
            "description": """Export a conversation to a specific format.

USE THIS TOOL WHEN: user says "export to markdown", "save as json", "export conversation".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json", "jsonl"],
                        "description": "Export format (default: markdown)"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "duplicate_conversation",
            "description": """Create a copy of a conversation with a new ID.

USE THIS TOOL WHEN: user says "duplicate", "copy conversation", "clone this".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or partial conversation ID to duplicate"
                    },
                    "new_title": {
                        "type": "string",
                        "description": "Optional title for the copy"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "get_recent_conversations",
            "description": """Get the N most recently updated conversations.

USE THIS TOOL WHEN: user says "recent conversations", "latest chats", "what did I work on recently".""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of conversations to return (default: 10)"
                    }
                },
                "required": []
            }
        },
        {
            "name": "list_conversations",
            "description": """List conversations with optional filters.

USE THIS TOOL WHEN: user asks to "list conversations", "show all chats", "list starred", "show pinned", "what's archived".

Returns a formatted table of conversations matching the criteria.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "starred": {
                        "type": "boolean",
                        "description": "Filter to starred conversations only"
                    },
                    "pinned": {
                        "type": "boolean",
                        "description": "Filter to pinned conversations only"
                    },
                    "archived": {
                        "type": "boolean",
                        "description": "Filter to archived conversations only"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20)"
                    },
                    "source": {
                        "type": "string",
                        "description": "Filter by source (e.g., 'anthropic', 'openai')"
                    },
                    "model": {
                        "type": "string",
                        "description": "Filter by model name"
                    }
                },
                "required": []
            }
        },
        {
            "name": "list_conversation_paths",
            "description": """List all paths in a branching conversation tree.

USE THIS TOOL WHEN: user asks "show paths", "list branches", "how many paths", "conversation branches".

Returns all distinct paths from root to leaf in the conversation tree.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or prefix of conversation ID"
                    }
                },
                "required": ["conversation_id"]
            }
        },
        {
            "name": "list_plugins",
            "description": """List available importer and exporter plugins.

USE THIS TOOL WHEN: user asks "what plugins", "list importers", "list exporters", "supported formats".""",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "auto_tag_conversation",
            "description": """Automatically tag a conversation using LLM analysis.

USE THIS TOOL WHEN: user says "auto-tag", "suggest tags", "analyze and tag".

Uses LLM to analyze conversation content and suggest relevant tags.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "Full or prefix of conversation ID"
                    }
                },
                "required": ["conversation_id"]
            }
        }
    ]


def get_ctk_system_prompt(db: 'ConversationDB', current_path: str = "/") -> str:
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
        total_convs = stats.get('total_conversations', 0)
        total_msgs = stats.get('total_messages', 0)

        # Get counts for starred, pinned, archived
        starred_count = len(db.list_conversations(starred=True, limit=None))
        pinned_count = len(db.list_conversations(pinned=True, limit=None))
        archived_count = len(db.list_conversations(archived=True, limit=None))

        # Get top sources
        sources = stats.get('by_source', {})
        source_summary = ", ".join(f"{k}: {v}" for k, v in list(sources.items())[:3]) if sources else "none"

    except Exception:
        total_convs = 0
        total_msgs = 0
        starred_count = 0
        pinned_count = 0
        archived_count = 0
        source_summary = "unknown"

    prompt = f"""You are an assistant within CTK (Conversation Toolkit), a tool for managing and exploring conversation data from various LLM providers.

## Current Context
- VFS Path: {current_path}
- Database: {total_convs} conversations, {total_msgs} messages
- Starred: {starred_count} | Pinned: {pinned_count} | Archived: {archived_count}
- Sources: {source_summary}

## CRITICAL RULES

### Rule 1: NEVER mention tool names to users
When suggesting actions, tell users to type SHELL COMMANDS, not tool function names.
- WRONG: "You can use execute_shell_command('ls /starred')"
- CORRECT: "You can type `ls /starred` to see starred conversations"
- WRONG: "Use the search_conversations tool"
- CORRECT: "Try searching with `find -content 'python' -l`"

### Rule 2: NO TOOLS for greetings or chitchat
For "hi", "hello", "hey", "thanks", etc. → Just respond conversationally. NO TOOL CALLS.

### Rule 3: Use tools ONLY for explicit data requests
USE TOOLS when user explicitly asks to:
- Search/find/list conversations → search_conversations
- View a specific conversation → show_conversation_content or get_conversation
- Star/pin/archive something → star_conversation, pin_conversation, etc.
- Get statistics → get_statistics

## Shell Commands Users Can Type
Tell users about these commands (they type them directly, you don't):
- `ls /starred` or `ls /pinned` - List filtered conversations
- `find -name "pattern"` - Find by title
- `find -content "text" -l` - Find by content (shows table)
- `show <id>` - View conversation content
- `cd <id>` - Navigate to conversation
- `tree` - Show conversation structure
- `star`, `pin`, `archive` - Organize conversations
- `help` - Full command reference

## Example Responses

User: "hi"
Response: "Hello! I'm here to help you explore your {total_convs} conversations. What would you like to find?"
(NO TOOL CALLS)

User: "find conversations about python"
Action: Call search_conversations with query="python"
Response: [show results] "To view any of these, type `show <id>` or `cd <id>` to explore it."

User: "show me starred"
Action: Call search_conversations with starred=true
Response: [show results] "Type `show <id>` to view any conversation."

User: "what commands are there?"
Response: "Type `help` at the prompt for a full command reference. Key commands include `find`, `show`, `ls`, `cd`, `star`, `pin`, and `archive`." """

    return prompt


def get_ctk_system_prompt_no_tools(db: 'ConversationDB', current_path: str = "/") -> str:
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
        total_convs = stats.get('total_conversations', 0)
        total_msgs = stats.get('total_messages', 0)

        # Get counts for starred, pinned, archived
        starred_count = len(db.list_conversations(starred=True, limit=None))
        pinned_count = len(db.list_conversations(pinned=True, limit=None))

        # Get top sources
        sources = stats.get('by_source', {})
        source_summary = ", ".join(f"{k}: {v}" for k, v in list(sources.items())[:3]) if sources else "none"

    except Exception:
        total_convs = 0
        total_msgs = 0
        starred_count = 0
        pinned_count = 0
        source_summary = "unknown"

    prompt = f"""You are an assistant within CTK (Conversation Toolkit), a CLI tool for managing and exploring conversation data from various LLM providers.

## Current Database
- {total_convs} conversations, {total_msgs} messages
- Starred: {starred_count} | Pinned: {pinned_count}
- Sources: {source_summary}

## Shell Commands Reference
Navigation:
- `cd /chats` - Go to conversations list
- `cd /starred` or `cd /pinned` or `cd /archived` - Go to filtered views
- `cd <id>` - Navigate to conversation (supports prefix matching like `cd abc12`)
- `ls` - List current directory
- `pwd` - Show current path

Search:
- `find -name "pattern"` - Find conversations by title (* and ? wildcards)
- `find -content "text"` - Find by message content
- `find -l` - Show results as table with metadata
- `find /starred -content "python" -l` - Combined search

View:
- `cat text` - View message content (when in a message node)
- `tree` - Show conversation tree structure
- `paths` - List all conversation paths

Organize:
- `star` / `unstar` - Star/unstar current conversation
- `pin` / `unpin` - Pin/unpin current conversation
- `archive` / `unarchive` - Archive/unarchive
- `title "New Title"` - Rename conversation

Chat:
- `say <message>` - Send message to LLM
- `chat` - Enter interactive chat mode
- `help` - Full command reference

## How to Help
Guide users to use shell commands directly. Be accurate with command syntax - don't invent flags that don't exist."""

    return prompt


def show_conversation_helper(
    db: ConversationDB,
    conv_id: str,
    path_selection: str = 'longest',
    plain_output: bool = True,
    show_metadata: bool = True,
    render_markdown: bool = False
) -> Dict[str, Any]:
    """
    Load and format a conversation for display.

    This is a shared helper used by both CLI `ctk show` and shell `show` commands.

    Args:
        db: Database instance
        conv_id: Conversation ID or prefix
        path_selection: 'longest', 'latest', or path number as string
        plain_output: If True, return plain text; if False, return Rich-formatted
        show_metadata: Include metadata in output
        render_markdown: Render markdown in messages (for Rich output)

    Returns:
        Dict with keys:
            'success': bool
            'conversation': ConversationTree if found
            'output': formatted string output
            'error': error message if failed
    """
    from ctk.core.tree import ConversationTreeNavigator

    # Load conversation (with prefix matching)
    conversation = db.load_conversation(conv_id)

    if not conversation:
        # Try partial ID match
        all_convs = db.list_conversations(limit=None, include_archived=True)
        matches = [c for c in all_convs if c.id.startswith(conv_id)]

        if len(matches) == 0:
            return {
                'success': False,
                'conversation': None,
                'output': '',
                'error': f"No conversation found matching '{conv_id}'"
            }
        elif len(matches) > 1:
            match_list = "\n".join(f"  {m.id[:12]}... {m.title}" for m in matches[:5])
            return {
                'success': False,
                'conversation': None,
                'output': '',
                'error': f"Multiple conversations match '{conv_id}':\n{match_list}"
            }
        else:
            conversation = db.load_conversation(matches[0].id)

    if not conversation:
        return {
            'success': False,
            'conversation': None,
            'output': '',
            'error': f"Failed to load conversation: {conv_id}"
        }

    # Create navigator
    nav = ConversationTreeNavigator(conversation)
    path_count = nav.get_path_count()

    # Select path
    if path_selection == 'longest':
        path = nav.get_longest_path()
    elif path_selection == 'latest':
        path = nav.get_latest_path()
    elif path_selection.isdigit():
        path_num = int(path_selection)
        path = nav.get_path(path_num)
        if not path:
            return {
                'success': False,
                'conversation': conversation,
                'output': '',
                'error': f"Path {path_num} not found (available: 0-{path_count-1})"
            }
    else:
        path = nav.get_longest_path()

    # Build output
    output_lines = []

    if show_metadata:
        output_lines.append(f"\nConversation: {conversation.title or '(untitled)'}")
        output_lines.append(f"ID: {conversation.id}")
        if conversation.metadata:
            if conversation.metadata.source:
                output_lines.append(f"Source: {conversation.metadata.source}")
            if conversation.metadata.model:
                output_lines.append(f"Model: {conversation.metadata.model}")
            if conversation.metadata.created_at:
                output_lines.append(f"Created: {conversation.metadata.created_at}")
            if conversation.metadata.tags:
                output_lines.append(f"Tags: {', '.join(conversation.metadata.tags)}")
        output_lines.append(f"Total messages: {len(conversation.message_map)}")
        output_lines.append(f"Paths: {path_count}")
        output_lines.append("")

    if not path:
        output_lines.append("(no messages)")
    else:
        output_lines.append(f"Messages (path: {path_selection}, {len(path)} messages):")
        output_lines.append("=" * 80)

        for msg in path:
            role_label = msg.role.value.title() if msg.role else "User"
            content_text = msg.content.get_text() if hasattr(msg.content, 'get_text') else str(msg.content)
            output_lines.append(f"\n[{role_label}]")
            output_lines.append(content_text)

        output_lines.append("=" * 80)

    if path_count > 1:
        output_lines.append(f"\nNote: This conversation has {path_count} paths")
        output_lines.append("Use --path N or -L for different path views")

    return {
        'success': True,
        'conversation': conversation,
        'navigator': nav,
        'path': path,
        'path_count': path_count,
        'output': '\n'.join(output_lines) + '\n',
        'error': ''
    }
