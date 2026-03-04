# MCP Server Consolidation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Consolidate 13 MCP tools down to 7 by merging related tools, dropping heavyweight analysis, and adding a read-only SQL escape hatch.

**Architecture:** Keep the handler-module pattern. Merge `list_conversations` into `search_conversations`, merge star/pin/archive/title into `update_conversation`, merge tags into statistics, drop network/clusters, add `execute_sql` in new `sql.py` handler.

**Tech Stack:** Python, MCP SDK (`mcp.types`, `mcp.server`), SQLAlchemy `text()` for SQL handler.

---

### Task 1: Remove `list_conversations` tool (merge into `search_conversations`)

**Files:**
- Modify: `ctk/interfaces/mcp/handlers/search.py`

**Step 1: Update the search tool description and default limit**

In `ctk/interfaces/mcp/handlers/search.py`, replace the entire `TOOLS` list and delete `handle_list_conversations`:

```python
TOOLS: List[types.Tool] = [
    types.Tool(
        name="search_conversations",
        description=(
            "Search conversations by text query. Returns matching conversations"
            " with IDs, titles, and message counts. If no query is provided,"
            " lists recent conversations. Supports filtering by"
            " starred/pinned/archived status and cursor-based pagination."
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
```

**Step 2: Update `handle_search_conversations` default limit from 10 to 20**

Change line 113:
```python
    limit = (
        validate_integer(arguments.get("limit"), "limit", min_val=1, max_val=MAX_LIMIT)
        or 20
    )
```

**Step 3: Delete `handle_list_conversations` function entirely (lines 178-238)**

**Step 4: Update HANDLERS dict to remove `list_conversations`**

```python
HANDLERS: Dict[str, callable] = {
    "search_conversations": handle_search_conversations,
}
```

**Step 5: Remove unused import `TITLE_TRUNCATE_WIDTH_SHORT`**

It's only used by the deleted `handle_list_conversations`.

**Step 6: Run tests to verify**

Run: `pytest tests/unit/test_mcp_server.py -v -x -k "search" 2>&1 | head -30`

**Step 7: Commit**

```
feat(mcp): merge list_conversations into search_conversations

search_conversations now lists recent conversations when called without
a query parameter. Default limit changed from 10 to 20.
```

---

### Task 2: Replace star/pin/archive/title tools with `update_conversation`

**Files:**
- Modify: `ctk/interfaces/mcp/handlers/conversation.py`

**Step 1: Replace the 4 individual tool definitions with one `update_conversation` tool**

Replace the `star_conversation`, `pin_conversation`, `archive_conversation`, and `set_title` entries in the `TOOLS` list with:

```python
    types.Tool(
        name="update_conversation",
        description=(
            "Update conversation properties. Only provided fields are changed."
            " Use partial IDs (first 6-8 chars) for convenience."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Conversation ID (full or partial)",
                },
                "starred": {
                    "type": "boolean",
                    "description": "Star (true) or unstar (false)",
                },
                "pinned": {
                    "type": "boolean",
                    "description": "Pin (true) or unpin (false)",
                },
                "archived": {
                    "type": "boolean",
                    "description": "Archive (true) or unarchive (false)",
                },
                "title": {
                    "type": "string",
                    "description": "New title for the conversation",
                },
            },
            "required": ["id"],
        },
    ),
```

**Step 2: Write the `handle_update_conversation` function**

Add after `handle_get_conversation`:

```python
async def handle_update_conversation(arguments: dict, db) -> list[types.TextContent]:
    """Handle update_conversation tool call."""
    conv_id = validate_string(arguments.get("id"), "id", MAX_ID_LENGTH, required=True)
    starred = validate_boolean(arguments.get("starred"), "starred")
    pinned = validate_boolean(arguments.get("pinned"), "pinned")
    archived = validate_boolean(arguments.get("archived"), "archived")
    title = validate_string(arguments.get("title"), "title", MAX_TITLE_LENGTH)

    if not conv_id:
        return [types.TextContent(type="text", text="Error: conversation ID is required")]

    full_id = resolve_conversation_id(conv_id, db=db)
    if not full_id:
        return [
            types.TextContent(
                type="text",
                text=f"Error: Could not find conversation '{conv_id}'",
            )
        ]

    changes = []

    if starred is not None:
        db.star_conversation(full_id, star=starred)
        changes.append(f"{'Starred' if starred else 'Unstarred'}")

    if pinned is not None:
        db.pin_conversation(full_id, pin=pinned)
        changes.append(f"{'Pinned' if pinned else 'Unpinned'}")

    if archived is not None:
        db.archive_conversation(full_id, archive=archived)
        changes.append(f"{'Archived' if archived else 'Unarchived'}")

    if title is not None:
        db.update_conversation_metadata(full_id, title=title)
        changes.append(f'Title set to "{title}"')

    if not changes:
        return [
            types.TextContent(
                type="text",
                text=f"No changes specified for {full_id[:8]}.",
            )
        ]

    return [
        types.TextContent(
            type="text",
            text=f"Updated {full_id[:8]}: {', '.join(changes)}",
        )
    ]
```

