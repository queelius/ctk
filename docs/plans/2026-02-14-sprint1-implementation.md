# Sprint 1: Quick Foundations - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete plan phases 4, 6, and 7 — centralize magic numbers, reduce OpenAI importer nesting, and update documentation.

**Architecture:** Extract hardcoded constants into `ctk/core/constants.py`, refactor deeply nested multimodal parsing in the OpenAI importer into testable helper methods, and update project docs to reflect all recent work.

**Tech Stack:** Python, pytest, SQLAlchemy

---

## Task 1: Create constants module with tests

**Files:**
- Create: `ctk/core/constants.py`
- Create: `tests/unit/test_constants.py`

**Step 1: Write the test file**

```python
"""Tests for ctk.core.constants module."""

import pytest
from ctk.core import constants


class TestTimeoutConstants:
    """Verify timeout constants exist and have sensible values."""

    def test_default_timeout(self):
        assert constants.DEFAULT_TIMEOUT == 120

    def test_health_check_timeout(self):
        assert constants.HEALTH_CHECK_TIMEOUT == 5

    def test_model_list_timeout(self):
        assert constants.MODEL_LIST_TIMEOUT == 30

    def test_short_timeout(self):
        assert constants.SHORT_TIMEOUT == 2

    def test_embedding_timeout(self):
        assert constants.EMBEDDING_TIMEOUT == 60

    def test_migration_lock_timeout(self):
        assert constants.MIGRATION_LOCK_TIMEOUT == 30.0


class TestLimitConstants:
    """Verify limit constants exist and have sensible values."""

    def test_default_search_limit(self):
        assert constants.DEFAULT_SEARCH_LIMIT == 1000

    def test_default_timeline_limit(self):
        assert constants.DEFAULT_TIMELINE_LIMIT == 30

    def test_max_query_length(self):
        assert constants.MAX_QUERY_LENGTH == 10000

    def test_max_title_length(self):
        assert constants.MAX_TITLE_LENGTH == 1000

    def test_max_id_length(self):
        assert constants.MAX_ID_LENGTH == 200

    def test_max_result_limit(self):
        assert constants.MAX_RESULT_LIMIT == 10000

    def test_search_buffer(self):
        assert constants.SEARCH_BUFFER == 100

    def test_title_match_boost(self):
        assert constants.TITLE_MATCH_BOOST == 10

    def test_ambiguity_check_limit(self):
        assert constants.AMBIGUITY_CHECK_LIMIT == 2


class TestDisplayConstants:
    """Verify display constants."""

    def test_title_truncate_width(self):
        assert constants.TITLE_TRUNCATE_WIDTH == 60

    def test_title_truncate_width_short(self):
        assert constants.TITLE_TRUNCATE_WIDTH_SHORT == 50


class TestEstimationConstants:
    """Verify estimation constants."""

    def test_chars_per_token(self):
        assert constants.CHARS_PER_TOKEN == 4
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_constants.py -v`
Expected: FAIL — module not found

**Step 3: Write the constants module**

```python
"""
Global constants for CTK.

Centralizes magic numbers used across LLM providers, database operations,
and display formatting. Import from here instead of hardcoding values.
"""

# --- Network Timeouts (seconds) ---

DEFAULT_TIMEOUT = 120        # Default LLM chat/stream timeout
HEALTH_CHECK_TIMEOUT = 5     # Quick health/availability check
MODEL_LIST_TIMEOUT = 30      # Listing available models
SHORT_TIMEOUT = 2            # Very short checks (Ollama health)
EMBEDDING_TIMEOUT = 60       # Embedding generation timeout
MIGRATION_LOCK_TIMEOUT = 30.0  # Database migration lock

# --- Database & Query Limits ---

DEFAULT_SEARCH_LIMIT = 1000  # FTS5 search result limit
DEFAULT_TIMELINE_LIMIT = 30  # Timeline query default limit
SEARCH_BUFFER = 100          # Extra records fetched for post-filtering
TITLE_MATCH_BOOST = 10       # Boost factor for title matches in search
AMBIGUITY_CHECK_LIMIT = 2    # Max matches to check for ambiguous IDs

# --- Input Validation Limits ---

MAX_QUERY_LENGTH = 10000     # Maximum search query length
MAX_TITLE_LENGTH = 1000      # Maximum conversation title length
MAX_ID_LENGTH = 200          # Maximum conversation ID length
MAX_RESULT_LIMIT = 10000     # Maximum results per query

# --- Display ---

TITLE_TRUNCATE_WIDTH = 60    # Truncation width for titles in tables
TITLE_TRUNCATE_WIDTH_SHORT = 50  # Shorter truncation width

# --- Estimation ---

CHARS_PER_TOKEN = 4          # Rough characters-per-token estimate
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_constants.py -v`
Expected: PASS (all tests green)

