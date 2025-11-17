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

        title = conv_dict.get('title') or conv_dict.get('title', 'Untitled')
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
    if hasattr(parser, '_subparsers'):
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
            "description": """Search and filter conversations. If query is provided, searches text content. If query is omitted, lists conversations with filters. Multiple filters are combined with AND logic.

IMPORTANT EXAMPLES:
- "search for python in starred conversations" → {"query": "python", "starred": true}
- "find discussions about AI" → {"query": "AI"}
- "show me starred conversations" → {"starred": true} (no query = list)
- "list all conversations" → {} (no filters, no query)
- "show archived conversations" → {"archived": true}

RULE: Only include starred/pinned/archived parameters if the user EXPLICITLY mentions that status. Otherwise omit them entirely.""",
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
            "description": "Get details of a specific conversation by ID",
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
            "description": "Get database statistics (conversation counts, sources, etc.)",
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    ]
