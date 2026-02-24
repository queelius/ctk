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

**ConversationTree** (`ctk/core/models.py`) — Central data structure. All conversations are trees; linear chats are single-path trees, branching conversations (e.g., ChatGPT regenerations) preserve all paths. Key methods: `get_all_paths()`, `get_longest_path()`, `add_message()`.

**Database** — Two-layer design:
- `ctk/core/db_models.py`: SQLAlchemy ORM models (`ConversationModel`, `MessageModel`, `TagModel`, `PathModel`). Tables: `conversations`, `messages`, `tags`, `paths`, `embeddings`, `similarities`.
- `ctk/core/database.py`: `ConversationDB` — high-level database operations (save, load, search, list). FTS5 full-text search with LIKE fallback.
- `ctk/core/db_operations.py`: Database-level operations (merge, diff, intersect, filter, split, dedupe).
- `ctk/core/pagination.py`: Cursor-based keyset pagination via `encode_cursor()`/`decode_cursor()`.

### CLI Architecture

Top-level commands in `ctk/cli.py`: `import`, `export`, `view`, `plugins`, `auto-tag`, `chat`, `say`, `query`, `sql`

Subcommand groups (each in its own module):
- `ctk conv` (`cli_conv.py`): show, tree, paths, star, pin, archive, title, delete, duplicate, tag, untag, say, fork, reply, export, info, summarize
- `ctk lib` (`cli_lib.py`): list, search, stats, tags, models, sources, recent, count
- `ctk db` (`cli_db.py`): init, info, vacuum, backup, merge, diff, intersect, filter, split, dedupe, stats, validate
- `ctk net` (`cli_net.py`): embeddings, similar, links, network, clusters, neighbors, path, central, outliers, export
- `ctk llm` (`cli_llm.py`): provider/model management
- `ctk config` (`cli_config.py`): configuration management

### Shell-First TUI (`ctk/integrations/chat/tui.py`)

Two-mode system entered via `ctk chat`:
1. **Shell mode** (default): Unix-like VFS navigation
2. **Chat mode**: Interactive LLM conversation with streaming, entered via `chat` command

**VFS** (`ctk/core/vfs.py`, `ctk/core/vfs_navigator.py`):
- Conversations as directories under `/chats/<conv_id>/`, messages as `m1/m2/m3` subdirs
- Virtual directories: `/starred/`, `/pinned/`, `/archived/`, `/tags/`, `/recent/`, `/source/`, `/model/`, `/views/`
- Prefix resolution: `cd 7c8` resolves to full UUID

**Commands** (`ctk/core/commands/`):
| Module | Commands |
|--------|----------|
| `navigation.py` | cd, ls, pwd |
| `unix.py` | cat, head, tail, echo, grep |
| `search.py` | find (-name, -content, -role, -type, -i, -limit, -l) |
| `visualization.py` | tree, paths |
| `organization.py` | star, unstar, pin, unpin, archive, unarchive, title |
| `chat.py` | chat, complete |
| `tree_nav.py` | Tree navigation |
| `session.py` | Session management |
| `settings.py` | Settings commands |
| `database.py` | Database commands |
| `llm.py` | LLM commands |
| `semantic.py` | semantic (search, similar), index (build, status, clear) |

Pipe support (`ls | grep pattern | head 5`), env vars (`$CWD`, `$MODEL`, `$PROVIDER`, `$CONV_ID`), tab completion.

**CommandResult pattern**:
```python
@dataclass
class CommandResult:
    success: bool
    output: str = ""
    error: str = ""
    pipe_data: Optional[str] = None
```

### Plugin System (`ctk/core/plugin.py`)

Auto-discovers importers/exporters in `ctk/integrations/`. Registry pattern with `ImporterPlugin`/`ExporterPlugin` base classes.

**Importers** (`ctk/integrations/importers/`): openai, anthropic, gemini, copilot, jsonl, filesystem_coding

**Exporters** (`ctk/integrations/exporters/`): json, jsonl, markdown, html, hugo, csv, echo

**HTML Exporter Chat Features** (`ctk/integrations/exporters/html.py`): The HTML exporter produces self-contained interactive HTML files with tree-aware chat continuation. Key JS components embedded in the export:
- **ConversationTree** JS class: mirrors Python `ConversationTree` — builds `childrenMap`/`roots` from `parent_id`, methods: `getChildren()`, `getPathToRoot()`, `getDefaultPath()`, `addMessage()`
- **ChatClient** JS class: async SSE streaming to OpenAI-compatible endpoints (`/v1/chat/completions`), `AbortController` for cancellation
- **Path-based rendering**: `showConversation(conv, pathLeafId)` renders selected tree path with branch indicators (`Branch N of M [prev][next]`)
- **Chat input**: Reply buttons on assistant messages, quick continue at bottom, inline reply areas
- **localStorage persistence**: chat branches saved under `chat_branches_${convId}`, merged on page load
- **Settings UI**: AI Chat section with endpoint (default `localhost:11434`), model, temperature, system prompt
- Tests: `tests/unit/test_html_chat.py` (39 tests)

**Flow**: Import: File → Format Detection → Importer → ConversationTree → Database. Export: Database → ConversationTree → Path Selection → Exporter → Output.

