# Sub-project C: Unify the Tool Surface (Design)

**Date:** 2026-06-18
**Status:** Design (decisions approved in discussion; pending spec review)
**Part of:** [CTK Improvement Program](2026-06-04-improvement-program-roadmap.md), sub-project C
**Decisions taken with user:** self-dispatching tools (each tool carries its schema and handler);
handlers return structured data and each surface renders it; two zero-dependency fixes (the
`_format_message` crash-guard and provider-derived routing) ship immediately, the structural collapse
follows E-core.

---

## 1. Goal and definition of done

C collapses four parallel, hand-maintained tool surfaces into one structured registry where each
tool's identity (its JSON schema) and its behavior (its handler) live together, and every surface
(TUI chat, the CLI, the MCP server, and the REST API) is generated from or dispatches through that one
source. The root defect is uniform: a tool's schema and its executor are separate artifacts joined only
by a matching name string, and the flat list built by `all_tools()`/`get_ask_tools()` discards the
provider boundary that should drive dispatch.

**Definition of done:**

1. Each builtin tool is one structured object carrying name, input schema, pass-through flag, and a
   handler callable. The 832-line stringly-typed `execute_ask_tool` if/elif chain is gone; dispatch is
   a registry lookup, and an unknown tool is a registry miss rather than a string fallthrough.
2. Handlers return structured data. Each surface renders it: the CLI owns Rich tables, the TUI owns
   bubble rendering, the MCP server owns `TextContent` wrapping. The `use_rich` "already printed"
   sentinel and the stdout coupling are gone.
3. Routing is derived from provider ownership. The hardcoded `_NETWORK_TOOL_NAMES` frozenset is
   deleted; adding a provider needs no edit to `app.py`.
4. The MCP server's tools are projected from the same specs as the builtin/network providers. The five
   tools currently defined twice with divergent schemas (search_conversations, get_conversation,
   get_statistics, find_similar, update_conversation) have one schema each. Argument coercion is one
   validation layer before dispatch, not re-implemented per branch.
5. The REST interface dispatches through the same registry/handlers instead of re-calling
   `ConversationDB` directly (lands last within C).
6. `_format_message` is type-safe (no crash on non-string content) and round-trips assistant
   `tool_calls`, with regression tests. (The crash-guard ships immediately, ahead of the rest of C.)
7. Stale tool-count docs (CLAUDE.md "7 tools" lists 6; MEMORY.md "13 tools") are corrected.
8. Suite green: mypy 0, coverage at or above 59, all unit + integration tests pass; the collapsed
   dispatcher and the projected MCP/REST surfaces have tests, including a contract test asserting the
   projections agree.

---

## 2. Empirical grounding (probed against the real code)

**Four parallel surfaces.** (1) The `ctk.builtin` schema is 27 dicts in `tools_registry.py:17-493`;
its executor is `cli.execute_ask_tool` (cli.py:833-1665), an 832-line if/elif on `tool_name` ending in
`else: return f"Unknown tool: {tool_name}"` (cli.py:1659) under one catch-all `except` (cli.py:1662).
Schema and executor are linked only by identical name strings; the two name sets match by hand. (2) The
`ctk.network` provider (network_tools.py:41-237) is the structural counter-example: schema, executor,
and `register_provider` self-registration co-located in one module. This is the pattern to copy. (3) The
real MCP server (`ctk/interfaces/mcp/handlers/`) defines 7 tools with co-located `TOOLS` + async
`HANDLERS` and real validation (`mcp/validation.py`); five of them redefine builtin tools with divergent
schemas. (4) The Flask REST interface (`rest/api.py`) is a fourth surface re-calling `db.*` directly.

**Divergence examples.** `get_conversation`: MCP is `id` + `include_content` default **true**
(conversation.py:115-136), builtin is `conversation_id` + `show_messages` default **false**
(tools_registry.py:83-96); defaults inverted, different resolution code. `find_similar` (MCP:
`id`/`top_k`/`threshold`, analysis.py:80-99) versus `find_similar_conversations` (network:
`conversation_id`/`limit`/`min_similarity`, network_tools.py:56-73): same operation, zero shared
parameter names. `search_conversations`: MCP exposes `cursor` (search.py:32-64), builtin exposes
`source`/`project`/`model`/`tags` (tools_registry.py:35-72).

**Stringly-typed routing.** `CTKApp._execute_tool` (app.py:675-697) routes by
`if name in self._NETWORK_TOOL_NAMES` where `_NETWORK_TOOL_NAMES` is a hardcoded frozenset (app.py:673)
duplicating what the registry already knows; a third network tool would silently route to the builtin
chain and fall through to "Unknown tool."

**pass_through double-encoded.** A per-tool `pass_through` key (tools_registry.py) and a standalone
`PASS_THROUGH_TOOLS` set (tools_registry.py:496-502) both encode the same fact; `is_pass_through_tool`
reads only the set (tools.py:48), and the two are already inconsistent for `list_conversations`.

