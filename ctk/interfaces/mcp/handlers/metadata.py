"""MCP handlers for database metadata operations."""

import logging
from typing import Dict, List

import mcp.types as types

logger = logging.getLogger(__name__)


# --- Tool Definitions ---

TOOLS: List[types.Tool] = [
    types.Tool(
        name="get_statistics",
        description=(
            "Get database statistics: total conversations, messages,"
            " starred/pinned/archived counts, sources, models,"
            " and all tags with usage counts."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]


# --- Handler Functions ---


async def handle_get_statistics(arguments: dict, db) -> list[types.TextContent]:
    """Handle get_statistics tool call."""
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

    tags = db.get_all_tags()
    if tags:
        lines.append("\nTags:")
        for tag_dict in sorted(tags, key=lambda x: -x.get("usage_count", 0)):
            name = tag_dict.get("name", "unknown")
            count = tag_dict.get("usage_count", 0)
            lines.append(f"  {name}: {count}")

    return [types.TextContent(type="text", text="\n".join(lines))]


# --- Handler Dispatch Map ---

HANDLERS: Dict[str, callable] = {
    "get_statistics": handle_get_statistics,
}
