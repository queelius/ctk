"""
Tests for semantic search and network analysis via the folded registry.

The old hand-written handler module (handlers/analysis.py) was deleted in the
Task-7 refactor. These tests verify equivalent behavior through the production
paths: projection.project_tools(), projection.handle_tool(), and
execute_network_tool().
"""

import asyncio
from unittest.mock import MagicMock

import pytest


class TestAnalysisToolsViaProjection:
    """Verify analysis tools are exposed correctly through the projection."""

    def test_find_similar_conversations_in_projection(self):
        """find_similar_conversations is in the curated MCP tool list."""
        from ctk.interfaces.mcp.projection import project_tools

        names = {t.name for t in project_tools()}
        assert "find_similar_conversations" in names

    def test_legacy_find_similar_alias_in_projection(self):
        """Legacy 'find_similar' alias is still exposed for backward compat."""
        from ctk.interfaces.mcp.projection import project_tools

        names = {t.name for t in project_tools()}
        assert "find_similar" in names

    def test_semantic_search_in_projection(self):
        """semantic_search is in the curated MCP tool list."""
        from ctk.interfaces.mcp.projection import project_tools

        names = {t.name for t in project_tools()}
        assert "semantic_search" in names

    def test_find_similar_conversations_schema_requires_conversation_id(self):
        """find_similar_conversations requires 'conversation_id' in canonical form."""
        from ctk.interfaces.mcp.projection import project_tools

        tool = next(
            t for t in project_tools() if t.name == "find_similar_conversations"
        )
        assert "conversation_id" in tool.inputSchema["required"]
        assert "conversation_id" in tool.inputSchema["properties"]

    def test_legacy_find_similar_schema_requires_id(self):
        """Legacy find_similar alias still requires 'id' (old MCP name)."""
        from ctk.interfaces.mcp.projection import project_tools

        tool = next(t for t in project_tools() if t.name == "find_similar")
        assert "id" in tool.inputSchema["required"]
        assert "id" in tool.inputSchema["properties"]

    def test_legacy_find_similar_schema_has_top_k_and_threshold(self):
        """Legacy find_similar alias still has top_k and threshold params."""
        from ctk.interfaces.mcp.projection import project_tools

        tool = next(t for t in project_tools() if t.name == "find_similar")
        props = tool.inputSchema["properties"]
        assert "top_k" in props
        assert "threshold" in props
        assert props["top_k"]["type"] == "integer"
        assert props["threshold"]["type"] == "number"

    def test_semantic_search_schema_requires_query(self):
        """semantic_search requires 'query' parameter."""
        from ctk.interfaces.mcp.projection import project_tools

        tool = next(t for t in project_tools() if t.name == "semantic_search")
        assert "query" in tool.inputSchema["required"]
        assert "query" in tool.inputSchema["properties"]

    def test_semantic_search_schema_has_top_k(self):
        """semantic_search has top_k optional param."""
        from ctk.interfaces.mcp.projection import project_tools

        tool = next(t for t in project_tools() if t.name == "semantic_search")
        assert "top_k" in tool.inputSchema["properties"]

    def test_total_curated_tool_count(self):
        """MCP exposes the expected number of curated tools."""
        from ctk.interfaces.mcp.projection import project_tools

        # 7 canonical + 1 legacy alias = 8
        tools = project_tools()
        assert len(tools) == 8


