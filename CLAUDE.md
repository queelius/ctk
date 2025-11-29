# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development Setup
```bash
# Initial setup (one-time)
make install  # Installs all dependencies including dev requirements
```

### Testing
```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run integration tests only
make test-integration

# Run with coverage report
make coverage

# Run specific test file
pytest tests/unit/test_database.py -v

# Run specific test function
pytest tests/unit/test_database.py::TestDatabase::test_save_conversation -v
```

### Code Quality
```bash
# Format code (black + isort)
make format

# Lint code (flake8 + mypy)
make lint

# Clean build artifacts
make clean
```

## Architecture Overview

### Core Components

**ConversationTree Model** (`ctk/core/models.py`)
- Central data structure representing conversations as trees
- Linear chats are single-path trees; branching conversations preserve all paths
- Key methods: `get_all_paths()`, `get_longest_path()`, `add_message()`
- All conversations use tree structure for consistency

**Database Layer** (`ctk/core/database.py`)
- SQLAlchemy-based persistence using SQLite
- Tables: conversations, messages, tags, paths
- Full-text search via SQL LIKE queries
- Connection management with context managers

**Plugin System** (`ctk/core/plugin.py`)
- Auto-discovery of importers/exporters in `ctk/integrations/`
- Dynamic module loading with validation
- Registry pattern for plugin management
- Base classes: `ImporterPlugin`, `ExporterPlugin`

### Interfaces (`ctk/interfaces/`)

**Base Interface** (`ctk/interfaces/base.py`)
- Abstract base class all interfaces inherit from
- Standard methods: import, export, search, list, get, update, delete
- Unified response format via `InterfaceResponse`

**REST API** (`ctk/interfaces/rest/`)
- Flask-based RESTful API
- Full CRUD operations for conversations
- File upload support for imports
- CORS enabled for web frontends
- Example server: `examples/rest_server.py`

**Web Frontend** (`examples/web_frontend.html`)
- Single-page application for browser access
- Connect to REST API for all operations
- Search, import, export, and view conversations

### CLI Architecture (`ctk/cli.py`)
Main commands:
- `import`: Load conversations from various formats
- `export`: Export conversations to different formats
- `list`: Display conversations with filtering (supports --starred, --pinned, --archived)
- `search`: Full-text search across all messages with Rich table output
- `ask`: Natural language queries using LLM with tool calling
- `show`: Display specific conversation (supports path selection)
- `tree`: Visualize conversation tree structure
- `paths`: List all paths in branching conversation
- `star/pin/archive`: Organize conversations
- `title`: Rename conversations
- `tag`: Auto-tag with LLM
- `stats`: Database statistics and analytics
- `plugins`: List available plugins
- `chat`: Launch interactive TUI (shell-first mode)
- `merge/diff/filter`: Database operations

### Shell-First Mode (`ctk/integrations/chat/tui.py`)

The TUI features a Unix-like shell interface for navigating and managing conversations via a Virtual Filesystem (VFS).

**VFS Architecture** (`ctk/core/vfs.py`, `ctk/core/vfs_navigator.py`):
- Conversations exposed as directories under `/chats/<conv_id>/`
- Message trees navigable as `m1/m2/m3` subdirectories
- Message metadata accessible as files: `text`, `role`, `timestamp`, `id`
- Virtual directories: `/starred/`, `/pinned/`, `/archived/`, `/tags/`, `/recent/`, `/source/`, `/model/`
- Prefix resolution allows short IDs (e.g., `cd 7c8` resolves to full UUID)

**Command System** (`ctk/core/commands/`):
- `navigation.py`: cd, ls, pwd
- `unix.py`: cat, head, tail, echo, grep
- `search.py`: find with -name, -content, -role, -type, -i, -limit, -l flags
- `visualization.py`: tree, paths
- `organization.py`: star, unstar, pin, unpin, archive, unarchive, title
- `chat.py`: chat, complete

**Key Features**:
- 20 shell commands with Unix-like semantics
- Pipe support: `ls | grep pattern | head 5`
- Environment variables: `$CWD`, `$MODEL`, `$PROVIDER`, `$CONV_ID`
- Tab completion for paths and commands
- `find -l` shows rich metadata table with titles, models, dates, tags

**CommandResult Pattern**:
```python
@dataclass
class CommandResult:
    success: bool
    output: str = ""
    error: str = ""
    pipe_data: Optional[str] = None
```

See `SHELL_COMMANDS_REFERENCE.md` for complete command documentation.

### Import/Export Flow

1. **Import**: File → Format Detection → Importer Plugin → ConversationTree → Database
2. **Export**: Database → ConversationTree → Path Selection → Exporter Plugin → Output File

### Plugin Structure

Importers (`ctk/integrations/importers/`):
- Each importer implements `validate()` and `import_data()` methods
- Handles provider-specific formats (OpenAI, Anthropic, Gemini, etc.)
- Returns list of `ConversationTree` objects

Exporters (`ctk/integrations/exporters/`):
- Implements `export_conversations()` method
- Available formats:
  - **JSONL**: For fine-tuning and data pipelines
  - **JSON**: Native CTK format, OpenAI, Anthropic, or generic JSON
  - **Markdown**: Human-readable with tree visualization
  - **HTML5**: Interactive HTML with browsing and search

### TUI Architecture (`ctk/integrations/chat/tui.py`)

**Two-Mode System**:
1. **Shell Mode** (default): Unix-like VFS navigation with 20 commands
2. **Chat Mode**: Interactive LLM conversation with streaming

