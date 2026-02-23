"""
CTK MCP Server — core server with tool registration and dispatch.

Collects tool definitions and handlers from handler modules, registers them
with the MCP Server, and implements dispatch.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from ctk.interfaces.mcp.handlers import ALL_HANDLERS, ALL_TOOLS
from ctk.interfaces.mcp.validation import ValidationError

logger = logging.getLogger(__name__)

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


def _resolve_get_db():
    """Resolve get_db, supporting monkey-patching on ctk.mcp_server.

    Tests may patch ctk.mcp_server.get_db (the backward-compatible entry
    point). This helper checks there first so those patches take effect,
    then falls back to this module's own get_db.
    """
    entry = sys.modules.get("ctk.mcp_server")
    if entry is not None and hasattr(entry, "get_db"):
        return entry.get_db()
    return get_db()


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available CTK tools."""
    return ALL_TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Handle tool calls with input validation."""

    try:
        handler = ALL_HANDLERS.get(name)
        if handler is None:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

        db = _resolve_get_db()
        return await handler(arguments, db)

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
