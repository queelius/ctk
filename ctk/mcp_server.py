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
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions


# Create server instance
server = Server("ctk")

# Lazy-loaded database connection
_db = None


def get_db():
    """Get or initialize database connection."""
    global _db
    if _db is None:
        import os
        from ctk.core.database import ConversationDB
        from ctk.core.config import get_config

        # Check for environment variable override first
        db_path = os.environ.get('CTK_DATABASE_PATH')

        if not db_path:
            config = get_config()
            db_path = config.get('database.default_path', '~/.ctk/conversations')

        db_path = str(Path(db_path).expanduser())

        # ConversationDB expects directory for SQLite
        if db_path.endswith('.db'):
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
                        "description": "Search text to find in conversation titles and messages"
                    },
                    "starred": {
                        "type": "boolean",
                        "description": "Filter to only starred conversations (optional)"
                    },
                    "pinned": {
                        "type": "boolean",
                        "description": "Filter to only pinned conversations (optional)"
                    },
                    "archived": {
                        "type": "boolean",
                        "description": "Filter to only archived conversations (optional)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (default: 10)",
                        "default": 10
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="list_conversations",
            description="List recent conversations. Returns IDs, titles, dates, and metadata.",
            inputSchema={
                "type": "object",
                "properties": {
                    "starred": {
                        "type": "boolean",
                        "description": "Filter to only starred conversations"
                    },
                    "pinned": {
                        "type": "boolean",
                        "description": "Filter to only pinned conversations"
                    },
                    "archived": {
                        "type": "boolean",
                        "description": "Filter to only archived conversations"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (default: 20)",
                        "default": 20
                    }
                },
                "required": []
            }
        ),
        types.Tool(
            name="get_conversation",
            description="Get full content of a specific conversation by ID. Use partial IDs (first 6-8 chars) for convenience.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Conversation ID (full or partial prefix)"
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "Include full message content (default: true)",
                        "default": True
                    }
                },
                "required": ["id"]
            }
        ),
        types.Tool(
            name="get_statistics",
            description="Get database statistics: total conversations, messages, starred/pinned/archived counts, sources, models.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="star_conversation",
            description="Star or unstar a conversation for quick access.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Conversation ID (full or partial)"
                    },
                    "starred": {
                        "type": "boolean",
                        "description": "True to star, False to unstar"
                    }
                },
                "required": ["id", "starred"]
            }
        ),
        types.Tool(
            name="pin_conversation",
            description="Pin or unpin a conversation to keep it at the top.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Conversation ID (full or partial)"
                    },
                    "pinned": {
                        "type": "boolean",
                        "description": "True to pin, False to unpin"
                    }
                },
                "required": ["id", "pinned"]
            }
        ),
        types.Tool(
            name="archive_conversation",
            description="Archive or unarchive a conversation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Conversation ID (full or partial)"
                    },
                    "archived": {
                        "type": "boolean",
                        "description": "True to archive, False to unarchive"
                    }
                },
                "required": ["id", "archived"]
            }
        ),
        types.Tool(
            name="set_title",
            description="Set or update the title of a conversation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Conversation ID (full or partial)"
                    },
                    "title": {
                        "type": "string",
                        "description": "New title for the conversation"
                    }
                },
                "required": ["id", "title"]
            }
        ),
        types.Tool(
            name="get_tags",
            description="List all tags used in the database with conversation counts.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
    ]


def resolve_conversation_id(partial_id: str) -> Optional[str]:
    """Resolve a partial ID to full conversation ID."""
    db = get_db()

    # Try exact match first
    conv = db.load_conversation(partial_id)
    if conv:
        return partial_id

    # Try prefix match
    all_convs = db.list_conversations(limit=10000)
    matches = [c for c in all_convs if c.id.startswith(partial_id)]

    if len(matches) == 1:
        return matches[0].id
    elif len(matches) > 1:
        return None  # Ambiguous

    return None


