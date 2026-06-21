# Sub-project C2: Tool Surface Unification (Design)

**Date:** 2026-06-21
**Status:** Design (decisions approved in discussion; pending spec review)
**Part of:** [CTK Improvement Program](2026-06-04-improvement-program-roadmap.md), sub-project C, phase 2
**Supersedes:** the W3-W5 portion of `2026-06-18-unified-tool-surface-design.md` (revised in light of C1, which made `builtin_tools.py` the canonical layer).

---

## 1. Goal and definition of done

C1 collapsed the builtin tool executor into a self-dispatching `ctk/core/builtin_tools.py` (each tool co-locates schema + handler; `ToolResult` returns). C2 finishes the job: make that registry the ONE source of truth for every tool surface, so the MCP server projects from it rather than maintaining a parallel, divergent definition, and retire the unused REST surface entirely.

**Decisions taken with the user:**

1. **Builtin is canonical; the MCP server projects from it.** The MCP `types.Tool` list and dispatch are generated from the registry; the MCP handler files stop hand-maintaining schemas.
2. **`update_conversation` (toggle) is the canonical mutation;** the seven verb tools (star/unstar/pin/unpin/archive/unarchive/rename) delegate to it.
3. **Fold the MCP-only tools** (`execute_sql`, `semantic_search`) into the registry as real provider tools.
4. **Remove the REST interface** as a planned feature (delete it; do not migrate it). It has no live consumer.

**Definition of done:**

1. The MCP server exposes a curated tool set whose `types.Tool` schemas are GENERATED from the registry providers, and whose dispatch routes through `execute_builtin_tool`/`execute_network_tool`, wrapping the result into `TextContent`. No tool's schema is hand-written twice. A contract test asserts every MCP-projected tool's schema equals the registry's.
2. The five tools that were defined twice with divergent schemas (search_conversations, get_conversation, get_statistics, find_similar/find_similar_conversations, update_conversation) have ONE schema each, the builtin one. The MCP server keeps a thin one-release alias map for the old MCP parameter names so existing MCP clients do not break immediately.
3. `execute_sql` and `semantic_search` are registry tools (a provider owns each), so the MCP server projects them like everything else and the TUI chat path can reach them too.
4. `update_conversation(conversation_id, starred?, pinned?, archived?, title?)` is a registry tool implementing the mutation once; the seven verb handlers are thin wrappers that call the same core.
5. `ctk/interfaces/rest/` is deleted, along with `examples/rest_server.py` and the REST tests; the Flask dependencies are dropped if nothing else uses them; CLAUDE.md and the docs no longer describe a REST surface.
6. `_format_message` round-trips assistant `tool_calls` so a strict OpenAI-spec server accepts the multi-turn tool history.
7. CLAUDE.md and MEMORY.md tool-count and surface descriptions are corrected.
8. Suite green: mypy 0, coverage at or above 59, all unit + integration tests pass; the projection layer, the folded tools, and the mutation refactor have tests.

---

## 2. Empirical grounding (current state, post-C1)

- **builtin_tools (canonical):** 26 self-dispatching `_do_<name>(ctx: ToolContext) -> ToolResult` handlers, each a `BuiltinTool(name, description, input_schema, handler, pass_through)` with `as_schema_dict()`. `execute_builtin_tool(db, name, args, ...) -> str` dict-dispatches. `ctk.network` (network_tools.py) is the same shape for find_similar_conversations + list_neighbors.
- **MCP server (independent):** `ctk/interfaces/mcp/handlers/{search,conversation,metadata,analysis,sql}.py` each export a `TOOLS: list[types.Tool]` and `HANDLERS: dict[str, async handle_X(arguments, db) -> list[types.TextContent]]`, aggregated in `handlers/__init__.py` into `ALL_TOOLS` (7) + `ALL_HANDLERS`. Five of the seven duplicate builtin tools with divergent schemas (get_conversation: `id`/`include_content` vs `conversation_id`/`show_messages`; find_similar: `id`/`top_k`/`threshold` vs network find_similar_conversations `conversation_id`/`limit`/`min_similarity`; search adds `cursor`; etc.). Two (`execute_sql`, `semantic_search`) have no registry equivalent. The server uses its own `mcp/validation.py`.
- **REST (unused):** `ctk/interfaces/rest/api.py` is a Flask surface with ~30 endpoints and 76 direct `db.*` call sites. The ONLY instantiation is `examples/rest_server.py`; there is no `ctk` subcommand to serve it; the HTML exporter is self-contained and does not call it. CLAUDE.md's "used for the HTML viewer" line is stale. No live consumer exists.
- **`_format_message`** (openai.py): coerces content (fixed in 2.18.0) but does not reattach the assistant's `tool_calls` on the multi-turn round-trip; harmless against lenient/ollama endpoints, latent against strict OpenAI.

---

## 3. Architecture and workstreams

### W1: MCP projects from the registry (`ctk/interfaces/mcp/`)

Replace the per-handler schema+handler files with a generic projection driven by the registry:

- A `MCP_TOOLSET` allowlist names the curated subset the MCP server exposes (the current 7 names, mapped to their canonical registry names). The MCP `types.Tool` list is built by looking up each name in the registry (`tools_registry.provider_for_tool` + the provider's tool dict) and converting `input_schema` to `inputSchema` (the only shape difference).
- One generic `async def handle_tool(name, arguments, db) -> list[types.TextContent]` applies the alias map (see below), dispatches through `execute_builtin_tool`/`execute_network_tool` (routing by `provider_for_tool(name)`), and wraps the returned string (or a `ToolResult.data` JSON payload when present) into a single `TextContent`. This is the same routing the TUI already uses.
- **Alias map:** a small `{old_mcp_param: canonical_param}` table per tool (e.g. `id -> conversation_id`, `include_content -> show_messages`, `top_k -> limit`, `threshold -> min_similarity`) applied to incoming arguments, and `find_similar -> find_similar_conversations` as a tool-name alias. The alias map is documented as a one-release compatibility shim with a removal note.
- The `handlers/{search,conversation,metadata,analysis,sql}.py` schema/handler bodies are deleted; `validation.py` rules are folded into the shared coercion the registry handlers already do (one validation regime). `server.py` keeps its `@server.list_tools()`/`@server.call_tool()` wiring but sources from the projection.

### W2: Fold the MCP-only tools into the registry

- `semantic_search` becomes a `ctk.network` (or analysis) provider tool: move its handler logic into `network_tools.py` (it is embedding/similarity work, the same family as find_similar_conversations), schema co-located, registered.
- `execute_sql` becomes a `ctk.builtin` tool (read-only SQL via `PRAGMA query_only`, the existing behavior): a handler in `builtin_tools.py`, schema co-located. It is `pass_through=True` (its output is shown, not re-reasoned).
- Once registered, both are projected to MCP by W1 like every other tool, and the TUI chat path can call them.

### W3: Canonical `update_conversation` mutation

- Add `update_conversation` as a registry tool: `update_conversation(conversation_id, starred?, pinned?, archived?, title?)`. Its handler is the single mutation point (it calls `db.star/pin/archive/update_conversation_metadata` for whichever fields are present, with the boolean semantics the verb tools used).
- Refactor the seven verb handlers (star/unstar/pin/unpin/archive/unarchive/rename) to be thin wrappers that build the appropriate `update_conversation` args and call the shared core, so the mutation logic lives once. The verb tools STAY registered (the LLM keeps its verb vocabulary); only their implementation collapses.
- Net LLM-facing change: one new tool (`update_conversation`). The C1 golden digest snapshot is intentionally updated for this (a real new capability, not a drift).

### W4: Remove the REST interface

- Delete `ctk/interfaces/rest/` (api.py, the validation module, `__init__.py`), `examples/rest_server.py`, `tests/unit/test_rest_api.py`, `tests/unit/test_rest_validation.py`.
- Drop `flask` and `flask_cors` (and any REST-only dep) from `setup.py`/`requirements.txt` AFTER confirming nothing else imports them (grep). If something else uses Flask, keep it.
- Remove the REST API section from CLAUDE.md and the REST references in `docs/advanced/architecture.md`; fix the stale "used for the HTML viewer" claim.

### W5: `_format_message` round-trip + doc corrections

- `_format_message`/the TUI tool loop reattach the assistant message's `tool_calls` in the multi-turn history so a strict OpenAI server accepts the follow-up tool message. Add a provider test asserting the assistant turn carrying tool_calls is serialized with them.
- Correct CLAUDE.md (the MCP "7 tools" / builtin "legacy dispatcher" lines, now stale post-C1 and post-projection) and the MEMORY.md "13 tools" note.

---

## 4. Out of scope (deferred)

- External MCP federation (consuming third-party MCP servers as providers). The registry is designed for it; wiring real external providers is later.
- Any new tool capability beyond `update_conversation` and the two folded tools.
- A general-purpose, supported HTTP API. REST is removed, not replaced; if a real HTTP need arises later it is a fresh, scoped project.

---

## 5. Testing

- **Projection contract test:** for every name in `MCP_TOOLSET`, the MCP `types.Tool.inputSchema` equals the registry tool's `input_schema` (after the canonical-name reconciliation), so the two can never drift again.
- **MCP dispatch tests:** calling each projected tool through the MCP `call_tool` path returns the same content the registry handler produces (a `TextContent` wrapping `execute_*` output); the alias map maps old MCP params to canonical ones (e.g. `id` still works, mapped to `conversation_id`).
- **Folded tools:** `execute_sql` enforces read-only and returns rows; `semantic_search` returns ranked results; both are reachable via the registry and via MCP.
- **Mutation:** `update_conversation` sets each field correctly; each verb tool produces the same effect and string it did before (wrappers preserve behavior); the C1 RESOLVING_TOOLS net still passes.
- **REST removal:** the suite is green after deletion (no dangling imports); a guard that `ctk.interfaces.rest` no longer exists / is not imported anywhere.
- **`_format_message`:** an assistant message with tool_calls round-trips with them in the payload.

---

## 6. Release

C2 has user-facing changes (a new `update_conversation` tool, the MCP schema reconciliation with one-release aliases, and the REST removal), so it ships as a minor version bump (2.20.0) after merge, user-gated. The release notes must call out: the REST interface removal (a removed feature), the new `update_conversation` tool, and the MCP parameter aliases (and that the old names are deprecated for one release).

---

## 7. Definition-of-done checklist

- [ ] MCP `types.Tool` list + dispatch generated from the registry; per-handler schema files deleted; one generic projection + alias map; contract test green.
- [ ] `execute_sql` + `semantic_search` are registry provider tools; MCP projects them; TUI can reach them.
- [ ] `update_conversation` registry tool is the single mutation core; the seven verb tools are wrappers over it.
- [ ] `ctk/interfaces/rest/` + `examples/rest_server.py` + REST tests deleted; Flask deps dropped if REST-only; docs de-RESTed.
- [ ] `_format_message` round-trips assistant `tool_calls`; provider test.
- [ ] CLAUDE.md + MEMORY.md tool/surface descriptions corrected.
- [ ] Suite green: mypy 0, coverage at or above 59, unit + integration pass.