**`_format_message` hazard.** `_format_message` (openai.py:350-359) sets `"content": msg.content`
with no coercion; `llm.base.Message.content` is typed `str` (base.py:27). Every current caller
pre-normalizes to a string, so the crash is latent, not live, but unguarded; and the assistant's
`tool_calls` are not reattached on the multi-turn round-trip, which a strict OpenAI-spec server can
reject (works against lenient/ollama endpoints).

---

## 3. Decisions taken with the user

1. **Self-dispatching tools.** Each tool is one structured object (name, input schema, pass_through,
   handler). Providers own execution. This matches the `ctk.network` module already in the codebase and
   the project's "derive behavior from structure" rule.
2. **Structured-data returns with per-surface renderers.** Handlers return data, not pre-rendered
   text; the CLI/TUI/MCP each render it. This is what lets one handler genuinely serve all surfaces and
   resolves the `use_rich` stdout coupling.
3. **Two zero-dependency fixes ship immediately,** ahead of E-core completing: the `_format_message`
   crash-guard (plus a `validate_messages` type check) and provider-derived routing (kill
   `_NETWORK_TOOL_NAMES`). Each lands with its regression test.

Recommendations carried into the spec for confirmation at the review gate (not yet locked):

4. **Canonical naming: the MCP handler layer wins, with one-release back-compat aliases** for the
   builtin names the LLM has been prompted with (id over conversation_id, include_content over
   show_messages, top_k over limit, threshold over min_similarity, find_similar over
   find_similar_conversations). The MCP layer already pairs schema + handler + validation and supports
   cursor pagination.
5. **Mutation shape: `update_conversation(starred, pinned, archived, title)` is canonical;** the seven
   verb tools (star/unstar/pin/unpin/archive/unarchive/rename) become thin pre-filled wrappers so the
   LLM keeps both vocabularies.
6. **REST is in scope for C but lands last.** It is the same `db.*` duplication the registry removes;
   leaving it out means a fourth surface keeps drifting.

---

## 4. Architecture and workstreams

C is sequenced after E-core's `database.py` work settles, except W0 which ships immediately. The
handler extraction benefits from E-core having centralized the duplicated filter blocks and fixed the
list N+1, so handlers that call list/search inherit the fix for free.

### W0: Zero-dependency hotfixes (ship now, ahead of the rest of C)

- **`_format_message` crash-guard:** coerce content defensively:
  `content = msg.content.get_text() if hasattr(msg.content, "get_text") else (msg.content if isinstance(msg.content, str) else str(msg.content))`.
  Back it with a type check in `validate_messages` (base.py:206) so a non-string content fails loudly
  at the boundary with a clear message instead of deep in the SDK's JSON encoder. Regression test:
  construct an `llm.base.Message` with non-string content and assert `_build_payload` yields a
  JSON-serializable payload.
- **Provider-derived routing:** make `get_ask_tools`/`all_tools` preserve each tool's provider, and
  have `CTKApp._execute_tool` dispatch on provider ownership instead of `_NETWORK_TOOL_NAMES`. The
  OpenAI format conversion downstream only reads name/description/input_schema, so adding provenance is
  additive. Regression test: a tool owned by `ctk.network` routes to the network executor without being
  named in any hardcoded set.

These two are independent of the larger collapse and of E-core; they close a latent crash and a silent
misroute with small, isolated diffs.

### W1: Self-dispatching builtin tools (`ctk/core/builtin_tools.py`)

Create the module the codebase already promises (CLAUDE.md and app.py:681-683 both say the legacy
dispatcher "will move into a dedicated builtin_tools module"). Model it on `network_tools.py`:

```python
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[ConversationDB, dict], ToolResult]   # returns structured data
    pass_through: bool = False

BUILTIN_TOOLS: list[Tool] = [ ... ]   # schema + handler co-located, one entry per tool
register_provider(ToolProvider(name="ctk.builtin", tools=[t.as_schema_dict() for t in BUILTIN_TOOLS]))
```

- Extract the 26 if/elif branch bodies from `cli.execute_ask_tool` into 26 handler functions in this
  module (mechanical). Each handler takes `(db, args)` and returns a structured `ToolResult` (a small
  dataclass or typed dict), never printing.
- `execute_ask_tool` becomes a thin shim that looks up the tool by name and calls its handler, kept at
  its current signature initially so `tests/unit/test_execute_ask_tool.py` and the TUI worker keep
  passing. The "Unknown tool" string becomes a registry miss raising a clear error.
- Argument coercion (the inline `to_bool_or_none`/`clean_none` at cli.py:872-905) moves into one
  schema-validation step applied before dispatch, reusing the rules in `mcp/validation.py`.
- `pass_through` is read from the tool object; the standalone `PASS_THROUGH_TOOLS` set is deleted and
  `list_conversations` gets its missing `pass_through` flag.