**Step 5: Commit**

```bash
git add ctk/core/constants.py tests/unit/test_constants.py
git commit -m "feat: add centralized constants module with tests"
```

---

## Task 2: Replace hardcoded values in LLM providers with constants

**Files:**
- Modify: `ctk/integrations/llm/openai.py` (lines 48, 293, 374)
- Modify: `ctk/integrations/llm/ollama.py` (lines 34, 227, 242, 327)
- Modify: `ctk/integrations/llm/anthropic.py` (line 59)
- Modify: `ctk/integrations/llm/base.py` (line 194)
- Modify: `ctk/integrations/embeddings/ollama.py` (lines 34, 131, 189)

**Step 1: Run existing tests to establish baseline**

Run: `pytest tests/unit/test_llm_openai.py tests/unit/test_llm_ollama.py tests/unit/test_llm_anthropic.py -v`
Expected: All pass

**Step 2: Update OpenAI LLM provider**

In `ctk/integrations/llm/openai.py`:
- Add import: `from ctk.core.constants import DEFAULT_TIMEOUT, MODEL_LIST_TIMEOUT, HEALTH_CHECK_TIMEOUT`
- Line 48: `self.timeout = config.get("timeout", 120)` → `self.timeout = config.get("timeout", DEFAULT_TIMEOUT)`
- Line 293: `timeout=30` → `timeout=MODEL_LIST_TIMEOUT`
- Line 374: `timeout=5` → `timeout=HEALTH_CHECK_TIMEOUT`

**Step 3: Update Ollama LLM provider**

In `ctk/integrations/llm/ollama.py`:
- Add import: `from ctk.core.constants import DEFAULT_TIMEOUT, MODEL_LIST_TIMEOUT, HEALTH_CHECK_TIMEOUT, SHORT_TIMEOUT`
- Line 34: `config.get("timeout", 120)` → `config.get("timeout", DEFAULT_TIMEOUT)`
- Line 227: `timeout=10` → `timeout=MODEL_LIST_TIMEOUT` (note: Ollama uses 10 not 30, but they serve the same purpose — listing models. Standardize to MODEL_LIST_TIMEOUT=30 or keep Ollama-specific? Decision: use MODEL_LIST_TIMEOUT for consistency)
- Line 242: `timeout=5` → `timeout=HEALTH_CHECK_TIMEOUT`
- Line 327: `timeout=2` → `timeout=SHORT_TIMEOUT`

**Step 4: Update Anthropic LLM provider**

In `ctk/integrations/llm/anthropic.py`:
- Add import: `from ctk.core.constants import DEFAULT_TIMEOUT`
- Line 59: `config.get("timeout", 120)` → `config.get("timeout", DEFAULT_TIMEOUT)`

**Step 5: Update base LLM provider**

In `ctk/integrations/llm/base.py`:
- Add import: `from ctk.core.constants import CHARS_PER_TOKEN`
- Line 194: `len(text) // 4` → `len(text) // CHARS_PER_TOKEN`

**Step 6: Update Ollama embeddings provider**

In `ctk/integrations/embeddings/ollama.py`:
- Add import: `from ctk.core.constants import EMBEDDING_TIMEOUT, MODEL_LIST_TIMEOUT, SHORT_TIMEOUT`
- Line 34: `config.get("timeout", 60)` → `config.get("timeout", EMBEDDING_TIMEOUT)`
- Line 131: `timeout=10` → `timeout=MODEL_LIST_TIMEOUT`
- Line 189: `timeout=2` → `timeout=SHORT_TIMEOUT`

**Step 7: Run tests to verify no regressions**

Run: `pytest tests/unit/ -q --tb=short`
Expected: 1296 passed, 1 failed (pre-existing), 1 skipped

