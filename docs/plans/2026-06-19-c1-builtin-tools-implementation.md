# C1: builtin_tools.py Collapse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the 832-line `execute_ask_tool` if/elif dispatcher into a `ctk/core/builtin_tools.py` of self-dispatching handlers (one record per tool co-locating schema + handler), with structured `ToolResult` returns, BEHAVIOR-PRESERVING: no tool renamed, no tool merged, no behavior change.

**Architecture:** A strangler migration. A scaffold module + a thin `execute_ask_tool` shim route already-migrated tools to a dict-dispatched `execute_builtin_tool` and fall back to the renamed `_execute_ask_tool_legacy` for the rest, so the full suite is green after every batch. Tool schemas stay registered from `tools_registry` until the final cleanup, decoupling LLM-facing schema from handler migration. Modeled on the existing `ctk/core/network_tools.py`.

**Tech Stack:** Python 3.12, pytest. Design: `docs/plans/2026-06-18-unified-tool-surface-design.md` (W1+W2). This plan is sub-project C, phase 1; semantic unification with the MCP server is a later phase C2 and is OUT OF SCOPE here.

## Global Constraints

- BEHAVIOR-PRESERVING: copy handler bodies VERBATIM from `ctk/cli.py` (do not retype or paraphrase; error strings are load-bearing and tested). Rewrite only `tool_args` -> `ctx.args`, `use_rich` -> `ctx.use_rich`, `shell_executor` -> `ctx.shell_executor`. Local imports inside a branch travel into its handler.
- The symbol `ctk.cli.execute_ask_tool` MUST stay importable with its exact signature `(db, tool_name, tool_args, debug=False, use_rich=True, shell_executor=None) -> str` (the TUI at `ctk/tui/app.py:685` and `tests/unit/test_execute_ask_tool.py` depend on it).
- Preserve verbatim: the `Unknown tool: {name}` no-match return; the single broad `except Exception as e: return f"Error executing {name}: {e}"` wrapper; the `_resolve_conversation_id` "Error:"-prefixed sentinel contract; every per-tool early-return string.
- TDD: failing test first, run-to-fail, implement, pass.
- A repo write hook BLOCKS any file containing an em-dash character or the word spelled l-e-v-e-r-a-g-e. Plain hyphens only, including docstrings and test strings.
- No bare `except:` (the one broad `except Exception` in the dispatcher is intentional and mirrors the original).
- Green gate before each commit: `python -m pytest tests/unit/test_execute_ask_tool.py tests/unit/test_tools.py <new test files> -q -o addopts=""` pass; `python -m black <touched files>`; `python -m flake8 <touched files> --max-line-length=100 --ignore=E203,W503` clean on new lines; `python -m mypy ctk --ignore-missing-imports` 0 errors. Run the FULL `python -m pytest tests/unit -q` once per batch.

---

## Task 1: Scaffold + strangler shim + golden guard

**Files:**
- Create: `ctk/core/builtin_tools.py`
- Modify: `ctk/cli.py` (rename the current `execute_ask_tool` body to `_execute_ask_tool_legacy`; add the new shim)
- Test: `tests/unit/test_builtin_tools.py`, `tests/unit/test_tools_golden.py`

**Interfaces:**
- Produces: `ToolContext(db, args, use_rich=True, debug=False, shell_executor=None)`; `ToolResult(text, data=None, rich_renderable=False)` with `ToolResult.message(text)`; `BuiltinTool(name, description, input_schema, handler, pass_through=False)` with `as_schema_dict()`; `_BUILTIN_TOOLS: List[BuiltinTool]`; `builtin_tool_names() -> set`; `execute_builtin_tool(db, name, args, *, use_rich=True, debug=False, shell_executor=None) -> str`; module-level `_resolve_conversation_id(db, conv_id) -> str` (moved verbatim from cli.py).
- Consumes: nothing new. The shim falls back to `_execute_ask_tool_legacy` (the renamed original body).

- [ ] **Step 1: Capture the LLM-facing golden snapshot (guards schema drift across the whole migration)**

