# CTK Testing Plan

## Current Status

### Existing Tests
- ✅ Unit tests for models (`test_models.py`) - 19 tests, all passing
- ⚠️ Unit tests for database (`test_database.py`) - 12 tests, 1 failing
- ✅ Unit tests for taggers (`test_taggers.py`)
- ✅ Integration tests (`test_end_to_end.py`)
- ⚠️ Various comprehensive tests with mixed results

### Coverage Target
- Current: ~6%
- Target: >70%
- Gap: Need comprehensive tests for:
  - CLI commands
  - TUI functionality
  - LLM integration
  - Importers/Exporters
  - Helper functions
  - Database operations (star, pin, archive, title, etc.)

## Test Structure

```
tests/
├── unit/                       # Unit tests for individual components
│   ├── test_models.py          # ✅ ConversationTree, Message, Metadata
│   ├── test_database.py        # ⚠️ Database CRUD operations
│   ├── test_cli_core.py        # CLI command functions
│   ├── test_helpers.py         # NEW: Helper functions
│   ├── test_llm_providers.py   # NEW: LLM provider abstraction
│   ├── test_importers.py       # Importer plugins
│   ├── test_exporters.py       # Exporter plugins
│   └── test_taggers.py         # ✅ Auto-tagging functionality
│
└── integration/                # End-to-end workflow tests
    ├── test_cli.py             # CLI command integration
    ├── test_tui.py             # NEW: TUI integration
    ├── test_import_export.py   # NEW: Import/export workflows
    └── test_end_to_end.py      # ✅ Complete workflows
```

## Priority 1: Core Components (Week 1)

### 1.1 Fix Existing Test Failures
- [x] Fix `test_list_conversations` - ConversationSummary type issue

### 1.2 Database Operations (`test_database_operations.py`)
Test new database features:
- [ ] Star/unstar conversations
- [ ] Pin/unpin conversations
- [ ] Archive/unarchive conversations
- [ ] Title/rename conversations
- [ ] Timestamp verification (starred_at, pinned_at, archived_at)
- [ ] Batch operations (multiple IDs)

### 1.3 Helper Functions (`test_helpers.py`)
Test shared utilities:
- [ ] `format_conversations_table()` - Rich table formatting
- [ ] `list_conversations_helper()` - Unified listing logic
- [ ] `search_conversations_helper()` - Unified search logic
- [ ] `get_ask_tools()` - Tool definitions
- [ ] `execute_ask_tool()` - Tool execution
- [ ] Boolean filter handling (None vs True vs False)

## Priority 2: CLI Commands (Week 2)

### 2.1 CLI Core Commands (`test_cli_commands.py`)
Test individual CLI command functions:
- [ ] `list_cmd()` - With various filters
- [ ] `search_cmd()` - Full-text search
- [ ] `ask_cmd()` - Natural language queries
- [ ] `show_cmd()` - Display conversation
- [ ] `tree_cmd()` - Tree visualization
- [ ] `paths_cmd()` - List paths
- [ ] `star_cmd()`, `pin_cmd()`, `archive_cmd()` - Organization
- [ ] `title_cmd()` - Rename
- [ ] `tag_cmd()` - Auto-tagging

### 2.2 Ask Command (`test_ask_command.py`)
Special focus on natural language queries:
- [ ] Tool selection based on query
- [ ] Boolean filter handling (explicit vs implicit)
- [ ] Direct tool output (no LLM reformatting)
- [ ] JSON output format
- [ ] Debug mode output
- [ ] Error handling for invalid queries
- [ ] Few-shot prompt examples working correctly

## Priority 3: LLM & Embeddings (Week 2-3)

### 3.1 LLM Providers (`test_llm_providers.py`)
Test provider abstraction:
- [ ] Base `LLMProvider` interface
- [ ] Ollama provider (with mocked server)
- [ ] OpenAI provider (with mocked API)
- [ ] Anthropic provider (with mocked API)
- [ ] Tool formatting for each provider
- [ ] Streaming support
- [ ] Error handling (network, auth, rate limits)

### 3.2 Embedding Providers (`test_embedding_providers.py`)
Test embedding abstraction (future):
- [ ] Base `EmbeddingProvider` interface
- [ ] Ollama embeddings
- [ ] Weighted embeddings
- [ ] Aggregation strategies

## Priority 4: Import/Export (Week 3)