**Shell Mode Features**:
- Enter via `ctk chat` command
- Navigate conversations with cd, ls, pwd
- Search with `find` command (supports -name, -content, -role, -type, -i, -limit, -l)
- View content with cat, head, tail, grep
- Organize with star, pin, archive, title
- Enter chat mode with `chat` command (loads conversation history as context)

**Chat Mode Features**:
- Live chat with LLM providers (Ollama, OpenAI, Anthropic)
- Model Context Protocol (MCP) tool support
- Streaming responses
- Exit to shell with `/exit` or Ctrl+D

**Legacy Slash Commands** (still available):
- `/browse`: Browse conversations table
- `/ask <query>`: Natural language query (LLM-powered)
- `/search <query>`: Full-text search
- `/show <id>`, `/tree <id>`, `/paths <id>`: View conversations
- `/star`, `/pin`, `/archive`, `/title`: Organization
- `/fork`, `/regenerate`, `/edit`: Chat operations
- `/export`, `/tag`, `/help`, `/quit`: Utilities

### LLM Integration (`ctk/integrations/llm/`)

**Provider Abstraction** (`base.py`):
- Abstract `LLMProvider` class for unified interface
- Standard methods: `chat()`, `list_models()`, `format_tools_for_api()`
- Supports streaming and tool calling
- Provider implementations: Ollama, OpenAI, Anthropic

**Tool Calling** (`ctk/core/helpers.py`):
- `get_ask_tools()`: Returns tool definitions for database queries
- `execute_ask_tool()`: Executes tools and returns formatted results
- Tools: `search_conversations`, `get_conversation_by_id`
- Supports both CLI and TUI contexts

### Helper Functions (`ctk/core/helpers.py`)

**Shared Utilities**:
- `format_conversations_table()`: Rich table formatting for CLI/TUI
- `list_conversations_helper()`: Unified conversation listing logic
- `search_conversations_helper()`: Unified search logic
- Tool schemas and execution for LLM queries

## Critical Notes

### Current Status
- Shell-first mode fully implemented with 20 commands
- Test coverage at ~35% (698 tests passing)
- Key modules well-tested: shell parser (99%), command dispatcher (100%), VFS navigator (96%), models (96%)

### Known Issues
- Test coverage target: >70% (currently ~35%)
- Database queries use LIKE instead of full-text search (consider FTS5)
- Plugin system needs additional security validation
- Performance optimization needed for large databases (>100k conversations)
- Some legacy tests need API updates (53 failing)

### Testing Approach
- Unit tests in `tests/unit/` - test individual components
- Integration tests in `tests/integration/` - test end-to-end workflows
- Use pytest fixtures for database and sample data setup
- Mock external dependencies when appropriate

**Key Test Files** (comprehensive coverage):
- `test_shell_parser.py`: Shell command parsing (99% coverage)
- `test_command_dispatcher.py`: Command dispatch logic (100% coverage)
- `test_vfs_path_parser.py`: VFS path parsing (88% coverage)
- `test_vfs_navigator.py`: VFS navigation (96% coverage)
- `test_navigation_commands.py`: cd, ls, pwd (100% coverage)
- `test_unix_commands.py`: cat, head, tail, echo, grep (90% coverage)
- `test_search_commands.py`: find command (92% coverage)
- `test_organization_commands.py`: star, pin, archive, title (96% coverage)
- `test_visualization_commands.py`: tree, paths (95% coverage)
- `test_chat_commands.py`: chat, complete (95% coverage)
- `test_models_comprehensive.py`: ConversationTree model (96% coverage)

### Error Handling Patterns
- Use specific exceptions instead of bare `except:` clauses
- Database operations should handle SQLAlchemy exceptions
- Import/export operations should validate data before processing
- CLI should provide clear error messages to users

### Database Migrations
- No formal migration system currently implemented
- Database schema changes require manual handling
- Consider adding Alembic for future schema evolution

## Feature Highlights

### Natural Language Queries (Ask Command)
The `ctk ask` command and TUI `/ask` command use LLM tool calling to interpret natural language queries:

**Implementation** (`ctk/cli.py`, `ctk/core/helpers.py`):
- System prompt with few-shot examples guides LLM behavior
- Tools: `search_conversations`, `get_conversation_by_id`
- Boolean filters (starred/pinned/archived) only included when explicitly mentioned
- Direct tool output (no LLM reformatting to prevent hallucination)
- Rich table output for readability

**Critical Pattern** - Boolean filter handling:
```python
# Only include filter if explicitly present in tool call
starred_val = tool_args.get('starred')
starred = to_bool(starred_val) if starred_val is not None else None
```

### Rich Console Output
All CLI list/search/ask commands use shared `format_conversations_table()` function:
- Color-coded columns with emoji flags (⭐📌📦)
- Truncated titles for readability
- Consistent styling across commands
- JSON output option for scripting

### Organization Features
Database schema supports starred_at, pinned_at, archived_at timestamps:
- Star: Quick access to important conversations
- Pin: Keep conversations at top of lists
- Archive: Hide old conversations from default views
- Multiple IDs supported for batch operations

### Auto-tagging
LLM-powered tagging extracts topics/themes from conversation content:
- Analyzes conversation messages for key concepts
- Generates relevant tags automatically
- Available in both CLI and TUI

### Database Operations
- `merge`: Combine multiple databases (handles duplicates by ID)
- `diff`: Compare databases to find unique/modified conversations
- `filter`: Extract subset of conversations to new database