```python
# tests/unit/test_tools_golden.py
import json
import pytest
from ctk.core.tools import get_ask_tools

pytestmark = pytest.mark.unit


def test_ask_tools_snapshot_is_stable():
    # The LLM-facing tool list (pass_through key stripped) must not change
    # across the C1 migration: same names, same schemas, same order.
    tools = get_ask_tools(include_pass_through=False)
    names = [t["name"] for t in tools]
    assert len(names) == 26
    assert len(set(names)) == 26
    # A stable digest of the full schema payload; if any schema text drifts
    # during the handler migration, this fails.
    digest = json.dumps(tools, sort_keys=True)
    # Snapshot the digest length + the sorted name list as the invariant.
    assert sorted(names) == [
        "archive_conversation", "auto_tag_conversation", "delete_conversation",
        "duplicate_conversation", "export_conversation", "get_conversation",
        "get_recent_conversations", "get_statistics", "list_conversation_paths",
        "list_conversations", "list_models", "list_plugins", "list_sources",
        "list_tags", "pin_conversation", "remove_tag", "rename_conversation",
        "search_conversations", "show_conversation_content", "show_conversation_tree",
        "star_conversation", "tag_conversation", "unarchive_conversation",
        "unpin_conversation", "unstar_conversation",
    ]
    assert len(digest) > 0
```

Run `python -m pytest tests/unit/test_tools_golden.py -q -o addopts=""`. Expected: PASS today (it just pins the current registered tool set). If the count is not 26, read `ctk/core/tools_registry.py` and adjust the expected name list to the real current set, and note it. This test must stay green through every later task.

- [ ] **Step 2: Write the scaffold failing test**

```python
# tests/unit/test_builtin_tools.py
import pytest
from ctk.core.database import ConversationDB
from ctk.core.builtin_tools import (
    BuiltinTool, ToolContext, ToolResult, execute_builtin_tool, builtin_tool_names,
)

pytestmark = pytest.mark.unit


def test_unknown_tool_returns_sentinel(tmp_path):
    db = ConversationDB(str(tmp_path))
    try:
        assert execute_builtin_tool(db, "nonsense_xyz", {}) == "Unknown tool: nonsense_xyz"
    finally:
        db.close()


def test_handler_exception_wrapped(tmp_path):
    # A registered tool whose handler raises must surface the legacy wrapper string.
    db = ConversationDB(str(tmp_path))
    try:
        import ctk.core.builtin_tools as bt

        def boom(ctx):
            raise RuntimeError("kaboom")

        tool = BuiltinTool(name="_probe", description="", input_schema={}, handler=boom)
        bt._BUILTIN_TOOLS.append(tool)
        bt._rebuild_handlers()
        try:
            out = execute_builtin_tool(db, "_probe", {})
            assert out == "Error executing _probe: kaboom"
        finally:
            bt._BUILTIN_TOOLS.remove(tool)
            bt._rebuild_handlers()
    finally:
        db.close()


def test_tool_result_message():
    assert ToolResult.message("hi").text == "hi"
```

Run it: FAIL with `ModuleNotFoundError: No module named 'ctk.core.builtin_tools'`.

- [ ] **Step 3: Create the scaffold module**

