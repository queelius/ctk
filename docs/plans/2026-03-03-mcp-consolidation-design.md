# MCP Server Consolidation Design

**Date:** 2026-03-03
**Status:** Approved
**Scope:** Consolidate & polish — reduce tool count, improve descriptions, add SQL

## Context

The CTK MCP server has 13 tools across 4 handler modules. The primary consumer is Claude Code via direct MCP integration. The main problem: tool sprawl confuses Claude — too many small, overlapping tools make it hard for the AI to pick the right one.

CTK is in maintenance mode heading toward archival (memex is the successor), so this is a focused polish, not a rewrite.

## Decision: Merge-in-place (13 → 7 tools)

Consolidate related tools, drop heavyweight analysis, add a read-only SQL escape hatch. Keep the handler module structure.

### Removed tools
- `list_conversations` — merged into `search_conversations` (no query = list)
- `star_conversation`, `pin_conversation`, `archive_conversation`, `set_title` — merged into `update_conversation`
- `get_tags` — merged into `get_statistics`
- `get_network_summary` — heavyweight O(n²), available via CLI
- `get_clusters` — heavyweight, requires NetworkX, available via CLI

### Final tool surface

| # | Tool | Handler | Purpose |
|---|------|---------|---------|
| 1 | `search_conversations` | search.py | Search or list conversations with filters + cursor pagination |
| 2 | `get_conversation` | conversation.py | Load full conversation tree by ID (partial prefix OK) |
| 3 | `update_conversation` | conversation.py | Update star/pin/archive/title on a conversation |
| 4 | `get_statistics` | metadata.py | Database overview: counts, sources, models, tags |
| 5 | `find_similar` | analysis.py | Find conversations similar to a given one (embeddings) |
| 6 | `semantic_search` | analysis.py | Search by meaning, not keywords (embeddings) |
| 7 | `execute_sql` | sql.py | Read-only SQL queries against the database |

## Tool Schemas

### 1. `search_conversations`

```
Description: "Search conversations by text query. Returns matching conversations
with IDs, titles, and message counts. If no query is provided, lists recent
conversations. Supports filtering by starred/pinned/archived status and
cursor-based pagination."

Parameters:
  query        (string, optional)    - Search text for titles and messages
  starred      (boolean, optional)   - Filter to starred only
  pinned       (boolean, optional)   - Filter to pinned only
  archived     (boolean, optional)   - Filter to archived only
  limit        (integer, default=20) - Max results (1-100)
  cursor       (string, optional)    - Pagination cursor from previous next_cursor
```

Merges `search_conversations` + `list_conversations`. No query → falls through to `db.list_conversations()`.

### 2. `get_conversation`

```
Description: "Get full content of a specific conversation by ID. Use partial IDs
(first 6-8 chars) for convenience. Returns title, metadata, flags, tags, and
all messages in tree order with role labels."

Parameters:
  id               (string, required)       - Conversation ID (full or partial prefix)
  include_content  (boolean, default=true)  - Include full message content
```

Unchanged from current.

### 3. `update_conversation`

```
Description: "Update conversation properties. Only provided fields are changed.
Use partial IDs (first 6-8 chars) for convenience."

Parameters:
  id       (string, required)   - Conversation ID (full or partial)
  starred  (boolean, optional)  - Star (true) or unstar (false)
  pinned   (boolean, optional)  - Pin (true) or unpin (false)
  archived (boolean, optional)  - Archive (true) or unarchive (false)
  title    (string, optional)   - New title
```

Merges 4 tools. Resolves ID once, applies each provided field, returns summary of changes.

### 4. `get_statistics`

```
Description: "Get database statistics: total conversations, messages,
starred/pinned/archived counts, sources, models, and all tags with usage counts."

Parameters: (none)
```

Merges `get_statistics` + `get_tags`. Calls both `db.get_statistics()` and `db.get_all_tags()`.

### 5. `find_similar`

```
Description: "Find conversations similar to a given conversation using cached
embeddings. Requires embeddings to have been generated first (via ctk net
embeddings). Returns ranked results with similarity scores."

Parameters:
  id        (string, required)               - Conversation ID (full or partial)
  top_k     (integer, default=10, 1-100)     - Number of results
  threshold (number, default=0.1, 0.0-1.0)   - Minimum similarity score
```

Unchanged from current.

### 6. `semantic_search`

```
Description: "Search conversations by meaning using embeddings. Unlike text
search, this finds conceptually similar conversations even without keyword
matches. Requires embeddings to have been generated first (via ctk net embeddings)."

Parameters:
  query  (string, required)             - Natural language query
  top_k  (integer, default=10, 1-100)   - Number of results
```

Unchanged from current.

### 7. `execute_sql`

```
Description: "Run a read-only SQL query against the CTK database. Use for
flexible queries not covered by other tools. Tables: conversations (id, title,
source, model, starred, pinned, archived, created_at, updated_at, message_count),
messages (id, conversation_id, role, content, parent_id, created_at), tags
(conversation_id, tag). Full-text search available via messages_fts table."

Parameters:
  sql    (string, required)   - SQL query to execute
  params (array, optional)    - Query parameters for ? placeholders
```

New tool. Uses `PRAGMA query_only = ON` per-connection for safety. Caps output at ~100 rows.

## Handler Module Changes

```
ctk/interfaces/mcp/handlers/
  __init__.py        # Aggregates ALL_TOOLS + ALL_HANDLERS (7 total)
  search.py          # search_conversations (1 tool, down from 2)
  conversation.py    # get_conversation + update_conversation (2 tools, down from 5)
  metadata.py        # get_statistics (1 tool, down from 2)
  analysis.py        # find_similar + semantic_search (2 tools, down from 4)
  sql.py             # execute_sql (1 tool, new)
```

### Per-file changes

- **search.py**: Delete `handle_list_conversations` and its TOOLS entry. Current `handle_search_conversations` already falls through to list when no query.
- **conversation.py**: Delete `handle_star/pin/archive/set_title`. Add single `handle_update_conversation`.
- **metadata.py**: Fold `get_all_tags()` into `handle_get_statistics`. Delete `handle_get_tags`.
- **analysis.py**: Delete `handle_get_network_summary`, `handle_get_clusters`, and pairwise similarity / NetworkX helpers.
- **sql.py**: New file. Thin handler using SQLAlchemy `text()` with read-only pragma.
- **__init__.py**: Add `sql` to imports.
- **validation.py**: Unchanged.
- **server.py**: Unchanged.

## Test Changes

- Delete tests for removed tools (list_conversations, star/pin/archive/title as separate tools, get_tags, network_summary, clusters)
- Add tests for `update_conversation` (partial updates, multiple fields, ID resolution)
- Add tests for `execute_sql` (SELECT, read-only enforcement, param binding, row cap, error handling)
- Update tool count assertions (13 → 7)
