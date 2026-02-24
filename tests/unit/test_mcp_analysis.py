"""
Tests for the MCP analysis handler module.

Tests the tool definitions, handler dispatch, and handler behavior for
semantic search and network analysis operations.
"""

import asyncio
from unittest.mock import MagicMock

import pytest


class TestAnalysisToolDefinitions:
    """Test that analysis tools are properly defined."""

    def test_tools_list_is_not_empty(self):
        """Verify TOOLS list has entries."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        assert len(TOOLS) == 4

    def test_find_similar_tool_exists(self):
        """Verify find_similar tool is defined."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        names = {t.name for t in TOOLS}
        assert "find_similar" in names

    def test_semantic_search_tool_exists(self):
        """Verify semantic_search tool is defined."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        names = {t.name for t in TOOLS}
        assert "semantic_search" in names

    def test_get_network_summary_tool_exists(self):
        """Verify get_network_summary tool is defined."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        names = {t.name for t in TOOLS}
        assert "get_network_summary" in names

    def test_get_clusters_tool_exists(self):
        """Verify get_clusters tool is defined."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        names = {t.name for t in TOOLS}
        assert "get_clusters" in names

    def test_find_similar_schema_requires_id(self):
        """Verify find_similar requires 'id' parameter."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        tool = next(t for t in TOOLS if t.name == "find_similar")
        assert "id" in tool.inputSchema["required"]
        assert "id" in tool.inputSchema["properties"]

    def test_find_similar_schema_has_optional_params(self):
        """Verify find_similar has top_k and threshold optional params."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        tool = next(t for t in TOOLS if t.name == "find_similar")
        props = tool.inputSchema["properties"]
        assert "top_k" in props
        assert "threshold" in props
        assert props["top_k"]["type"] == "integer"
        assert props["threshold"]["type"] == "number"

    def test_semantic_search_schema_requires_query(self):
        """Verify semantic_search requires 'query' parameter."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        tool = next(t for t in TOOLS if t.name == "semantic_search")
        assert "query" in tool.inputSchema["required"]
        assert "query" in tool.inputSchema["properties"]

    def test_semantic_search_schema_has_top_k(self):
        """Verify semantic_search has top_k optional param."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        tool = next(t for t in TOOLS if t.name == "semantic_search")
        assert "top_k" in tool.inputSchema["properties"]

    def test_get_network_summary_schema_has_threshold(self):
        """Verify get_network_summary has threshold optional param."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        tool = next(t for t in TOOLS if t.name == "get_network_summary")
        assert "threshold" in tool.inputSchema["properties"]
        assert tool.inputSchema["required"] == []

    def test_get_clusters_schema_has_algorithm_enum(self):
        """Verify get_clusters has algorithm enum with correct values."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        tool = next(t for t in TOOLS if t.name == "get_clusters")
        algo_prop = tool.inputSchema["properties"]["algorithm"]
        assert algo_prop["type"] == "string"
        assert "enum" in algo_prop
        assert "label_propagation" in algo_prop["enum"]
        assert "greedy_modularity" in algo_prop["enum"]
        assert tool.inputSchema["required"] == []

    def test_get_clusters_schema_has_threshold(self):
        """Verify get_clusters now has threshold parameter."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        tool = next(t for t in TOOLS if t.name == "get_clusters")
        assert "threshold" in tool.inputSchema["properties"]
        assert tool.inputSchema["properties"]["threshold"]["type"] == "number"

    def test_network_summary_schema_has_max_conversations(self):
        """Verify get_network_summary has max_conversations parameter."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        tool = next(t for t in TOOLS if t.name == "get_network_summary")
        assert "max_conversations" in tool.inputSchema["properties"]

    def test_get_clusters_schema_has_max_conversations(self):
        """Verify get_clusters has max_conversations parameter."""
        from ctk.interfaces.mcp.handlers.analysis import TOOLS

        tool = next(t for t in TOOLS if t.name == "get_clusters")
        assert "max_conversations" in tool.inputSchema["properties"]


class TestAnalysisHandlerDispatch:
    """Test that handlers are properly registered."""

    def test_handlers_dict_has_all_tools(self):
        """Verify HANDLERS dict has entries for all 4 tools."""
        from ctk.interfaces.mcp.handlers.analysis import HANDLERS

        assert "find_similar" in HANDLERS
        assert "semantic_search" in HANDLERS
        assert "get_network_summary" in HANDLERS
        assert "get_clusters" in HANDLERS

    def test_handlers_are_callable(self):
        """Verify all handlers are callable."""
        from ctk.interfaces.mcp.handlers.analysis import HANDLERS

        for name, handler in HANDLERS.items():
            assert callable(handler), f"Handler '{name}' is not callable"

    def test_handlers_are_async(self):
        """Verify all handlers are async functions."""
        import asyncio

        from ctk.interfaces.mcp.handlers.analysis import HANDLERS

        for name, handler in HANDLERS.items():
            assert asyncio.iscoroutinefunction(
                handler
            ), f"Handler '{name}' is not async"


class TestAnalysisRegistration:
    """Test that analysis module is registered in __init__.py."""

    def test_analysis_tools_in_all_tools(self):
        """Verify analysis tools appear in ALL_TOOLS."""
        from ctk.interfaces.mcp.handlers import ALL_TOOLS

        tool_names = {t.name for t in ALL_TOOLS}
        assert "find_similar" in tool_names
        assert "semantic_search" in tool_names
        assert "get_network_summary" in tool_names
        assert "get_clusters" in tool_names

    def test_analysis_handlers_in_all_handlers(self):
        """Verify analysis handlers appear in ALL_HANDLERS."""
        from ctk.interfaces.mcp.handlers import ALL_HANDLERS

        assert "find_similar" in ALL_HANDLERS
        assert "semantic_search" in ALL_HANDLERS
        assert "get_network_summary" in ALL_HANDLERS
        assert "get_clusters" in ALL_HANDLERS

    def test_total_tool_count(self):
        """Verify total tool count includes analysis tools."""
        from ctk.interfaces.mcp.handlers import ALL_TOOLS

        # search (2) + conversation (5) + metadata (2) + analysis (4) = 13
        assert len(ALL_TOOLS) == 13

    def test_total_handler_count(self):
        """Verify total handler count includes analysis handlers."""
        from ctk.interfaces.mcp.handlers import ALL_HANDLERS

        assert len(ALL_HANDLERS) == 13


class TestHandleFindSimilar:
    """Test handle_find_similar handler."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.get_all_embeddings.return_value = []
        db.resolve_identifier.return_value = None
        db.get_similar_conversations.return_value = []
        db.load_conversation.return_value = None
        return db

    def test_no_embeddings_returns_error(self, event_loop, mock_db):
        """Test find_similar returns error when no embeddings exist."""
        from ctk.interfaces.mcp.handlers.analysis import handle_find_similar

        mock_db.resolve_identifier.return_value = ("full-id-123", "slug")
        mock_db.get_all_embeddings.return_value = []

        result = event_loop.run_until_complete(
            handle_find_similar({"id": "abc123"}, mock_db)
        )

        assert len(result) == 1
        assert "No embeddings found" in result[0].text

    def test_invalid_id_returns_error(self, event_loop, mock_db):
        """Test find_similar returns error for unresolvable ID."""
        from ctk.interfaces.mcp.handlers.analysis import handle_find_similar

        mock_db.resolve_identifier.return_value = None

        result = event_loop.run_until_complete(
            handle_find_similar({"id": "nonexistent"}, mock_db)
        )

        assert len(result) == 1
        assert "Could not find conversation" in result[0].text

    def test_no_similar_found(self, event_loop, mock_db):
        """Test find_similar when no similar conversations found."""
        from ctk.interfaces.mcp.handlers.analysis import handle_find_similar

        mock_db.resolve_identifier.return_value = ("full-id-123", "slug")
        mock_db.get_all_embeddings.return_value = [
            {
                "conversation_id": "full-id-123",
                "embedding": [1.0, 0.0, 0.0],
                "provider": "tfidf",
            },
        ]
        mock_db.get_similar_conversations.return_value = []

        result = event_loop.run_until_complete(
            handle_find_similar({"id": "full-id"}, mock_db)
        )

        assert len(result) == 1
        assert "No similar conversations found" in result[0].text

    def test_finds_similar_from_cached(self, event_loop, mock_db):
        """Test find_similar returns results from cached similarities."""
        from ctk.interfaces.mcp.handlers.analysis import handle_find_similar

        mock_db.resolve_identifier.return_value = ("full-id-123", "slug")
        mock_db.get_all_embeddings.return_value = [
            {
                "conversation_id": "full-id-123",
                "embedding": [1.0, 0.0],
                "provider": "tfidf",
            },
        ]
        mock_db.get_similar_conversations.return_value = [
            {"conversation_id": "other-id-456", "similarity": 0.95},
        ]

        # Title cache uses list_conversations
        mock_summary = MagicMock()
        mock_summary.id = "other-id-456"
        mock_summary.title = "Test Conversation"
        mock_db.list_conversations.return_value = [mock_summary]

        result = event_loop.run_until_complete(
            handle_find_similar({"id": "full-id"}, mock_db)
        )

        assert len(result) == 1
        assert "similar to" in result[0].text
        assert "other-id" in result[0].text
        assert "0.95" in result[0].text

    def test_computes_similarity_on_the_fly(self, event_loop, mock_db):
        """Test find_similar computes cosine similarity when no cached results."""
        from ctk.interfaces.mcp.handlers.analysis import handle_find_similar

        mock_db.resolve_identifier.return_value = ("full-id-123", "slug")
        mock_db.get_all_embeddings.return_value = [
            {
                "conversation_id": "full-id-123",
                "embedding": [1.0, 0.0, 0.0],
                "provider": "tfidf",
            },
            {
                "conversation_id": "similar-id",
                "embedding": [0.9, 0.1, 0.0],
                "provider": "tfidf",
            },
            {
                "conversation_id": "different-id",
                "embedding": [0.0, 0.0, 1.0],
                "provider": "tfidf",
            },
        ]
        mock_db.get_similar_conversations.return_value = []

        # Title cache
        summaries = []
        for sid in ["full-id-123", "similar-id", "different-id"]:
            s = MagicMock()
            s.id = sid
            s.title = "Some Title"
            summaries.append(s)
        mock_db.list_conversations.return_value = summaries

        result = event_loop.run_until_complete(
            handle_find_similar({"id": "full-id", "threshold": 0.5}, mock_db)
        )

        assert len(result) == 1
        text = result[0].text
        # similar-id should appear (high similarity) — IDs are truncated to 8 chars
        assert "similar-" in text

    def test_missing_id_raises_validation_error(self, event_loop, mock_db):
        """Test find_similar raises ValidationError when id is missing."""
        from ctk.interfaces.mcp.handlers.analysis import handle_find_similar
        from ctk.interfaces.mcp.validation import ValidationError

        with pytest.raises(ValidationError, match="'id' is required"):
            event_loop.run_until_complete(handle_find_similar({}, mock_db))

    def test_no_embedding_for_target(self, event_loop, mock_db):
        """Test find_similar when target conversation has no embedding."""
        from ctk.interfaces.mcp.handlers.analysis import handle_find_similar

        mock_db.resolve_identifier.return_value = ("full-id-123", "slug")
        mock_db.get_all_embeddings.return_value = [
            {
                "conversation_id": "other-id",
                "embedding": [1.0, 0.0],
                "provider": "tfidf",
            },
        ]
        mock_db.get_similar_conversations.return_value = []

        result = event_loop.run_until_complete(
            handle_find_similar({"id": "full-id"}, mock_db)
        )

        assert len(result) == 1
        assert "No embedding found" in result[0].text


