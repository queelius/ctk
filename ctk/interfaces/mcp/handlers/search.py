"""MCP handlers for search and list operations."""

import logging
from typing import Dict, List

import mcp.types as types

from ctk.core.constants import (MAX_QUERY_LENGTH, MAX_RESULT_LIMIT,
                                TITLE_TRUNCATE_WIDTH,
                                TITLE_TRUNCATE_WIDTH_SHORT)
from ctk.interfaces.mcp.validation import (validate_boolean,
                                           validate_integer, validate_string)

logger = logging.getLogger(__name__)

MAX_LIMIT = MAX_RESULT_LIMIT


# --- Tool Definitions ---

TOOLS: List[types.Tool] = [
    types.Tool(
        name="search_conversations",
        description=(
            "Search conversations by text query. Returns matching"
            " conversations with IDs, titles, and message counts."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search text to find in conversation titles and messages",
                },
                "starred": {
                    "type": "boolean",
                    "description": "Filter to only starred conversations (optional)",
                },
                "pinned": {
                    "type": "boolean",
                    "description": "Filter to only pinned conversations (optional)",
                },
                "archived": {
                    "type": "boolean",
                    "description": "Filter to only archived conversations (optional)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 10)",
                    "default": 10,
                },
                "cursor": {
                    "type": "string",
                    "description": (
                        "Pagination cursor from previous"
                        " response's next_cursor."
                    ),
                },
            },
            "required": [],
        },
    ),
    types.Tool(
        name="list_conversations",
        description="List recent conversations. Returns IDs, titles, dates, and metadata.",
        inputSchema={
            "type": "object",
            "properties": {
                "starred": {
                    "type": "boolean",
                    "description": "Filter to only starred conversations",
                },
                "pinned": {
                    "type": "boolean",
                    "description": "Filter to only pinned conversations",
                },
                "archived": {
                    "type": "boolean",
                    "description": "Filter to only archived conversations",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 20)",
                    "default": 20,
                },
                "cursor": {
                    "type": "string",
                    "description": (
                        "Pagination cursor from previous"
                        " response's next_cursor."
                    ),
                },
            },
            "required": [],
        },
    ),
]


# --- Handler Functions ---


async def handle_search_conversations(arguments: dict, db) -> list[types.TextContent]:
    """Handle search_conversations tool call."""
    # Validate inputs
    query = validate_string(arguments.get("query"), "query", MAX_QUERY_LENGTH) or ""
    starred = validate_boolean(arguments.get("starred"), "starred")
    pinned = validate_boolean(arguments.get("pinned"), "pinned")
    archived = validate_boolean(arguments.get("archived"), "archived")
    limit = (
        validate_integer(arguments.get("limit"), "limit", min_val=1, max_val=MAX_LIMIT)
        or 10
    )
    cursor = validate_string(arguments.get("cursor"), "cursor", MAX_QUERY_LENGTH)

    # Build common kwargs
    search_kwargs = {
        "starred": starred,
        "pinned": pinned,
        "archived": archived,
        "limit": limit,
    }
    if cursor is not None:
        search_kwargs["cursor"] = cursor
        search_kwargs["page_size"] = limit

    # Search
    if query:
        search_kwargs["query_text"] = query
        results = db.search_conversations(**search_kwargs)
    else:
        results = db.list_conversations(**search_kwargs)

    # Handle PaginatedResult vs plain list
    from ctk.core.models import PaginatedResult

    if isinstance(results, PaginatedResult):
        items = results.items
        next_cursor = results.next_cursor
        has_more = results.has_more
    else:
        items = results
        next_cursor = None
        has_more = False

    if not items:
        return [
            types.TextContent(
                type="text",
                text="No conversations found matching your criteria.",
            )
        ]

    # Format results
    lines = [f"Found {len(items)} conversation(s):\n"]
    for i, conv in enumerate(items, 1):
        title = (conv.title or "Untitled")[:TITLE_TRUNCATE_WIDTH]
        msg_count = conv.message_count if hasattr(conv, "message_count") else "?"

        flags = []
        if hasattr(conv, "starred_at") and conv.starred_at:
            flags.append("\u2b50")
        if hasattr(conv, "pinned_at") and conv.pinned_at:
            flags.append("\U0001f4cc")
        if hasattr(conv, "archived_at") and conv.archived_at:
            flags.append("\U0001f4e6")

        flag_str = "".join(flags) + " " if flags else ""
        lines.append(f"[{i}] {conv.id[:8]} - {flag_str}{title} ({msg_count} msgs)")

    lines.append("\nUse get_conversation with ID to view full content.")
    if has_more and next_cursor:
        lines.append(f"\nnext_cursor: {next_cursor}")

    return [types.TextContent(type="text", text="\n".join(lines))]


async def handle_list_conversations(arguments: dict, db) -> list[types.TextContent]:
    """Handle list_conversations tool call."""
    # Validate inputs
    starred = validate_boolean(arguments.get("starred"), "starred")
    pinned = validate_boolean(arguments.get("pinned"), "pinned")
    archived = validate_boolean(arguments.get("archived"), "archived")
    limit = (
        validate_integer(arguments.get("limit"), "limit", min_val=1, max_val=MAX_LIMIT)
        or 20
    )
    cursor = validate_string(arguments.get("cursor"), "cursor", MAX_QUERY_LENGTH)

    list_kwargs = {
        "starred": starred,
        "pinned": pinned,
        "archived": archived,
        "limit": limit,
    }
    if cursor is not None:
        list_kwargs["cursor"] = cursor
        list_kwargs["page_size"] = limit

    results = db.list_conversations(**list_kwargs)

    # Handle PaginatedResult vs plain list
    from ctk.core.models import PaginatedResult

    if isinstance(results, PaginatedResult):
        items = results.items
        next_cursor = results.next_cursor
        has_more = results.has_more
    else:
        items = results
        next_cursor = None
        has_more = False

    if not items:
        return [types.TextContent(type="text", text="No conversations found.")]

    lines = [f"Recent conversations ({len(items)}):\n"]
    for i, conv in enumerate(items, 1):
        title = (conv.title or "Untitled")[:TITLE_TRUNCATE_WIDTH_SHORT]
        date = ""
        if hasattr(conv, "created_at") and conv.created_at:
            date = conv.created_at.strftime("%Y-%m-%d")

        flags = []
        if hasattr(conv, "starred_at") and conv.starred_at:
            flags.append("\u2b50")
        if hasattr(conv, "pinned_at") and conv.pinned_at:
            flags.append("\U0001f4cc")
        if hasattr(conv, "archived_at") and conv.archived_at:
            flags.append("\U0001f4e6")

        flag_str = "".join(flags) + " " if flags else ""
        lines.append(f"[{i}] {conv.id[:8]} {date} {flag_str}{title}")

    if has_more and next_cursor:
        lines.append(f"\nnext_cursor: {next_cursor}")

    return [types.TextContent(type="text", text="\n".join(lines))]


# --- Handler Dispatch Map ---

HANDLERS: Dict[str, callable] = {
    "search_conversations": handle_search_conversations,
    "list_conversations": handle_list_conversations,
}