**Step 3: Delete the 4 old handler functions**

Delete `handle_star_conversation`, `handle_pin_conversation`, `handle_archive_conversation`, `handle_set_title`.

**Step 4: Update HANDLERS dict**

```python
HANDLERS: Dict[str, callable] = {
    "get_conversation": handle_get_conversation,
    "update_conversation": handle_update_conversation,
}
```

**Step 5: Run tests**

Run: `pytest tests/unit/test_mcp_server.py -v -x -k "conversation" 2>&1 | head -30`

**Step 6: Commit**

```
feat(mcp): consolidate star/pin/archive/title into update_conversation

Single tool with optional fields replaces 4 separate tools. Only
provided fields are changed. Returns summary of all changes made.
```

---

### Task 3: Merge `get_tags` into `get_statistics`

**Files:**
- Modify: `ctk/interfaces/mcp/handlers/metadata.py`

**Step 1: Update tool description to include tags**

```python
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
```

**Step 2: Add tags to `handle_get_statistics`**

After the existing sources/models lines, add:

```python
    tags = db.get_all_tags()
    if tags:
        lines.append("\nTags:")
        for tag_dict in sorted(tags, key=lambda x: -x.get("usage_count", 0)):
            name = tag_dict.get("name", "unknown")
            count = tag_dict.get("usage_count", 0)
            lines.append(f"  {name}: {count}")
```

**Step 3: Delete `handle_get_tags` function and its TOOLS/HANDLERS entries**

**Step 4: Update HANDLERS dict**

```python
HANDLERS: Dict[str, callable] = {
    "get_statistics": handle_get_statistics,
}
```

**Step 5: Run tests**

Run: `pytest tests/unit/test_mcp_server.py -v -x -k "statistic or tag" 2>&1 | head -30`

**Step 6: Commit**

```
feat(mcp): merge get_tags into get_statistics

Statistics now includes all tags with usage counts. Reduces tool count
by one without losing any capability.
```

---

### Task 4: Remove `get_network_summary` and `get_clusters` from analysis

**Files:**
- Modify: `ctk/interfaces/mcp/handlers/analysis.py`

**Step 1: Remove the two tool definitions from TOOLS list**

Keep only `find_similar` and `semantic_search` in the TOOLS list.

**Step 2: Delete handler functions**

Delete `handle_get_network_summary` and `handle_get_clusters`.

**Step 3: Delete helper functions only used by removed tools**

Delete `_compute_pairwise_similarities`.

**Step 4: Remove unused imports**

Remove `MAX_PAIRWISE_CONVERSATIONS` constant. The `numpy` import stays (used by `find_similar` and `semantic_search`).

**Step 5: Update HANDLERS dict**

```python
HANDLERS: Dict[str, callable] = {
    "find_similar": handle_find_similar,
    "semantic_search": handle_semantic_search,
}
```

**Step 6: Run tests**

Run: `pytest tests/unit/test_mcp_analysis.py -v -x 2>&1 | head -40`

**Step 7: Commit**

```
feat(mcp): remove network_summary and clusters tools

Heavyweight O(n²) analysis tools removed from MCP. Still available
via CLI (ctk net network, ctk net clusters).
```

---

### Task 5: Create `execute_sql` handler

**Files:**
- Create: `ctk/interfaces/mcp/handlers/sql.py`
- Modify: `ctk/interfaces/mcp/handlers/__init__.py`

**Step 1: Create `ctk/interfaces/mcp/handlers/sql.py`**

```python
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
    sql = validate_string(
        arguments.get("sql"), "sql", MAX_QUERY_LENGTH, required=True
    )
    params = arguments.get("params", [])

    if not sql:
        return [types.TextContent(type="text", text="Error: sql is required")]

    try:
        with db.engine.connect() as conn:
            conn.execute(text("PRAGMA query_only = ON"))
            if params:
                result = conn.execute(text(sql), {f"p{i}": v for i, v in enumerate(params)})
            else:
                result = conn.execute(text(sql))

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
```

**Step 2: Update `__init__.py` to include sql module**

Replace `ctk/interfaces/mcp/handlers/__init__.py`:

```python
"""MCP handler modules for CTK tools."""

from ctk.interfaces.mcp.handlers import (analysis, conversation, metadata,
                                         search, sql)

# Collect all tools from handler modules
ALL_TOOLS = (
    search.TOOLS + conversation.TOOLS + metadata.TOOLS
    + analysis.TOOLS + sql.TOOLS
)

# Collect all handlers from handler modules
ALL_HANDLERS = {}
ALL_HANDLERS.update(search.HANDLERS)
ALL_HANDLERS.update(conversation.HANDLERS)
ALL_HANDLERS.update(metadata.HANDLERS)
ALL_HANDLERS.update(analysis.HANDLERS)
ALL_HANDLERS.update(sql.HANDLERS)
```