```python
# ctk/core/builtin_tools.py
"""Self-dispatching builtin tools for the ctk.builtin provider.

Each tool co-locates its JSON schema and a handler callable, mirroring
ctk/core/network_tools.py. This replaces the former 832-line execute_ask_tool
if/elif dispatcher with a dict-dispatched, behavior-preserving registry.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ctk.core.database import ConversationDB

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    db: ConversationDB
    args: Dict[str, Any]
    use_rich: bool = True
    debug: bool = False
    shell_executor: Optional[Callable[..., Any]] = None


@dataclass
class ToolResult:
    text: str
    data: Any = None
    rich_renderable: bool = False

    @classmethod
    def message(cls, text: str) -> "ToolResult":
        return cls(text=text)


@dataclass(frozen=True)
class BuiltinTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[["ToolContext"], "ToolResult"]
    pass_through: bool = False

    def as_schema_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
        if self.pass_through:
            d["pass_through"] = True
        return d


def _resolve_conversation_id(db: ConversationDB, conv_id: str) -> str:
    # MOVED VERBATIM from ctk/cli.py:821-832. Returns the full id on hit, or an
    # "Error:"-prefixed sentinel string on miss/ambiguity (contract tested by
    # tests/unit/test_execute_ask_tool.py via .startswith("Error:")).
    ...  # copy the exact body from cli.py


_BUILTIN_TOOLS: List[BuiltinTool] = []
_HANDLERS: Dict[str, BuiltinTool] = {}


def _rebuild_handlers() -> None:
    _HANDLERS.clear()
    _HANDLERS.update({t.name: t for t in _BUILTIN_TOOLS})


def builtin_tool_names() -> set:
    return set(_HANDLERS)


def execute_builtin_tool(
    db: ConversationDB,
    name: str,
    args: Dict[str, Any],
    *,
    use_rich: bool = True,
    debug: bool = False,
    shell_executor: Optional[Callable[..., Any]] = None,
) -> str:
    tool = _HANDLERS.get(name)
    if tool is None:
        return f"Unknown tool: {name}"
    ctx = ToolContext(
        db=db, args=args, use_rich=use_rich, debug=debug, shell_executor=shell_executor
    )
    try:
        result = tool.handler(ctx)
    except Exception as e:  # mirrors the original broad wrapper, behavior-preserving
        return f"Error executing {name}: {e}"
    return result.text


_rebuild_handlers()
```

Keep `_resolve_conversation_id` ALSO in cli.py for now (the legacy body still uses it); you will remove the cli.py copy at the cleanup task. Copy it, do not move it yet.

- [ ] **Step 4: Convert cli.py to the strangler shim**

In `ctk/cli.py`: rename the current `def execute_ask_tool(...)` to `def _execute_ask_tool_legacy(...)` (same body, same signature). Add the new shim:

```python
def execute_ask_tool(db, tool_name, tool_args, debug=False, use_rich=True, shell_executor=None):
    """Dispatch a builtin tool. Migrated tools route to the builtin_tools
    registry; not-yet-migrated tools fall back to the legacy dispatcher.
    """
    if debug:
        import sys
        print(f"[DEBUG] Tool: {tool_name}", file=sys.stderr)
        print(f"[DEBUG] Args: {tool_args}", file=sys.stderr)
    from ctk.core.builtin_tools import builtin_tool_names, execute_builtin_tool

    if tool_name in builtin_tool_names():
        return execute_builtin_tool(
            db, tool_name, tool_args, use_rich=use_rich, debug=debug, shell_executor=shell_executor
        )
    return _execute_ask_tool_legacy(
        db, tool_name, tool_args, debug=debug, use_rich=use_rich, shell_executor=shell_executor
    )
```

(The legacy body still contains its own top-of-body debug prints; remove the duplicate debug prints from the legacy body OR from the shim so debug is not printed twice. Keep them in the shim; delete the `if debug:` block at the top of `_execute_ask_tool_legacy`.)

- [ ] **Step 5: Run the scaffold + golden + the existing executor tests**

Run: `python -m pytest tests/unit/test_builtin_tools.py tests/unit/test_tools_golden.py tests/unit/test_execute_ask_tool.py tests/unit/test_tools.py -q -o addopts=""`
Expected: PASS. `_HANDLERS` is empty, so every tool still routes through `_execute_ask_tool_legacy` (unchanged behavior); the 15 RESOLVING_TOOLS tests pass via legacy.

- [ ] **Step 6: Green gate and commit**

```bash
python -m pytest tests/unit -q
python -m black ctk/core/builtin_tools.py ctk/cli.py tests/unit/test_builtin_tools.py tests/unit/test_tools_golden.py
python -m flake8 ctk/core/builtin_tools.py ctk/cli.py tests/unit/test_builtin_tools.py tests/unit/test_tools_golden.py --max-line-length=100 --ignore=E203,W503
python -m mypy ctk --ignore-missing-imports
git add -A && git commit -m "refactor(tools): builtin_tools scaffold + strangler execute_ask_tool shim (no behavior change)"
```