class TestHandleSemanticSearch:
    """Test handle_semantic_search handler."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.get_all_embeddings.return_value = []
        db.load_conversation.return_value = None
        return db

    def test_no_embeddings_returns_error(self, event_loop, mock_db):
        """Test semantic_search returns error when no embeddings exist."""
        from ctk.interfaces.mcp.handlers.analysis import handle_semantic_search

        mock_db.get_all_embeddings.return_value = []

        result = event_loop.run_until_complete(
            handle_semantic_search({"query": "test query"}, mock_db)
        )

        assert len(result) == 1
        assert "No embeddings found" in result[0].text

    def test_missing_query_raises_validation_error(self, event_loop, mock_db):
        """Test semantic_search raises ValidationError when query is missing."""
        from ctk.interfaces.mcp.handlers.analysis import handle_semantic_search
        from ctk.interfaces.mcp.validation import ValidationError

        with pytest.raises(ValidationError, match="'query' is required"):
            event_loop.run_until_complete(handle_semantic_search({}, mock_db))


class TestHandleGetNetworkSummary:
    """Test handle_get_network_summary handler."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.get_all_embeddings.return_value = []
        db.load_conversation.return_value = None
        return db

    def test_no_embeddings_returns_error(self, event_loop, mock_db):
        """Test get_network_summary returns error when no embeddings exist."""
        from ctk.interfaces.mcp.handlers.analysis import \
            handle_get_network_summary

        result = event_loop.run_until_complete(handle_get_network_summary({}, mock_db))

        assert len(result) == 1
        assert "No embeddings found" in result[0].text

    def test_returns_summary_with_embeddings(self, event_loop, mock_db):
        """Test get_network_summary returns summary when embeddings exist."""
        from ctk.interfaces.mcp.handlers.analysis import \
            handle_get_network_summary

        mock_db.get_all_embeddings.return_value = [
            {
                "conversation_id": "id-1",
                "embedding": [1.0, 0.0, 0.0],
                "provider": "tfidf",
            },
            {
                "conversation_id": "id-2",
                "embedding": [0.9, 0.1, 0.0],
                "provider": "tfidf",
            },
            {
                "conversation_id": "id-3",
                "embedding": [0.0, 0.0, 1.0],
                "provider": "tfidf",
            },
        ]

        result = event_loop.run_until_complete(
            handle_get_network_summary({"threshold": 0.5}, mock_db)
        )

        assert len(result) == 1
        text = result[0].text
        assert "Conversation Network Summary" in text
        assert "Nodes: 3" in text
        assert "Density:" in text

    def test_threshold_string_conversion(self, event_loop, mock_db):
        """Test that string threshold is converted to float via validate_float."""
        from ctk.interfaces.mcp.handlers.analysis import \
            handle_get_network_summary

        mock_db.get_all_embeddings.return_value = [
            {"conversation_id": "id-1", "embedding": [1.0, 0.0], "provider": "tfidf"},
        ]

        result = event_loop.run_until_complete(
            handle_get_network_summary({"threshold": "0.5"}, mock_db)
        )

        assert len(result) == 1
        assert "Nodes: 1" in result[0].text

    def test_invalid_threshold_raises_validation_error(self, event_loop, mock_db):
        """Test that invalid threshold raises ValidationError."""
        from ctk.interfaces.mcp.handlers.analysis import \
            handle_get_network_summary
        from ctk.interfaces.mcp.validation import ValidationError

        with pytest.raises(ValidationError, match="must be a number"):
            event_loop.run_until_complete(
                handle_get_network_summary({"threshold": "abc"}, mock_db)
            )

    def test_threshold_out_of_range_raises_error(self, event_loop, mock_db):
        """Test that out-of-range threshold raises ValidationError."""
        from ctk.interfaces.mcp.handlers.analysis import \
            handle_get_network_summary
        from ctk.interfaces.mcp.validation import ValidationError

        with pytest.raises(ValidationError, match="between"):
            event_loop.run_until_complete(
                handle_get_network_summary({"threshold": 5.0}, mock_db)
            )

    def test_central_conversations_shown(self, event_loop, mock_db):
        """Test that most connected conversations are listed."""
        from ctk.interfaces.mcp.handlers.analysis import \
            handle_get_network_summary

        # Create embeddings where id-1 and id-2 are very similar
        mock_db.get_all_embeddings.return_value = [
            {
                "conversation_id": "id-1",
                "embedding": [1.0, 0.0, 0.0],
                "provider": "tfidf",
            },
            {
                "conversation_id": "id-2",
                "embedding": [0.99, 0.01, 0.0],
                "provider": "tfidf",
            },
        ]

        # Title cache uses list_conversations (not load_conversation)
        mock_summary = MagicMock()
        mock_summary.id = "id-1"
        mock_summary.title = "Central Conv"
        mock_summary2 = MagicMock()
        mock_summary2.id = "id-2"
        mock_summary2.title = "Other Conv"
        mock_db.list_conversations.return_value = [mock_summary, mock_summary2]

        result = event_loop.run_until_complete(
            handle_get_network_summary({"threshold": 0.5}, mock_db)
        )

        text = result[0].text
        assert "Most connected" in text


