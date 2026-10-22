# Whole-codebase review: bugs, design, simplification (2026-10-21)

Scope: all of `ctk/` (~33K LOC) at `b7d089e` + the uncommitted G lint-sweep diff. Five parallel
subsystem reviews (DB; models/tools/network; TUI/LLM; CLI/API/packaging; importers/exporters/
plugins). "C" = reproduced by running code (scratch venv, temp DBs, HOME sandboxed); "P" = plausible
from reading. Every P0 marked C† was independently re-reproduced during synthesis.

Baseline: 2140 unit tests pass (with `mcp<2`). Nothing below is caught by the suite.

---

## P0: data loss, destruction, security (hotfix: 2.20.1)

| # | Where | Defect | |
|---|---|---|---|
| 1 | `setup.py:37`, `requirements.txt` | `mcp>=1.0.0` resolves to mcp 2.x, which removed `Server.list_tools()`/`call_tool()` decorators: `import ctk.mcp_server` crashes on any fresh install. Pin `<2` now; port later. | C† |
| 2 | `cli_db.py:693-695` | `ctk db init X.db --force` `rmtree`s the *parent dir* of X.db; with no path it wipes `~/.ctk` (config, backups). | C† |
| 3 | `builtin_tools.py:1001` | `execute_sql` sets `PRAGMA query_only=ON` on the pooled connection and never resets: every later write in the process fails (MCP `update_conversation`, TUI star/save). | C† |
| 4 | `database.py:593-680` + `db_models.py:68` | `save_conversation` autoflush + `onupdate=func.now()` overwrites `updated_at` with UTC now on every save, so all imports lose real recency. | C† |
| 5 | `database.py:776,832` | `load_conversation` re-stamps `updated_at` to local now (`add_message`); `merge NEWEST/OLDEST` and dedupe keepers pick wrong versions. | C† |
| 6 | `exporters/html.py:404-409`, `~2516-2557`, `3504`, `4366-4381`, `2771` | Stored XSS: only lowercase `</script>` escaped; `marked.parse` → `innerHTML` unsanitized; gallery attrs unescaped; `escapeHtml` skips `"`. | C† (a), C (rest) |
| 7 | `importers/openai.py:224-247`, `exporters/html.py:205-226`, `exporters/hugo.py:356-369` | Crafted import file exfiltrates local files: `file-service://../x` becomes a glob outside the export dir; abs/`../` image paths are base64-embedded / copied into bundles. | C |
| 8 | `exporters/echo.py:93`, `exporters/hugo.py:211` | Path traversal via conversation id (ids come straight from import files). | C |
| 9 | `exporters/html.py:66-71,107-113` | HTML export copies *all* DB media regardless of which conversations were selected. | C |
| 10 | `cli.py:1644`, `tui/slash.py:680` | "Read-only" `ctk sql` / `/sql` writable via `ATTACH ... ; DELETE ...; COMMIT`. | C |
| 11 | `tui/app.py:307-341,783-899` | Switching conversation mid-turn: reply saved into the *other* conversation / overwrites its last assistant message; Ctrl+N mid-turn loses both messages. | C |
| 12 | `database.py:1754` + `db_models.py:398-408` | `delete_conversation` raises IntegrityError for any conversation that has similarity rows (no cascade on backrefs). | C |
| 13 | `api.py:584,620` | `QueryBuilder.where(starred=True)` silently drops unknown keys, so `.where(...).delete_all()` deletes unmatched conversations. | C |
| 14 | `core/config.py:77,86` | Shallow `DEFAULTS.copy()` + in-place `_deep_merge` poisons defaults (`config reset` no-ops); invalid JSON → defaults, next `config set` overwrites user file. | C |
| 15 | `llm/factory.py:95` | `OPENAI_API_KEY` sent to every profile's endpoint (incl. plain-http third-party hosts). | C |
| 16 | `db_operations.py:710-716` | In-place dedupe bulk-deletes and orphans messages/tags/embeddings/FTS rows. | C |

## P1: core features silently broken