**Step 8: Commit**

```bash
git add ctk/integrations/llm/openai.py ctk/integrations/llm/ollama.py ctk/integrations/llm/anthropic.py ctk/integrations/llm/base.py ctk/integrations/embeddings/ollama.py
git commit -m "refactor: replace hardcoded timeouts with constants"
```

---

## Task 3: Replace hardcoded values in database and MCP server

**Files:**
- Modify: `ctk/core/database.py` (lines 160, 480, 517, 746, 756, 880, 895, 1083, 1726)
- Modify: `ctk/mcp_server.py` (lines 46-49, 530, 574)

**Step 1: Update database.py**

In `ctk/core/database.py`:
- Add import: `from ctk.core.constants import MIGRATION_LOCK_TIMEOUT, DEFAULT_SEARCH_LIMIT, TITLE_MATCH_BOOST, AMBIGUITY_CHECK_LIMIT, SEARCH_BUFFER, DEFAULT_TIMELINE_LIMIT`
- Line 160: `timeout=30.0` → `timeout=MIGRATION_LOCK_TIMEOUT`
- Line 480: `limit: int = 1000` → `limit: int = DEFAULT_SEARCH_LIMIT`
- Line 517: `row[1] - 10` → `row[1] - TITLE_MATCH_BOOST`
- Lines 746, 756, 880, 895: `.limit(2)` → `.limit(AMBIGUITY_CHECK_LIMIT)` and `.limit(10)` → keep as-is (message resolution is different context)
- Line 1083: `limit + offset + 100` → `limit + offset + SEARCH_BUFFER`
- Line 1726: `limit: int = 30` → `limit: int = DEFAULT_TIMELINE_LIMIT`

**Step 2: Update mcp_server.py**

In `ctk/mcp_server.py`:
- Add import: `from ctk.core.constants import MAX_QUERY_LENGTH, MAX_TITLE_LENGTH, MAX_ID_LENGTH, MAX_RESULT_LIMIT, TITLE_TRUNCATE_WIDTH, TITLE_TRUNCATE_WIDTH_SHORT`
- Lines 46-49: Replace the 4 local constants with imports (remove the local definitions)
- Line 530: `[:60]` → `[:TITLE_TRUNCATE_WIDTH]`
- Line 574: `[:50]` → `[:TITLE_TRUNCATE_WIDTH_SHORT]`

**Step 3: Run tests**

Run: `pytest tests/unit/ -q --tb=short`
Expected: All pass (same as baseline)

**Step 4: Commit**

```bash
git add ctk/core/database.py ctk/mcp_server.py
git commit -m "refactor: replace hardcoded limits in database and MCP server with constants"
```

---

## Task 4: Write tests for OpenAI importer helper methods

**Files:**
- Create: `tests/unit/test_openai_importer.py`

**Step 1: Write comprehensive tests for the helper methods we'll extract**