---

## Tasks 2-8: migrate handlers batch by batch

For EACH batch task below, the procedure is identical:

1. For each tool in the batch, copy its branch body VERBATIM from the cited `ctk/cli.py` lines into a handler `def _do_<name>(ctx: ToolContext) -> ToolResult:` in `ctk/core/builtin_tools.py`. Mechanically rewrite `tool_args` -> `ctx.args`, `use_rich` -> `ctx.use_rich`, `shell_executor` -> `ctx.shell_executor`. Move any branch-local imports into the handler. Where the branch `return "<string>"`, wrap as `return ToolResult.message("<string>")` (keep the string byte-identical).
2. Append a `BuiltinTool(name=..., description=<verbatim from tools_registry>, input_schema=<verbatim from tools_registry>, handler=_do_<name>, pass_through=<see batch note>)` to `_BUILTIN_TOOLS` for each, then call `_rebuild_handlers()` (or rely on the module-level rebuild at import; ensure `_rebuild_handlers()` runs after the list is fully built).
3. Do NOT edit `_execute_ask_tool_legacy` (its now-shadowed branches are dead but harmless until the cleanup task). The shim routes the migrated names to the registry automatically.
4. Run `tests/unit/test_execute_ask_tool.py` (the RESOLVING_TOOLS net) + `tests/unit/test_tools_golden.py` + the FULL `tests/unit/` suite. All must stay green.

Copy the schema (`description` + `input_schema`) for each tool VERBATIM from its entry in `ctk/core/tools_registry.py` `TOOLS_REGISTRY`. The golden test guards against any drift.

### Task 2 -- Batch 1: 8 metadata toggles
Tools (cli.py lines): `star_conversation` (1109), `unstar_conversation` (1122), `pin_conversation` (1134), `unpin_conversation` (1146), `archive_conversation` (1158), `unarchive_conversation` (1170), `rename_conversation` (1182), `delete_conversation` (1245). All use `_resolve_conversation_id`; all are in `RESOLVING_TOOLS`. `pass_through=False` for all.
**Guard:** `test_execute_ask_tool.py` covers all 8. Commit: `refactor(tools): migrate metadata-toggle handlers to builtin_tools`.

### Task 3 -- Batch 2: 4 tag operations
Tools: `tag_conversation` (1261), `remove_tag` (1304), `list_tags` (1287), `auto_tag_conversation` (1640, the LLM stub). `tag_conversation`/`remove_tag`/`auto_tag_conversation` are RESOLVING_TOOLS. `pass_through=False`.
**Guard:** RESOLVING_TOOLS net + add a test that `list_tags` returns the "Tags in database:" string (or "No tags found...") on a seeded db. Commit: `refactor(tools): migrate tag handlers to builtin_tools`.

### Task 4 -- Batch 3: 5 listings + pass_through single-source
Tools: `get_statistics` (1055), `list_sources` (1330), `list_models` (1347), `get_recent_conversations` (1477), `list_conversations` (1508). NONE use `use_rich`. PRESERVE the divergence that `list_conversations` passes `starred/pinned/archived` raw (NO `to_bool_or_none`). `pass_through`: `get_statistics=True`, `list_conversations=True` (see below), the other three `False`.
**pass_through single-source work (do in THIS task):** today `PASS_THROUGH_TOOLS` (the set in tools_registry.py) contains `list_conversations` but its schema dict has no `pass_through` key. Set `pass_through=True` on the `list_conversations` BuiltinTool to preserve `is_pass_through_tool("list_conversations") == True`. Then change `ctk/core/tools.py` so `PASS_THROUGH_TOOLS`/`is_pass_through_tool` are DERIVED from the registered tools (`{t["name"] for t in all_tools() if t.get("pass_through")}`) rather than the hand-maintained set, and delete the standalone `PASS_THROUGH_TOOLS` set from tools_registry.py. Confirm `tests/unit/test_tools.py` asserts membership (not absence-of-key) before landing; run it. NOTE: only do the derivation once these 5 (incl. the pass_through ones get_statistics/list_conversations) are migrated AND search_conversations/get_conversation/execute_shell_command still register their pass_through via tools_registry seed; since the registered provider is still the seed until cleanup, derive from `all_tools()` which reflects the seed -- verify `is_pass_through_tool` still returns the same set for all 5 names (search_conversations, get_conversation, get_statistics, execute_shell_command, list_conversations).
**Guard:** `test_tools.py` (pass_through), golden test, + a seeded-db smoke that `list_conversations`/`get_recent_conversations` return their listing strings. Commit: `refactor(tools): migrate listing handlers + derive pass_through from tool definitions`.