**Step 3: Run basic smoke test**

Run: `python -c "from ctk.interfaces.mcp.handlers import ALL_TOOLS, ALL_HANDLERS; print(f'{len(ALL_TOOLS)} tools, {len(ALL_HANDLERS)} handlers'); print([t.name for t in ALL_TOOLS])"`

Expected: `7 tools, 7 handlers` and the correct 7 tool names.

**Step 4: Commit**

```
feat(mcp): add execute_sql tool for read-only SQL queries

New handler in sql.py. Uses PRAGMA query_only = ON for safety.
Results formatted as text table, capped at 100 rows.
```

---

### Task 6: Update tests

**Files:**
- Modify: `tests/unit/test_mcp_server.py`
- Modify: `tests/unit/test_mcp_analysis.py`

**Step 1: Update `test_list_tools_returns_expected_tools`**

Replace the expected tools set:

```python
        expected_tools = {
            "search_conversations",
            "get_conversation",
            "update_conversation",
            "get_statistics",
            "find_similar",
            "semantic_search",
            "execute_sql",
        }
```

**Step 2: Delete test for removed `list_conversations` tool**

Delete `test_list_conversations_returns_results` (line 106-118).

**Step 3: Update `test_get_tags_returns_list` to test tags in statistics**

Replace:
```python
    def test_get_statistics_includes_tags(self, event_loop):
        """Test get_statistics includes tag information."""
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(handle_call_tool("get_statistics", {}))

        assert len(result) == 1
        text = result[0].text

        assert "CTK Database Statistics" in text
        # Tags are now included in statistics
        assert "Tags" in text or "Total conversations" in text
```

**Step 4: Update `test_get_conversation_with_valid_id` to use `search_conversations` instead of `list_conversations`**

Change the line that calls `list_conversations` to call `search_conversations` with `{"limit": 1}`.

**Step 5: Add test for `update_conversation`**

```python
    def test_update_conversation_no_changes(self, event_loop):
        """Test update_conversation with no fields specified."""
        from ctk.mcp_server import handle_call_tool

        # First get a conversation ID
        list_result = event_loop.run_until_complete(
            handle_call_tool("search_conversations", {"limit": 1})
        )
        list_text = list_result[0].text

        if "[1]" in list_text:
            import re
            match = re.search(r"\[1\]\s+([a-f0-9]+)", list_text)
            if match:
                partial_id = match.group(1)[:8]
                result = event_loop.run_until_complete(
                    handle_call_tool("update_conversation", {"id": partial_id})
                )
                text = result[0].text
                assert "No changes" in text
```

**Step 6: Add test for `execute_sql`**

```python
    def test_execute_sql_select(self, event_loop):
        """Test execute_sql with a SELECT query."""
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(
            handle_call_tool(
                "execute_sql",
                {"sql": "SELECT COUNT(*) as cnt FROM conversations"},
            )
        )

        assert len(result) == 1
        text = result[0].text
        assert "cnt" in text

    def test_execute_sql_invalid_query(self, event_loop):
        """Test execute_sql with invalid SQL."""
        from ctk.mcp_server import handle_call_tool

        result = event_loop.run_until_complete(
            handle_call_tool("execute_sql", {"sql": "INVALID SQL"})
        )

        text = result[0].text
        assert "error" in text.lower() or "Error" in text
```

**Step 7: In `test_mcp_analysis.py`, remove tests referencing `get_network_summary` and `get_clusters` tools**

Search for any test classes/methods that reference these tool names and delete them.

**Step 8: Run full test suite**

Run: `pytest tests/unit/test_mcp_server.py tests/unit/test_mcp_analysis.py tests/unit/test_mcp_validation.py -v 2>&1 | tail -20`

**Step 9: Commit**

```
test(mcp): update tests for 7-tool consolidated MCP server

Update expected tool list, remove tests for deleted tools, add tests
for update_conversation and execute_sql.
```

---

### Task 7: Update backward-compat re-exports in `ctk/mcp_server.py`

**Files:**
- Modify: `ctk/mcp_server.py`

**Step 1: Check current re-exports**

Read `ctk/mcp_server.py` and update any re-exports that reference removed handlers (e.g., `handle_list_conversations`, `handle_star_conversation`, etc.). Add re-export for new `handle_update_conversation` and `handle_execute_sql`.

**Step 2: Run import test**

Run: `python -c "from ctk.mcp_server import handle_list_tools, handle_call_tool; print('OK')"`

**Step 3: Commit**

```
chore(mcp): update backward-compat re-exports in mcp_server.py
```

---

### Task 8: Update CLAUDE.md MCP documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update the MCP Server line**

Change "13 tools total" to "7 tools total" in the MCP Server description.

**Step 2: Run full test suite to confirm nothing is broken**

Run: `pytest tests/unit/test_mcp_server.py tests/unit/test_mcp_analysis.py tests/unit/test_mcp_validation.py -v`

**Step 3: Commit**

```
docs: update CLAUDE.md for 7-tool MCP server
```
