# C2 Tool Surface Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the registry (`ctk.builtin` + `ctk.network`) the single source of truth for every tool surface: the MCP server projects from it, the two MCP-only tools fold into it, `update_conversation` becomes the canonical mutation, and the unused REST/web surface is removed.

**Architecture:** Fold the MCP-only tools (`execute_sql`, `semantic_search`) and reconcile `find_similar` into the registry; add a canonical `update_conversation` tool with the 7 verb tools as thin wrappers; replace the 5 hand-written MCP handler modules with a generic `projection.py` that generates `types.Tool` from the registry and dispatches through `execute_builtin_tool`/`execute_network_tool` (with a one-release alias map); fix `_format_message` to round-trip assistant `tool_calls`; delete `ctk/interfaces/rest/` and `ctk/interfaces/web/`.

**Tech Stack:** Python 3.12, the `mcp` SDK, SQLAlchemy, pytest. Spec: `docs/plans/2026-06-21-c2-tool-surface-unification-design.md`.

## Global Constraints

- BEHAVIOR-PRESERVING where stated: verbatim ports (execute_sql, semantic_search) keep their exact friendly-error strings INSIDE the handler (the registry dispatcher's generic except would otherwise mask them). The 7 verb wrappers keep their EXACT existing return strings and per-verb guards.
- A repo write hook BLOCKS any file containing an em-dash character or the word spelled l-e-v-e-r-a-g-e. Plain hyphens only, including docstrings/test strings.
- No bare `except:`; name exception types. (The MCP `call_tool` broad `except Exception` and the registry dispatcher's broad `except Exception` are pre-existing and intentional.)
- The C1 golden test `tests/unit/test_tools_golden.py` snapshots the `ctk.builtin` provider's `{name, description, input_schema}` view as a hardcoded sha256 (`_EXPECTED_DIGEST`) plus `_EXPECTED_NAMES`. Adding `execute_sql` (Task 1) and `update_conversation` (Task 5) to `ctk.builtin` changes it BY DESIGN: update `_EXPECTED_NAMES` and recompute `_EXPECTED_DIGEST` in the SAME commit as each tool addition, using the recompute one-liner in the test header. `semantic_search`/`find_similar` are `ctk.network` and do NOT affect that digest.
- Green gate before each commit: `python -m pytest <touched test files> -q -o addopts=""` pass; full `python -m pytest tests/unit -q` once per task; `python -m black <touched files>`; `python -m flake8 <touched files> --max-line-length=100 --ignore=E203,W503` clean on new lines; `python -m mypy ctk --ignore-missing-imports` 0 errors.

---

## Task 1: Fold `execute_sql` into `ctk.builtin`

**Files:** Modify `ctk/core/builtin_tools.py`; Test `tests/unit/test_builtin_execute_sql.py`; Modify `tests/unit/test_tools_golden.py` (digest).

**Interfaces:** Produces a `ctk.builtin` tool `execute_sql` reachable via `execute_builtin_tool(db, "execute_sql", {"sql": ...})`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_builtin_execute_sql.py
import pytest
from ctk.core.database import ConversationDB
from ctk.core.builtin_tools import execute_builtin_tool

pytestmark = pytest.mark.unit


def test_select_returns_table(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        out = execute_builtin_tool(db, "execute_sql", {"sql": "SELECT 1 AS one"})
        assert "one" in out and "1" in out and not out.startswith("Error")
    finally:
        db.close()


def test_write_is_read_only_rejected(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        out = execute_builtin_tool(
            db, "execute_sql",
            {"sql": "CREATE TABLE x (a INTEGER)"},
        )
        # read-only DB rejects writes with a friendly message, not a raw stack
        assert "read" in out.lower() or "only" in out.lower() or "Error" in out
    finally:
        db.close()


def test_missing_sql_errors(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        assert execute_builtin_tool(db, "execute_sql", {}).startswith("Error")
    finally:
        db.close()
```

- [ ] **Step 2: Run to verify it fails**: `python -m pytest tests/unit/test_builtin_execute_sql.py -q -o addopts=""` -> FAIL (`Unknown tool: execute_sql`).

- [ ] **Step 3: Implement.** Read `ctk/interfaces/mcp/handlers/sql.py` (`handle_execute_sql`, the schema, MAX_SQL_ROWS). Add `_do_execute_sql(ctx: ToolContext) -> ToolResult` to `builtin_tools.py` porting that body EXACTLY: `sql = ctx.args.get("sql")` with empty-guard returning `ToolResult.message("Error: sql is required")`; `params = ctx.args.get("params", [])`; `with ctx.db.engine.connect() as conn: conn.execute(text("PRAGMA query_only = ON"))` (import `text` from sqlalchemy locally); named `:pN` binds; `fetchmany(MAX_SQL_ROWS + 1)` then truncate to MAX_SQL_ROWS with a footer; keep the query-only/read-only friendly-error branch INSIDE the handler (catch the specific SQLAlchemy error type sql.py catches); the `col | col` text table; "Query returned no results." empty case. Return `ToolResult(text=table, data={"columns": [...], "rows": [...]})`. Append `BuiltinTool(name="execute_sql", description=<copied verbatim from sql.py>, input_schema=<copied verbatim from sql.py>, handler=_do_execute_sql, pass_through=True)` to `_BUILTIN_TOOLS`. Import MAX_SQL_ROWS/MAX_QUERY_LENGTH from `ctk.core.constants` (match sql.py).

- [ ] **Step 4: Update the C1 golden.** In `tests/unit/test_tools_golden.py`, add `"execute_sql"` to `_EXPECTED_NAMES` (keep sorted) and recompute `_EXPECTED_DIGEST` via the header one-liner. Run `python -m pytest tests/unit/test_tools_golden.py tests/unit/test_builtin_execute_sql.py -q -o addopts=""` -> PASS.

- [ ] **Step 5: Green gate + commit.** Full `tests/unit`; black/flake8/mypy. Commit: `feat(tools): fold execute_sql into the ctk.builtin registry`.

---

## Task 2: Fold `semantic_search` into `ctk.network`

**Files:** Modify `ctk/core/network_tools.py`; Test `tests/unit/test_network_semantic_search.py`.

**Interfaces:** Produces a `ctk.network` tool `semantic_search` reachable via `execute_network_tool(db, "semantic_search", {"query": ...})`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_network_semantic_search.py
import pytest
from ctk.core.database import ConversationDB
from ctk.core.network_tools import execute_network_tool

pytestmark = pytest.mark.unit


def test_no_embeddings_friendly_message(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        out = execute_network_tool(db, "semantic_search", {"query": "python"})
        # no embeddings built yet -> a friendly hint, not a stack trace
        assert "embedding" in out.lower() and not out.startswith("Traceback")
    finally:
        db.close()
```

- [ ] **Step 2: Run to verify it fails**: FAIL (`Error: unknown ctk.network tool` or similar).

- [ ] **Step 3: Implement.** Read `ctk/interfaces/mcp/handlers/analysis.py` (`handle_semantic_search` 221-328 + its helpers). Add `_do_semantic_search(db, args) -> str` to `network_tools.py` porting it wholesale: the `db.get_all_embeddings()` existence check returning a friendly "No embeddings found..." string (reconcile the hint wording to match `find_similar_conversations`); provider-from-first-embedding; the TF-IDF refit branch vs the `ConversationEmbedder` branch; the numpy cosine scan keeping `sim > 0`; sort desc + `top_k`; a ported `_build_title_cache` (one `db.list_conversations(limit=N+100)` -> `{id: title[:50]}`, no per-row load). Return ranked lines or `"Error: ..."` strings (network convention; do not raise). Add the `{"name": "semantic_search", "pass_through": False, "description": <verbatim from analysis.py>, "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}}, "required": ["query"]}}` dict to `_NETWORK_TOOLS`, and a `if name == "semantic_search": return _do_semantic_search(db, args)` branch to `execute_network_tool`. Move the needed imports (numpy, `ctk.core.similarity` helpers, `ctk.embeddings.tfidf.TFIDFEmbedding`, `ctk.embeddings.base` strategies) into `network_tools.py`.

- [ ] **Step 4: Run to verify pass** + full suite. (C1 golden untouched: `ctk.network` is not in that digest.)

- [ ] **Step 5: Commit.** `feat(tools): fold semantic_search into the ctk.network registry`.

---

## Task 3: Reconcile `find_similar` into `find_similar_conversations`

**Files:** Modify `ctk/core/network_tools.py`; Test extend `tests/unit/test_network_*.py`.

- [ ] **Step 1: Write the failing test**: seed a conversation with embeddings but NO persisted `SimilarityModel` rows, call `find_similar_conversations`, assert it still returns results (the on-the-fly cosine fallback) and resolves an 8-char prefix id. (FAILS today: `_do_find_similar` only reads the persisted table.)
- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement.** Read MCP `handle_find_similar` (analysis.py:130-218). Add to `network_tools._do_find_similar`: an embeddings-existence precheck; an on-the-fly cosine fallback when the `SimilarityModel` query is empty (port the MCP computation); switch the resolver to `db.resolve_identifier`; set the `min_similarity` default to `0.1` (was 0.0). Preserve the already-populated-table path byte-for-byte.
- [ ] **Step 4: Run + full suite.**
- [ ] **Step 5: Commit.** `feat(tools): find_similar_conversations gains on-the-fly fallback + 0.1 floor (reconciles MCP find_similar)`.

---

## Task 4: `update_conversation` core + verb wrappers

**Files:** Modify `ctk/core/builtin_tools.py`; Test `tests/unit/test_update_core.py`.

**Interfaces:** Produces `_update_core(db, conversation_id, *, starred=None, pinned=None, archived=None, title=None) -> tuple[str, list[str]]` (returns `(full_id_or_error_sentinel, changes)`).

- [ ] **Step 1: Write the failing test** for `_update_core`: only-provided-fields change (set `starred=True` only -> the conversation is starred, not pinned/archived); a missing id returns the `"Error:"` sentinel as the first tuple element.
- [ ] **Step 2: Run to verify it fails** (`_update_core` undefined).
- [ ] **Step 3: Implement.** Add `_update_core`: resolve once via `_resolve_conversation_id`; if it `startswith("Error:")` return `(full, [])`; else apply ONLY not-None fields (`starred -> db.star_conversation(full, star=starred)`, `pinned -> db.pin_conversation(full, pin=pinned)`, `archived -> db.archive_conversation(full, archive=archived)`, `title -> db.update_conversation_metadata(full, title=title)`), accumulating a `changes` list; return `(full, changes)`. Refactor the 7 verb handlers (`_do_star_conversation` ... `_do_rename_conversation`) to KEEP their own empty-arg guard (and rename's title guard), call `_update_core` with one fixed field, detect the `"Error:"` sentinel, and RETURN THEIR EXACT EXISTING STRING (do NOT delegate return formatting). Example: `_do_star_conversation` -> `full, _ = _update_core(ctx.db, conv_id, starred=True); if full.startswith("Error:"): return ToolResult.message(full); return ToolResult.message(f"Starred conversation {full[:8]}...")`.
- [ ] **Step 4: Run.** The EXISTING verb tests (`tests/unit/test_execute_ask_tool.py` RESOLVING_TOOLS + any verb-specific) MUST pass UNCHANGED (byte-identical strings). Plus `test_update_core.py`. Golden digest UNCHANGED (no schema change).
- [ ] **Step 5: Commit.** `refactor(tools): verb tools delegate to a shared update core (exact strings preserved)`.

---

## Task 5: LLM-facing `update_conversation` tool

**Files:** Modify `ctk/core/builtin_tools.py`; Test `tests/unit/test_builtin_update_conversation.py`; Modify `tests/unit/test_tools_golden.py` (digest).

- [ ] **Step 1: Write the failing test**: `execute_builtin_tool(db, "update_conversation", {"conversation_id": <prefix>, "starred": True, "title": "X"})` sets both and returns a changes summary; `{"conversation_id": <prefix>}` with no fields returns "No changes specified"; `archived=False` is applied (tri-state: false is a real value, not "no filter").
- [ ] **Step 2: Run to verify it fails** (`Unknown tool: update_conversation`).
- [ ] **Step 3: Implement.** Add `_do_update_conversation(ctx) -> ToolResult`: read `conversation_id` + tri-state `starred/pinned/archived` (`v = ctx.args.get("starred"); starred = to_bool(v) if v is not None else None`) + `title`; call `_update_core`; return `ToolResult.message("No changes specified")` when changes empty (and id resolved), the `"Error:"` sentinel on miss, else a joined changes summary (port `conversation.py:218-260` wording). Append `BuiltinTool(name="update_conversation", description=<the canonical description>, input_schema={"type": "object", "properties": {"conversation_id": {"type": "string"}, "starred": {"type": "boolean"}, "pinned": {"type": "boolean"}, "archived": {"type": "boolean"}, "title": {"type": "string"}}, "required": ["conversation_id"]}, handler=_do_update_conversation, pass_through=False)` to `_BUILTIN_TOOLS`.
- [ ] **Step 4: Update the C1 golden**: add `"update_conversation"` to `_EXPECTED_NAMES`, recompute `_EXPECTED_DIGEST`. Run the golden + the new test -> PASS.
- [ ] **Step 5: Green gate + commit.** `feat(tools): canonical update_conversation tool (LLM + MCP facing)`.

---

## Task 6: MCP generic projection

**Files:** Create `ctk/interfaces/mcp/projection.py`; Modify `ctk/interfaces/mcp/server.py`; Test rewrite `tests/unit/test_mcp_server.py`.

**Interfaces:** Produces `projection.project_tools() -> list[types.Tool]` and `async projection.handle_tool(name, arguments, db) -> list[types.TextContent]`.

- [ ] **Step 1: Write the failing test**: assert `project_tools()` returns exactly the curated set `{search_conversations, get_conversation, update_conversation, get_statistics, find_similar_conversations, semantic_search, execute_sql}` plus the `find_similar` legacy alias, each a `types.Tool` with an `inputSchema` (camel) and NO `pass_through` key; and that `await handle_tool("find_similar", {"id": <prefix>, "top_k": 5}, db)` dispatches to the canonical `find_similar_conversations` handler (legacy name + legacy params still work).
- [ ] **Step 2: Run to verify it fails.**
- [ ] **Step 3: Implement `projection.py`** per the spec: `_CURATED_MCP_TOOLS` (the 7 canonical names); `project_tools()` iterating `tools_registry.all_tools()`, filtering to the curated set, emitting `types.Tool(name, description, inputSchema=t["input_schema"])` (drop `pass_through`), sorted by name, plus the synthesized legacy `find_similar` tool def (canonical schema with `conversation_id/limit/min_similarity` renamed back to `id/top_k/threshold`); the `_ALIAS` map (`find_similar -> {_canonical: find_similar_conversations, id: conversation_id, top_k: limit, threshold: min_similarity}`, `get_conversation -> {id: conversation_id, include_content: show_messages}`, `update_conversation -> {id: conversation_id}`); `canonical_name(name)` and `normalize_aliases(name, args)` (rename only present keys); `handle_tool` rejecting non-curated/alias names, normalizing aliases, optionally running `validation.py` over the args, routing by `provider_for_tool(canonical)` to `execute_builtin_tool`/`execute_network_tool`, wrapping the `str` result as `[types.TextContent(type="text", text=result)]`. Rewrite `server.py`: `list_tools -> project_tools()`; `call_tool -> await handle_tool(...)`; drop the `from ...handlers import ALL_TOOLS, ALL_HANDLERS`; ADD explicit `import ctk.core.builtin_tools` and `import ctk.core.network_tools` at the top so the providers register before `list_tools`.
- [ ] **Step 4: Run** the rewritten `test_mcp_server.py` + full suite -> PASS.
- [ ] **Step 5: Commit.** `refactor(mcp): project the MCP tool surface from the registry (generic projection + alias map)`.

---

## Task 7: Delete the MCP handler package

**Files:** Delete `ctk/interfaces/mcp/handlers/{search,conversation,metadata,analysis,sql}.py` and `handlers/__init__.py`; Modify `tests/unit/test_mcp_analysis.py` (retarget to the folded `ctk.network` tools).

- [ ] **Step 1:** Delete the six files. `grep -rn "ctk.interfaces.mcp.handlers\|mcp.handlers import\|ALL_TOOLS\|ALL_HANDLERS" ctk/ tests/` -> the only remaining hits must be in tests you then fix.
- [ ] **Step 2:** Retarget `tests/unit/test_mcp_analysis.py` (and any test importing the deleted handlers) to test the folded `semantic_search`/`find_similar_conversations` via `execute_network_tool` and the projection.
- [ ] **Step 3:** Run the full MCP test set + full `tests/unit` -> green. mypy 0 (no dangling imports).
- [ ] **Step 4: Commit.** `refactor(mcp): delete the hand-written handler modules (superseded by projection)`.

---

## Task 8: `_format_message` assistant-`tool_calls` round-trip

**Files:** Modify `ctk/tui/app.py` (`_stream_worker` tool-call branch), `ctk/llm/openai.py` (`_format_message`); Test `tests/unit/test_openai_tool_roundtrip.py`.

- [ ] **Step 1: Write the failing test**: (a) `_format_message(Message(role=ASSISTANT, content="", metadata={"tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "search_conversations", "arguments": "{}"}}]}))` returns a dict whose `["tool_calls"][0]["id"] == "call_1"`; and a following `Message(role=TOOL, metadata={"tool_call_id": "call_1"})` formats with the matching `tool_call_id`. (b) Driving the TUI tool loop (or the history-assembly helper) with a fake provider yielding a tool_calls event with EMPTY text produces an ASSISTANT history message (not skipped) whose `metadata.tool_calls[0].id` equals the subsequent TOOL message's `tool_call_id`.
- [ ] **Step 2: Run to verify it fails** (today: empty-text turn drops the assistant message; `_format_message` never emits `tool_calls`).
- [ ] **Step 3: Implement** the two edits from the spec's format_fix: in `_stream_worker`'s tool_calls branch, ALWAYS append an assistant `LLMMessage` when tool_calls is non-empty (even empty text), with `metadata={"tool_calls": [OpenAI-shaped from the assembled tc dicts]}`; in `_format_message`, when `role == "assistant"` and `msg.metadata` has `"tool_calls"`, set `formatted["tool_calls"] = msg.metadata["tool_calls"]` and allow empty/None content.
- [ ] **Step 4: Run** + full suite. (`tests/unit/test_tui_chat_dispatch.py` and the streaming tests must stay green.)
- [ ] **Step 5: Commit.** `fix(llm): round-trip assistant tool_calls so strict OpenAI servers accept the tool history`.

---

## Task 9: Remove the REST and web interfaces

**Files:** Delete `ctk/interfaces/rest/`, `ctk/interfaces/web/`, `examples/rest_server.py`, `tests/unit/test_rest_api.py`, `tests/unit/test_rest_api_realdb.py`, `tests/unit/test_rest_validation.py`; Create `tests/unit/test_interface_response.py`; Modify `setup.py`, `CLAUDE.md`, `README.md`, `docs/`.

- [ ] **Step 1: Migrate the salvageable test FIRST.** Move the `TestInterfaceResponse` class from `tests/unit/test_rest_api.py` (the `InterfaceResponse`/`ResponseStatus` helper tests, which are not REST-specific) into a new `tests/unit/test_interface_response.py` so `ctk/interfaces/base.py` keeps coverage. Run it -> PASS.
- [ ] **Step 2: Delete** `ctk/interfaces/rest/` (whole dir), `ctk/interfaces/web/` (whole dir; `WebInterface` subclasses `RestInterface`, Flask-only, no importer), `examples/rest_server.py`, and the three `test_rest_*` files. KEEP `ctk/interfaces/base.py` and `ctk/interfaces/__init__.py`.
- [ ] **Step 3: Drop the Flask deps.** In `setup.py`, remove the `rest` extra (the flask + flask-cors lines) and the two flask/flask-cors lines duplicated into the `dev` extra. Do NOT touch `requirements.txt` (it has no flask). Leave `entry_points` (REST had no console_scripts).
- [ ] **Step 4: De-REST the docs.** Remove the "REST API ... Flask-based read/write REST surface" bullet from CLAUDE.md and the `rest_server.py` mention; grep `docs/ README.md` for `rest`/`REST`/`flask` and remove the REST/Flask references and the stale "HTML viewer is backed by the REST server" claim (the HTML exporter is self-contained, leave HTML-export docs intact).
- [ ] **Step 5: Verify.** `grep -rn "interfaces.rest\|interfaces.web\|RestInterface\|WebInterface\|flask" ctk/ tests/ examples/` -> no live source hits. Full `tests/unit` + integration green; `python -c "import ctk"` clean with no flask installed (the import path must not require flask).
- [ ] **Step 6: Commit.** `refactor: remove the unused REST and web (Flask) interfaces`.

---

## Task 10: Green gate + docs + 2.20.0

**Files:** Modify `CLAUDE.md`, `MEMORY.md` references; `ctk/__init__.py`, `setup.py`, `CITATION.cff` (bump 2.20.0).

- [ ] **Step 1: Full gate.** `python -m pytest tests/unit -q` (coverage enforced); `python -m pytest tests/integration -q -o addopts="" -m "not requires_ollama and not requires_api_key"`; `python -m mypy ctk --ignore-missing-imports`; `python -m flake8` on all C2-touched files. All green.
- [ ] **Step 2: Smoke `/mcp`.** Confirm the registry now shows `ctk.builtin` including `execute_sql` + `update_conversation`, and `ctk.network` including `semantic_search`; confirm the MCP projection lists the 7 curated tools. (A scripted import-and-list check, not the interactive TUI.)
- [ ] **Step 3: Docs.** Update the CLAUDE.md MCP-server section to describe the projection (7 curated tools projected from the registry, the alias map, REST removed) and correct the stale "7 tools"/"legacy dispatcher" lines. Note the MEMORY.md tool-count line is stale (the agent updates memory separately).
- [ ] **Step 4: Bump to 2.20.0** in `ctk/__init__.py`, `setup.py`, `CITATION.cff` (date today). Commit: `release: 2.20.0 (tool surface unification: MCP projects from registry, update_conversation, REST removed)`. Do NOT tag/push/upload (user-gated).

---

## Self-review notes

- Spec coverage: W1 MCP projection -> Tasks 6,7; W2 fold -> Tasks 1,2,3; W3 mutation -> Tasks 4,5; W4 REST removal -> Task 9; W5 format + docs -> Tasks 8,10. Every DoD item maps to a task.
- Ordering rationale: fold the tools INTO the registry (1-3) and add update_conversation (4-5) BEFORE the projection (6) so the projection has a complete registry to project; delete the handler package (7) only after the projection replaces it; REST removal (9) and the format fix (8) are independent and can slot anywhere after their own deps.
- Digest interplay: Tasks 1 and 5 each change the C1 golden digest by design (execute_sql, update_conversation join ctk.builtin) and update it in the same commit. Task 4 does NOT (no schema change). The schema-parity discipline from C1 (copy descriptions verbatim, adjacent-string-literal for long lines, never a newline inside a triple-quoted string) applies to Tasks 1 and 5.
- Risk guards (R1 digest-by-design, R2 verb-string preservation, R3 MCP alias compat, R4 provider registration order, R5 folded-handler friendly messages, R6 tool_calls round-trip test, R7 REST/web deleted together) are each pinned by a named test in the task that introduces them.
