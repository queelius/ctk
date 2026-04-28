# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
make install          # pip install requirements + dev deps + editable install

# Testing
make test             # pytest tests/ -v (all tests)
make test-unit        # Unit tests only (tests/unit, -m unit)
make test-integration # Integration tests only (tests/integration, -m integration)
make coverage         # pytest --cov with HTML + term-missing reports
pytest tests/unit/test_database.py -v                              # Single file
pytest tests/unit/test_database.py::TestDatabase::test_save -v     # Single test

# Code quality
make format           # black + isort
make lint             # flake8 (max-line-length=100) + mypy
make clean            # Remove build artifacts and __pycache__
```

## Architecture Overview

### Data Model

**ConversationTree** (`ctk/core/models.py`) is the central data structure. All conversations are trees; linear chats are single-path trees, branching conversations (e.g., ChatGPT regenerations) preserve all paths. Key methods: `get_all_paths()`, `get_longest_path()`, `add_message()`.

**Tree primitives** (since 2.13.0): every "fork / branch / detach / promote / snapshot" UI op decomposes into one of six primitives. Five live on the tree itself: `delete_subtree(n)`, `prune_to(n)`, `copy()`, `copy_subtree(n)`, `graft(n, other)`. The sixth is DB-level `delete_conversation(id)`. Tests in `tests/unit/test_tree_primitives.py`. Add a new tree operation by composing these, not by reaching into `message_map` directly. Reasoning helpers `descendants_of(n)` and `ancestors_of(n)` are public for the same reason.

**Database** is a two-layer design:
- `ctk/core/db_models.py`: SQLAlchemy ORM models (`ConversationModel`, `MessageModel`, `TagModel`, `EmbeddingModel`, `SimilarityModel`).
- `ctk/core/database.py`: `ConversationDB`, the high-level wrapper (save, load, search, list). FTS5 full-text search with LIKE fallback. The "db_path" is a directory; the SQLite file lives at `<dir>/conversations.db` and an associated `media/` directory holds image attachments.
- `ctk/core/db_operations.py`: maintenance ops (merge, diff, intersect, filter, split, dedupe).
- `ctk/core/pagination.py`: cursor-based keyset pagination via `encode_cursor()` / `decode_cursor()`.

### CLI surface (since 2.12.0)

`ctk` with no subcommand opens the Textual TUI. The full top-level command list is intentionally small:

| Command | Purpose |
|---|---|
| `ctk` (no args) | Open the TUI on the configured DB |
| `ctk tui` | Same; alias for muscle memory |
| `ctk import` | Bulk import conversation exports |
| `ctk export` | Bulk export to file |
| `ctk query` | Filter/search with formatted output (table/json/csv) |
| `ctk sql` | Read-only SQL on the DB |
| `ctk db` | Maintenance: init, info, vacuum, backup, merge, diff, intersect, filter, split, dedupe, validate |
| `ctk net` | Build embeddings + similarity graph (analytical queries are MCP tools, see TUI) |
| `ctk auto-tag` | Bulk LLM-driven tagging |
| `ctk llm` | Provider config: providers, models, test |
| `ctk config` | Edit `~/.ctk/config.json` |

The previous per-conversation, per-library, per-view, chat REPL, and ad-hoc network analysis subcommands all moved into the TUI as bindings, slash commands, or MCP tool calls.

### Textual TUI (`ctk/tui/`)

`CTKApp` composes a tabbed sidebar and a chat main pane.

**Sidebar tabs**: All / Starred / Pinned / Recent / Archived. Search overlay at `/`. Implemented in `ctk/tui/sidebar.py`.

**Sidebar pagination** (since 2.14.0): cursor-based keyset pagination via `ConversationList.DEFAULT_PAGE_SIZE` (200 rows). The header shows `conversations · N loaded · more (Ctrl+L)` when more pages remain. `load_more()` appends the next page in place; switching mode/search resets the cursor and reloads. Backed by `db.list_conversations(cursor=…, page_size=…)` and `db.search_conversations(cursor=…, page_size=…)`, both of which return `PaginatedResult(items, next_cursor, has_more)` when `cursor` is not None.

**Main pane** (`ctk/tui/main_pane.py`): scrollable message bubbles, multi-line chat input at the bottom. Bubbles are focusable (`Tab` / `Shift+Tab` between them). Branch indicators with `[` / `]` to switch siblings.

**Bindings**:
- `q` quit; `Ctrl+R` refresh; `Ctrl+N` new conversation; `Ctrl+H` help modal
- `Ctrl+F` fork at focused message (truncate); `Ctrl+B` branch (preserve full tree)
- `Ctrl+D` delete subtree at focus; `Ctrl+E` extract subtree at focus; `Ctrl+P` promote focused path
- `Ctrl+L` load more conversations into the sidebar (when `more` indicator is showing)
- `Ctrl+S` toggle star; `Ctrl+G` system prompt modal; `Ctrl+O` attach file modal
- `[` / `]` previous/next sibling at focused message

**Slash commands** (`ctk/tui/slash.py`): typed in the chat input. Routed to dispatcher before the LLM. `/help` lists them all. Includes `/mcp`, `/model`, `/system`, `/title`, `/star`, `/pin`, `/archive`, `/tag`, `/untag`, `/export`, `/attach`, `/fork`, `/branch`, `/clone`, `/snapshot`, `/delete`, `/delete-subtree`, `/extract`, `/detach`, `/promote`, `/graft`, `/clear`, `/sql`, `/quit`.

**Modals** (`ctk/tui/modals.py`): `SystemPromptModal` (TextArea), `FilePathModal` (Input), `ConfirmModal` (y/n for destructive ops), `HelpModal` (bindings + slash + MCP). Both stateful modals capture the target conversation id at modal-open and re-resolve at callback time so a sidebar switch mid-modal can't apply the change to the wrong tree.

**Inline images** (`ctk/tui/images.py`): conversations imported with image attachments render below the message bubble via `textual-image`'s `AutoImage` (auto-detects Sixel / Kitty TGP / Halfcell). Handles three source types: existing local `path`, base64 `data` (decoded to a tracked temp file, cleaned up at shutdown), and relative `url` (resolved against the DB's parent dir, since ChatGPT exports use paths like `media/<uuid>.webp`). Protocol detection runs in `run()` before Textual takes over stdin (otherwise the OSC reply is stolen).

### Tools / MCP providers (`ctk/core/tools_registry.py`)

Everything the LLM can do is a tool, and every tool comes from a named provider, modeled on MCP servers:

- `ctk.builtin` is search/list/get/update/star/etc. Full registry in `ctk/core/tools_registry.py`.
- `ctk.network` is `find_similar_conversations`, `list_neighbors` (queries the persisted `SimilarityModel` table). Defined in `ctk/core/network_tools.py`.

`/mcp` in the TUI lists all providers and their tools. The TUI's chat worker fetches the flat tool list via `ctk.core.tools.get_ask_tools()` which calls `tools_registry.all_tools()` across providers. Adding a new provider: define it in a module that calls `register_provider(...)`, then ensure something imports the module before the TUI starts (e.g., from `ctk/tui/app.py:_register_builtin_providers`).

Tool execution is dispatched in `CTKApp._execute_tool` based on tool name: network tools route to `network_tools.execute_network_tool`, builtin tools to `cli.execute_ask_tool` (legacy dispatcher; will move to a dedicated module in a follow-up).

### Plugin System (`ctk/core/plugin.py`)

Auto-discovers importers/exporters via Python's normal import system (built-in plugins re-exported from each package's `__init__.py`). Registry pattern with `ImporterPlugin` / `ExporterPlugin` base classes. AST-based security validation runs only for user-installed plugins from non-trusted directories.

**Importers** (`ctk/importers/`): openai, anthropic, gemini, copilot, jsonl, filesystem_coding.

**Exporters** (`ctk/exporters/`): json, jsonl, markdown, html, hugo, csv, echo.

**HTML Exporter** (`ctk/exporters/html.py`) produces self-contained interactive HTML files with tree-aware chat continuation embedded in JS (`ConversationTree`, `ChatClient`, branch indicators, localStorage persistence). Tests: `tests/unit/test_html_chat.py`.

### LLM Integration (`ctk/llm/`)

Single `LLMProvider` abstract base + one concrete impl (`OpenAIProvider`) wrapping the official `openai` SDK. Targets any OpenAI-compatible endpoint (OpenAI, Azure, OpenRouter, vLLM, llama.cpp server, LM Studio, Ollama via `http://localhost:11434/v1`). Configure via `~/.ctk/config.json` under `providers.openai.{base_url,default_model,timeout}`; build instances via `ctk.llm.factory.build_provider()`.