### Other Key Components

**Fluent Python API** (`ctk/api.py`): `CTK` class with builder pattern — `CTK("db.db").search("python").limit(10).get()`

**MCP Server** (`ctk/interfaces/mcp/`): Modular MCP server with handler modules for search, conversation, metadata, and analysis (semantic search, similarity, clustering). 13 tools total. Entry point: `python -m ctk.mcp_server` (thin wrapper). Handlers in `ctk/interfaces/mcp/handlers/`.

**View System** (`ctk/core/views.py`): YAML-based named collections. Selection types: `ITEMS`, `QUERY`, `SQL`, `UNION/INTERSECT/SUBTRACT`. CLI: `ctk view create/list/show/eval`.

**LLM Integration** (`ctk/integrations/llm/`): Abstract `LLMProvider` with implementations for Ollama, OpenAI, Anthropic. Tool calling via `ctk/core/tools.py` and `ctk/core/tools_registry.py`.

**Shared Utilities**:
- `ctk/core/formatting.py`: `format_conversations_table()` (Rich tables with emoji flags)
- `ctk/core/db_helpers.py`: `list_conversations_helper()`, `search_conversations_helper()`
- `ctk/core/conversation_display.py`: `show_conversation_helper()`
- `ctk/core/tools.py` + `ctk/core/tools_registry.py`: Tool definitions and execution for LLM tool calling
- `ctk/core/prompts.py`: `get_ctk_system_prompt()`, `get_ctk_system_prompt_no_tools()`
- `ctk/core/utils.py`: `parse_timestamp()`, `try_parse_json()`
- `ctk/core/input_validation.py`: `validate_conversation_id()`, `validate_file_path()`
- `ctk/core/constants.py`: All magic numbers (timeouts, limits, widths)

## Critical Notes

### Gotchas
- **`EvaluatedView` is falsy when empty** — it implements `__len__`, so always use `is None` checks, not `if not evaluated:`
- **`EvaluatedViewItem` attributes**: use `item.item.id`, `item.effective_title`, `item.effective_description` — NOT `item.conversation_id` or `item.title_override`
- **CLI subcommand structure**: `ctk query` (not `ctk list`/`ctk search`), `ctk conv show/star/pin` (not `ctk show`/`ctk star`), `ctk db stats/merge/diff` (not `ctk stats`), `ctk lib list/search/stats` for library-level operations
- **`ConversationDB` context manager** is for cleanup only; session is initialized in `__init__`
- **`ConversationDB(":memory:")`** must be special-cased to use true in-memory SQLite (not file at `:memory:/conversations.db`)
- **`ConversationModel.updated_at`** has `onupdate=func.now()` — ORM overwrites explicit values; use raw SQL in tests to force timestamps
- **`ConversationTree.add_message()`** overwrites `metadata.updated_at` to `datetime.now()`
- **`ConversationMetadata`** defaults `created_at`/`updated_at` to `datetime.now()` — tests must set `None` explicitly
- **Python 3.12 SQLite datetime**: `isoformat()` uses `T`, SQLite stores with space. Use `strftime("%Y-%m-%d %H:%M:%S")` for cursor comparisons
- **Substring model detection in importers**: sort `model_map.items()` by key length DESC to avoid short-key matches (gpt-4 vs gpt-4-turbo)
- Integration tests in `tests/integration/test_cli.py` use old command names — known-failing

### Exception Handling
- Never use bare `except:` — always specify exception types
- `except Exception:` acceptable only in cleanup/finally blocks with logging
- HTTP: `requests.exceptions.RequestException`, JSON: `json.JSONDecodeError`, Files: `(IOError, OSError)`

### Constants (`ctk/core/constants.py`)
Import from here instead of hardcoding. Key values: `DEFAULT_TIMEOUT` (120s), `HEALTH_CHECK_TIMEOUT` (5s), `DEFAULT_SEARCH_LIMIT` (1000), `MAX_QUERY_LENGTH` (10000), `VFS_LIST_LIMIT` (1000).

### Natural Language Queries
The `ctk query` and TUI `/ask` use LLM tool calling. Critical pattern — boolean filters must only be included when explicitly present:
```python
starred_val = tool_args.get('starred')
starred = to_bool(starred_val) if starred_val is not None else None
```

### Testing
- Unit tests in `tests/unit/`, integration tests in `tests/integration/`
- ~2300 unit tests pass, 1 pre-existing failure (test_taggers)
- 9 integration test failures (pre-existing, old CLI command names)
- Coverage threshold: 59% (enforced in pytest.ini via `--cov-fail-under=59`)
- Well-tested modules: shell parser (99%), command dispatcher (100%), VFS navigator (96%), models (96%)

### Release Process
- Version bumps: `ctk/__init__.py`, `setup.py`, `CITATION.cff`
- Build: `rm -rf dist/ build/ *.egg-info && python -m build`
- Publish: `twine check dist/* && twine upload dist/*`
- Tag: `git tag -a v<version> -m "message" && git push && git push --tags`
- PyPI package name: `conversation-tk`, entry point: `ctk=ctk.cli:main`