**DB / search**
- Cursor pagination drops same-second rows: cursor uses `%H:%M:%S`, ORM stores `.ffffff` (`database.py:1084,1660`). Sidebar `load_more` affected. C
- FTS candidate pool capped (`limit+offset+100`, unordered) *before* filters, so `search("python", starred=True)` misses matches (`database.py:1512-1539`). C
- FTS escaping is a blacklist: `? . ' , #` → syntax error → swallowed → LIKE on whole phrase → `[]` for `"node.js"`, `"don't"`, `"c#"` (`database.py:427-479`). C
- `ctk query` hides every branching conversation (`has_branches=False` default treated as "linear only", `db_helpers.py:156,217`, `cli.py:562`). C
- `message_count`/`min_messages` wrong under multi-tag join or LIKE content search. C
- Nested DB call inside `iter_conversations` → `DetachedInstanceError` (`scoped_session` shared). C
- Re-save is O(n) FTS scans per message (UNINDEXED `message_id`): 7.3 s to re-save 250 msgs in a 50K-msg DB; TUI saves whole tree per turn. C
- `db filter --tags a,b` / `DatabaseOperations.filter` never matches (same-alias join). C
- `save_conversation` never writes `starred_at/pinned_at/archived_at`, so stars are lost on export/import. C
- `duplicate_conversation` copies slug, leaves stale `root_message_ids` (`is_branching=0`), `KeyError` on dangling parent. Same slug copy in `tree.copy()`, so `/clone /snapshot /branch /extract` create slug collisions. C

**TUI**
- Every `refresh_list` re-highlights row 0 and *opens* it (`sidebar.py:149-159`). C
- Ctrl+F / Ctrl+B / `/fork` / `/branch` silently do nothing (new tree never saved; reload restores original). Existing test hand-simulates the steps. C
- `/tag`, `/untag` reverted by the next save (DB written, in-memory tags not). C
- Star/pin/archive toggles can't be turned off (stale `metadata.starred_at`). C
- Search can't be cleared (`refresh_list(search=None)` keeps old search). C
- After `[`/`]` sibling switch, new message attaches to the longest path, not the visible one (`app.py:483-487`). C
- Escape doesn't cancel in `--no-tools` mode; `/system` shows an attached file as the system prompt. C
- LLM offered `execute_shell_command` (always fails) and an unconfirmed `delete_conversation`. C/P

**Tools / MCP**
- `execute_sql` `?` placeholders don't work (binds a dict). C
- MCP legacy aliases for `get_conversation`/`update_conversation` are dead: the SDK validates `conversation_id` against the schema before the alias rewrite. Tests call `handle_tool` directly and miss it. C
- MCP `get_conversation` no longer returns content (≤5 msgs × 100 chars even with `show_messages`). C
- `tag_conversation(tags="python")` adds tags `p,y,t,h,o,n`; `list_conversations` passes `"false"` through as truthy. C

