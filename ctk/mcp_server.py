#!/usr/bin/env python3
"""CTK MCP Server -- entry point. See ctk/interfaces/mcp/ for implementation."""

import asyncio
import logging
from typing import Optional

# Re-export constants that were previously available at module level
from ctk.core.constants import MAX_ID_LENGTH, MAX_QUERY_LENGTH, MAX_TITLE_LENGTH
from ctk.interfaces.mcp.server import (
    get_db,
    handle_call_tool,
    handle_list_tools,
    main,
    server,
)

# Re-export validation for backward compatibility
from ctk.interfaces.mcp.validation import (
    MAX_LIMIT,
    ValidationError,
    validate_boolean,
    validate_conversation_id,
    validate_integer,
    validate_string,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public helper functions (previously in handlers/conversation.py)
# ---------------------------------------------------------------------------


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
        from ctk.interfaces.mcp.server import get_db as _get_db

        db = _get_db()

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


__all__ = [
    "server",
    "get_db",
    "handle_list_tools",
    "handle_call_tool",
    "main",
    "resolve_conversation_id",
    "format_conversation_for_output",
    "ValidationError",
    "validate_string",
    "validate_boolean",
    "validate_integer",
    "validate_conversation_id",
    "MAX_LIMIT",
    "MAX_ID_LENGTH",
    "MAX_QUERY_LENGTH",
    "MAX_TITLE_LENGTH",
]

if __name__ == "__main__":
    asyncio.run(main())
