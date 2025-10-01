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
- `list`: Display conversations with filtering
- `search`: Full-text search across all messages
- `stats`: Database statistics and analytics
- `plugins`: List available plugins

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
  - **JSON**: Native CTK format preserving tree structure
  - **Markdown**: Human-readable with optional tree visualization

### New Export Formats

**Markdown Exporter** (`ctk/integrations/exporters/markdown.py`)
- Human-readable format with emoji indicators
- Tree structure visualization option
- Support for multimodal content (images, tools)
- Path selection strategies (longest, first, last, all)

**JSON Exporter** (`ctk/integrations/exporters/json.py`)
- Multiple format styles: ctk (native), openai, anthropic, generic
- Preserves full tree structure in CTK format
- Compatible with provider-specific formats
- Pretty-print option for readability

## Critical Notes

### Current Refactoring Status
The codebase is undergoing refactoring per `TODO.md`:
- Phase 1 & 2 completed: Security fixes and error handling standardization
- Phase 3 in progress: Testing infrastructure
- Phase 4 pending: Performance optimization

### Known Issues
- Test coverage needs improvement (target: >70%)
- Database queries use LIKE instead of full-text search
- Plugin system needs additional security validation
- CLI needs comprehensive integration tests

### Testing Approach
- Unit tests in `tests/unit/` - test individual components
- Integration tests in `tests/integration/` - test end-to-end workflows
- Use pytest fixtures for database and sample data setup
- Mock external dependencies when appropriate

### Error Handling Patterns
- Use specific exceptions instead of bare `except:` clauses
- Database operations should handle SQLAlchemy exceptions
- Import/export operations should validate data before processing
- CLI should provide clear error messages to users

### Database Migrations
- No formal migration system currently implemented
- Database schema changes require manual handling
- Consider adding Alembic for future schema evolution