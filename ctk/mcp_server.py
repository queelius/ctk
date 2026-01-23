#!/usr/bin/env python3
"""
CTK MCP Server - Exposes conversation database operations via MCP protocol.

This allows Claude Code and other MCP clients to directly:
- Search conversations
- View conversation content
- Get database statistics
- Organize conversations (star/pin/archive)

Usage:
    # Add to Claude Code MCP config (~/.claude.json):
    {
        "mcpServers": {
            "ctk": {
                "command": "python",
                "args": ["-m", "ctk.mcp_server"],
                "cwd": "/path/to/ctk"
            }
        }
    }

    # Or run standalone:
    python -m ctk.mcp_server

Security note: All tool inputs are validated before processing to prevent
DoS attacks and injection vulnerabilities.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

logger = logging.getLogger(__name__)


# Input validation constants
MAX_QUERY_LENGTH = 10000  # Maximum length for search queries
MAX_TITLE_LENGTH = 1000  # Maximum length for conversation titles
MAX_ID_LENGTH = 200  # Maximum length for conversation IDs
MAX_LIMIT = 10000  # Maximum limit for result counts


class ValidationError(Exception):
    """Raised when input validation fails"""

    pass


def validate_string(
    value: Any, name: str, max_length: int, required: bool = False
) -> Optional[str]:
    """
    Validate a string parameter.

    Args:
        value: Value to validate
        name: Parameter name for error messages
        max_length: Maximum allowed length
        required: Whether the parameter is required

    Returns:
        Validated string or None

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        if required:
            raise ValidationError(f"'{name}' is required")
        return None

    if not isinstance(value, str):
        raise ValidationError(f"'{name}' must be a string, got {type(value).__name__}")

    if len(value) > max_length:
        raise ValidationError(
            f"'{name}' exceeds maximum length ({len(value)} > {max_length})"
        )

    return value


def validate_boolean(value: Any, name: str) -> Optional[bool]:
    """
    Validate a boolean parameter.

    Args:
        value: Value to validate
        name: Parameter name for error messages

    Returns:
        Validated boolean or None

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        if value.lower() in ("true", "1", "yes"):
            return True
        if value.lower() in ("false", "0", "no"):
            return False

    raise ValidationError(f"'{name}' must be a boolean, got {type(value).__name__}")


def validate_integer(
    value: Any, name: str, min_val: int = 0, max_val: int = MAX_LIMIT
) -> Optional[int]:
    """
    Validate an integer parameter.

    Args:
        value: Value to validate
        name: Parameter name for error messages
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Validated integer or None

    Raises:
        ValidationError: If validation fails
    """
    if value is None:
        return None

    if isinstance(value, bool):
        raise ValidationError(f"'{name}' must be an integer, got boolean")

    if isinstance(value, int):
        if value < min_val:
            raise ValidationError(f"'{name}' must be >= {min_val}, got {value}")
        if value > max_val:
            raise ValidationError(f"'{name}' must be <= {max_val}, got {value}")
        return value

    if isinstance(value, str):
        try:
            int_val = int(value)
            if int_val < min_val or int_val > max_val:
                raise ValidationError(
                    f"'{name}' must be between {min_val} and {max_val}"
                )
            return int_val
        except ValueError:
            pass

    raise ValidationError(f"'{name}' must be an integer, got {type(value).__name__}")


def validate_conversation_id(value: Any, name: str = "id") -> str:
    """
    Validate a conversation ID.

    Args:
        value: Value to validate
        name: Parameter name for error messages

    Returns:
        Validated ID string

    Raises:
        ValidationError: If validation fails
    """
    validated = validate_string(value, name, MAX_ID_LENGTH, required=True)
    if not validated:
        raise ValidationError(f"'{name}' is required")

    # IDs should only contain alphanumeric, dashes, and underscores
    import re

    if not re.match(r"^[a-zA-Z0-9_-]+$", validated):
        raise ValidationError(f"'{name}' contains invalid characters")

    return validated


# Create server instance
server = Server("ctk")

# Lazy-loaded database connection
_db = None


def get_db():
    """Get or initialize database connection."""
    global _db
    if _db is None:
        import os

        from ctk.core.config import get_config
        from ctk.core.database import ConversationDB

        # Check for environment variable override first
        db_path = os.environ.get("CTK_DATABASE_PATH")

        if not db_path:
            config = get_config()
            db_path = config.get("database.default_path", "~/.ctk/conversations")

        db_path = str(Path(db_path).expanduser())

        # ConversationDB expects directory for SQLite
        if db_path.endswith(".db"):
            db_path = str(Path(db_path).parent)

        _db = ConversationDB(db_path)
    return _db


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available CTK tools."""
    return [
        types.Tool(
            name="search_conversations",
            description="Search conversations by text query. Returns matching conversations with IDs, titles, and message counts.",
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
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_conversation",
            description="Get full content of a specific conversation by ID. Use partial IDs (first 6-8 chars) for convenience.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Conversation ID (full or partial prefix)",
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "Include full message content (default: true)",
                        "default": True,
                    },
                },
                "required": ["id"],
            },
        ),
        types.Tool(
            name="get_statistics",
            description="Get database statistics: total conversations, messages, starred/pinned/archived counts, sources, models.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="star_conversation",
            description="Star or unstar a conversation for quick access.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Conversation ID (full or partial)",
                    },
                    "starred": {
                        "type": "boolean",
                        "description": "True to star, False to unstar",
                    },
                },
                "required": ["id", "starred"],
            },
        ),
        types.Tool(
            name="pin_conversation",
            description="Pin or unpin a conversation to keep it at the top.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Conversation ID (full or partial)",
                    },
                    "pinned": {
                        "type": "boolean",
                        "description": "True to pin, False to unpin",
                    },
                },
                "required": ["id", "pinned"],
            },
        ),
        types.Tool(
            name="archive_conversation",
            description="Archive or unarchive a conversation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Conversation ID (full or partial)",
                    },
                    "archived": {
                        "type": "boolean",
                        "description": "True to archive, False to unarchive",
                    },
                },
                "required": ["id", "archived"],
            },
        ),
        types.Tool(
            name="set_title",
            description="Set or update the title of a conversation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Conversation ID (full or partial)",
                    },
                    "title": {
                        "type": "string",
                        "description": "New title for the conversation",
                    },
                },
                "required": ["id", "title"],
            },
        ),
        types.Tool(
            name="get_tags",
            description="List all tags used in the database with conversation counts.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
    ]