class TestFindSimilarViaExecuteNetworkTool:
    """Test find_similar_conversations behavior via execute_network_tool."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.get_all_embeddings.return_value = []
        db.resolve_identifier.return_value = None
        db.get_similar_conversations.return_value = []
        db.load_conversation.return_value = None
        return db

    def test_invalid_id_returns_error(self, mock_db):
        """find_similar_conversations returns error for unresolvable ID."""
        from ctk.core.network_tools import execute_network_tool

        mock_db.resolve_identifier.return_value = None

        result = execute_network_tool(
            mock_db, "find_similar_conversations", {"conversation_id": "nonexistent"}
        )

        assert "Error" in result or "no conversation" in result.lower()

    def test_no_embeddings_returns_hint(self, mock_db):
        """find_similar_conversations returns hint when no embeddings exist."""
        from ctk.core.network_tools import execute_network_tool

        mock_db.resolve_identifier.return_value = ("full-id-123", "slug")
        mock_db.get_all_embeddings.return_value = []

        # _query_similarities returns [] because there are no rows
        from unittest.mock import patch

        with patch("ctk.core.network_tools._query_similarities", return_value=[]):
            result = execute_network_tool(
                mock_db,
                "find_similar_conversations",
                {"conversation_id": "full-id"},
            )

        assert "No embeddings" in result or "embeddings" in result.lower()

    def test_no_similar_found(self, mock_db):
        """find_similar_conversations reports when nothing is above threshold."""
        from unittest.mock import patch

        from ctk.core.network_tools import execute_network_tool

        mock_db.resolve_identifier.return_value = ("full-id-123", "slug")
        mock_db.get_all_embeddings.return_value = [
            {
                "conversation_id": "full-id-123",
                "embedding": [1.0, 0.0, 0.0],
                "provider": "tfidf",
            }
        ]

        with patch(
            "ctk.core.network_tools._query_similarities", return_value=[]
        ), patch("ctk.core.network_tools._compute_cosine_fallback", return_value=[]):
            result = execute_network_tool(
                mock_db,
                "find_similar_conversations",
                {"conversation_id": "full-id"},
            )

        assert "no similarities" in result.lower() or "no similar" in result.lower()

    def test_finds_similar_from_cached(self, mock_db):
        """find_similar_conversations returns cached similarity results."""
        from unittest.mock import patch

        from ctk.core.network_tools import execute_network_tool

        mock_db.resolve_identifier.return_value = ("full-id-123", "slug")

        mock_conv = MagicMock()
        mock_conv.title = "Test Conversation"
        mock_db.load_conversation.return_value = mock_conv

        with patch(
            "ctk.core.network_tools._query_similarities",
            return_value=[("other-id-456", 0.95)],
        ):
            result = execute_network_tool(
                mock_db,
                "find_similar_conversations",
                {"conversation_id": "full-id"},
            )

        assert "other-id" in result
        assert "0.95" in result or ".950" in result

    def test_missing_conversation_id_returns_error(self, mock_db):
        """find_similar_conversations returns an error when conversation_id is empty."""
        from ctk.core.network_tools import execute_network_tool

        result = execute_network_tool(
            mock_db, "find_similar_conversations", {"conversation_id": ""}
        )
        assert "Error" in result or "no conversation" in result.lower()


class TestSemanticSearchViaExecuteNetworkTool:
    """Test semantic_search behavior via execute_network_tool."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = MagicMock()
        db.get_all_embeddings.return_value = []
        db.load_conversation.return_value = None
        return db

    def test_no_embeddings_returns_hint(self, mock_db):
        """semantic_search returns hint when no embeddings exist."""
        from ctk.core.network_tools import execute_network_tool

        mock_db.get_all_embeddings.return_value = []

        result = execute_network_tool(
            mock_db, "semantic_search", {"query": "test query"}
        )

        assert "No embeddings" in result or "embeddings" in result.lower()

    def test_missing_query_returns_error(self, mock_db):
        """semantic_search returns an error when query is empty."""
        from ctk.core.network_tools import execute_network_tool

        result = execute_network_tool(mock_db, "semantic_search", {"query": ""})
        assert "Error" in result or "required" in result.lower()


class TestHandleToolProjectionDispatch:
    """Test projection.handle_tool dispatches analysis tools correctly."""

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
        return db

    def test_unknown_tool_returns_error(self, event_loop, mock_db):
        """handle_tool returns error text for unknown tool names."""
        from ctk.interfaces.mcp.projection import handle_tool

        result = event_loop.run_until_complete(
            handle_tool("nonexistent_tool", {}, mock_db)
        )
        assert len(result) == 1
        assert "Unknown tool" in result[0].text

    def test_legacy_find_similar_dispatches(self, event_loop, mock_db):
        """Legacy 'find_similar' alias is dispatched correctly."""
        from unittest.mock import patch

        from ctk.interfaces.mcp.projection import handle_tool

        with patch(
            "ctk.core.network_tools.execute_network_tool",
            return_value="(no similar conversations found)",
        ) as mock_execute:
            event_loop.run_until_complete(
                handle_tool(
                    "find_similar",
                    {"id": "abc123", "top_k": 5, "threshold": 0.2},
                    mock_db,
                )
            )

        # Should have been called with canonical name and rewritten args
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert call_args[0][1] == "find_similar_conversations"
        normalized = call_args[0][2]
        assert "conversation_id" in normalized
        assert normalized["conversation_id"] == "abc123"

    def test_semantic_search_dispatches(self, event_loop, mock_db):
        """semantic_search is dispatched through handle_tool."""
        from unittest.mock import patch

        from ctk.interfaces.mcp.projection import handle_tool

        with patch(
            "ctk.core.network_tools.execute_network_tool",
            return_value="No semantically similar conversations found.",
        ):
            result = event_loop.run_until_complete(
                handle_tool("semantic_search", {"query": "python async"}, mock_db)
            )

        assert len(result) == 1
        assert "No semantically similar" in result[0].text