def format_conversation_for_output(conv, include_content: bool = True) -> str:
    """Format a conversation for text output."""
    lines = []

    # Header
    title = conv.title or "Untitled"
    lines.append(f"# {title}")
    lines.append(f"ID: {conv.id}")

    if hasattr(conv, 'metadata') and conv.metadata:
        meta = conv.metadata
        if hasattr(meta, 'source') and meta.source:
            lines.append(f"Source: {meta.source}")
        if hasattr(meta, 'model') and meta.model:
            lines.append(f"Model: {meta.model}")

    # Flags
    flags = []
    if hasattr(conv, 'starred_at') and conv.starred_at:
        flags.append("starred")
    if hasattr(conv, 'pinned_at') and conv.pinned_at:
        flags.append("pinned")
    if hasattr(conv, 'archived_at') and conv.archived_at:
        flags.append("archived")
    if flags:
        lines.append(f"Flags: {', '.join(flags)}")

    # Tags
    if hasattr(conv, 'tags') and conv.tags:
        lines.append(f"Tags: {', '.join(conv.tags)}")

    lines.append("")

    # Content
    if include_content:
        if hasattr(conv, 'get_longest_path'):
            path = conv.get_longest_path()
            msg_count = len(conv.message_map) if hasattr(conv, 'message_map') else len(path)
            lines.append(f"Messages: {msg_count}")
            lines.append("")

            for msg in path:
                role = msg.role.value.upper() if hasattr(msg.role, 'value') else str(msg.role).upper()
                lines.append(f"## [{role}]")

                if hasattr(msg.content, 'get_text'):
                    text = msg.content.get_text()
                else:
                    text = str(msg.content) if msg.content else ""

                lines.append(text)
                lines.append("")

    return "\n".join(lines)


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls."""

    try:
        if name == "search_conversations":
            query = arguments.get("query", "")
            starred = arguments.get("starred")
            pinned = arguments.get("pinned")
            archived = arguments.get("archived")
            limit = arguments.get("limit", 10)

            db = get_db()

            # Search
            if query:
                results = db.search_conversations(
                    query_text=query,
                    starred=starred,
                    pinned=pinned,
                    archived=archived,
                    limit=limit
                )
            else:
                results = db.list_conversations(
                    starred=starred,
                    pinned=pinned,
                    archived=archived,
                    limit=limit
                )

            if not results:
                return [types.TextContent(
                    type="text",
                    text="No conversations found matching your criteria."
                )]

            # Format results
            lines = [f"Found {len(results)} conversation(s):\n"]
            for i, conv in enumerate(results, 1):
                title = (conv.title or "Untitled")[:60]
                msg_count = conv.message_count if hasattr(conv, 'message_count') else "?"

                flags = []
                if hasattr(conv, 'starred_at') and conv.starred_at:
                    flags.append("⭐")
                if hasattr(conv, 'pinned_at') and conv.pinned_at:
                    flags.append("📌")
                if hasattr(conv, 'archived_at') and conv.archived_at:
                    flags.append("📦")

                flag_str = "".join(flags) + " " if flags else ""
                lines.append(f"[{i}] {conv.id[:8]} - {flag_str}{title} ({msg_count} msgs)")

            lines.append(f"\nUse get_conversation with ID to view full content.")

            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]

        elif name == "list_conversations":
            starred = arguments.get("starred")
            pinned = arguments.get("pinned")
            archived = arguments.get("archived")
            limit = arguments.get("limit", 20)

            db = get_db()
            results = db.list_conversations(
                starred=starred,
                pinned=pinned,
                archived=archived,
                limit=limit
            )

            if not results:
                return [types.TextContent(
                    type="text",
                    text="No conversations found."
                )]

            lines = [f"Recent conversations ({len(results)}):\n"]
            for i, conv in enumerate(results, 1):
                title = (conv.title or "Untitled")[:50]
                date = ""
                if hasattr(conv, 'created_at') and conv.created_at:
                    date = conv.created_at.strftime("%Y-%m-%d")

                flags = []
                if hasattr(conv, 'starred_at') and conv.starred_at:
                    flags.append("⭐")
                if hasattr(conv, 'pinned_at') and conv.pinned_at:
                    flags.append("📌")
                if hasattr(conv, 'archived_at') and conv.archived_at:
                    flags.append("📦")

                flag_str = "".join(flags) + " " if flags else ""
                lines.append(f"[{i}] {conv.id[:8]} {date} {flag_str}{title}")

            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]

        elif name == "get_conversation":
            conv_id = arguments.get("id", "")
            include_content = arguments.get("include_content", True)

            if not conv_id:
                return [types.TextContent(
                    type="text",
                    text="Error: conversation ID is required"
                )]

            # Resolve partial ID
            full_id = resolve_conversation_id(conv_id)
            if not full_id:
                return [types.TextContent(
                    type="text",
                    text=f"Error: Could not find conversation with ID '{conv_id}'. ID may be ambiguous or not exist."
                )]

            db = get_db()
            conv = db.load_conversation(full_id)

            if not conv:
                return [types.TextContent(
                    type="text",
                    text=f"Error: Conversation '{full_id}' not found."
                )]

            output = format_conversation_for_output(conv, include_content)

            return [types.TextContent(
                type="text",
                text=output
            )]

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

            if stats.get('sources'):
                lines.append(f"\nSources: {', '.join(stats['sources'][:10])}")

            if stats.get('models'):
                lines.append(f"Models: {', '.join(stats['models'][:10])}")

            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]

        elif name == "star_conversation":
            conv_id = arguments.get("id", "")
            starred = arguments.get("starred", True)

            full_id = resolve_conversation_id(conv_id)
            if not full_id:
                return [types.TextContent(
                    type="text",
                    text=f"Error: Could not find conversation '{conv_id}'"
                )]

            db = get_db()
            db.star_conversation(full_id, star=starred)
            if starred:
                return [types.TextContent(type="text", text=f"⭐ Starred conversation {full_id[:8]}")]
            else:
                return [types.TextContent(type="text", text=f"Unstarred conversation {full_id[:8]}")]

        elif name == "pin_conversation":
            conv_id = arguments.get("id", "")
            pinned = arguments.get("pinned", True)

            full_id = resolve_conversation_id(conv_id)
            if not full_id:
                return [types.TextContent(
                    type="text",
                    text=f"Error: Could not find conversation '{conv_id}'"
                )]

            db = get_db()
            db.pin_conversation(full_id, pin=pinned)
            if pinned:
                return [types.TextContent(type="text", text=f"📌 Pinned conversation {full_id[:8]}")]
            else:
                return [types.TextContent(type="text", text=f"Unpinned conversation {full_id[:8]}")]

        elif name == "archive_conversation":
            conv_id = arguments.get("id", "")
            archived = arguments.get("archived", True)

            full_id = resolve_conversation_id(conv_id)
            if not full_id:
                return [types.TextContent(
                    type="text",
                    text=f"Error: Could not find conversation '{conv_id}'"
                )]

            db = get_db()
            db.archive_conversation(full_id, archive=archived)
            if archived:
                return [types.TextContent(type="text", text=f"📦 Archived conversation {full_id[:8]}")]
            else:
                return [types.TextContent(type="text", text=f"Unarchived conversation {full_id[:8]}")]

        elif name == "set_title":
            conv_id = arguments.get("id", "")
            title = arguments.get("title", "")

            if not title:
                return [types.TextContent(
                    type="text",
                    text="Error: title is required"
                )]

            full_id = resolve_conversation_id(conv_id)
            if not full_id:
                return [types.TextContent(
                    type="text",
                    text=f"Error: Could not find conversation '{conv_id}'"
                )]

            db = get_db()
            db.update_conversation_metadata(full_id, title=title)

            return [types.TextContent(
                type="text",
                text=f"Updated title for {full_id[:8]}: \"{title}\""
            )]

        elif name == "get_tags":
            db = get_db()
            tags = db.get_all_tags()

            if not tags:
                return [types.TextContent(
                    type="text",
                    text="No tags found in database."
                )]

            lines = ["Tags in database:\n"]
            # tags is List[Dict] with 'name' and 'usage_count' keys
            for tag_dict in sorted(tags, key=lambda x: -x.get('usage_count', 0)):
                name = tag_dict.get('name', 'unknown')
                count = tag_dict.get('usage_count', 0)
                lines.append(f"  {name}: {count} conversation(s)")

            return [types.TextContent(
                type="text",
                text="\n".join(lines)
            )]

        else:
            return [types.TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]

    except Exception as e:
        import traceback
        return [types.TextContent(
            type="text",
            text=f"Error: {type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}"
        )]


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