### Other Key Components

**Fluent Python API** (`ctk/api.py`): `CTK` class with builder pattern, e.g. `CTK("db.db").search("python").limit(10).get()`.

**MCP Server** (`ctk/interfaces/mcp/`): exposes a subset of CTK as a real MCP server for use by external clients. 7 tools: `search_conversations`, `get_conversation`, `update_conversation`, `get_statistics`, `find_similar`, `semantic_search`, `execute_sql`. Entry point: `python -m ctk.mcp_server`.

**REST API** (`ctk/interfaces/rest/api.py`): Flask-based read/write REST surface. Defaults to `127.0.0.1` because there's no auth. Used for the HTML viewer and any external integrations.

**Shared Utilities**:
- `ctk/core/formatting.py`: `format_conversations_table()` (Rich tables with emoji flags)
- `ctk/core/db_helpers.py`: `list_conversations_helper()`, `search_conversations_helper()`
- `ctk/core/conversation_display.py`: `show_conversation_helper()`
- `ctk/core/tools.py` + `tools_registry.py` + `network_tools.py`: tool definitions and provider registry
- `ctk/core/prompts.py`: `get_ctk_system_prompt()`
- `ctk/core/utils.py`: `parse_timestamp()`, `try_parse_json()`
- `ctk/core/input_validation.py`: `validate_conversation_id()`, `validate_file_path()`
- `ctk/core/constants.py`: timeouts, limits, widths