def resolve_conversation_id(partial_id: str) -> Optional[str]:
    """
    Resolve a partial ID or slug to full conversation ID.

    Uses the database's built-in resolve_identifier method which uses
    database indexes for O(log n) lookups instead of loading all conversations.

    Args:
        partial_id: Full ID, partial ID prefix, or slug

    Returns:
        Full conversation ID if unique match found, None otherwise
    """
    if not partial_id:
        return None

    db = get_db()

    # Use database's efficient resolution method (uses indexes)
    # This handles: exact slug, exact ID, slug prefix, and ID prefix
    result = db.resolve_identifier(partial_id)
    if result:
        return result[0]  # Returns (id, slug) tuple

    # resolve_identifier already checks exact ID match, so no need
    # for expensive load_conversation fallback
    return None


def format_conversation_for_output(conv, include_content: bool = True) -> str:
    """Format a conversation for text output."""
    lines = []

    # Header
    title = conv.title or "Untitled"
    lines.append(f"# {title}")
    lines.append(f"ID: {conv.id}")

    if hasattr(conv, "metadata") and conv.metadata:
        meta = conv.metadata
        if hasattr(meta, "source") and meta.source:
            lines.append(f"Source: {meta.source}")
        if hasattr(meta, "model") and meta.model:
            lines.append(f"Model: {meta.model}")

    # Flags
    flags = []
    if hasattr(conv, "starred_at") and conv.starred_at:
        flags.append("starred")
    if hasattr(conv, "pinned_at") and conv.pinned_at:
        flags.append("pinned")
    if hasattr(conv, "archived_at") and conv.archived_at:
        flags.append("archived")
    if flags:
        lines.append(f"Flags: {', '.join(flags)}")

    # Tags
    if hasattr(conv, "tags") and conv.tags:
        lines.append(f"Tags: {', '.join(conv.tags)}")

    lines.append("")

    # Content
    if include_content:
        if hasattr(conv, "get_longest_path"):
            path = conv.get_longest_path()
            msg_count = (
                len(conv.message_map) if hasattr(conv, "message_map") else len(path)
            )
            lines.append(f"Messages: {msg_count}")
            lines.append("")

            for msg in path:
                role = (
                    msg.role.value.upper()
                    if hasattr(msg.role, "value")
                    else str(msg.role).upper()
                )
                lines.append(f"## [{role}]")

                if hasattr(msg.content, "get_text"):
                    text = msg.content.get_text()
                else:
                    text = str(msg.content) if msg.content else ""

                lines.append(text)
                lines.append("")

    return "\n".join(lines)


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls with input validation."""

    try:
        if name == "search_conversations":
            # Validate inputs
            query = (
                validate_string(arguments.get("query"), "query", MAX_QUERY_LENGTH) or ""
            )
            starred = validate_boolean(arguments.get("starred"), "starred")
            pinned = validate_boolean(arguments.get("pinned"), "pinned")
            archived = validate_boolean(arguments.get("archived"), "archived")
            limit = (
                validate_integer(
                    arguments.get("limit"), "limit", min_val=1, max_val=MAX_LIMIT
                )
                or 10
            )

            db = get_db()

            # Search
            if query:
                results = db.search_conversations(
                    query_text=query,
                    starred=starred,
                    pinned=pinned,
                    archived=archived,
                    limit=limit,
                )
            else:
                results = db.list_conversations(
                    starred=starred, pinned=pinned, archived=archived, limit=limit
                )

            if not results:
                return [
                    types.TextContent(
                        type="text",
                        text="No conversations found matching your criteria.",
                    )
                ]

            # Format results
            lines = [f"Found {len(results)} conversation(s):\n"]
            for i, conv in enumerate(results, 1):
                title = (conv.title or "Untitled")[:60]
                msg_count = (
                    conv.message_count if hasattr(conv, "message_count") else "?"
                )

                flags = []
                if hasattr(conv, "starred_at") and conv.starred_at:
                    flags.append("⭐")
                if hasattr(conv, "pinned_at") and conv.pinned_at:
                    flags.append("📌")
                if hasattr(conv, "archived_at") and conv.archived_at:
                    flags.append("📦")

                flag_str = "".join(flags) + " " if flags else ""
                lines.append(
                    f"[{i}] {conv.id[:8]} - {flag_str}{title} ({msg_count} msgs)"
                )

            lines.append(f"\nUse get_conversation with ID to view full content.")

            return [types.TextContent(type="text", text="\n".join(lines))]

        elif name == "list_conversations":
            # Validate inputs
            starred = validate_boolean(arguments.get("starred"), "starred")
            pinned = validate_boolean(arguments.get("pinned"), "pinned")
            archived = validate_boolean(arguments.get("archived"), "archived")
            limit = (
                validate_integer(
                    arguments.get("limit"), "limit", min_val=1, max_val=MAX_LIMIT
                )
                or 20
            )

            db = get_db()
            results = db.list_conversations(
                starred=starred, pinned=pinned, archived=archived, limit=limit
            )

            if not results:
                return [types.TextContent(type="text", text="No conversations found.")]

            lines = [f"Recent conversations ({len(results)}):\n"]
            for i, conv in enumerate(results, 1):
                title = (conv.title or "Untitled")[:50]
                date = ""
                if hasattr(conv, "created_at") and conv.created_at:
                    date = conv.created_at.strftime("%Y-%m-%d")

                flags = []
                if hasattr(conv, "starred_at") and conv.starred_at:
                    flags.append("⭐")
                if hasattr(conv, "pinned_at") and conv.pinned_at:
                    flags.append("📌")
                if hasattr(conv, "archived_at") and conv.archived_at:
                    flags.append("📦")

                flag_str = "".join(flags) + " " if flags else ""
                lines.append(f"[{i}] {conv.id[:8]} {date} {flag_str}{title}")

            return [types.TextContent(type="text", text="\n".join(lines))]

        elif name == "get_conversation":
            # Validate inputs
            conv_id = validate_string(
                arguments.get("id"), "id", MAX_ID_LENGTH, required=True
            )
            include_content = validate_boolean(
                arguments.get("include_content"), "include_content"
            )
            if include_content is None:
                include_content = True

            if not conv_id:
                return [
                    types.TextContent(
                        type="text", text="Error: conversation ID is required"
                    )
                ]

            # Resolve partial ID
            full_id = resolve_conversation_id(conv_id)
            if not full_id:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error: Could not find conversation with ID '{conv_id}'. ID may be ambiguous or not exist.",
                    )
                ]

            db = get_db()
            conv = db.load_conversation(full_id)

            if not conv:
                return [
                    types.TextContent(
                        type="text", text=f"Error: Conversation '{full_id}' not found."
                    )
                ]

            output = format_conversation_for_output(conv, include_content)

            return [types.TextContent(type="text", text=output)]

        elif name == "get_statistics":
            db = get_db()
            stats = db.get_statistics()

            lines = [
                "CTK Database Statistics",
                "=" * 40,
                f"Total conversations: {stats.get('total_conversations', 0)}",
                f"Total messages: {stats.get('total_messages', 0)}",
                f"Starred: {stats.get('starred_count', 0)}",
                f"Pinned: {stats.get('pinned_count', 0)}",
                f"Archived: {stats.get('archived_count', 0)}",
            ]

            if stats.get("sources"):
                lines.append(f"\nSources: {', '.join(stats['sources'][:10])}")

            if stats.get("models"):
                lines.append(f"Models: {', '.join(stats['models'][:10])}")

            return [types.TextContent(type="text", text="\n".join(lines))]

        elif name == "star_conversation":
            # Validate inputs
            conv_id = validate_string(
                arguments.get("id"), "id", MAX_ID_LENGTH, required=True
            )
            starred = validate_boolean(arguments.get("starred"), "starred")
            if starred is None:
                starred = True

            full_id = resolve_conversation_id(conv_id)
            if not full_id:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error: Could not find conversation '{conv_id}'",
                    )
                ]

            db = get_db()
            db.star_conversation(full_id, star=starred)
            if starred:
                return [
                    types.TextContent(
                        type="text", text=f"⭐ Starred conversation {full_id[:8]}"
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text", text=f"Unstarred conversation {full_id[:8]}"
                    )
                ]

        elif name == "pin_conversation":
            # Validate inputs
            conv_id = validate_string(
                arguments.get("id"), "id", MAX_ID_LENGTH, required=True
            )
            pinned = validate_boolean(arguments.get("pinned"), "pinned")
            if pinned is None:
                pinned = True

            full_id = resolve_conversation_id(conv_id)
            if not full_id:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error: Could not find conversation '{conv_id}'",
                    )
                ]

            db = get_db()
            db.pin_conversation(full_id, pin=pinned)
            if pinned:
                return [
                    types.TextContent(
                        type="text", text=f"📌 Pinned conversation {full_id[:8]}"
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text", text=f"Unpinned conversation {full_id[:8]}"
                    )
                ]

        elif name == "archive_conversation":
            # Validate inputs
            conv_id = validate_string(
                arguments.get("id"), "id", MAX_ID_LENGTH, required=True
            )
            archived = validate_boolean(arguments.get("archived"), "archived")
            if archived is None:
                archived = True

            full_id = resolve_conversation_id(conv_id)
            if not full_id:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error: Could not find conversation '{conv_id}'",
                    )
                ]

            db = get_db()
            db.archive_conversation(full_id, archive=archived)
            if archived:
                return [
                    types.TextContent(
                        type="text", text=f"📦 Archived conversation {full_id[:8]}"
                    )
                ]
            else:
                return [
                    types.TextContent(
                        type="text", text=f"Unarchived conversation {full_id[:8]}"
                    )
                ]

        elif name == "set_title":
            # Validate inputs
            conv_id = validate_string(
                arguments.get("id"), "id", MAX_ID_LENGTH, required=True
            )
            title = validate_string(
                arguments.get("title"), "title", MAX_TITLE_LENGTH, required=True
            )

            if not title:
                return [types.TextContent(type="text", text="Error: title is required")]

            full_id = resolve_conversation_id(conv_id)
            if not full_id:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error: Could not find conversation '{conv_id}'",
                    )
                ]

            db = get_db()
            db.update_conversation_metadata(full_id, title=title)

            return [
                types.TextContent(
                    type="text", text=f'Updated title for {full_id[:8]}: "{title}"'
                )
            ]

        elif name == "get_tags":
            db = get_db()
            tags = db.get_all_tags()

            if not tags:
                return [
                    types.TextContent(type="text", text="No tags found in database.")
                ]

            lines = ["Tags in database:\n"]
            # tags is List[Dict] with 'name' and 'usage_count' keys
            for tag_dict in sorted(tags, key=lambda x: -x.get("usage_count", 0)):
                name = tag_dict.get("name", "unknown")
                count = tag_dict.get("usage_count", 0)
                lines.append(f"  {name}: {count} conversation(s)")

            return [types.TextContent(type="text", text="\n".join(lines))]

        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    except ValidationError as e:
        # Return validation errors without traceback (they're expected)
        return [types.TextContent(type="text", text=f"Validation error: {str(e)}")]
    except Exception as e:
        # Log unexpected errors but don't expose full traceback to client
        import traceback

        logger.error(
            f"MCP tool error: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        )
        return [
            types.TextContent(type="text", text=f"Error: {type(e).__name__}: {str(e)}")
        ]


async def main():
    """Run the MCP server."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="ctk",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