```python
"""Tests for OpenAI importer multimodal content parsing."""

import json
import pytest
from unittest.mock import patch, MagicMock

from ctk.integrations.importers.openai import OpenAIImporter
from ctk.core.models import MessageContent, ToolCall


@pytest.fixture
def importer():
    """Create an OpenAI importer instance."""
    return OpenAIImporter()


class TestProcessTextPart:
    """Test extraction of text from content parts."""

    def test_string_part_returns_text(self, importer):
        result = importer._process_part("Hello world")
        assert result == "Hello world"

    def test_dict_with_text_key(self, importer):
        result = importer._process_part({"text": "Hello"})
        assert result == "Hello"

    def test_dict_with_content_key(self, importer):
        result = importer._process_part({"content": 42})
        assert result == "42"

    def test_empty_string_part(self, importer):
        result = importer._process_part("")
        assert result == ""


class TestProcessAssetPointer:
    """Test DALL-E asset pointer processing."""

    def test_asset_pointer_with_dalle_prompt(self, importer):
        content = MessageContent()
        part = {
            "asset_pointer": "file-service://image123.png",
            "metadata": {
                "dalle": {
                    "prompt": "A cat on a cloud"
                }
            }
        }
        with patch.object(importer, '_resolve_and_copy_image', return_value="media/image123.png"):
            importer._process_asset_pointer(part, content)

        assert len(content.images) == 1
        assert content.images[0].url == "media/image123.png"
        assert content.images[0].caption == "A cat on a cloud"

    def test_asset_pointer_without_metadata(self, importer):
        content = MessageContent()
        part = {"asset_pointer": "file-service://img.png"}
        with patch.object(importer, '_resolve_and_copy_image', return_value="media/img.png"):
            importer._process_asset_pointer(part, content)

        assert len(content.images) == 1
        assert content.images[0].caption is None

    def test_asset_pointer_no_url(self, importer):
        content = MessageContent()
        part = {"asset_pointer": None}
        importer._process_asset_pointer(part, content)
        assert len(content.images) == 0

    def test_asset_pointer_resolve_fails(self, importer):
        content = MessageContent()
        part = {"asset_pointer": "file-service://missing.png"}
        with patch.object(importer, '_resolve_and_copy_image', return_value=None):
            importer._process_asset_pointer(part, content)
        assert len(content.images) == 0

    def test_asset_pointer_metadata_not_dict(self, importer):
        content = MessageContent()
        part = {
            "asset_pointer": "file-service://img.png",
            "metadata": "not a dict"
        }
        with patch.object(importer, '_resolve_and_copy_image', return_value="media/img.png"):
            importer._process_asset_pointer(part, content)
        assert len(content.images) == 1
        assert content.images[0].caption is None

    def test_asset_pointer_dalle_not_dict(self, importer):
        content = MessageContent()
        part = {
            "asset_pointer": "file-service://img.png",
            "metadata": {"dalle": "not a dict"}
        }
        with patch.object(importer, '_resolve_and_copy_image', return_value="media/img.png"):
            importer._process_asset_pointer(part, content)
        assert len(content.images) == 1
        assert content.images[0].caption is None


class TestProcessImageUrl:
    """Test image URL processing."""

    def test_string_url_regular(self, importer):
        content = MessageContent()
        part = {"image_url": "https://example.com/cat.png"}
        importer._process_image_url(part, content)
        assert len(content.images) == 1
        assert content.images[0].url == "https://example.com/cat.png"

    def test_string_url_file_service(self, importer):
        content = MessageContent()
        part = {"image_url": "file-service://local.png"}
        with patch.object(importer, '_resolve_and_copy_image', return_value="media/local.png"):
            importer._process_image_url(part, content)
        assert len(content.images) == 1
        assert content.images[0].url == "media/local.png"

    def test_string_url_file_service_resolve_fails(self, importer):
        content = MessageContent()
        part = {"image_url": "file-service://missing.png"}
        with patch.object(importer, '_resolve_and_copy_image', return_value=None):
            importer._process_image_url(part, content)
        assert len(content.images) == 0

    def test_dict_url_regular(self, importer):
        content = MessageContent()
        part = {"image_url": {"url": "https://example.com/dog.png", "detail": "high"}}
        importer._process_image_url(part, content)
        assert len(content.images) == 1
        assert content.images[0].url == "https://example.com/dog.png"
        assert content.images[0].caption == "high"

    def test_dict_url_file_service(self, importer):
        content = MessageContent()
        part = {"image_url": {"url": "file-service://local.png", "detail": "low"}}
        with patch.object(importer, '_resolve_and_copy_image', return_value="media/local.png"):
            importer._process_image_url(part, content)
        assert len(content.images) == 1
        assert content.images[0].url == "media/local.png"
        assert content.images[0].caption == "low"

    def test_dict_url_missing_url_key(self, importer):
        content = MessageContent()
        part = {"image_url": {"detail": "high"}}
        importer._process_image_url(part, content)
        assert len(content.images) == 0


class TestProcessToolCalls:
    """Test tool call extraction."""

    def test_modern_tool_calls(self, importer):
        content = MessageContent()
        content_data = {
            "tool_calls": [{
                "id": "call_123",
                "function": {
                    "name": "search",
                    "arguments": '{"query": "cats"}'
                }
            }]
        }
        importer._process_tool_calls(content_data, content)
        assert len(content.tool_calls) == 1
        assert content.tool_calls[0].name == "search"
        assert content.tool_calls[0].arguments == {"query": "cats"}

    def test_legacy_function_call(self, importer):
        content = MessageContent()
        content_data = {
            "function_call": {
                "name": "get_weather",
                "arguments": '{"location": "NYC"}'
            }
        }
        importer._process_tool_calls(content_data, content)
        assert len(content.tool_calls) == 1
        assert content.tool_calls[0].name == "get_weather"
        assert content.tool_calls[0].arguments == {"location": "NYC"}

    def test_tool_call_empty_arguments(self, importer):
        content = MessageContent()
        content_data = {
            "tool_calls": [{
                "id": "call_1",
                "function": {"name": "list_all", "arguments": ""}
            }]
        }
        importer._process_tool_calls(content_data, content)
        assert content.tool_calls[0].arguments == {}

    def test_tool_call_no_arguments(self, importer):
        content = MessageContent()
        content_data = {
            "tool_calls": [{
                "id": "call_1",
                "function": {"name": "list_all"}
            }]
        }
        importer._process_tool_calls(content_data, content)
        assert content.tool_calls[0].arguments == {}

    def test_both_modern_and_legacy(self, importer):
        content = MessageContent()
        content_data = {
            "tool_calls": [{"id": "c1", "function": {"name": "a", "arguments": "{}"}}],
            "function_call": {"name": "b", "arguments": "{}"}
        }
        importer._process_tool_calls(content_data, content)
        assert len(content.tool_calls) == 2

    def test_no_tool_calls(self, importer):
        content = MessageContent()
        content_data = {"text": "Hello"}
        importer._process_tool_calls(content_data, content)
        assert len(content.tool_calls) == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_openai_importer.py -v`