class TestBuildTitleCacheFromNetworkTools:
    """Test _build_title_cache from ctk.core.network_tools (canonical location)."""

    def test_returns_title_dict(self):
        """_build_title_cache returns a dict of id -> title."""
        from ctk.core.network_tools import _build_title_cache

        mock_db = MagicMock()
        mock_summary = MagicMock()
        mock_summary.id = "test-id-123"
        mock_summary.title = "My Title"
        mock_db.list_conversations.return_value = [mock_summary]

        cache = _build_title_cache(mock_db, ["test-id-123"])
        assert cache["test-id-123"] == "My Title"

    def test_handles_none_title(self):
        """_build_title_cache uses 'Untitled' when title is None."""
        from ctk.core.network_tools import _build_title_cache

        mock_db = MagicMock()
        mock_summary = MagicMock()
        mock_summary.id = "test-id-123"
        mock_summary.title = None
        mock_db.list_conversations.return_value = [mock_summary]

        cache = _build_title_cache(mock_db, ["test-id-123"])
        assert cache["test-id-123"] == "Untitled"

    def test_truncates_to_max_len(self):
        """_build_title_cache truncates titles to max_len."""
        from ctk.core.network_tools import _build_title_cache

        mock_db = MagicMock()
        mock_summary = MagicMock()
        mock_summary.id = "test-id-123"
        mock_summary.title = "A" * 100
        mock_db.list_conversations.return_value = [mock_summary]

        cache = _build_title_cache(mock_db, ["test-id-123"], max_len=10)
        assert len(cache["test-id-123"]) == 10

    def test_returns_empty_dict_on_exception(self):
        """_build_title_cache returns empty dict when db raises."""
        from ctk.core.network_tools import _build_title_cache

        mock_db = MagicMock()
        mock_db.list_conversations.side_effect = Exception("DB error")

        cache = _build_title_cache(mock_db, ["test-id"])
        assert cache == {}


class TestHelperFunctions:
    """Test shared utility functions that survive from the old analysis tests."""

    def test_cosine_similarity_identical_vectors(self):
        """cosine_similarity of identical vectors is 1.0."""
        import numpy as np

        from ctk.core.similarity import cosine_similarity

        vec = np.array([1.0, 2.0, 3.0])
        assert abs(cosine_similarity(vec, vec) - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal_vectors(self):
        """cosine_similarity of orthogonal vectors is 0.0."""
        import numpy as np

        from ctk.core.similarity import cosine_similarity

        vec_a = np.array([1.0, 0.0])
        vec_b = np.array([0.0, 1.0])
        assert abs(cosine_similarity(vec_a, vec_b)) < 1e-6

    def test_cosine_similarity_mismatched_shapes(self):
        """cosine_similarity returns 0 for mismatched shapes."""
        import numpy as np

        from ctk.core.similarity import cosine_similarity

        vec_a = np.array([1.0, 0.0])
        vec_b = np.array([1.0, 0.0, 0.0])
        assert cosine_similarity(vec_a, vec_b) == 0.0

    def test_cosine_similarity_zero_vector(self):
        """cosine_similarity with zero vector returns 0."""
        import numpy as np

        from ctk.core.similarity import cosine_similarity

        vec_a = np.array([0.0, 0.0])
        vec_b = np.array([1.0, 0.0])
        assert cosine_similarity(vec_a, vec_b) == 0.0

    def test_validate_float_threshold(self):
        """validate_float for threshold boundary conditions."""
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