class TestHandleGetClusters:
    """Test handle_get_clusters handler."""

    @pytest.fixture
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.get_all_embeddings.return_value = []
        db.load_conversation.return_value = None
        return db

    def test_no_embeddings_returns_error(self, event_loop, mock_db):
        """Test get_clusters returns error when no embeddings exist."""
        from ctk.interfaces.mcp.handlers.analysis import handle_get_clusters

        result = event_loop.run_until_complete(handle_get_clusters({}, mock_db))

        assert len(result) == 1
        assert "No embeddings found" in result[0].text

    def test_clusters_with_embeddings(self, event_loop, mock_db):
        """Test get_clusters detects communities with embeddings."""
        from ctk.interfaces.mcp.handlers.analysis import handle_get_clusters

        mock_db.get_all_embeddings.return_value = [
            {
                "conversation_id": "id-1",
                "embedding": [1.0, 0.0, 0.0],
                "provider": "tfidf",
            },
            {
                "conversation_id": "id-2",
                "embedding": [0.95, 0.05, 0.0],
                "provider": "tfidf",
            },
            {
                "conversation_id": "id-3",
                "embedding": [0.0, 0.0, 1.0],
                "provider": "tfidf",
            },
            {
                "conversation_id": "id-4",
                "embedding": [0.0, 0.05, 0.95],
                "provider": "tfidf",
            },
        ]

        # Title cache uses list_conversations
        summaries = []
        for i in range(1, 5):
            s = MagicMock()
            s.id = f"id-{i}"
            s.title = "Test"
            summaries.append(s)
        mock_db.list_conversations.return_value = summaries

        result = event_loop.run_until_complete(handle_get_clusters({}, mock_db))

        assert len(result) == 1
        text = result[0].text
        assert "cluster" in text.lower()

    def test_greedy_modularity_algorithm(self, event_loop, mock_db):
        """Test get_clusters with greedy_modularity algorithm."""
        from ctk.interfaces.mcp.handlers.analysis import handle_get_clusters

        mock_db.get_all_embeddings.return_value = [
            {"conversation_id": "id-1", "embedding": [1.0, 0.0], "provider": "tfidf"},
            {"conversation_id": "id-2", "embedding": [0.9, 0.1], "provider": "tfidf"},
            {"conversation_id": "id-3", "embedding": [0.0, 1.0], "provider": "tfidf"},
        ]

        summaries = []
        for i in range(1, 4):
            s = MagicMock()
            s.id = f"id-{i}"
            s.title = "Test"
            summaries.append(s)
        mock_db.list_conversations.return_value = summaries

        result = event_loop.run_until_complete(
            handle_get_clusters({"algorithm": "greedy_modularity"}, mock_db)
        )

        assert len(result) == 1
        assert "cluster" in result[0].text.lower()

    def test_unknown_algorithm_returns_error(self, event_loop, mock_db):
        """Test get_clusters returns error for unknown algorithm."""
        from ctk.interfaces.mcp.handlers.analysis import handle_get_clusters

        mock_db.get_all_embeddings.return_value = [
            {"conversation_id": "id-1", "embedding": [1.0, 0.0], "provider": "tfidf"},
        ]

        result = event_loop.run_until_complete(
            handle_get_clusters({"algorithm": "nonexistent"}, mock_db)
        )

        assert len(result) == 1
        assert "Unknown algorithm" in result[0].text


