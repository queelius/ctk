"""MCP handlers for conversation operations."""

import logging
from typing import Dict, List, Optional

import mcp.types as types

from ctk.core.constants import MAX_ID_LENGTH, MAX_TITLE_LENGTH
from ctk.interfaces.mcp.validation import validate_boolean, validate_string

logger = logging.getLogger(__name__)


# --- Helper Functions ---


def resolve_conversation_id(partial_id: str, db=None) -> Optional[str]:
    """
    Resolve a partial ID or slug to full conversation ID.

    Uses the database's built-in resolve_identifier method which uses
    database indexes for O(log n) lookups instead of loading all conversations.

    Args:
        partial_id: Full ID, partial ID prefix, or slug
        db: Database instance. If None, uses get_db() from server module.

    Returns:
        Full conversation ID if unique match found, None otherwise
    """
    if not partial_id:
        return None

    if db is None:
        from ctk.interfaces.mcp.server import get_db

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


# --- Tool Definitions ---

TOOLS: List[types.Tool] = [
    types.Tool(
        name="get_conversation",
        description=(
            "Get full content of a specific conversation by ID."
            " Use partial IDs (first 6-8 chars) for convenience."
        ),
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
]


# --- Handler Functions ---


async def handle_get_conversation(arguments: dict, db) -> list[types.TextContent]:
    """Handle get_conversation tool call."""
    # Validate inputs
    conv_id = validate_string(arguments.get("id"), "id", MAX_ID_LENGTH, required=True)
    include_content = validate_boolean(
        arguments.get("include_content"), "include_content"
    )
    if include_content is None:
        include_content = True

    if not conv_id:
        return [
            types.TextContent(type="text", text="Error: conversation ID is required")
        ]

    # Resolve partial ID
    full_id = resolve_conversation_id(conv_id, db=db)
    if not full_id:
        return [
            types.TextContent(
                type="text",
                text=(
                    f"Error: Could not find conversation with ID"
                    f" '{conv_id}'. ID may be ambiguous or not exist."
                ),
            )
        ]

    conv = db.load_conversation(full_id)

    if not conv:
        return [
            types.TextContent(
                type="text", text=f"Error: Conversation '{full_id}' not found."
            )
        ]

    output = format_conversation_for_output(conv, include_content)

    return [types.TextContent(type="text", text=output)]


async def handle_star_conversation(arguments: dict, db) -> list[types.TextContent]:
    """Handle star_conversation tool call."""
    # Validate inputs
    conv_id = validate_string(arguments.get("id"), "id", MAX_ID_LENGTH, required=True)
    starred = validate_boolean(arguments.get("starred"), "starred")
    if starred is None:
        starred = True

    full_id = resolve_conversation_id(conv_id, db=db)
    if not full_id:
        return [
            types.TextContent(
                type="text",
                text=f"Error: Could not find conversation '{conv_id}'",
            )
        ]

    db.star_conversation(full_id, star=starred)
    if starred:
        return [
            types.TextContent(
                type="text", text=f"\u2b50 Starred conversation {full_id[:8]}"
            )
        ]
    else:
        return [
            types.TextContent(type="text", text=f"Unstarred conversation {full_id[:8]}")
        ]


async def handle_pin_conversation(arguments: dict, db) -> list[types.TextContent]:
    """Handle pin_conversation tool call."""
    # Validate inputs
    conv_id = validate_string(arguments.get("id"), "id", MAX_ID_LENGTH, required=True)
    pinned = validate_boolean(arguments.get("pinned"), "pinned")
    if pinned is None:
        pinned = True

    full_id = resolve_conversation_id(conv_id, db=db)
    if not full_id:
        return [
            types.TextContent(
                type="text",
                text=f"Error: Could not find conversation '{conv_id}'",
            )
        ]

    db.pin_conversation(full_id, pin=pinned)
    if pinned:
        return [
            types.TextContent(
                type="text", text=f"\U0001f4cc Pinned conversation {full_id[:8]}"
            )
        ]
    else:
        return [
            types.TextContent(type="text", text=f"Unpinned conversation {full_id[:8]}")
        ]


async def handle_archive_conversation(arguments: dict, db) -> list[types.TextContent]:
    """Handle archive_conversation tool call."""
    # Validate inputs
    conv_id = validate_string(arguments.get("id"), "id", MAX_ID_LENGTH, required=True)
    archived = validate_boolean(arguments.get("archived"), "archived")
    if archived is None:
        archived = True

    full_id = resolve_conversation_id(conv_id, db=db)
    if not full_id:
        return [
            types.TextContent(
                type="text",
                text=f"Error: Could not find conversation '{conv_id}'",
            )
        ]

    db.archive_conversation(full_id, archive=archived)
    if archived:
        return [
            types.TextContent(
                type="text", text=f"\U0001f4e6 Archived conversation {full_id[:8]}"
            )
        ]
    else:
        return [
            types.TextContent(
                type="text", text=f"Unarchived conversation {full_id[:8]}"
            )
        ]


async def handle_set_title(arguments: dict, db) -> list[types.TextContent]:
    """Handle set_title tool call."""
    # Validate inputs
    conv_id = validate_string(arguments.get("id"), "id", MAX_ID_LENGTH, required=True)
    title = validate_string(
        arguments.get("title"), "title", MAX_TITLE_LENGTH, required=True
    )

    if not title:
        return [types.TextContent(type="text", text="Error: title is required")]

    full_id = resolve_conversation_id(conv_id, db=db)
    if not full_id:
        return [
            types.TextContent(
                type="text",
                text=f"Error: Could not find conversation '{conv_id}'",
            )
        ]

    db.update_conversation_metadata(full_id, title=title)

    return [
        types.TextContent(
            type="text", text=f'Updated title for {full_id[:8]}: "{title}"'
        )
    ]


# --- Handler Dispatch Map ---

HANDLERS: Dict[str, callable] = {
    "get_conversation": handle_get_conversation,
    "star_conversation": handle_star_conversation,
    "pin_conversation": handle_pin_conversation,
    "archive_conversation": handle_archive_conversation,
    "set_title": handle_set_title,
}