Expected: FAIL — methods `_process_part`, `_process_asset_pointer`, `_process_image_url`, `_process_tool_calls` do not exist

**Step 3: Commit the test file**

```bash
git add tests/unit/test_openai_importer.py
git commit -m "test: add failing tests for OpenAI importer helper methods"
```

---

## Task 5: Extract helper methods in OpenAI importer

**Files:**
- Modify: `ctk/integrations/importers/openai.py` (lines 254-353)

**Step 1: Add helper methods to the OpenAIImporter class**

Add these methods to the class (after `import_data` or before `_resolve_and_copy_image`):

```python
def _process_part(self, part):
    """Process a single content part. Returns text string or None."""
    if isinstance(part, str):
        return part
    if not isinstance(part, dict):
        return None
    if "text" in part:
        return part["text"]
    if "content" in part:
        return str(part["content"])
    return None

def _process_asset_pointer(self, part, content):
    """Process DALL-E asset pointer part, adding image to content."""
    asset_url = part.get("asset_pointer")
    if not asset_url:
        return
    media_path = self._resolve_and_copy_image(asset_url)
    if not media_path:
        return
    metadata = part.get("metadata") or {}
    dalle_data = metadata.get("dalle") if isinstance(metadata, dict) else {}
    prompt = dalle_data.get("prompt") if isinstance(dalle_data, dict) else None
    content.add_image(url=media_path, caption=prompt)

def _process_image_url(self, part, content):
    """Process image_url part (string or dict format)."""
    img_data = part["image_url"]
    if isinstance(img_data, str):
        if img_data.startswith("file-service://"):
            media_path = self._resolve_and_copy_image(img_data)
            if media_path:
                content.add_image(url=media_path)
        else:
            content.add_image(url=img_data)
    elif isinstance(img_data, dict):
        url = img_data.get("url")
        if not url:
            return
        if url.startswith("file-service://"):
            media_path = self._resolve_and_copy_image(url)
            if media_path:
                content.add_image(url=media_path, caption=img_data.get("detail"))
        else:
            content.add_image(url=url, caption=img_data.get("detail"))

def _process_tool_calls(self, content_data, content):
    """Process tool/function calls from content data."""
    if "tool_calls" in content_data:
        for tool_data in content_data["tool_calls"]:
            func_info = tool_data.get("function", {})
            args_str = func_info.get("arguments")
            arguments = json.loads(args_str) if args_str else {}
            tool_call = ToolCall(
                id=tool_data.get("id", ""),
                name=func_info.get("name", ""),
                arguments=arguments,
            )
            content.tool_calls.append(tool_call)

    if "function_call" in content_data:
        func_call = content_data["function_call"]
        args_str = func_call.get("arguments")
        arguments = json.loads(args_str) if args_str else {}
        tool_call = ToolCall(
            name=func_call.get("name", ""),
            arguments=arguments,
        )
        content.tool_calls.append(tool_call)
```