- `shell_executor`-dependent tools (`execute_shell_command`, `show_conversation_tree`) keep degrading
  gracefully when no executor is injected (the current "not available in this context" behavior).

### W2: Rendering split (handlers return data, surfaces render)

- Define `ToolResult` as structured data (the rows/record/summary a tool produced) plus an optional
  default text rendering for callers that want a string.
- The CLI command path renders Rich tables from `ToolResult` (moving `format_conversations_table`
  usage out of the executor). The `use_rich` flag and the `""` "already printed" sentinel are removed
  from the executor entirely.
- The TUI renders `ToolResult` into its existing tool-call panels.
- The MCP server wraps `ToolResult` into `list[types.TextContent]`.

### W3: One spec projected into MCP + builtin + network

- Promote the co-located `TOOLS` + `HANDLERS` shape (already used by the MCP handlers) to the canonical
  form. Generate the MCP `types.Tool` list and the `ctk.builtin`/`ctk.network` provider dicts from the
  same specs. Route `server.call_tool`, `execute_ask_tool`, and `execute_network_tool` through the
  shared handlers.
- Resolve the five divergent tools to one schema each, applying the canonical-naming decision (D4) with
  one-release aliases for the old names so existing chat behavior does not regress.
- Collapse the seven verb-mutation tools into wrappers over one canonical `update_conversation` handler
  (D5).
- One validation regime (`mcp/validation.py`) replaces the two parallel ones.
- **Contract test:** for every tool present in more than one projected surface, assert the param schema
  and defaults match (this is the structural guard that keeps the projections from drifting again).

### W4: REST through the registry (lands last)

- Replace the direct `db.*` calls in `rest/api.py` route handlers with dispatch through the shared
  registry/handlers, keeping the same HTTP surface. The REST layer becomes a thin adapter that maps
  requests to tool calls and renders `ToolResult` to JSON.
- `_format_message` round-trips assistant `tool_calls` (reattach the original `tool_calls` to the
  assistant message in the multi-turn history) so strict OpenAI-spec servers accept the follow-up.

### W5: Doc correction

- Fix CLAUDE.md ("7 tools" but lists 6; the real `ALL_TOOLS` is 7: search 1, conversation 2, metadata
  1, analysis 2, sql 1) and the stale MEMORY.md "13 tools" note, as part of whichever workstream
  touches the MCP surface.

---

## 5. Out of scope (deferred)

- New tools or new tool capabilities. C is a structural collapse, not a feature expansion.
- External MCP server federation (consuming third-party MCP servers as providers). The registry is
  designed to allow it (the `available` flag exists for it), but wiring real external providers is a
  later pass.
- The `available`-flag activation: it stays dead until external providers exist, but the
  provider-derived routing (W0) is the groundwork.

---

## 6. Testing

- **W0:** `_format_message` non-string-content payload test; provider-routing test (network tool routes
  without a hardcoded name).
- **W1:** every builtin tool dispatches via the registry; an unknown tool raises a clear error; the
  existing `test_execute_ask_tool.py` call surface still passes through the shim; arg coercion turns
  `"false"`/`"None"` into the right types once, before dispatch.
- **W2:** a handler returns `ToolResult` with no stdout side effect; the CLI renders a table from it;
  the MCP wraps it in `TextContent`.
- **W3:** the contract test (overlapping tools agree on schema/defaults); the canonical names resolve
  and the aliases still work; `update_conversation` toggles and the verb wrappers both reach the one
  handler.
- **W4:** REST endpoints return the same payloads after routing through the registry; the
  assistant-`tool_calls` round-trip is present in the payload.

---

## 7. Release

The W0 hotfixes ship as a patch as soon as they land (or fold into E-core's release if it is close).
The full structural collapse ships as its own minor version after E-core, user-gated as usual. The
release notes must call out any tool name changes and the one-release alias window.

---

## 8. Definition-of-done checklist

- [ ] W0: `_format_message` coercion + `validate_messages` check + test; provider-derived routing +
      test; `_NETWORK_TOOL_NAMES` deleted.
- [ ] W1: `ctk/core/builtin_tools.py` with co-located schema + handler per tool; `execute_ask_tool`
      reduced to a registry-lookup shim; arg coercion centralized; `PASS_THROUGH_TOOLS` removed.
- [ ] W2: `ToolResult` structured returns; Rich rendering moved to the CLI; `use_rich` sentinel gone;
      TUI and MCP render the result.
- [ ] W3: MCP/builtin/network projected from one spec set; five divergent tools unified with aliases;
      verb tools become wrappers; one validation regime; contract test green.
- [ ] W4: REST dispatches through the registry; `_format_message` round-trips `tool_calls`.
- [ ] W5: CLAUDE.md and MEMORY.md tool counts corrected.
- [ ] Suite green: mypy 0, coverage at or above 59, unit + integration pass.
