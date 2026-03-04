"""MCP handler for read-only SQL queries."""

import logging
from typing import Dict, List

import mcp.types as types
from sqlalchemy import text

from ctk.core.constants import MAX_QUERY_LENGTH
from ctk.interfaces.mcp.validation import validate_string

logger = logging.getLogger(__name__)

MAX_SQL_ROWS = 100


# --- Tool Definitions ---

TOOLS: List[types.Tool] = [
    types.Tool(
        name="execute_sql",
        description=(
            "Run a read-only SQL query against the CTK database. Use for"
            " flexible queries not covered by other tools."
            " Tables: conversations (id, title, source, model, starred_at,"
            " pinned_at, archived_at, created_at, updated_at, message_count),"
            " messages (id, conversation_id, role, content, parent_id,"
            " created_at), tags (conversation_id, tag)."
            " Full-text search available via messages_fts table."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL query to execute",
                },
                "params": {
                    "type": "array",
                    "description": "Query parameters for ? placeholders",
                    "items": {},
                },
            },
            "required": ["sql"],
        },
    ),
]


# --- Handler Functions ---


async def handle_execute_sql(arguments: dict, db) -> list[types.TextContent]:
    """Handle execute_sql tool call."""
    sql_query = validate_string(
        arguments.get("sql"), "sql", MAX_QUERY_LENGTH, required=True
    )
    params = arguments.get("params", [])

    if not sql_query:
        return [types.TextContent(type="text", text="Error: sql is required")]

    try:
        with db.engine.connect() as conn:
            conn.execute(text("PRAGMA query_only = ON"))
            if params:
                result = conn.execute(
                    text(sql_query),
                    {f"p{i}": v for i, v in enumerate(params)},
                )
            else:
                result = conn.execute(text(sql_query))

            columns = list(result.keys())
            rows = result.fetchmany(MAX_SQL_ROWS + 1)

            truncated = len(rows) > MAX_SQL_ROWS
            if truncated:
                rows = rows[:MAX_SQL_ROWS]

    except Exception as e:
        error_msg = str(e)
        if "query_only" in error_msg.lower() or "readonly" in error_msg.lower():
            return [
                types.TextContent(
                    type="text",
                    text="Error: Only SELECT queries are allowed (database is read-only).",
                )
            ]
        return [
            types.TextContent(type="text", text=f"SQL error: {error_msg}")
        ]

    if not rows:
        return [types.TextContent(type="text", text="Query returned no results.")]

    # Format as text table
    lines = [" | ".join(columns)]
    lines.append("-|-".join("-" * len(c) for c in columns))
    for row in rows:
        lines.append(" | ".join(str(v) if v is not None else "NULL" for v in row))

    if truncated:
        lines.append(f"\n... truncated to {MAX_SQL_ROWS} rows")

    return [types.TextContent(type="text", text="\n".join(lines))]


# --- Handler Dispatch Map ---

HANDLERS: Dict[str, callable] = {
    "execute_sql": handle_execute_sql,
}