class TestHelperFunctions:
    """Test helper/utility functions in the analysis module."""

    def test_cosine_similarity_identical_vectors(self):
        """Test shared cosine similarity of identical vectors is 1.0."""
        import numpy as np

        from ctk.core.similarity import cosine_similarity

        vec = np.array([1.0, 2.0, 3.0])
        assert abs(cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal_vectors(self):
        """Test shared cosine similarity of orthogonal vectors is 0.0."""
        import numpy as np

        from ctk.core.similarity import cosine_similarity

        vec_a = np.array([1.0, 0.0])
        vec_b = np.array([0.0, 1.0])
        assert abs(cosine_similarity(vec_a, vec_b)) < 1e-6

    def test_cosine_similarity_mismatched_shapes(self):
        """Test shared cosine similarity returns 0 for mismatched shapes."""
        import numpy as np

        from ctk.core.similarity import cosine_similarity

        vec_a = np.array([1.0, 0.0])
        vec_b = np.array([1.0, 0.0, 0.0])
        assert cosine_similarity(vec_a, vec_b) == 0.0

    def test_cosine_similarity_zero_vector(self):
        """Test shared cosine similarity with zero vector returns 0."""
        import numpy as np

        from ctk.core.similarity import cosine_similarity

        vec_a = np.array([0.0, 0.0])
        vec_b = np.array([1.0, 0.0])
        assert cosine_similarity(vec_a, vec_b) == 0.0

    def test_no_embeddings_error_message(self):
        """Test the standard no-embeddings error message."""
        from ctk.interfaces.mcp.handlers.analysis import _no_embeddings_error

        result = _no_embeddings_error()
        assert len(result) == 1
        assert "No embeddings found" in result[0].text
        assert "ctk net embeddings" in result[0].text

    def test_build_title_cache_returns_dict(self):
        """Test _build_title_cache returns title dict from summaries."""
        from ctk.interfaces.mcp.handlers.analysis import _build_title_cache

        mock_db = MagicMock()
        mock_summary = MagicMock()
        mock_summary.id = "test-id-123"
        mock_summary.title = "My Title"
        mock_db.list_conversations.return_value = [mock_summary]

        cache = _build_title_cache(mock_db, ["test-id-123"])
        assert cache["test-id-123"] == "My Title"

    def test_build_title_cache_untitled(self):
        """Test _build_title_cache handles None title."""
        from ctk.interfaces.mcp.handlers.analysis import _build_title_cache

        mock_db = MagicMock()
        mock_summary = MagicMock()
        mock_summary.id = "test-id-123"
        mock_summary.title = None
        mock_db.list_conversations.return_value = [mock_summary]

        cache = _build_title_cache(mock_db, ["test-id-123"])
        assert cache["test-id-123"] == "Untitled"

    def test_build_title_cache_truncates(self):
        """Test _build_title_cache truncates to max_len."""
        from ctk.interfaces.mcp.handlers.analysis import _build_title_cache

        mock_db = MagicMock()
        mock_summary = MagicMock()
        mock_summary.id = "test-id-123"
        mock_summary.title = "A" * 100
        mock_db.list_conversations.return_value = [mock_summary]

        cache = _build_title_cache(mock_db, ["test-id-123"], max_len=10)
        assert len(cache["test-id-123"]) == 10

    def test_build_title_cache_exception_returns_empty(self):
        """Test _build_title_cache returns empty dict on exception."""
        from ctk.interfaces.mcp.handlers.analysis import _build_title_cache

        mock_db = MagicMock()
        mock_db.list_conversations.side_effect = Exception("DB error")

        cache = _build_title_cache(mock_db, ["test-id"])
        assert cache == {}

    def test_get_title_from_cache(self):
        """Test _get_title returns title from cache."""
        from ctk.interfaces.mcp.handlers.analysis import _get_title

        cache = {"id-123": "Cached Title"}
        assert _get_title(cache, "id-123") == "Cached Title"

    def test_get_title_missing_returns_unknown(self):
        """Test _get_title returns 'Unknown' for missing ID."""
        from ctk.interfaces.mcp.handlers.analysis import _get_title

        assert _get_title({}, "missing-id") == "Unknown"

    def test_compute_pairwise_similarities_shape(self):
        """Test vectorized pairwise similarity returns correct shape."""
        import numpy as np

        from ctk.interfaces.mcp.handlers.analysis import (
            _compute_pairwise_similarities,
        )

        vecs = [np.array([1.0, 0.0]), np.array([0.0, 1.0]), np.array([1.0, 1.0])]
        result = _compute_pairwise_similarities(vecs)
        assert result.shape == (3, 3)
        # Diagonal should be 1.0 (self-similarity)
        for i in range(3):
            assert abs(result[i, i] - 1.0) < 1e-6

    def test_compute_pairwise_similarities_empty(self):
        """Test vectorized pairwise similarity with empty input."""
        from ctk.interfaces.mcp.handlers.analysis import (
            _compute_pairwise_similarities,
        )

        result = _compute_pairwise_similarities([])
        assert result.size == 0

    def test_validate_float_in_threshold(self):
        """Test that threshold validation works via validate_float."""
        from ctk.interfaces.mcp.validation import ValidationError, validate_float

        assert validate_float(0.5, "threshold") == 0.5
        assert validate_float("0.3", "threshold") == 0.3
        assert validate_float(None, "threshold") is None
        with pytest.raises(ValidationError, match="between"):
            validate_float(-0.1, "threshold")
        with pytest.raises(ValidationError, match="between"):
            validate_float(1.5, "threshold")
        with pytest.raises(ValidationError, match="must be a number"):
            validate_float("abc", "threshold")
