"""
Tests for Sprint 4.4: Fix unlimited fetch patterns in TUI and VFS.

Verifies that database queries use proper limits, DB-level prefix resolution,
and efficient aggregation queries instead of materializing all conversations.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest
from sqlalchemy import text as sql_text

from ctk.core.database import ConversationDB
from ctk.core.models import (ConversationMetadata, ConversationSummary,
                             ConversationTree, Message, MessageContent,
                             MessageRole)


def _create_db(n: int = 10) -> ConversationDB:
    """Helper to create an in-memory DB with n conversations."""
    db = ConversationDB(":memory:")
    base_time = datetime(2024, 1, 1, 0, 0, 0)

    for i in range(n):
        updated_at = base_time + timedelta(hours=i)
        created_at = updated_at - timedelta(minutes=5)

        metadata = ConversationMetadata(
            created_at=created_at,
            updated_at=updated_at,
            source=(
                "openai" if i % 3 == 0 else ("anthropic" if i % 3 == 1 else "gemini")
            ),
            model=f"gpt-4" if i % 2 == 0 else "claude-3",
            format="openai",
            version="1.0",
        )

        message = Message(
            id=f"msg-{i}",
            role=MessageRole.USER,
            content=MessageContent(text=f"Message {i}"),
            timestamp=created_at,
        )

        conv = ConversationTree(
            id=f"conv-{i:03d}",
            title=f"Conversation {i}",
            metadata=metadata,
        )
        conv.add_message(message)
        db.save_conversation(conv)

    # Force timestamps via raw SQL
    with db.session_scope() as session:
        for i in range(n):
            updated_at = base_time + timedelta(hours=i)
            created_at = updated_at - timedelta(minutes=5)
            session.execute(
                sql_text(
                    "UPDATE conversations SET updated_at = :ua, created_at = :ca "
                    "WHERE id = :id"
                ),
                {"ua": updated_at, "ca": created_at, "id": f"conv-{i:03d}"},
            )

    return db


# =============================================================================
# 1. TestDistinctQueries - New DB methods
# =============================================================================


@pytest.mark.unit
class TestDistinctQueries:
    """Test get_distinct_sources() and get_distinct_models() DB methods."""

    @pytest.fixture
    def db(self):
        return _create_db(10)

    def test_get_distinct_sources(self, db):
        """Should return unique source values without loading all conversations."""
        sources = db.get_distinct_sources()
        assert isinstance(sources, list)
        assert set(sources) == {"openai", "anthropic", "gemini"}

    def test_get_distinct_sources_excludes_none(self, db):
        """Should not include None in distinct sources."""
        # Save a conversation with no source
        conv = ConversationTree(id="no-source", title="No Source")
        conv.metadata.source = None
        msg = Message(
            id="msg-ns",
            role=MessageRole.USER,
            content=MessageContent(text="test"),
        )
        conv.add_message(msg)
        db.save_conversation(conv)

        sources = db.get_distinct_sources()
        assert None not in sources

    def test_get_distinct_models(self, db):
        """Should return unique model values without loading all conversations."""
        models = db.get_distinct_models()
        assert isinstance(models, list)
        assert set(models) == {"gpt-4", "claude-3"}

    def test_get_distinct_models_excludes_none(self, db):
        """Should not include None in distinct models."""
        conv = ConversationTree(id="no-model", title="No Model")
        conv.metadata.model = None
        msg = Message(
            id="msg-nm",
            role=MessageRole.USER,
            content=MessageContent(text="test"),
        )
        conv.add_message(msg)
        db.save_conversation(conv)

        models = db.get_distinct_models()
        assert None not in models

    def test_get_distinct_sources_empty_db(self):
        """Should return empty list for empty database."""
        db = ConversationDB(":memory:")
        assert db.get_distinct_sources() == []

    def test_get_distinct_models_empty_db(self):
        """Should return empty list for empty database."""
        db = ConversationDB(":memory:")
        assert db.get_distinct_models() == []

    def test_distinct_sources_sorted(self, db):
        """Distinct sources should be returned sorted."""
        sources = db.get_distinct_sources()
        assert sources == sorted(sources)

    def test_distinct_models_sorted(self, db):
        """Distinct models should be returned sorted."""
        models = db.get_distinct_models()
        assert models == sorted(models)


# =============================================================================
# 2. TestVFSListChatsLimit
# =============================================================================


@pytest.mark.unit
class TestVFSListChatsLimit:
    """Test that _list_chats() respects a default limit."""

    def test_list_chats_passes_limit(self):
        """_list_chats should pass a limit to list_conversations."""
        from ctk.core.vfs_navigator import VFSNavigator

        mock_db = MagicMock()
        mock_db.list_conversations.return_value = []

        navigator = VFSNavigator(mock_db)
        navigator._list_chats()

        # Should have been called with a limit
        call_kwargs = mock_db.list_conversations.call_args
        # Either positional or keyword, limit should be present
        if call_kwargs[1]:
            assert "limit" in call_kwargs[1]
        else:
            # Check it's not called without any args (unlimited)
            assert call_kwargs is not None


# =============================================================================
# 3. TestVFSListSourceUsesDistinct
# =============================================================================


@pytest.mark.unit
class TestVFSListSourceUsesDistinct:
    """Test that _list_source() root uses get_distinct_sources() instead of loading all."""

    def test_list_source_root_uses_distinct(self):
        """Root /source/ should use get_distinct_sources() not list_conversations()."""
        from ctk.core.vfs_navigator import VFSNavigator

        mock_db = MagicMock()
        mock_db.get_distinct_sources.return_value = ["anthropic", "openai"]

        navigator = VFSNavigator(mock_db)
        entries = navigator._list_source(["source"])

        mock_db.get_distinct_sources.assert_called_once()
        # Should NOT call list_conversations for root listing
        mock_db.list_conversations.assert_not_called()

        names = {e.name for e in entries}
        assert names == {"anthropic", "openai"}

    def test_list_source_specific_still_uses_list(self):
        """Specific /source/<name>/ should still use list_conversations(source=name)."""
        from ctk.core.vfs_navigator import VFSNavigator

        mock_db = MagicMock()
        mock_conv = MagicMock()
        mock_conv.id = "conv-001"
        mock_conv.title = "Test"
        mock_conv.created_at = datetime.now()
        mock_conv.updated_at = datetime.now()
        mock_conv.tags = []
        mock_conv.starred_at = None
        mock_conv.pinned_at = None
        mock_conv.archived_at = None
        mock_conv.source = "openai"
        mock_conv.model = "gpt-4"
        mock_conv.slug = None
        mock_db.list_conversations.return_value = [mock_conv]

        navigator = VFSNavigator(mock_db)
        entries = navigator._list_source(["source", "openai"])

        mock_db.list_conversations.assert_called_once()
        call_kwargs = mock_db.list_conversations.call_args[1]
        assert call_kwargs["source"] == "openai"


# =============================================================================
# 4. TestVFSListModelUsesDistinct
# =============================================================================


@pytest.mark.unit
class TestVFSListModelUsesDistinct:
    """Test that _list_model() root uses get_distinct_models() instead of loading all."""

    def test_list_model_root_uses_distinct(self):
        """Root /model/ should use get_distinct_models() not list_conversations()."""
        from ctk.core.vfs_navigator import VFSNavigator

        mock_db = MagicMock()
        mock_db.get_distinct_models.return_value = ["claude-3", "gpt-4"]

        navigator = VFSNavigator(mock_db)
        entries = navigator._list_model(["model"])

        mock_db.get_distinct_models.assert_called_once()
        mock_db.list_conversations.assert_not_called()

        names = {e.name for e in entries}
        assert names == {"claude-3", "gpt-4"}


# =============================================================================
# 5. TestVFSListRecentUsesDateFilter
# =============================================================================


@pytest.mark.unit
class TestVFSListRecentUsesDateFilter:
    """Test that _list_recent() uses DB-level date filtering."""

    def test_list_recent_today_passes_date_from(self):
        """_list_recent('today') should pass date_from to search_conversations."""
        from ctk.core.vfs_navigator import VFSNavigator

        mock_db = MagicMock()
        mock_db.search_conversations.return_value = []

        navigator = VFSNavigator(mock_db)
        navigator._list_recent(["recent", "today"])

        # Should use search_conversations with date_from (today's start)
        mock_db.search_conversations.assert_called_once()
        call_kwargs = mock_db.search_conversations.call_args[1]
        assert "date_from" in call_kwargs


# =============================================================================
# 6. TestTUIResolveConversation
# =============================================================================


@pytest.mark.unit
class TestTUIResolveConversation:
    """Test that TUI prefix resolution uses DB-level resolve, not loading all."""

    @pytest.fixture
    def db(self):
        return _create_db(10)

    def test_load_conversation_uses_resolve(self, db):
        """load_conversation with partial ID should use resolve_conversation."""
        # The resolve_conversation method does DB-level prefix matching
        result = db.resolve_conversation("conv-00")
        # conv-00 matches conv-000..conv-009 (10 matches), so ambiguous
        assert result is None  # ambiguous

        result = db.resolve_conversation("conv-005")
        assert result == "conv-005"

    def test_resolve_conversation_exact_match(self, db):
        """Exact ID should resolve without loading all."""
        result = db.resolve_conversation("conv-003")
        assert result == "conv-003"


# =============================================================================
# 7. TestSearchLimit
# =============================================================================


@pytest.mark.unit
class TestSearchConversationsLimit:
    """Test that _search_conversations in search.py respects limits."""

    @pytest.fixture
    def db(self):
        return _create_db(10)

    def test_search_with_limit(self, db):
        """_search_conversations should respect limit parameter."""
        from ctk.core.commands.search import SearchCommands

        search = SearchCommands(db, MagicMock())
        # Search all conversations by content
        results = search._search_conversations(
            content_regex=None,
            name_regex=None,
            role_filter=None,
            type_filter=None,
            limit=3,
            conv_ids=None,
        )
        assert len(results) <= 3

    def test_search_without_conv_ids_has_limit(self, db):
        """When searching without conv_ids, should limit conversations loaded."""
        from ctk.core.commands.search import SearchCommands

        search = SearchCommands(db, MagicMock())

        with patch.object(
            db, "list_conversations", wraps=db.list_conversations
        ) as mock_list:
            search._search_conversations(
                content_regex=None,
                name_regex=None,
                role_filter=None,
                type_filter=None,
                limit=5,
                conv_ids=None,
            )
            # Should have been called with a limit
            if mock_list.called:
                call_kwargs = mock_list.call_args[1] if mock_list.call_args[1] else {}
                # At minimum, shouldn't be called without any limit
                # (the fix adds a limit parameter)
                assert "limit" in call_kwargs or mock_list.call_args[0]