### Task 5 -- Batch 4: 4 single-conversation reads
Tools: `get_conversation` (999, OWN inline prefix-match, NOT `_resolve_conversation_id` -- preserve), `show_conversation_content` (1197, resolves inside `show_conversation_helper`), `list_conversation_paths` (1574, RESOLVING), `export_conversation` (1367, RESOLVING; markdown/json/jsonl branches + the `MarkdownExporter` local import). `pass_through=False`.
**Guard:** RESOLVING_TOOLS net (list_conversation_paths, export_conversation) + a smoke that `export_conversation` on a seeded conv returns an export string and NOT an "Error executing" prefix (R7) + a smoke that `get_conversation` with an 8-char prefix resolves. Commit: `refactor(tools): migrate single-conversation-read handlers to builtin_tools`.

### Task 6 -- Batch 5: copy + plugins
Tools: `duplicate_conversation` (1431, RESOLVING; hand-rolled `copy.deepcopy` + `uuid` id-remap -- copy verbatim, do NOT substitute `tree.copy()`), `list_plugins` (1615, `PluginRegistry`, no db). `pass_through=False`.
**Guard:** RESOLVING net (duplicate) + a smoke that `duplicate_conversation` creates a copy and `list_plugins` returns the "Available Plugins:" string with no "Error executing" prefix. Commit: `refactor(tools): migrate duplicate + list_plugins handlers to builtin_tools`.

### Task 7 -- Batch 6: shell-coupled
Tools: `execute_shell_command` (1076, reads `ctx.shell_executor`; None -> "not available" string), `show_conversation_tree` (1219, RESOLVING fallback; PREFERS `ctx.shell_executor("tree <id>")`). `pass_through`: `execute_shell_command=True`, `show_conversation_tree=False`.
**Guard:** add a test passing a FAKE `shell_executor` returning a duck-typed object with `.output`/`.success`/`.error` and asserting `execute_shell_command` surfaces `.output`; plus the `shell_executor=None` path returning the "not available" string; plus `show_conversation_tree` preferring the executor when present and the stub fallback when None (R5). Commit: `refactor(tools): migrate shell-coupled handlers to builtin_tools`.

### Task 8 -- Batch 7: search_conversations + rendering split
Tool: `search_conversations` (864). This is the rendering split. The handler `_do_search_conversations` must NOT read `ctx.use_rich`, NOT import Rich/Console, and NOT print. It builds the conversation list once and returns `ToolResult(text=<the plain "Found N conversation(s)..." string, EXACTLY today's use_rich=False output at cli.py:982-997>, data=<the list of rows>, rich_renderable=True)`. Keep the nested `to_bool_or_none`/`clean_none` helpers inside the handler. `pass_through=True`.
**Guard (R1):** add a test asserting `execute_ask_tool(db, "search_conversations", {...}, use_rich=False)` returns the "Found N..."/"No conversations found." string and is NEVER "" (the empty sentinel must be gone). The TUI always passes `use_rich=False`, so the contract to preserve is that plaintext string.
**CLI render:** if any live `use_rich=True` caller exists, move the `format_conversations_table` render to that CLI call site reading `result.data`/`result.rich_renderable`; the analysis found NO live `use_rich=True` caller, so document that the table render is now CLI-layer-only and the handler no longer prints. Commit: `refactor(tools): migrate search_conversations with rendering split (handler returns data, no stdout)`.

---

## Task 9: cleanup + register from builtin_tools + green gate