**Embeddings / network: the pipeline is broken end to end**
- `ctk net embeddings` passes `ConversationSummary` to the embedder → every one fails, prints "Embedded 0", still saves a "current" session, exits 0 (`cli_net.py:99-160`). C
- `ctk net links` never persists similarities (`compute_similarity_matrix` doesn't save), so `list_neighbors` is always empty and `find_similar` always falls back. C
- Embedder embeds `str(MessageContent(...))` repr, not text (`similarity.py:321-344`). C
- `semantic_search` refits TF-IDF per query, so vocab and vector indices are misaligned ("aardvark sourdough" finds nothing) (`network_tools.py:284-301`). C
- Edges depend on node order (`similarity.py:766-790`); titles "Unknown" for older/archived (`network_tools.py:247-260`). C

**Importers / exporters**
- OpenAI importer drops all non-`parts` content. On `dev/openai-db`: 3,440 `code`, 1,543 `execution_output`, 798 browsing, 681 quote, 530 user-context, 158 error messages are empty; model slug discarded (1,122 convs show "ChatGPT"). C
- `ctk export -f json` drops metadata by default (`include_metadata` store_true overrides exporter default True). C
- CTK's own exports misdetected on re-import (anthropic-style → gemini, generic → jsonl with `None` text, ECHO → gemini root-only). C
- JSONL round trip loses id/title (nested under `metadata`), tool calls, images; `format="chat"` mis-pairs. C
- Naive-local (epoch) vs aware-UTC (ISO) timestamps across importers; HTML exporter `TypeError` on mixed. C
- One malformed record aborts a whole import (openai bad tool JSON, anthropic null attachment, null roles). C
- Anthropic cross-message `tool_result` dropped; Hugo front matter invalid YAML on `"` or trailing `\`. C

**CLI**
- Top-level `--db/--model` overwritten by subcommand defaults: `ctk --db X import f` prints "Imported 4", saves nothing, exits 0. C
- `ctk db info bk/snap.db` reports the *live* DB's count (any `*.db` → parent dir). Typo'd paths silently created as empty DBs and "validated". C
- `ctk export` never exports archived; `--limit` applied before filters; `--show-tree` can't be disabled. C
- `ctk auto-tag` crashes on untitled conversations, ignores `--provider`, exits 0 when all LLM calls fail. C

**Packaging**
- `python_requires>=3.8` + CI matrix 3.8/3.9, but deps need ≥3.10 (`textual-image` current ≥3.12). `release.yml` calls `test.yml`, which lacks `on: workflow_call`, so release can't run; PyPI upload `continue-on-error: true`.

---

## Design: cross-cutting themes

Several reviewers converged on the same root causes. Each theme lists the bugs it would kill.

1. **One `ConversationFilter` dataclass.** Filter kwargs are re-declared in 5 DB methods (with
   different semantics: `model` exact vs ILIKE, `has_branches` missing from `count`), rebuilt in 5
   CLI commands, post-filtered in Python in `api.py`, and raw-ORM'd in `db_operations`. One dataclass +
   one `_build_summary_query(filter, text=None)` + one `add_filter_args(parser)`. FTS becomes an
   `IN (subquery)` inside that query (fixes FTS-cap, count-under-join, tag-AND, has_branches, export
   limit-before-filter, api where-drop).
2. **One clock.** SQLite `CURRENT_TIMESTAMP` (UTC), Python `now()` (local naive), `parse_timestamp`
   (aware UTC for ISO, local naive for epoch). Drop `onupdate`, Python-side defaults only, a single
   `utils.now()`, normalize in `parse_timestamp`. Fixes P0-4/5, merge NEWEST, HTML TypeError.
3. **One mutation path, one in-memory truth.** TUI slash commands and bindings write the DB directly
   (`db.add_tags`, `db.star_conversation`) and leave `_current_tree` stale, so the next save reverts.
   Route through `update_conversation` (the canonical core from C2) and reload metadata. A TUI
   `ChatTurn` object owning target tree/worker/widgets fixes the mid-turn race (P0-11) and the
   no-tools cancel. `set_system_prompt` / `splice_out` become tree primitives (app.py currently
   pokes `message_map` directly, against the CLAUDE.md rule).
4. **One identifier resolver** (currently 5: `resolve_identifier`, `resolve_conversation`, inline
   scan in `_do_get_conversation`, `network_tools._resolve_id`, `show_conversation_helper`) with
   different precedence; and a unique index on `slug` (copies currently collide).
5. **One DB-path resolver** in core (`resolve_db_dir(path, must_exist)`), called by `ConversationDB`;
   currently 4 copies, root of P0-2 and the wrong-DB / typo-creates-DB bugs.
6. **One read-only SQL executor** (3 copies, all bypassable): `sqlite3` `set_authorizer` allowing
   only SELECT/READ/FUNCTION.
7. **One media resolver** `resolve_media(db_dir, ref) -> Optional[Path]` with containment check,
   used by importers, html, hugo, `tui/images.py`. Fixes P0-7/9 once.
8. **Tool policy on the tool, not in prose.** One `Tool(name, schema, handler, pass_through,
   destructive, available_in)` type for both providers (network tools are still dicts + if-chain;
   TUI and projection both branch on the string `"ctk.network"`); `registry.execute()` validates args
   from `input_schema` once (replaces 4 ad-hoc validators incl. the unused
   `interfaces/mcp/validation.py`) and enforces confirmation for `destructive`.
9. **Embedding identity.** `EmbeddingSession` owns config hash + the fitted vectorizer (persist it;
   `TFIDFEmbedding.save/load` exist); embeddings reference their session; staleness from
   `updated_at`. Fixes refit-per-query, stale mixed-vocab caches, wrong query model.
10. **Format detection by confidence score**, parse once, highest wins; a fidelity-matrix test that
    every exporter style is claimed by the intended importer (or none).
11. **Typed exporter options.** One options dataclass per exporter, argparse generated from it,
    unknown keys rejected, sanitization applied centrally (today `--sanitize` only affects JSONL; the
    sanitizer itself redacts "bypass" and misses `sk-proj-` keys).
12. **Composite message PK `(conversation_id, id)`** instead of `"{conv}::{msg}"` string concat;
    enables diff-save instead of delete-all/reinsert (fixes the quadratic FTS re-save).
13. **Decide PostgreSQL**: advertised, broken (`.astext` on generic JSON, migrations/FTS skipped). Drop it.
14. **Plugin "sandbox" is a denylist** (bypassed by `from os import system`, aliasing, importlib,
    `startswith` dir check). Treat plugins as trusted code via entry points; drop the validator.

---

## Simplification: deletable or collapsible code

Dead = no production importer/caller (grep-verified across `ctk/`, `tests/`, `examples/`).

| Item | LOC | Notes |
|---|---|---|
| `cli.py` dead handlers (`cmd_list`, `cmd_search`, `cmd_stats`, `cmd_tags/models/sources`, `cmd_show`…`cmd_duplicate` incl. `cmd_tree_view/paths`) | ~740 | no dispatch entries |
| `core/tree.py` navigator (+ `test_tree.py` 1072) | 606 | only `show_conversation_helper`; disagrees with `ConversationTree` on roots/order/path numbering |
| `core/prompts.py`, `core/conversation_index.py`, `core/network_analysis.py`, `interfaces/base.py` | ~1270 | test-only |
| `llm/mcp_client.py` | 458 | no importers; `remove_server` is broken anyway |
| `ctk/taggers/*` | ~720 | test-only; `cmd_auto_tag` hand-rolls its own. Wire in *or* delete |
| `importers/filesystem_coding.py` | ~400 | unreachable from CLI (gets contents, not paths); 3 stubs |
| `core/plugin.py` third-party loading + AST validator | ~380 | test-only (see design 14) |
| `database.py` dead methods (`find_by_slug`, `get_distinct_*`, `delete_embeddings`, `delete_similarities`, embedding-session getters, `delete_current_graph`, hierarchical-tag helpers, `_has_fts5`) | ~280 | 0 callers |
| `database.py` `iter_conversations`/`iter_search_results` | ~280 | test-only, broken (nested session) |
| `database.py` duplicated text predicate / flag filters / star-pin-archive trio / FTS escape pair | ~230 | collapse into filter builder + `_set_timestamp_flag` |
| `builtin_tools.py` stub tools (`execute_shell_command`, `show_conversation_tree`, `auto_tag_conversation`) + unused `ToolContext`/`ToolResult` fields | ~150 | |
| `builtin_tools.py` 7 verb tools → table over `_update_core`; `list_tags/sources/models` → `get_statistics` | ~330 | |
| `duplicate_conversation` ×2 (db + builtin) → `tree.copy()` | ~80 | |
| `similarity.py` unused (`detect_communities`, `find_similar`, `to_hash`, gephi/cytoscape export, dup DOT_PRODUCT branch) | ~200 | |
| TUI no-tools path (`StreamDone`, `_stream_worker`, `on_stream_done`, `stream_chat`) → tools path with `tools=None` | ~110 | also fixes no-tools cancel |
| `LLMProvider` unused methods (`get_model_info`, `extract_tool_calls`, `truncate_context`, `count_tokens`, `name`) | ~70 | |
| `cli.py` dispatch dicts → `set_defaults(func=...)`; `execute_ask_tool` shim; export option `hasattr` chain | ~120 | TUI stops importing the CLI module |
| MCP leftovers (`mcp_server` re-exports, `_resolve_get_db` test indirection, unused validation module) | ~300 | |
| Exporter duplication (json path loop ×3, role maps ×5 → `MessageRole`, branch checks ×3 → `count_branches`, module-level `exporter = X()` ×7, html `export_to_file` branches) | ~250 | |
| `PathModel` table (needs migration 5 `DROP TABLE paths`) | ~50 | |

**Total: roughly 6,000 source LOC (~18%)**, before the design consolidations.

---

## Test gaps that let these through

No test: does a write after `execute_sql`; checks `updated_at` survives save/load; runs MCP calls
through the SDK's schema validation; calls `cmd_embeddings`/`cmd_links` or any `cli_db`/`cli_net`/
`cli_config`/`cli_llm`/`cmd_sql` command; uses sub-second cursor timestamps; deletes a conversation
with similarities; filters by two tags; searches punctuation; exercises the TUI stream worker,
toggles, fork/branch actions (the existing fork test hand-simulates), mid-turn switching, or search
clearing; escapes HTML; re-imports each export format via auto-detect; uses ids containing `/`/`..`;
uses the real ChatGPT `code`/`execution_output` shape; has deep chains (>1000; recursive
`get_all_paths` hits RecursionError), cycles, or orphans. 10 test files use `:memory:` DBs, which
never exercise FTS.

---

## Proposed sequencing

1. **2.20.1 hotfix (P0 1-16).** Each is small and local; add a regression test per item. Commit the
   in-flight G lint sweep first so the hotfix diffs stay reviewable.
2. **H. Delete dead code** (the table above, minus anything a P1 fix needs). Pure deletion, low risk,
   shrinks the surface every later step touches.
3. **I. Filter/clock/identity consolidation** (design 1, 2, 4, 5, 6, 12) with the DB/search P1s.
4. **J. TUI turn ownership + single mutation path** (design 3) with the TUI P1s.
5. **E-scale, reframed**: the embeddings pipeline must first *work* (design 9 + network P1s) before
   it is scaled.
6. **K. Import/export fidelity**: media resolver, detection scoring, typed options, OpenAI non-`parts`
   content (design 7, 10, 11).
7. **Packaging**: `pyproject.toml`, `requires-python>=3.10`, CI matrix, `workflow_call`, port to mcp 2.