### 4.1 Importers (`test_importers_comprehensive.py`)
Test all importer plugins:
- [ ] OpenAI importer (ChatGPT exports)
- [ ] Anthropic importer (Claude exports)
- [ ] Gemini importer
- [ ] JSONL importer
- [ ] Copilot importer
- [ ] Format validation
- [ ] Error handling for malformed data
- [ ] Tree structure preservation

### 4.2 Exporters (`test_exporters_comprehensive.py`)
Test all exporter plugins:
- [ ] JSONL exporter (multiple formats)
- [ ] JSON exporter (ctk, openai, anthropic, generic)
- [ ] Markdown exporter (with/without tree viz)
- [ ] HTML5 exporter
- [ ] Path selection strategies (longest, first, last, all)
- [ ] Filtering (by tags, source, model, starred, etc.)
- [ ] Sanitization

## Priority 5: Integration Tests (Week 4)

### 5.1 CLI Integration (`test_cli_integration.py`)
End-to-end CLI workflows:
- [ ] Import → List → Search → Export workflow
- [ ] Star → Filter → Export workflow
- [ ] Ask command with tool execution
- [ ] Database merge/diff/filter operations
- [ ] Error scenarios (missing DB, invalid IDs, etc.)

### 5.2 TUI Integration (`test_tui_integration.py`)
Terminal UI workflows:
- [ ] Launch and navigate TUI
- [ ] Browse conversations
- [ ] Search and filter
- [ ] `/ask` command
- [ ] Star/pin/archive operations
- [ ] Export from TUI
- [ ] Chat with LLM (mocked)
- [ ] Fork conversations
- [ ] Command parsing and execution

### 5.3 Import/Export Workflows (`test_import_export_workflows.py`)
Cross-format workflows:
- [ ] Import ChatGPT → Export as JSONL
- [ ] Import multiple sources → Merge → Export
- [ ] Round-trip tests (import → export → import)
- [ ] Tree structure preservation through export/import

## Testing Utilities

### Fixtures (`conftest.py`)

**Existing:**
- `temp_dir` - Temporary directory
- `temp_db` - Temporary database
- `sample_conversation` - Linear conversation
- `branching_conversation` - Branching conversation

**Need to add:**
- `mock_ollama_server` - Mocked Ollama API
- `mock_openai_client` - Mocked OpenAI API
- `mock_anthropic_client` - Mocked Anthropic API
- `sample_conversations_batch` - Multiple conversations for testing filters
- `starred_conversations` - Pre-starred conversations
- `archived_conversations` - Pre-archived conversations

### Mocking Strategies

**LLM Providers:**
```python
@pytest.fixture
def mock_ollama_server(monkeypatch):
    """Mock Ollama server responses"""
    def mock_chat(*args, **kwargs):
        return ChatResponse(
            content="Mocked response",
            tool_calls=None
        )

    monkeypatch.setattr("ctk.integrations.llm.ollama.requests.post", mock_post)
    return mock_chat
```

**Database:**
```python
@pytest.fixture
def temp_db_with_data(temp_db):
    """Database pre-populated with test data"""
    # Add starred, pinned, archived conversations
    # Add conversations from different sources
    # Add conversations with various tags
    return temp_db
```

## Test Execution

### Commands
```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run integration tests only
make test-integration

# Run with coverage
make coverage

# Run specific test file
pytest tests/unit/test_helpers.py -v

# Run specific test
pytest tests/unit/test_database.py::TestConversationDB::test_star_conversation -v

# Run with debug output
pytest tests/unit/test_ask_command.py -xvs
```

### Coverage Goals

**Phase 1 (Week 1):**
- Core models: 80%+
- Database operations: 70%+
- Helper functions: 70%+

**Phase 2 (Week 2):**
- CLI commands: 60%+
- LLM providers: 60%+

**Phase 3 (Week 3):**
- Importers: 70%+
- Exporters: 70%+

**Phase 4 (Week 4):**
- Integration tests: End-to-end coverage
- Overall coverage: >70%

## Test Naming Conventions

```python
class TestFeatureName:
    """Test FeatureName functionality"""

    def test_basic_functionality(self):
        """Test basic happy path"""

    def test_error_handling(self):
        """Test error conditions"""

    def test_edge_cases(self):
        """Test edge cases and boundary conditions"""

    def test_integration_with_dependency(self):
        """Test integration with related component"""
```

## Documentation

Each test file should include:
- Module docstring explaining what's being tested
- Class docstrings for test groups
- Function docstrings for individual tests
- Inline comments for complex assertions

## Continuous Integration

Future:
- [ ] GitHub Actions workflow
- [ ] Coverage reporting
- [ ] Automated test runs on PR
- [ ] Performance benchmarking