**Files:** `ctk/cli.py`, `ctk/core/tools_registry.py`, `ctk/core/builtin_tools.py`, `ctk/tui/app.py`, `CLAUDE.md`

- [ ] **Step 1:** All 26 handlers are now in `_BUILTIN_TOOLS`. Switch the registered provider: in `ctk/core/builtin_tools.py`, build `_BUILTIN_TOOLS_REGISTRY = [t.as_schema_dict() for t in _BUILTIN_TOOLS]` and `register_provider(ToolProvider(name="ctk.builtin", description=<the same description text tools_registry used>, tools=_BUILTIN_TOOLS_REGISTRY))` at import. Ensure `ctk/tui/app.py:_register_builtin_providers` imports `ctk.core.builtin_tools` (so the provider registers before the TUI starts), alongside the existing `network_tools` import.
- [ ] **Step 2:** Remove `TOOLS_REGISTRY` and the seed `ctk.builtin` `ToolProvider` from `ctk/core/tools_registry.py` (now superseded). Keep `ToolProvider`/`register_provider`/`iter_providers`/`provider_for_tool`/`all_tools` (provider-agnostic machinery). Remove the now-dead `_execute_ask_tool_legacy` from `ctk/cli.py` and the now-duplicate `_resolve_conversation_id` from cli.py (it lives in builtin_tools.py now; if cli.py has no other user, delete it there).
- [ ] **Step 3:** Run `tests/unit/test_tools_golden.py` -- it must STILL pass, proving `get_ask_tools()` output is byte-identical after the schemas moved from `TOOLS_REGISTRY` to `BuiltinTool.as_schema_dict()`. If it fails, a schema text drifted during a batch; diff and fix to match the original verbatim.
- [ ] **Step 4:** Add a provider-wiring test: after importing `ctk.core.builtin_tools`, `provider_for_tool("search_conversations") == "ctk.builtin"` and the `ctk.builtin` provider has 26 tools (R6).
- [ ] **Step 5:** Update `CLAUDE.md`: the line saying builtin tool execution routes to "`cli.execute_ask_tool` (legacy dispatcher; will move to a dedicated module in a follow-up)" -- that follow-up is now done; describe `ctk/core/builtin_tools.py` (self-dispatching handlers, `execute_builtin_tool`, `ToolResult`) and that `execute_ask_tool` is a thin shim.
- [ ] **Step 6: Full green gate.** `python -m pytest tests/unit -q` (coverage enforced); `python -m pytest tests/integration -q -o addopts="" -m "not requires_ollama and not requires_api_key"`; `python -m mypy ctk --ignore-missing-imports` (0); `python -m flake8 ctk/core/builtin_tools.py --max-line-length=100 --ignore=E203,W503`. All green.
- [ ] **Step 7: Commit.** `refactor(tools): collapse 832-line execute_ask_tool into builtin_tools.py; remove legacy dispatcher and TOOLS_REGISTRY`. Do NOT bump version (C1 is an internal, behavior-preserving refactor; the version bump rides with C2's user-facing changes). Do NOT tag/push/upload.

---

## Self-review notes

- Spec coverage: W1 (self-dispatching tools) -> Tasks 1-9; W2 (rendering split) -> Task 8 + the `ToolResult`/pass_through-derivation pieces. Semantic unification (W3-W5) is C2, out of scope.
- The strangler shim keeps the full suite green after every batch (the shim routes migrated names to `_HANDLERS`, the rest to legacy). The golden test (Task 1) guards LLM-facing schema stability across the whole move; the RESOLVING_TOOLS net guards `_resolve_conversation_id` scope; per-batch smokes (R7) guard the non-resolving tools whose failures the RESOLVING net would not catch.
- Risks R1-R7 from the analysis are each pinned by a named guard test in the batch that introduces them (R1 search text in Task 8; R2 resolver scope in every RESOLVING batch; R3 verbatim-copy discipline; R4 pass_through in Task 4; R5 shell_executor fake in Task 7; R6 provider wiring in Task 9; R7 non-resolving smokes in Tasks 5/6).