## Critical Notes

### Gotchas
- **CLI no-subcommand path**: `ctk` opens the TUI, requires `database.default_path` in config (defaults to `~/.ctk`) or `--db`.
- **`ConversationDB(":memory:")`** must be special-cased to use true in-memory SQLite (not a file at `:memory:/conversations.db`).
- **`ConversationModel.updated_at`** has `onupdate=func.now()`. The ORM overwrites explicit values; use raw SQL in tests when you need to force timestamps.
- **`ConversationTree.add_message()`** overwrites `metadata.updated_at` to `datetime.now()`.
- **Python 3.12 SQLite datetime**: `isoformat()` uses `T`, SQLite stores with space. Use `strftime("%Y-%m-%d %H:%M:%S")` for cursor comparisons.
- **Importer model detection**: sort `model_map.items()` by key length DESC to avoid short-key matches (gpt-4 vs gpt-4-turbo).
- **`textual-image` protocol detection** runs at module import time and is broken once Textual takes over stdin. `ctk/tui/app.py:run()` calls `_detect_image_protocol_eagerly()` before mounting the app.
- **Modal callbacks must capture conversation id at open time** (see `_on_system_prompt_saved`, `_on_file_attached`). Otherwise a sidebar switch mid-modal applies the change to the wrong tree.

### Exception Handling
- Never use bare `except:`; always specify exception types.
- `except Exception:` acceptable only in cleanup/finally blocks with logging.
- HTTP: `requests.exceptions.RequestException`; JSON: `json.JSONDecodeError`; Files: `(IOError, OSError)`.

### Constants (`ctk/core/constants.py`)
Import from here instead of hardcoding. Key values: `DEFAULT_TIMEOUT` (120s), `HEALTH_CHECK_TIMEOUT` (5s), `DEFAULT_SEARCH_LIMIT` (1000), `MAX_QUERY_LENGTH` (10000).

### Natural-Language Tool Calls
Boolean filters in tool calls must only be included when explicitly present. Pattern:
```python
starred_val = tool_args.get('starred')
starred = to_bool(starred_val) if starred_val is not None else None
```

### Testing
- Unit tests in `tests/unit/`, integration tests in `tests/integration/`.
- ~1600 unit tests pass after the 2.12.0 cuts.
- Coverage threshold: 59% (enforced in pytest.ini).
- Markers: `unit`, `integration`, `slow`, `requires_ollama`, `requires_api_key`. Skip with `-m "not requires_ollama"`.

### Release Process
- Version bumps: `ctk/__init__.py`, `setup.py`, `CITATION.cff`.
- Build: `rm -rf dist/ build/ *.egg-info && python -m build`.
- Publish: `twine check dist/* && twine upload dist/*`.
- Tag: `git tag -a v<version> -m "..."` then `git push --follow-tags`.
- PyPI package name: `conversation-tk`; entry point: `ctk=ctk.cli:main`.