**Step 2: Refactor the main loop to use helper methods**

Replace lines 253-353 in `import_data()` with:

```python
                    text_parts = []
                    for part in parts:
                        # Try text extraction first
                        text = self._process_part(part)
                        if text is not None:
                            text_parts.append(text)
                        elif isinstance(part, dict):
                            # Handle multimodal content
                            if "asset_pointer" in part:
                                self._process_asset_pointer(part, content)
                            elif "image_url" in part:
                                self._process_image_url(part, content)

                            # Store original part content type in metadata
                            if "content_type" in part:
                                content.metadata["part_types"] = content.metadata.get(
                                    "part_types", []
                                )
                                content.metadata["part_types"].append(
                                    part["content_type"]
                                )

                    content.text = "\n".join(text_parts) if text_parts else ""
                    content.parts = parts

                    # Handle tool/function calls
                    self._process_tool_calls(content_data, content)
```

**Step 3: Run tests**

Run: `pytest tests/unit/test_openai_importer.py tests/unit/test_importers.py -v`
Expected: All pass — new helper method tests and existing import tests

**Step 4: Run full test suite**

Run: `pytest tests/unit/ -q --tb=short`
Expected: All pass (1296+ passed)

**Step 5: Commit**

```bash
git add ctk/integrations/importers/openai.py
git commit -m "refactor: extract multimodal parsing helpers in OpenAI importer

Reduces nesting from 7 levels to 2-3 levels by extracting:
- _process_part(): text extraction from content parts
- _process_asset_pointer(): DALL-E image handling
- _process_image_url(): image URL processing (string + dict)
- _process_tool_calls(): modern + legacy tool call extraction"
```

---

## Task 6: Update CLAUDE.md documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add exception handling patterns to Gotchas section**

After the existing Gotchas content, add:

```markdown
### Exception Handling
- Never use bare `except:` — always specify exception types
- `except Exception:` acceptable only in cleanup/finally blocks with logging
- HTTP errors: `requests.exceptions.RequestException`
- JSON parsing: `json.JSONDecodeError`
- File operations: `(IOError, OSError)`

### Constants
- Import timeouts/limits from `ctk/core/constants.py` instead of hardcoding
- Key constants: `DEFAULT_TIMEOUT` (120s), `HEALTH_CHECK_TIMEOUT` (5s), `DEFAULT_SEARCH_LIMIT` (1000)

### Shared Utilities
- Timestamp parsing: `from ctk.core.utils import parse_timestamp`
- JSON parsing: `from ctk.core.utils import try_parse_json`
- Input validation: `from ctk.core.input_validation import validate_conversation_id, validate_file_path`
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with exception handling, constants, and utilities patterns"
```

---

## Task 7: Update MEMORY.md and PLAN.md

**Files:**
- Modify: `MEMORY.md` (auto memory)
- Modify: `PLAN.md`

**Step 1: Update MEMORY.md**

Update test count and add constants note:
```markdown
## Test Status
- 1296+ unit tests pass, 1 pre-existing failure (test_taggers)
- Constants module: `ctk/core/constants.py` — import timeouts/limits from here
```

**Step 2: Mark phases 4, 6, 7 as DONE in PLAN.md**

Move phases 4, 6, 7 to the "Completed Phases" section.

**Step 3: Commit**

```bash
git add PLAN.md
git commit -m "docs: mark phases 4, 6, 7 complete in PLAN.md"
```

---

## Summary

| Task | Description | Key Files | Tests |
|------|-------------|-----------|-------|
| 1 | Create constants module | `constants.py` | 19 tests |
| 2 | Replace LLM provider hardcoded values | 5 LLM files | existing tests |
| 3 | Replace DB/MCP hardcoded values | `database.py`, `mcp_server.py` | existing tests |
| 4 | Write OpenAI importer helper tests | `test_openai_importer.py` | 24 tests |
| 5 | Extract helper methods in OpenAI importer | `openai.py` (importer) | task 4 tests |
| 6 | Update CLAUDE.md | `CLAUDE.md` | — |
| 7 | Update MEMORY.md and PLAN.md | `MEMORY.md`, `PLAN.md` | — |

**Estimated new tests: 43**
**Commits: 7**
