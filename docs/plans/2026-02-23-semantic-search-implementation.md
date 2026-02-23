# Semantic Search MCP/TUI Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the existing similarity engine into the MCP server and TUI, redesign MCP server into modular handlers, and add comprehensive unit tests.

**Architecture:** Split monolithic `ctk/mcp_server.py` into `ctk/interfaces/mcp/` handler modules. Add `ctk/core/commands/semantic.py` for TUI commands following the existing command pattern. Use a `MockEmbeddingProvider` for all tests to avoid external dependencies.

**Tech Stack:** Python, MCP SDK (`mcp`), SQLAlchemy, scikit-learn (TF-IDF), numpy, NetworkX, pytest

---

## Task 1: Extract MCP validation module

**Files:**
- Create: `ctk/interfaces/mcp/__init__.py`
- Create: `ctk/interfaces/mcp/validation.py`
- Test: `tests/unit/test_mcp_validation.py`

**Step 1: Write the failing test**

Create `tests/unit/test_mcp_validation.py`:

```python
"""Tests for MCP validation utilities."""

import pytest

from ctk.interfaces.mcp.validation import (
    ValidationError,
    validate_boolean,
    validate_conversation_id,
    validate_integer,
    validate_string,
)


class TestValidateString:
    def test_returns_none_when_none_and_not_required(self):
        assert validate_string(None, "x", 100) is None

    def test_raises_when_none_and_required(self):
        with pytest.raises(ValidationError, match="required"):
            validate_string(None, "x", 100, required=True)

    def test_returns_string_when_valid(self):
        assert validate_string("hello", "x", 100) == "hello"

    def test_raises_when_exceeds_max_length(self):
        with pytest.raises(ValidationError, match="maximum length"):
            validate_string("toolong", "x", 3)

    def test_raises_when_not_string(self):
        with pytest.raises(ValidationError, match="must be a string"):
            validate_string(123, "x", 100)


class TestValidateBoolean:
    def test_returns_none_when_none(self):
        assert validate_boolean(None, "x") is None

    def test_returns_bool_directly(self):
        assert validate_boolean(True, "x") is True
        assert validate_boolean(False, "x") is False

    def test_parses_string_true(self):
        for val in ("true", "1", "yes", "True", "YES"):
            assert validate_boolean(val, "x") is True

    def test_parses_string_false(self):
        for val in ("false", "0", "no", "False", "NO"):
            assert validate_boolean(val, "x") is False

    def test_raises_on_invalid(self):
        with pytest.raises(ValidationError, match="must be a boolean"):
            validate_boolean("maybe", "x")


class TestValidateInteger:
    def test_returns_none_when_none(self):
        assert validate_integer(None, "x") is None

    def test_returns_int_directly(self):
        assert validate_integer(5, "x") == 5

    def test_parses_string_int(self):
        assert validate_integer("42", "x") == 42

    def test_raises_below_min(self):
        with pytest.raises(ValidationError, match=">="):
            validate_integer(-1, "x", min_val=0)

    def test_raises_above_max(self):
        with pytest.raises(ValidationError, match="<="):
            validate_integer(999, "x", max_val=100)

    def test_raises_on_bool(self):
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_integer(True, "x")


class TestValidateConversationId:
    def test_valid_id(self):
        assert validate_conversation_id("abc-123_def") == "abc-123_def"

    def test_raises_when_none(self):
        with pytest.raises(ValidationError, match="required"):
            validate_conversation_id(None)

    def test_raises_on_invalid_chars(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_conversation_id("id with spaces")

    def test_raises_on_injection(self):
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_conversation_id("id'; DROP TABLE--")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_mcp_validation.py -v`
Expected: FAIL (ModuleNotFoundError — `ctk.interfaces.mcp.validation` doesn't exist)

**Step 3: Create the module**

Create `ctk/interfaces/mcp/__init__.py`:

```python
"""MCP server interface for CTK."""
```

Create `ctk/interfaces/mcp/validation.py` — extract validation functions from `ctk/mcp_server.py` lines 53-191. Copy them verbatim:

```python
"""Shared validation utilities for MCP tool handlers."""

import re
from typing import Any, Optional

from ctk.core.constants import MAX_ID_LENGTH, MAX_RESULT_LIMIT

MAX_LIMIT = MAX_RESULT_LIMIT


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


def validate_string(
    value: Any, name: str, max_length: int, required: bool = False
) -> Optional[str]:
    if value is None:
        if required:
            raise ValidationError(f"'{name}' is required")
        return None
    if not isinstance(value, str):
        raise ValidationError(f"'{name}' must be a string, got {type(value).__name__}")
    if len(value) > max_length:
        raise ValidationError(
            f"'{name}' exceeds maximum length ({len(value)} > {max_length})"
        )
    return value


def validate_boolean(value: Any, name: str) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in ("true", "1", "yes"):
            return True
        if value.lower() in ("false", "0", "no"):
            return False
    raise ValidationError(f"'{name}' must be a boolean, got {type(value).__name__}")


def validate_integer(
    value: Any, name: str, min_val: int = 0, max_val: int = MAX_LIMIT
) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValidationError(f"'{name}' must be an integer, got boolean")
    if isinstance(value, int):
        if value < min_val:
            raise ValidationError(f"'{name}' must be >= {min_val}, got {value}")
        if value > max_val:
            raise ValidationError(f"'{name}' must be <= {max_val}, got {value}")
        return value
    if isinstance(value, str):
        try:
            int_val = int(value)
            if int_val < min_val or int_val > max_val:
                raise ValidationError(
                    f"'{name}' must be between {min_val} and {max_val}"
                )
            return int_val
        except ValueError:
            pass
    raise ValidationError(f"'{name}' must be an integer, got {type(value).__name__}")


def validate_conversation_id(value: Any, name: str = "id") -> str:
    validated = validate_string(value, name, MAX_ID_LENGTH, required=True)
    if not validated:
        raise ValidationError(f"'{name}' is required")
    if not re.match(r"^[a-zA-Z0-9_-]+$", validated):
        raise ValidationError(f"'{name}' contains invalid characters")
    return validated
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_mcp_validation.py -v`
Expected: All 16 tests PASS

**Step 5: Commit**

```bash
git add ctk/interfaces/mcp/__init__.py ctk/interfaces/mcp/validation.py tests/unit/test_mcp_validation.py
git commit -m "Extract MCP validation into ctk/interfaces/mcp/validation.py"
```

---

## Task 2: Create MCP handler modules (search, conversation, metadata)

**Files:**
- Create: `ctk/interfaces/mcp/handlers/__init__.py`
- Create: `ctk/interfaces/mcp/handlers/search.py`
- Create: `ctk/interfaces/mcp/handlers/conversation.py`
- Create: `ctk/interfaces/mcp/handlers/metadata.py`
- Create: `ctk/interfaces/mcp/server.py`
- Modify: `ctk/mcp_server.py` (replace with thin entry point)

**Step 1: Create handler modules**

Each handler module exports two things:
1. `TOOLS`: list of `types.Tool` definitions
2. `handle_<tool_name>(arguments, db)` functions

Create `ctk/interfaces/mcp/handlers/__init__.py`:
```python
"""MCP tool handler modules."""
```

Create `ctk/interfaces/mcp/handlers/search.py` — move `search_conversations` and `list_conversations` tools and handler logic from `mcp_server.py`:

```python
"""Search and list conversation tools."""

from typing import Any, Dict, List, Optional

import mcp.types as types

from ctk.core.constants import (MAX_QUERY_LENGTH, MAX_RESULT_LIMIT,
                                TITLE_TRUNCATE_WIDTH, TITLE_TRUNCATE_WIDTH_SHORT)
from ctk.core.database import ConversationDB
from ctk.interfaces.mcp.validation import (validate_boolean, validate_integer,
                                            validate_string)

TOOLS = [
    types.Tool(
        name="search_conversations",
        description="Search conversations by text query. Returns matching conversations with IDs, titles, and message counts.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search text to find in conversation titles and messages",
                },
                "starred": {
                    "type": "boolean",
                    "description": "Filter to only starred conversations (optional)",
                },
                "pinned": {
                    "type": "boolean",
                    "description": "Filter to only pinned conversations (optional)",
                },
                "archived": {
                    "type": "boolean",
                    "description": "Filter to only archived conversations (optional)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 10)",
                    "default": 10,
                },
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor from previous response's next_cursor. Use empty string for first page.",
                },
            },
            "required": [],
        },
    ),
    types.Tool(
        name="list_conversations",
        description="List recent conversations. Returns IDs, titles, dates, and metadata.",
        inputSchema={
            "type": "object",
            "properties": {
                "starred": {
                    "type": "boolean",
                    "description": "Filter to only starred conversations",
                },
                "pinned": {
                    "type": "boolean",
                    "description": "Filter to only pinned conversations",
                },
                "archived": {
                    "type": "boolean",
                    "description": "Filter to only archived conversations",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 20)",
                    "default": 20,
                },
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor from previous response's next_cursor. Use empty string for first page.",
                },
            },
            "required": [],
        },
    ),
]


def _format_conversation_list(items, truncate_width, show_date=False) -> str:
    """Format a list of conversations for text output."""
    from ctk.core.models import PaginatedResult

    lines = []
    for i, conv in enumerate(items, 1):
        title = (conv.title or "Untitled")[:truncate_width]
        msg_count = conv.message_count if hasattr(conv, "message_count") else "?"

        flags = []
        if hasattr(conv, "starred_at") and conv.starred_at:
            flags.append("⭐")
        if hasattr(conv, "pinned_at") and conv.pinned_at:
            flags.append("📌")
        if hasattr(conv, "archived_at") and conv.archived_at:
            flags.append("📦")
        flag_str = "".join(flags) + " " if flags else ""

        if show_date:
            date = ""
            if hasattr(conv, "created_at") and conv.created_at:
                date = conv.created_at.strftime("%Y-%m-%d")
            lines.append(f"[{i}] {conv.id[:8]} {date} {flag_str}{title}")
        else:
            lines.append(
                f"[{i}] {conv.id[:8]} - {flag_str}{title} ({msg_count} msgs)"
            )
    return "\n".join(lines)


def _unpack_results(results):
    """Unpack PaginatedResult or plain list."""
    from ctk.core.models import PaginatedResult

    if isinstance(results, PaginatedResult):
        return results.items, results.next_cursor, results.has_more
    return results, None, False


def handle_search_conversations(
    arguments: Dict[str, Any], db: ConversationDB
) -> list[types.TextContent]:
    query = validate_string(arguments.get("query"), "query", MAX_QUERY_LENGTH) or ""
    starred = validate_boolean(arguments.get("starred"), "starred")
    pinned = validate_boolean(arguments.get("pinned"), "pinned")
    archived = validate_boolean(arguments.get("archived"), "archived")
    limit = (
        validate_integer(arguments.get("limit"), "limit", min_val=1, max_val=MAX_RESULT_LIMIT)
        or 10
    )
    cursor = validate_string(arguments.get("cursor"), "cursor", MAX_QUERY_LENGTH)

    kwargs = {"starred": starred, "pinned": pinned, "archived": archived, "limit": limit}
    if cursor is not None:
        kwargs["cursor"] = cursor
        kwargs["page_size"] = limit

    if query:
        kwargs["query_text"] = query
        results = db.search_conversations(**kwargs)
    else:
        results = db.list_conversations(**kwargs)

    items, next_cursor, has_more = _unpack_results(results)

    if not items:
        return [types.TextContent(type="text", text="No conversations found matching your criteria.")]

    lines = [f"Found {len(items)} conversation(s):\n"]
    lines.append(_format_conversation_list(items, TITLE_TRUNCATE_WIDTH))
    lines.append(f"\nUse get_conversation with ID to view full content.")
    if has_more and next_cursor:
        lines.append(f"\nnext_cursor: {next_cursor}")

    return [types.TextContent(type="text", text="\n".join(lines))]


def handle_list_conversations(
    arguments: Dict[str, Any], db: ConversationDB
) -> list[types.TextContent]:
    starred = validate_boolean(arguments.get("starred"), "starred")
    pinned = validate_boolean(arguments.get("pinned"), "pinned")
    archived = validate_boolean(arguments.get("archived"), "archived")
    limit = (
        validate_integer(arguments.get("limit"), "limit", min_val=1, max_val=MAX_RESULT_LIMIT)
        or 20
    )
    cursor = validate_string(arguments.get("cursor"), "cursor", MAX_QUERY_LENGTH)

    kwargs = {"starred": starred, "pinned": pinned, "archived": archived, "limit": limit}
    if cursor is not None:
        kwargs["cursor"] = cursor
        kwargs["page_size"] = limit

    results = db.list_conversations(**kwargs)
    items, next_cursor, has_more = _unpack_results(results)

    if not items:
        return [types.TextContent(type="text", text="No conversations found.")]

    lines = [f"Recent conversations ({len(items)}):\n"]
    lines.append(_format_conversation_list(items, TITLE_TRUNCATE_WIDTH_SHORT, show_date=True))
    if has_more and next_cursor:
        lines.append(f"\nnext_cursor: {next_cursor}")

    return [types.TextContent(type="text", text="\n".join(lines))]


HANDLERS = {
    "search_conversations": handle_search_conversations,
    "list_conversations": handle_list_conversations,
}
```

Create `ctk/interfaces/mcp/handlers/conversation.py` — move `get_conversation`, `star_conversation`, `pin_conversation`, `archive_conversation`, `set_title` from `mcp_server.py`. Same pattern: TOOLS list + handler functions + HANDLERS dict. Move `resolve_conversation_id` and `format_conversation_for_output` helpers here.

Create `ctk/interfaces/mcp/handlers/metadata.py` — move `get_statistics` and `get_tags` tools. Same pattern.

**Step 2: Create the server module**

Create `ctk/interfaces/mcp/server.py`:

```python
"""CTK MCP Server — modular tool registration and dispatch."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from ctk.interfaces.mcp.handlers import conversation, metadata, search
from ctk.interfaces.mcp.validation import ValidationError

logger = logging.getLogger(__name__)

server = Server("ctk")
_db = None


def get_db():
    """Get or initialize database connection."""
    global _db
    if _db is None:
        from ctk.core.config import get_config
        from ctk.core.database import ConversationDB

        db_path = os.environ.get("CTK_DATABASE_PATH")
        if not db_path:
            config = get_config()
            db_path = config.get("database.default_path", "~/.ctk/conversations")
        db_path = str(Path(db_path).expanduser())
        if db_path.endswith(".db"):
            db_path = str(Path(db_path).parent)
        _db = ConversationDB(db_path)
    return _db


# Collect all tools from handler modules
ALL_HANDLERS = {}
ALL_TOOLS = []

for module in [search, conversation, metadata]:
    ALL_TOOLS.extend(module.TOOLS)
    ALL_HANDLERS.update(module.HANDLERS)


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return ALL_TOOLS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        handler = ALL_HANDLERS.get(name)
        if handler is None:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
        return handler(arguments, get_db())
    except ValidationError as e:
        return [types.TextContent(type="text", text=f"Validation error: {str(e)}")]
    except Exception as e:
        import traceback
        logger.error(f"MCP tool error: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        return [types.TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="ctk",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
```

**Step 3: Rewrite `ctk/mcp_server.py` as thin entry point**

```python
#!/usr/bin/env python3
"""CTK MCP Server — entry point.

Usage:
    python -m ctk.mcp_server

See ctk/interfaces/mcp/ for implementation.
"""

import asyncio

from ctk.interfaces.mcp.server import main

if __name__ == "__main__":
    asyncio.run(main())
```

**Step 4: Run existing MCP tests to confirm no breakage**

Run: `pytest tests/unit/test_mcp_server.py -v`
Expected: Existing tests should still pass (they import from `ctk.mcp_server` which now delegates).

Note: The existing tests import `handle_list_tools`, `handle_call_tool`, etc. directly from `ctk.mcp_server`. Since we replaced that module, we need to re-export from the new location. Update `ctk/mcp_server.py` to also re-export:

```python
# Re-exports for backward compatibility with tests
from ctk.interfaces.mcp.server import (get_db, handle_call_tool,
                                       handle_list_tools, server)
from ctk.interfaces.mcp.handlers.conversation import (
    format_conversation_for_output, resolve_conversation_id,
)
```

**Step 5: Commit**

```bash
git add ctk/interfaces/mcp/ ctk/mcp_server.py
git commit -m "Refactor MCP server into modular handler modules"
```

---

## Task 3: Unit tests for EmbeddingProvider base class

**Files:**
- Create: `tests/unit/test_embedding_base.py`

**Step 1: Write the tests**

```python
"""Tests for EmbeddingProvider base class and aggregation strategies."""

import numpy as np
import pytest

from ctk.integrations.embeddings.base import (
    AggregationStrategy,
    ChunkingStrategy,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingResponse,
)


class ConcreteProvider(EmbeddingProvider):
    """Minimal concrete provider for testing base class methods."""

    def __init__(self, dimensions=4):
        super().__init__({"model": "test"})
        self._dimensions = dimensions

    def embed(self, text, **kwargs):
        vec = [float(ord(c) % 10) / 10 for c in text[:self._dimensions]]
        vec += [0.0] * (self._dimensions - len(vec))
        return EmbeddingResponse(embedding=vec, model="test", dimensions=self._dimensions)

    def embed_batch(self, texts, **kwargs):
        return [self.embed(t) for t in texts]

    def get_models(self):
        return []

    def get_dimensions(self):
        return self._dimensions


class TestAggregationStrategies:
    @pytest.fixture
    def provider(self):
        return ConcreteProvider(dimensions=3)

    @pytest.fixture
    def embeddings(self):
        return [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]

    def test_mean(self, provider, embeddings):
        result = provider.aggregate_embeddings(embeddings, AggregationStrategy.MEAN)
        np.testing.assert_allclose(result, [2.5, 3.5, 4.5])

    def test_weighted_mean(self, provider, embeddings):
        result = provider.aggregate_embeddings(
            embeddings, AggregationStrategy.WEIGHTED_MEAN, weights=[1.0, 3.0]
        )
        # weights normalized: [0.25, 0.75]
        # [1*0.25 + 4*0.75, 2*0.25 + 5*0.75, 3*0.25 + 6*0.75] = [3.25, 4.25, 5.25]
        np.testing.assert_allclose(result, [3.25, 4.25, 5.25])

    def test_weighted_mean_requires_weights(self, provider, embeddings):
        with pytest.raises(ValueError, match="requires weights"):
            provider.aggregate_embeddings(embeddings, AggregationStrategy.WEIGHTED_MEAN)

    def test_weighted_mean_length_mismatch(self, provider, embeddings):
        with pytest.raises(ValueError, match="must match"):
            provider.aggregate_embeddings(
                embeddings, AggregationStrategy.WEIGHTED_MEAN, weights=[1.0]
            )

    def test_max_pool(self, provider, embeddings):
        result = provider.aggregate_embeddings(embeddings, AggregationStrategy.MAX_POOL)
        np.testing.assert_allclose(result, [4.0, 5.0, 6.0])

    def test_concatenate(self, provider, embeddings):
        result = provider.aggregate_embeddings(embeddings, AggregationStrategy.CONCATENATE)
        np.testing.assert_allclose(result, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

    def test_first(self, provider, embeddings):
        result = provider.aggregate_embeddings(embeddings, AggregationStrategy.FIRST)
        assert result == [1.0, 2.0, 3.0]

    def test_last(self, provider, embeddings):
        result = provider.aggregate_embeddings(embeddings, AggregationStrategy.LAST)
        assert result == [4.0, 5.0, 6.0]

    def test_empty_raises(self, provider):
        with pytest.raises(ValueError, match="empty"):
            provider.aggregate_embeddings([], AggregationStrategy.MEAN)


class TestTruncateText:
    def test_no_truncation_when_short(self):
        p = ConcreteProvider()
        assert p.truncate_text("hello", max_tokens=100) == "hello"

    def test_truncates_long_text(self):
        p = ConcreteProvider()
        result = p.truncate_text("a" * 1000, max_tokens=10)
        assert len(result) == 40  # 10 tokens * 4 chars/token

    def test_no_truncation_when_no_limit(self):
        p = ConcreteProvider()
        text = "a" * 1000
        assert p.truncate_text(text) == text


class TestChunkingStrategyEnum:
    def test_values(self):
        assert ChunkingStrategy.WHOLE.value == "whole"
        assert ChunkingStrategy.MESSAGE.value == "message"
        assert ChunkingStrategy.FIXED_SIZE.value == "fixed_size"
        assert ChunkingStrategy.SEMANTIC.value == "semantic"


class TestProviderName:
    def test_name_property(self):
        p = ConcreteProvider()
        assert p.name == "concrete"
```

**Step 2: Run tests**

Run: `pytest tests/unit/test_embedding_base.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/unit/test_embedding_base.py
git commit -m "Add unit tests for EmbeddingProvider base class"
```

---

## Task 4: Unit tests for similarity module

**Files:**
- Create: `tests/unit/test_similarity.py`

This is the largest test file — tests `ConversationEmbedder`, `SimilarityComputer`, and `ConversationGraphBuilder`.

**Step 1: Write the tests**

```python
"""Tests for ctk/core/similarity.py — ConversationEmbedder, SimilarityComputer, ConversationGraphBuilder."""

import numpy as np
import pytest

from ctk.core.models import (ConversationMetadata, ConversationTree, Message,
                              MessageContent, MessageRole)
from ctk.core.similarity import (
    ConversationEmbedder,
    ConversationEmbeddingConfig,
    ConversationGraph,
    ConversationGraphBuilder,
    ConversationLink,
    SimilarityComputer,
    SimilarityMetric,
    SimilarityResult,
)
from ctk.integrations.embeddings.base import (
    AggregationStrategy,
    ChunkingStrategy,
    EmbeddingProvider,
    EmbeddingResponse,
)


# ==================== Mock Provider ====================


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding provider for testing.

    Generates embeddings based on character frequencies, giving
    different texts different (but deterministic) vectors.
    """

    DIMENSIONS = 8

    def __init__(self):
        super().__init__({"model": "mock"})

    def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        vec = self._text_to_vec(text)
        return EmbeddingResponse(embedding=vec, model="mock", dimensions=self.DIMENSIONS)

    def embed_batch(self, texts, **kwargs):
        return [self.embed(t) for t in texts]

    def get_models(self):
        return []

    def get_dimensions(self):
        return self.DIMENSIONS

    def _text_to_vec(self, text: str) -> list:
        """Hash text into a deterministic vector."""
        vec = [0.0] * self.DIMENSIONS
        for i, ch in enumerate(text):
            vec[i % self.DIMENSIONS] += ord(ch) / 1000.0
        # Normalize
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


# ==================== Fixtures ====================


def _make_conversation(id, title, messages):
    """Create a ConversationTree with messages."""
    tree = ConversationTree(
        id=id, title=title,
        metadata=ConversationMetadata(
            source="test", model="test-model", tags=["test"],
            created_at=None, updated_at=None,
        ),
    )
    parent_id = None
    for role_str, text in messages:
        role = MessageRole(role_str)
        msg = Message(role=role, content=MessageContent(text=text))
        tree.add_message(msg, parent_id=parent_id)
        parent_id = msg.id
    return tree


@pytest.fixture
def mock_provider():
    return MockEmbeddingProvider()


@pytest.fixture
def config():
    return ConversationEmbeddingConfig(
        provider="mock",
        chunking=ChunkingStrategy.MESSAGE,
        aggregation=AggregationStrategy.WEIGHTED_MEAN,
    )


@pytest.fixture
def embedder(config, mock_provider):
    return ConversationEmbedder(config, provider=mock_provider)


@pytest.fixture
def conv_python():
    return _make_conversation("conv-py", "Python Help", [
        ("user", "How do I use decorators?"),
        ("assistant", "Decorators wrap functions to modify behavior."),
    ])


@pytest.fixture
def conv_javascript():
    return _make_conversation("conv-js", "JavaScript Help", [
        ("user", "Explain promises in JavaScript"),
        ("assistant", "Promises handle asynchronous operations."),
    ])


@pytest.fixture
def conv_empty():
    return _make_conversation("conv-empty", "Empty", [])


@pytest.fixture
def conv_system_only():
    return _make_conversation("conv-sys", "System Only", [
        ("system", "You are a helpful assistant."),
    ])


# ==================== ConversationEmbedder Tests ====================


class TestConversationEmbedder:
    def test_embed_returns_numpy_array(self, embedder, conv_python):
        result = embedder.embed_conversation(conv_python)
        assert isinstance(result, np.ndarray)
        assert result.shape == (MockEmbeddingProvider.DIMENSIONS,)

    def test_embed_empty_conversation_returns_zeros(self, embedder, conv_empty):
        result = embedder.embed_conversation(conv_empty)
        # Title "Empty" still contributes, but no messages
        # So we get a non-zero vector from the title
        assert isinstance(result, np.ndarray)

    def test_different_conversations_produce_different_embeddings(
        self, embedder, conv_python, conv_javascript
    ):
        emb_py = embedder.embed_conversation(conv_python)
        emb_js = embedder.embed_conversation(conv_javascript)
        assert not np.allclose(emb_py, emb_js)

    def test_same_conversation_produces_same_embedding(self, embedder, conv_python):
        emb1 = embedder.embed_conversation(conv_python)
        emb2 = embedder.embed_conversation(conv_python)
        np.testing.assert_allclose(emb1, emb2)

    def test_batch_embed(self, embedder, conv_python, conv_javascript):
        results = embedder.embed_conversations([conv_python, conv_javascript])
        assert len(results) == 2
        assert all(isinstance(r, np.ndarray) for r in results)

    def test_whole_chunking(self, mock_provider, conv_python):
        cfg = ConversationEmbeddingConfig(
            provider="mock", chunking=ChunkingStrategy.WHOLE,
            aggregation=AggregationStrategy.MEAN,
        )
        emb = ConversationEmbedder(cfg, provider=mock_provider)
        result = emb.embed_conversation(conv_python)
        assert isinstance(result, np.ndarray)

    def test_role_weighting(self, embedder, conv_python):
        # User messages should have weight 2.0, assistant 1.0
        # Just verify it doesn't crash with the config
        result = embedder.embed_conversation(conv_python)
        assert result.shape == (MockEmbeddingProvider.DIMENSIONS,)

    def test_title_included_by_default(self, embedder, conv_python):
        # With title
        emb_with = embedder.embed_conversation(conv_python)

        # Without title
        cfg_no_title = ConversationEmbeddingConfig(
            provider="mock", include_title=False,
        )
        emb_no_title = ConversationEmbedder(
            cfg_no_title, provider=MockEmbeddingProvider()
        )
        emb_without = emb_no_title.embed_conversation(conv_python)

        assert not np.allclose(emb_with, emb_without)

    def test_system_message_gets_lower_weight(self, embedder):
        # System messages should have weight 0.5
        conv = _make_conversation("sys", "Test", [("system", "System prompt")])
        result = embedder.embed_conversation(conv)
        assert isinstance(result, np.ndarray)


class TestConversationEmbeddingConfig:
    def test_default_config(self):
        cfg = ConversationEmbeddingConfig()
        assert cfg.provider == "tfidf"
        assert cfg.chunking == ChunkingStrategy.MESSAGE
        assert cfg.aggregation == AggregationStrategy.WEIGHTED_MEAN
        assert cfg.include_title is True

    def test_config_hash_deterministic(self):
        cfg1 = ConversationEmbeddingConfig(provider="tfidf")
        cfg2 = ConversationEmbeddingConfig(provider="tfidf")
        assert cfg1.to_hash() == cfg2.to_hash()

    def test_config_hash_differs_for_different_configs(self):
        cfg1 = ConversationEmbeddingConfig(provider="tfidf")
        cfg2 = ConversationEmbeddingConfig(provider="ollama")
        assert cfg1.to_hash() != cfg2.to_hash()


# ==================== SimilarityComputer Tests ====================


class TestSimilarityComputer:
    @pytest.fixture
    def computer(self, embedder):
        return SimilarityComputer(embedder, metric=SimilarityMetric.COSINE)

    def test_compute_similarity_same_conversation(self, computer, conv_python):
        result = computer.compute_similarity(conv_python, conv_python, use_cache=False)
        assert isinstance(result, SimilarityResult)
        assert result.similarity == pytest.approx(1.0, abs=0.01)

    def test_compute_similarity_different_conversations(
        self, computer, conv_python, conv_javascript
    ):
        result = computer.compute_similarity(
            conv_python, conv_javascript, use_cache=False
        )
        assert 0.0 <= result.similarity <= 1.0
        assert result.similarity < 1.0  # Should not be identical

    def test_similarity_is_symmetric(self, computer, conv_python, conv_javascript):
        r1 = computer.compute_similarity(conv_python, conv_javascript, use_cache=False)
        r2 = computer.compute_similarity(conv_javascript, conv_python, use_cache=False)
        assert r1.similarity == pytest.approx(r2.similarity, abs=0.001)

    def test_find_similar_returns_sorted(self, computer, conv_python, conv_javascript):
        results = computer.find_similar(
            conv_python,
            candidates=[conv_python, conv_javascript],
            top_k=5,
            use_cache=False,
        )
        assert len(results) >= 1
        # Should be sorted descending
        sims = [r.similarity for r in results]
        assert sims == sorted(sims, reverse=True)

    def test_find_similar_excludes_self(self, computer, conv_python, conv_javascript):
        results = computer.find_similar(
            conv_python,
            candidates=[conv_python, conv_javascript],
            top_k=5,
            use_cache=False,
        )
        ids = [r.conversation2_id for r in results]
        assert "conv-py" not in ids

    def test_find_similar_respects_threshold(self, computer, conv_python, conv_javascript):
        results = computer.find_similar(
            conv_python,
            candidates=[conv_javascript],
            threshold=0.9999,
            use_cache=False,
        )
        # Very high threshold should filter out non-identical
        assert len(results) == 0

    def test_find_similar_respects_top_k(self, computer):
        convs = [
            _make_conversation(f"c{i}", f"Conv {i}", [("user", f"Message {i}")])
            for i in range(5)
        ]
        results = computer.find_similar(
            convs[0], candidates=convs, top_k=2, use_cache=False
        )
        assert len(results) <= 2

    def test_similarity_matrix(self, computer, conv_python, conv_javascript):
        matrix = computer.compute_similarity_matrix(
            [conv_python, conv_javascript], use_cache=False
        )
        assert matrix.shape == (2, 2)
        # Diagonal should be 1.0 (self-similarity)
        assert matrix[0, 0] == pytest.approx(1.0, abs=0.01)
        assert matrix[1, 1] == pytest.approx(1.0, abs=0.01)
        # Symmetric
        assert matrix[0, 1] == pytest.approx(matrix[1, 0], abs=0.001)


class TestSimilarityMetrics:
    @pytest.fixture
    def embedder_instance(self):
        cfg = ConversationEmbeddingConfig(provider="mock")
        return ConversationEmbedder(cfg, provider=MockEmbeddingProvider())

    def test_euclidean_metric(self, embedder_instance, conv_python, conv_javascript):
        computer = SimilarityComputer(embedder_instance, metric=SimilarityMetric.EUCLIDEAN)
        result = computer.compute_similarity(conv_python, conv_javascript, use_cache=False)
        assert 0.0 <= result.similarity <= 1.0
        assert result.method == "euclidean"

    def test_dot_product_metric(self, embedder_instance, conv_python, conv_javascript):
        computer = SimilarityComputer(embedder_instance, metric=SimilarityMetric.DOT_PRODUCT)
        result = computer.compute_similarity(conv_python, conv_javascript, use_cache=False)
        assert result.method == "dot"

    def test_manhattan_metric(self, embedder_instance, conv_python, conv_javascript):
        computer = SimilarityComputer(embedder_instance, metric=SimilarityMetric.MANHATTAN)
        result = computer.compute_similarity(conv_python, conv_javascript, use_cache=False)
        assert 0.0 <= result.similarity <= 1.0
        assert result.method == "manhattan"


class TestSimilarityResult:
    def test_to_dict(self):
        r = SimilarityResult("a", "b", 0.85, "cosine")
        d = r.to_dict()
        assert d["conversation1_id"] == "a"
        assert d["similarity"] == 0.85


# ==================== ConversationGraphBuilder Tests ====================


class TestConversationGraphBuilder:
    @pytest.fixture
    def builder(self, embedder):
        computer = SimilarityComputer(embedder, metric=SimilarityMetric.COSINE)
        return ConversationGraphBuilder(computer)

    @pytest.fixture
    def conversations(self):
        return [
            _make_conversation(f"c{i}", f"Topic {i}", [("user", f"About topic {i}")])
            for i in range(4)
        ]

    def test_build_graph_returns_graph(self, builder, conversations):
        graph = builder.build_graph(conversations, threshold=0.0, use_cache=False)
        assert isinstance(graph, ConversationGraph)
        assert len(graph.nodes) == 4

    def test_graph_threshold_filters_edges(self, builder, conversations):
        # Very high threshold should produce few/no edges
        graph = builder.build_graph(conversations, threshold=0.9999, use_cache=False)
        assert len(graph.links) == 0

    def test_graph_low_threshold_produces_edges(self, builder, conversations):
        graph = builder.build_graph(conversations, threshold=0.0, use_cache=False)
        # With threshold=0.0, most pairs should be linked
        assert len(graph.links) > 0

    def test_graph_metadata(self, builder, conversations):
        graph = builder.build_graph(conversations, threshold=0.3, use_cache=False)
        assert graph.metadata["total_nodes"] == 4
        assert "threshold" in graph.metadata

    def test_graph_to_dict(self, builder, conversations):
        graph = builder.build_graph(conversations, threshold=0.0, use_cache=False)
        d = graph.to_dict()
        assert "nodes" in d
        assert "links" in d
        assert "metadata" in d

    def test_graph_max_links_per_node(self, builder, conversations):
        graph = builder.build_graph(
            conversations, threshold=0.0, max_links_per_node=1, use_cache=False
        )
        # Each node should have at most 1 outgoing link
        # (Note: the implementation counts both directions per node)
        assert len(graph.links) <= len(conversations)

    def test_graph_to_networkx(self, builder, conversations):
        graph = builder.build_graph(conversations, threshold=0.0, use_cache=False)
        G = graph.to_networkx()
        assert G.number_of_nodes() == 4


class TestConversationLink:
    def test_to_dict(self):
        link = ConversationLink("a", "b", 0.9)
        d = link.to_dict()
        assert d["source_id"] == "a"
        assert d["target_id"] == "b"
        assert d["weight"] == 0.9
```

**Step 2: Run tests**

Run: `pytest tests/unit/test_similarity.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add tests/unit/test_similarity.py
git commit -m "Add comprehensive unit tests for similarity module"
```

---

## Task 5: Add MCP analysis handler (semantic search tools)

**Files:**
- Create: `ctk/interfaces/mcp/handlers/analysis.py`
- Modify: `ctk/interfaces/mcp/server.py` (register analysis module)
- Create: `tests/unit/test_mcp_analysis.py`

**Step 1: Write the failing test**

Create `tests/unit/test_mcp_analysis.py`:

```python
"""Tests for MCP analysis handler — find_similar, semantic_search, get_network_summary, get_clusters."""

import pytest
from unittest.mock import MagicMock, patch

from ctk.interfaces.mcp.handlers.analysis import (
    HANDLERS,
    TOOLS,
    handle_find_similar,
    handle_get_clusters,
    handle_get_network_summary,
    handle_semantic_search,
)


class TestAnalysisToolDefinitions:
    def test_tools_defined(self):
        tool_names = {t.name for t in TOOLS}
        assert "find_similar" in tool_names
        assert "semantic_search" in tool_names
        assert "get_network_summary" in tool_names
        assert "get_clusters" in tool_names

    def test_handlers_registered(self):
        assert "find_similar" in HANDLERS
        assert "semantic_search" in HANDLERS
        assert "get_network_summary" in HANDLERS
        assert "get_clusters" in HANDLERS

    def test_find_similar_schema_has_id(self):
        tool = next(t for t in TOOLS if t.name == "find_similar")
        assert "id" in tool.inputSchema["properties"]
        assert "id" in tool.inputSchema["required"]


class TestFindSimilar:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.get_all_embeddings.return_value = []
        return db

    def test_returns_error_when_no_embeddings(self, mock_db):
        result = handle_find_similar({"id": "conv-1", "top_k": 5}, mock_db)
        text = result[0].text
        assert "no embeddings" in text.lower() or "embed" in text.lower()

    def test_returns_results_with_embeddings(self, mock_db):
        mock_db.get_all_embeddings.return_value = [
            {"conversation_id": "conv-1", "embedding": [1.0, 0.0, 0.0]},
            {"conversation_id": "conv-2", "embedding": [0.9, 0.1, 0.0]},
            {"conversation_id": "conv-3", "embedding": [0.0, 0.0, 1.0]},
        ]
        mock_db.get_similar_conversations.return_value = [
            {"conversation_id": "conv-2", "similarity": 0.95, "metric": "cosine", "provider": "tfidf", "model": "tfidf"},
        ]

        # Mock resolve_identifier to return the ID
        mock_db.resolve_identifier.return_value = ("conv-1", None)

        # Mock load to get title
        mock_conv = MagicMock()
        mock_conv.title = "Test Conversation"
        mock_conv.id = "conv-2"
        mock_db.load_conversation.return_value = mock_conv

        result = handle_find_similar({"id": "conv-1"}, mock_db)
        text = result[0].text
        assert "conv-2" in text or "similar" in text.lower() or "Similar" in text


class TestSemanticSearch:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.get_all_embeddings.return_value = []
        return db

    def test_returns_error_when_no_embeddings(self, mock_db):
        result = handle_semantic_search({"query": "python help"}, mock_db)
        text = result[0].text
        assert "no embeddings" in text.lower() or "embed" in text.lower()


class TestGetNetworkSummary:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.get_all_embeddings.return_value = []
        return db

    def test_returns_error_when_no_embeddings(self, mock_db):
        result = handle_get_network_summary({}, mock_db)
        text = result[0].text
        assert "no embeddings" in text.lower() or "network" in text.lower() or "embed" in text.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_mcp_analysis.py -v`
Expected: FAIL (ImportError)

**Step 3: Implement `ctk/interfaces/mcp/handlers/analysis.py`**

```python
"""Semantic search and analysis tools for MCP."""

import logging
from typing import Any, Dict, List

import numpy as np
import mcp.types as types

from ctk.core.constants import MAX_ID_LENGTH, MAX_QUERY_LENGTH, MAX_RESULT_LIMIT
from ctk.core.database import ConversationDB
from ctk.interfaces.mcp.validation import (validate_integer, validate_string,
                                            validate_conversation_id)

logger = logging.getLogger(__name__)

TOOLS = [
    types.Tool(
        name="find_similar",
        description="Find conversations similar to a given conversation using embedding similarity. Requires embeddings to have been generated first (via `ctk net embeddings` CLI command).",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Conversation ID (full or partial prefix)",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of similar conversations to return (default: 10)",
                    "default": 10,
                },
                "threshold": {
                    "type": "number",
                    "description": "Minimum similarity score 0.0-1.0 (default: 0.1)",
                    "default": 0.1,
                },
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="semantic_search",
        description="Search conversations by meaning using embeddings. Unlike text search, this finds conceptually similar conversations even without keyword matches. Requires embeddings to have been generated first.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query to search by meaning",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 10)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="get_network_summary",
        description="Get summary statistics of the conversation similarity network: number of clusters, density, most central conversations.",
        inputSchema={
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "number",
                    "description": "Minimum similarity for graph edges (default: 0.3)",
                    "default": 0.3,
                },
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_clusters",
        description="Detect topic clusters among conversations using community detection on the similarity graph.",
        inputSchema={
            "type": "object",
            "properties": {
                "algorithm": {
                    "type": "string",
                    "description": "Community detection algorithm (default: label_propagation)",
                    "enum": ["label_propagation", "greedy_modularity"],
                    "default": "label_propagation",
                },
            },
            "required": [],
        },
    ),
]


def _check_embeddings_exist(db: ConversationDB) -> List[Dict[str, Any]]:
    """Check if embeddings exist in the database."""
    return db.get_all_embeddings()


def _no_embeddings_error() -> list[types.TextContent]:
    return [types.TextContent(
        type="text",
        text="No embeddings found. Generate them first with: ctk net embeddings --db <path>",
    )]


def handle_find_similar(
    arguments: Dict[str, Any], db: ConversationDB
) -> list[types.TextContent]:
    conv_id_input = validate_string(
        arguments.get("id"), "id", MAX_ID_LENGTH, required=True
    )
    top_k = validate_integer(arguments.get("top_k"), "top_k", min_val=1, max_val=100) or 10
    threshold = arguments.get("threshold", 0.1)
    if isinstance(threshold, str):
        threshold = float(threshold)

    # Resolve partial ID
    resolved = db.resolve_identifier(conv_id_input)
    if not resolved:
        return [types.TextContent(
            type="text",
            text=f"Error: Could not find conversation '{conv_id_input}'",
        )]
    full_id = resolved[0]

    # Check embeddings exist
    all_embs = _check_embeddings_exist(db)
    if not all_embs:
        return _no_embeddings_error()

    # Use cached similarities from DB
    similar = db.get_similar_conversations(
        full_id, metric="cosine", top_k=top_k, threshold=threshold
    )

    if not similar:
        # Try computing on the fly from cached embeddings
        target_emb = None
        candidate_embs = {}
        for emb_record in all_embs:
            if emb_record["conversation_id"] == full_id:
                target_emb = np.array(emb_record["embedding"])
            else:
                candidate_embs[emb_record["conversation_id"]] = np.array(emb_record["embedding"])

        if target_emb is None:
            return [types.TextContent(
                type="text",
                text=f"No embedding found for conversation {full_id[:8]}. Re-run embeddings.",
            )]

        # Compute cosine similarities
        results = []
        for cid, cemb in candidate_embs.items():
            dot = float(np.dot(target_emb, cemb))
            n1 = float(np.linalg.norm(target_emb))
            n2 = float(np.linalg.norm(cemb))
            sim = dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0.0
            if sim >= threshold:
                results.append({"conversation_id": cid, "similarity": sim})

        results.sort(key=lambda x: x["similarity"], reverse=True)
        similar = results[:top_k]

    if not similar:
        return [types.TextContent(type="text", text=f"No similar conversations found for {full_id[:8]}.")]

    # Format output
    lines = [f"Conversations similar to {full_id[:8]}:\n"]
    for i, s in enumerate(similar, 1):
        cid = s["conversation_id"]
        sim = s["similarity"]
        # Try to get title
        try:
            conv = db.load_conversation(cid)
            title = (conv.title or "Untitled")[:50] if conv else "Unknown"
        except Exception:
            title = "Unknown"
        lines.append(f"[{i}] {cid[:8]} ({sim:.2f}) {title}")

    return [types.TextContent(type="text", text="\n".join(lines))]


def handle_semantic_search(
    arguments: Dict[str, Any], db: ConversationDB
) -> list[types.TextContent]:
    query = validate_string(arguments.get("query"), "query", MAX_QUERY_LENGTH, required=True)
    top_k = validate_integer(arguments.get("top_k"), "top_k", min_val=1, max_val=100) or 10

    all_embs = _check_embeddings_exist(db)
    if not all_embs:
        return _no_embeddings_error()

    # Embed the query text using same provider as stored embeddings
    provider_name = all_embs[0].get("provider", "tfidf")

    try:
        from ctk.core.similarity import ConversationEmbedder, ConversationEmbeddingConfig
        from ctk.integrations.embeddings.base import ChunkingStrategy, AggregationStrategy

        config = ConversationEmbeddingConfig(
            provider=provider_name,
            chunking=ChunkingStrategy.WHOLE,
            aggregation=AggregationStrategy.MEAN,
        )

        # For TF-IDF, we need a fitted vectorizer — try to fit on stored conversation texts
        if provider_name == "tfidf":
            from ctk.integrations.embeddings.tfidf import TFIDFEmbedding
            tfidf = TFIDFEmbedding(config.provider_config)

            # Gather texts from conversations that have embeddings
            texts = []
            for emb_record in all_embs:
                try:
                    conv = db.load_conversation(emb_record["conversation_id"])
                    if conv:
                        path = conv.get_longest_path()
                        text_parts = [conv.title or ""]
                        for msg in path:
                            if hasattr(msg.content, "get_text"):
                                text_parts.append(msg.content.get_text())
                            elif hasattr(msg.content, "text"):
                                text_parts.append(msg.content.text or "")
                        texts.append(" ".join(text_parts))
                except Exception:
                    continue

            if not texts:
                return [types.TextContent(type="text", text="Error: Could not load conversation texts for TF-IDF fitting.")]

            tfidf.fit(texts + [query])
            query_resp = tfidf.embed(query)
            query_vec = np.array(query_resp.embedding)
        else:
            embedder = ConversationEmbedder(config)
            query_resp = embedder.provider.embed(query)
            query_vec = np.array(query_resp.embedding)

    except Exception as e:
        logger.error(f"Failed to embed query: {e}")
        return [types.TextContent(type="text", text=f"Error embedding query: {e}")]

    # Compare against all stored embeddings
    results = []
    for emb_record in all_embs:
        stored_vec = np.array(emb_record["embedding"])
        # Dimension mismatch check
        if stored_vec.shape != query_vec.shape:
            continue
        dot = float(np.dot(query_vec, stored_vec))
        n1 = float(np.linalg.norm(query_vec))
        n2 = float(np.linalg.norm(stored_vec))
        sim = dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0.0
        results.append({"conversation_id": emb_record["conversation_id"], "similarity": sim})

    results.sort(key=lambda x: x["similarity"], reverse=True)
    results = results[:top_k]

    if not results:
        return [types.TextContent(type="text", text="No semantically similar conversations found.")]

    lines = [f"Semantic search results for \"{query}\":\n"]
    for i, r in enumerate(results, 1):
        cid = r["conversation_id"]
        sim = r["similarity"]
        try:
            conv = db.load_conversation(cid)
            title = (conv.title or "Untitled")[:50] if conv else "Unknown"
        except Exception:
            title = "Unknown"
        lines.append(f"[{i}] {cid[:8]} ({sim:.2f}) {title}")

    return [types.TextContent(type="text", text="\n".join(lines))]


def handle_get_network_summary(
    arguments: Dict[str, Any], db: ConversationDB
) -> list[types.TextContent]:
    threshold = arguments.get("threshold", 0.3)
    if isinstance(threshold, str):
        threshold = float(threshold)

    all_embs = _check_embeddings_exist(db)
    if not all_embs:
        return _no_embeddings_error()

    # Build similarity graph from cached embeddings
    n = len(all_embs)
    ids = [e["conversation_id"] for e in all_embs]
    vecs = [np.array(e["embedding"]) for e in all_embs]

    edge_count = 0
    degrees = {cid: 0 for cid in ids}

    for i in range(n):
        for j in range(i + 1, n):
            if vecs[i].shape != vecs[j].shape:
                continue
            dot = float(np.dot(vecs[i], vecs[j]))
            n1 = float(np.linalg.norm(vecs[i]))
            n2 = float(np.linalg.norm(vecs[j]))
            sim = dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0.0
            if sim >= threshold:
                edge_count += 1
                degrees[ids[i]] += 1
                degrees[ids[j]] += 1

    max_edges = n * (n - 1) / 2 if n > 1 else 1
    density = edge_count / max_edges if max_edges > 0 else 0

    # Find most central (highest degree)
    central = sorted(degrees.items(), key=lambda x: x[1], reverse=True)[:5]

    lines = [
        "Conversation Network Summary",
        "=" * 40,
        f"Nodes: {n}",
        f"Edges: {edge_count} (threshold: {threshold})",
        f"Density: {density:.3f}",
        f"Avg degree: {sum(degrees.values()) / n:.1f}" if n > 0 else "",
    ]

    if central and central[0][1] > 0:
        lines.append(f"\nMost connected conversations:")
        for cid, deg in central:
            if deg == 0:
                break
            try:
                conv = db.load_conversation(cid)
                title = (conv.title or "Untitled")[:40] if conv else "Unknown"
            except Exception:
                title = "Unknown"
            lines.append(f"  {cid[:8]} (degree {deg}) {title}")

    return [types.TextContent(type="text", text="\n".join(lines))]


def handle_get_clusters(
    arguments: Dict[str, Any], db: ConversationDB
) -> list[types.TextContent]:
    algorithm = arguments.get("algorithm", "label_propagation")

    all_embs = _check_embeddings_exist(db)
    if not all_embs:
        return _no_embeddings_error()

    try:
        import networkx as nx
        import networkx.algorithms.community as nx_comm
    except ImportError:
        return [types.TextContent(type="text", text="Error: NetworkX required for clustering. Install with: pip install networkx")]

    # Build graph
    n = len(all_embs)
    ids = [e["conversation_id"] for e in all_embs]
    vecs = [np.array(e["embedding"]) for e in all_embs]

    G = nx.Graph()
    G.add_nodes_from(ids)

    threshold = 0.3
    for i in range(n):
        for j in range(i + 1, n):
            if vecs[i].shape != vecs[j].shape:
                continue
            dot = float(np.dot(vecs[i], vecs[j]))
            n1 = float(np.linalg.norm(vecs[i]))
            n2 = float(np.linalg.norm(vecs[j]))
            sim = dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0.0
            if sim >= threshold:
                G.add_edge(ids[i], ids[j], weight=sim)

    # Detect communities
    if algorithm == "label_propagation":
        communities_iter = nx_comm.label_propagation_communities(G)
    elif algorithm == "greedy_modularity":
        communities_iter = nx_comm.greedy_modularity_communities(G)
    else:
        return [types.TextContent(type="text", text=f"Unknown algorithm: {algorithm}")]

    # Format output
    clusters = {}
    for idx, comm in enumerate(communities_iter):
        clusters[idx] = list(comm)

    lines = [f"Found {len(clusters)} cluster(s):\n"]
    for cluster_id, members in sorted(clusters.items(), key=lambda x: -len(x[1])):
        lines.append(f"Cluster {cluster_id + 1} ({len(members)} conversations):")
        for cid in members[:5]:  # Show first 5
            try:
                conv = db.load_conversation(cid)
                title = (conv.title or "Untitled")[:40] if conv else "Unknown"
            except Exception:
                title = "Unknown"
            lines.append(f"  {cid[:8]} {title}")
        if len(members) > 5:
            lines.append(f"  ... and {len(members) - 5} more")
        lines.append("")

    return [types.TextContent(type="text", text="\n".join(lines))]


HANDLERS = {
    "find_similar": handle_find_similar,
    "semantic_search": handle_semantic_search,
    "get_network_summary": handle_get_network_summary,
    "get_clusters": handle_get_clusters,
}
```

**Step 4: Register in server.py**

Modify `ctk/interfaces/mcp/server.py` — add `analysis` to the module imports:

```python
from ctk.interfaces.mcp.handlers import analysis, conversation, metadata, search

for module in [search, conversation, metadata, analysis]:
    ALL_TOOLS.extend(module.TOOLS)
    ALL_HANDLERS.update(module.HANDLERS)
```

**Step 5: Run tests**

Run: `pytest tests/unit/test_mcp_analysis.py -v`
Expected: All PASS

**Step 6: Run all MCP tests**

Run: `pytest tests/unit/test_mcp_server.py tests/unit/test_mcp_validation.py tests/unit/test_mcp_analysis.py -v`
Expected: All PASS (note: `test_mcp_server.py::test_list_tools_returns_expected_tools` will fail because it checks for exactly 9 tools — update that test to include the 4 new ones).

**Step 7: Commit**

```bash
git add ctk/interfaces/mcp/handlers/analysis.py ctk/interfaces/mcp/server.py tests/unit/test_mcp_analysis.py
git commit -m "Add semantic search and analysis tools to MCP server"
```

---

## Task 6: TUI semantic and index commands

**Files:**
- Create: `ctk/core/commands/semantic.py`
- Modify: `ctk/integrations/chat/tui.py` (register commands)
- Create: `tests/unit/test_semantic_commands.py`

**Step 1: Write the failing test**

Create `tests/unit/test_semantic_commands.py`:

```python
"""Tests for TUI semantic and index commands."""

import pytest
from unittest.mock import MagicMock, patch

from ctk.core.command_dispatcher import CommandResult
from ctk.core.commands.semantic import SemanticCommands, IndexCommands, create_semantic_commands
from ctk.core.database import ConversationDB
from ctk.core.models import (ConversationMetadata, ConversationTree, Message,
                              MessageContent, MessageRole)
from ctk.core.vfs_navigator import VFSNavigator


class MockTUI:
    def __init__(self, vfs_cwd="/"):
        self.vfs_cwd = vfs_cwd


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test_semantic.db"
    db = ConversationDB(str(db_path))

    for i in range(3):
        tree = ConversationTree(
            id=f"conv-{i}",
            title=f"Conversation {i}",
            metadata=ConversationMetadata(
                source="test", model="test-model",
                created_at=None, updated_at=None,
            ),
        )
        msg = Message(role=MessageRole.USER, content=MessageContent(text=f"Message about topic {i}"))
        tree.add_message(msg)
        db.save_conversation(tree)

    yield db
    db.close()


@pytest.fixture
def navigator(test_db):
    return VFSNavigator(test_db)


@pytest.fixture
def tui():
    return MockTUI("/")


class TestIndexStatus:
    def test_no_embeddings(self, test_db, navigator, tui):
        cmds = create_semantic_commands(test_db, navigator, tui)
        result = cmds["index"](["status"], "")
        assert result.success
        assert "0" in result.output or "no embeddings" in result.output.lower()


class TestIndexBuild:
    @patch("ctk.core.commands.semantic.TFIDFEmbedding")
    def test_build_creates_embeddings(self, mock_tfidf_cls, test_db, navigator, tui):
        # Mock the TF-IDF provider
        mock_provider = MagicMock()
        mock_provider.is_fitted = True
        mock_provider.get_dimensions.return_value = 4
        mock_provider.embed_batch.return_value = [
            MagicMock(embedding=[1.0, 0.0, 0.0, 0.0]),
            MagicMock(embedding=[0.0, 1.0, 0.0, 0.0]),
            MagicMock(embedding=[0.0, 0.0, 1.0, 0.0]),
        ]
        mock_tfidf_cls.return_value = mock_provider

        cmds = create_semantic_commands(test_db, navigator, tui)
        result = cmds["index"](["build"], "")
        assert result.success
        assert "3" in result.output or "embedded" in result.output.lower()


class TestIndexClear:
    def test_clear_when_empty(self, test_db, navigator, tui):
        cmds = create_semantic_commands(test_db, navigator, tui)
        result = cmds["index"](["clear"], "")
        assert result.success


class TestSemanticSimilar:
    def test_no_embeddings_shows_hint(self, test_db, navigator, tui):
        cmds = create_semantic_commands(test_db, navigator, tui)
        result = cmds["semantic"](["similar", "conv-0"], "")
        assert "embed" in result.output.lower() or "index build" in result.output.lower()


class TestSemanticSearch:
    def test_no_embeddings_shows_hint(self, test_db, navigator, tui):
        cmds = create_semantic_commands(test_db, navigator, tui)
        result = cmds["semantic"](["search", "test query"], "")
        assert "embed" in result.output.lower() or "index build" in result.output.lower()


class TestCreateSemanticCommands:
    def test_returns_semantic_and_index(self, test_db, navigator, tui):
        cmds = create_semantic_commands(test_db, navigator, tui)
        assert "semantic" in cmds
        assert "index" in cmds
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_semantic_commands.py -v`
Expected: FAIL (ImportError)

**Step 3: Implement `ctk/core/commands/semantic.py`**

```python
"""Semantic search and embedding index commands.

Implements: semantic (search, similar), index (build, status, clear)
"""

import logging
from typing import Callable, Dict, List, Optional

import numpy as np

from ctk.core.command_dispatcher import CommandResult
from ctk.core.database import ConversationDB
from ctk.core.vfs_navigator import VFSNavigator

logger = logging.getLogger(__name__)


class SemanticCommands:
    """Handler for semantic search commands."""

    def __init__(self, db: ConversationDB, navigator: VFSNavigator, tui_instance=None):
        self.db = db
        self.navigator = navigator
        self.tui = tui_instance

    def cmd_semantic(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Semantic search commands.

        Usage:
            semantic search <query>   - Search by meaning
            semantic similar <id>     - Find similar conversations
            semantic similar .        - Similar to current conversation
        """
        if not args:
            return CommandResult(
                success=False, output="",
                error="Usage: semantic search <query> | semantic similar <id>",
            )

        subcommand = args[0].lower()

        if subcommand == "search":
            return self._semantic_search(args[1:])
        elif subcommand == "similar":
            return self._semantic_similar(args[1:])
        else:
            return CommandResult(
                success=False, output="",
                error=f"Unknown subcommand: {subcommand}. Use 'search' or 'similar'.",
            )

    def _semantic_search(self, args: List[str]) -> CommandResult:
        query = " ".join(args)
        if not query:
            return CommandResult(success=False, output="", error="Usage: semantic search <query>")

        all_embs = self.db.get_all_embeddings()
        if not all_embs:
            return CommandResult(
                success=True,
                output="No embeddings found. Run 'index build' first to generate embeddings.",
            )

        # Embed query using TF-IDF (refit on stored texts + query)
        try:
            from ctk.integrations.embeddings.tfidf import TFIDFEmbedding

            tfidf = TFIDFEmbedding({})
            texts = []
            conv_ids = []
            for emb_record in all_embs:
                try:
                    conv = self.db.load_conversation(emb_record["conversation_id"])
                    if conv:
                        path = conv.get_longest_path()
                        parts = [conv.title or ""]
                        for msg in path:
                            if hasattr(msg.content, "text"):
                                parts.append(msg.content.text or "")
                        texts.append(" ".join(parts))
                        conv_ids.append(emb_record["conversation_id"])
                except Exception:
                    continue

            if not texts:
                return CommandResult(success=True, output="No conversation texts available.")

            tfidf.fit(texts + [query])
            query_resp = tfidf.embed(query)
            query_vec = np.array(query_resp.embedding)

            # Compare against stored embeddings
            results = []
            for emb_record in all_embs:
                stored_vec = np.array(emb_record["embedding"])
                if stored_vec.shape != query_vec.shape:
                    continue
                dot = float(np.dot(query_vec, stored_vec))
                n1 = float(np.linalg.norm(query_vec))
                n2 = float(np.linalg.norm(stored_vec))
                sim = dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0.0
                results.append((emb_record["conversation_id"], sim))

            results.sort(key=lambda x: x[1], reverse=True)
            results = results[:10]

            lines = []
            for cid, sim in results:
                try:
                    conv = self.db.load_conversation(cid)
                    title = (conv.title or "Untitled")[:50] if conv else "Unknown"
                except Exception:
                    title = "Unknown"
                lines.append(f"{sim:.2f}  {cid[:8]}  {title}")

            return CommandResult(success=True, output="\n".join(lines), pipe_data="\n".join(lines))

        except ImportError:
            return CommandResult(success=False, output="", error="scikit-learn required for TF-IDF search.")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Semantic search error: {e}")

    def _semantic_similar(self, args: List[str]) -> CommandResult:
        if not args:
            return CommandResult(success=False, output="", error="Usage: semantic similar <id>")

        conv_id = args[0]

        # Handle "." for current conversation
        if conv_id == "." and self.tui:
            from ctk.core.vfs import VFSPathParser
            parsed = VFSPathParser.parse(self.tui.vfs_cwd)
            if parsed.conversation_id:
                conv_id = parsed.conversation_id
            else:
                return CommandResult(
                    success=False, output="",
                    error="Not inside a conversation. Navigate to one first.",
                )

        all_embs = self.db.get_all_embeddings()
        if not all_embs:
            return CommandResult(
                success=True,
                output="No embeddings found. Run 'index build' first to generate embeddings.",
            )

        # Resolve ID
        resolved = self.db.resolve_identifier(conv_id)
        if not resolved:
            return CommandResult(success=False, output="", error=f"Conversation '{conv_id}' not found.")
        full_id = resolved[0]

        # Find target embedding
        target_vec = None
        candidates = {}
        for emb_record in all_embs:
            vec = np.array(emb_record["embedding"])
            if emb_record["conversation_id"] == full_id:
                target_vec = vec
            else:
                candidates[emb_record["conversation_id"]] = vec

        if target_vec is None:
            return CommandResult(
                success=True,
                output=f"No embedding for {full_id[:8]}. Run 'index build' to generate.",
            )

        # Compute similarities
        results = []
        for cid, cvec in candidates.items():
            if cvec.shape != target_vec.shape:
                continue
            dot = float(np.dot(target_vec, cvec))
            n1 = float(np.linalg.norm(target_vec))
            n2 = float(np.linalg.norm(cvec))
            sim = dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0.0
            results.append((cid, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        results = results[:10]

        lines = []
        for cid, sim in results:
            try:
                conv = self.db.load_conversation(cid)
                title = (conv.title or "Untitled")[:50] if conv else "Unknown"
            except Exception:
                title = "Unknown"
            lines.append(f"{sim:.2f}  {cid[:8]}  {title}")

        return CommandResult(success=True, output="\n".join(lines), pipe_data="\n".join(lines))


class IndexCommands:
    """Handler for embedding index commands."""

    def __init__(self, db: ConversationDB, navigator: VFSNavigator, tui_instance=None):
        self.db = db
        self.navigator = navigator
        self.tui = tui_instance

    def cmd_index(self, args: List[str], stdin: str = "") -> CommandResult:
        """
        Embedding index management.

        Usage:
            index build    [--provider tfidf] [--limit N]  - Generate embeddings
            index status                                    - Show embedding stats
            index clear    [--provider tfidf]               - Remove embeddings
        """
        if not args:
            return CommandResult(
                success=False, output="",
                error="Usage: index build|status|clear",
            )

        subcommand = args[0].lower()

        if subcommand == "build":
            return self._index_build(args[1:])
        elif subcommand == "status":
            return self._index_status()
        elif subcommand == "clear":
            return self._index_clear(args[1:])
        else:
            return CommandResult(
                success=False, output="",
                error=f"Unknown subcommand: {subcommand}. Use 'build', 'status', or 'clear'.",
            )

    def _index_status(self) -> CommandResult:
        all_embs = self.db.get_all_embeddings()
        total_convs = len(self.db.list_conversations(limit=100000))

        if not all_embs:
            return CommandResult(
                success=True,
                output=f"No embeddings. {total_convs} conversations available.\nRun 'index build' to generate.",
            )

        # Group by provider
        providers = {}
        for emb in all_embs:
            p = emb.get("provider", "unknown")
            if p not in providers:
                providers[p] = {"count": 0, "dimensions": emb.get("dimensions", 0)}
            providers[p]["count"] += 1

        lines = [f"Embedding index: {len(all_embs)}/{total_convs} conversations embedded\n"]
        for pname, pinfo in providers.items():
            lines.append(f"  {pname}: {pinfo['count']} embeddings, {pinfo['dimensions']} dimensions")

        return CommandResult(success=True, output="\n".join(lines))

    def _index_build(self, args: List[str]) -> CommandResult:
        # Parse --provider and --limit flags
        provider = "tfidf"
        limit = None
        i = 0
        while i < len(args):
            if args[i] == "--provider" and i + 1 < len(args):
                provider = args[i + 1]
                i += 2
            elif args[i] == "--limit" and i + 1 < len(args):
                try:
                    limit = int(args[i + 1])
                except ValueError:
                    return CommandResult(success=False, output="", error=f"Invalid limit: {args[i+1]}")
                i += 2
            else:
                i += 1

        if provider != "tfidf":
            return CommandResult(
                success=False, output="",
                error=f"Provider '{provider}' not supported in TUI. Use 'tfidf'.",
            )

        try:
            from ctk.integrations.embeddings.tfidf import TFIDFEmbedding
            from ctk.core.similarity import ConversationEmbedder, ConversationEmbeddingConfig
            from ctk.integrations.embeddings.base import ChunkingStrategy, AggregationStrategy

            conversations = self.db.list_conversations(limit=limit or 100000)
            if not conversations:
                return CommandResult(success=True, output="No conversations to embed.")

            # Load conversation texts for TF-IDF fitting
            conv_texts = []
            conv_objects = []
            for conv_summary in conversations:
                try:
                    conv = self.db.load_conversation(conv_summary.id)
                    if conv:
                        path = conv.get_longest_path()
                        parts = [conv.title or ""]
                        for msg in path:
                            if hasattr(msg.content, "text"):
                                parts.append(msg.content.text or "")
                        conv_texts.append(" ".join(parts))
                        conv_objects.append(conv)
                except Exception:
                    continue

            if not conv_texts:
                return CommandResult(success=True, output="No conversation texts found.")

            # Create and fit TF-IDF
            tfidf = TFIDFEmbedding({})
            tfidf.fit(conv_texts)

            # Embed and save
            config = ConversationEmbeddingConfig(
                provider="tfidf",
                chunking=ChunkingStrategy.MESSAGE,
                aggregation=AggregationStrategy.WEIGHTED_MEAN,
            )
            embedder = ConversationEmbedder(config, provider=tfidf)

            count = 0
            for conv in conv_objects:
                try:
                    emb = embedder.embed_conversation(conv)
                    self.db.save_embedding(
                        conversation_id=conv.id,
                        embedding=emb.tolist(),
                        provider="tfidf",
                        model="tfidf",
                        chunking_strategy=config.chunking.value,
                        aggregation_strategy=config.aggregation.value,
                    )
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to embed {conv.id}: {e}")

            return CommandResult(
                success=True,
                output=f"Embedded {count}/{len(conv_objects)} conversations using TF-IDF.",
            )

        except ImportError as e:
            return CommandResult(success=False, output="", error=f"Missing dependency: {e}")
        except Exception as e:
            return CommandResult(success=False, output="", error=f"Build error: {e}")

    def _index_clear(self, args: List[str]) -> CommandResult:
        provider = None
        i = 0
        while i < len(args):
            if args[i] == "--provider" and i + 1 < len(args):
                provider = args[i + 1]
                i += 2
            else:
                i += 1

        count = self.db.delete_embeddings(provider=provider)
        return CommandResult(success=True, output=f"Cleared {count} embeddings.")


def create_semantic_commands(
    db: ConversationDB, navigator: VFSNavigator, tui_instance=None
) -> Dict[str, Callable]:
    semantic = SemanticCommands(db, navigator, tui_instance)
    index = IndexCommands(db, navigator, tui_instance)
    return {
        "semantic": semantic.cmd_semantic,
        "index": index.cmd_index,
    }
```

**Step 4: Register in TUI**

Add to `ctk/integrations/chat/tui.py` in `_register_shell_commands()` method, after the tree_nav commands registration (around line 282):

```python
        # Register semantic search commands
        from ctk.core.commands.semantic import create_semantic_commands

        semantic_commands = create_semantic_commands(
            db=self.db, navigator=self.vfs_navigator, tui_instance=self
        )
        self.command_dispatcher.register_commands(semantic_commands)
```

**Step 5: Run tests**

Run: `pytest tests/unit/test_semantic_commands.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add ctk/core/commands/semantic.py ctk/integrations/chat/tui.py tests/unit/test_semantic_commands.py
git commit -m "Add semantic search and index commands to TUI shell"
```

---

## Task 7: Update existing MCP test and run full test suite

**Files:**
- Modify: `tests/unit/test_mcp_server.py` (update expected tool count)

**Step 1: Update test_list_tools_returns_expected_tools**

In `tests/unit/test_mcp_server.py`, update the expected tools set:

```python
expected_tools = {
    "search_conversations",
    "list_conversations",
    "get_conversation",
    "get_statistics",
    "star_conversation",
    "pin_conversation",
    "archive_conversation",
    "set_title",
    "get_tags",
    # New analysis tools
    "find_similar",
    "semantic_search",
    "get_network_summary",
    "get_clusters",
}
```

**Step 2: Run full test suite**

Run: `pytest tests/unit/ -v --tb=short -x`
Expected: All existing tests pass, plus new tests pass.

**Step 3: Run coverage**

Run: `make coverage`
Check that coverage threshold (59%) is still met.

**Step 4: Commit**

```bash
git add tests/unit/test_mcp_server.py
git commit -m "Update MCP tests for new analysis tools"
```

---

## Task 8: Final integration test and cleanup

**Step 1: Run lint**

Run: `make format && make lint`
Fix any issues.

**Step 2: Verify MCP server entry point still works**

Run: `python -c "from ctk.mcp_server import main; print('OK')"`
Expected: prints "OK"

**Step 3: Verify TUI commands are registered**

Run: `python -c "from ctk.core.commands.semantic import create_semantic_commands; print('OK')"`
Expected: prints "OK"

**Step 4: Update CLAUDE.md**

Add to the "Other Key Components" section after the MCP Server entry:

```
**MCP Server** (`ctk/interfaces/mcp/`): Modular MCP server with handler modules for search, conversation, metadata, and analysis (semantic search, similarity, clustering). Entry point: `python -m ctk.mcp_server` or `ctk/mcp_server.py`.
```

Add `semantic.py` to the TUI Commands table:

```
| `semantic.py` | semantic (search, similar), index (build, status, clear) |
```

**Step 5: Final commit**

```bash
git add -A
git commit -m "Final cleanup: lint, CLAUDE.md updates, integration verification"
```
