"""
Tests for streaming/generator query methods in ConversationDB.

These methods yield ConversationSummary objects one at a time instead of
materializing full lists, enabling memory-efficient processing of large
result sets (e.g., exporting 100k conversations).

Covers:
1. iter_conversations() - generator version of list_conversations()
2. iter_search_results() - generator version of search_conversations()
"""

import gc
from datetime import datetime, timedelta
from typing import Generator

import pytest
from sqlalchemy import text as sql_text

from ctk.core.database import ConversationDB
from ctk.core.models import (ConversationMetadata, ConversationSummary,
                             ConversationTree, Message, MessageContent,
                             MessageRole)


def _create_db_with_conversations(n: int = 10) -> ConversationDB:
    """Helper to create an in-memory DB with n conversations."""
    db = ConversationDB(":memory:")
    base_time = datetime(2024, 1, 1, 0, 0, 0)

    for i in range(n):
        updated_at = base_time + timedelta(hours=i)
        created_at = updated_at - timedelta(minutes=5)

        metadata = ConversationMetadata(
            created_at=created_at,
            updated_at=updated_at,
            source="openai" if i % 2 == 0 else "anthropic",
            model=f"model-{i}",
            format="openai",
            version="1.0",
        )

        # Even-numbered conversations mention "python"
        text = f"Message {i} about python" if i % 2 == 0 else f"Message {i} about rust"

        message = Message(
            id=f"msg-{i}",
            role=MessageRole.USER,
            content=MessageContent(text=text),
            timestamp=created_at,
        )

        conv = ConversationTree(
            id=f"conv-{i:03d}",
            title=f"Conversation {i}",
            metadata=metadata,
        )
        conv.add_message(message)
        db.save_conversation(conv)

    # Force timestamps via raw SQL to bypass ORM onupdate=func.now()
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
# 1. TestIterConversations
# =============================================================================


@pytest.mark.unit
class TestIterConversations:
    """Test iter_conversations() generator method."""

    @pytest.fixture
    def db(self):
        return _create_db_with_conversations(10)

    def test_returns_generator(self, db):
        """iter_conversations() should return a generator."""
        result = db.iter_conversations()
        assert hasattr(result, "__next__")
        assert hasattr(result, "__iter__")
        # Exhaust it to clean up session
        list(result)

    def test_yields_conversation_summaries(self, db):
        """Each yielded item should be a ConversationSummary."""
        items = list(db.iter_conversations())
        assert len(items) == 10
        assert all(isinstance(item, ConversationSummary) for item in items)

    def test_ordered_by_updated_at_desc(self, db):
        """Results should be ordered by updated_at descending (most recent first)."""
        items = list(db.iter_conversations())
        for i in range(len(items) - 1):
            assert items[i].updated_at >= items[i + 1].updated_at

    def test_yields_all_conversations(self, db):
        """Should yield all conversations when no filters applied."""
        items = list(db.iter_conversations())
        assert len(items) == 10
        ids = {item.id for item in items}
        assert ids == {f"conv-{i:03d}" for i in range(10)}

    def test_empty_database(self):
        """Should yield nothing for empty database."""
        db = ConversationDB(":memory:")
        items = list(db.iter_conversations())
        assert len(items) == 0

    def test_with_limit(self, db):
        """Should respect limit parameter."""
        items = list(db.iter_conversations(limit=3))
        assert len(items) == 3

    def test_with_source_filter(self, db):
        """Should filter by source."""
        items = list(db.iter_conversations(source="openai"))
        assert len(items) == 5
        assert all(item.source == "openai" for item in items)

    def test_with_starred_filter(self, db):
        """Should filter by starred status."""
        db.star_conversation("conv-003")
        db.star_conversation("conv-007")
        items = list(db.iter_conversations(starred=True))
        assert len(items) == 2
        assert all(item.starred_at is not None for item in items)

    def test_excludes_archived_by_default(self, db):
        """Should exclude archived conversations by default."""
        db.archive_conversation("conv-005")
        items = list(db.iter_conversations())
        assert len(items) == 9
        assert "conv-005" not in {item.id for item in items}

    def test_include_archived(self, db):
        """Should include archived when explicitly requested."""
        db.archive_conversation("conv-005")
        items = list(db.iter_conversations(include_archived=True))
        assert len(items) == 10

    def test_partial_iteration(self, db):
        """Partial iteration should not leak sessions."""
        gen = db.iter_conversations()
        # Only consume 3 items
        first = next(gen)
        second = next(gen)
        third = next(gen)
        assert isinstance(first, ConversationSummary)
        assert isinstance(second, ConversationSummary)
        assert isinstance(third, ConversationSummary)
        # Explicitly close generator
        gen.close()

    def test_multiple_generators_independent(self, db):
        """Multiple generators should be independent."""
        gen1 = db.iter_conversations()
        gen2 = db.iter_conversations()

        item1 = next(gen1)
        item2 = next(gen2)

        # Both should start at the same first item
        assert item1.id == item2.id

        # Exhaust to clean up
        list(gen1)
        list(gen2)

    def test_with_chunk_size(self, db):
        """Custom chunk_size should still yield all results."""
        items = list(db.iter_conversations(chunk_size=2))
        assert len(items) == 10

    def test_chunk_size_larger_than_results(self, db):
        """chunk_size larger than result set should work."""
        items = list(db.iter_conversations(chunk_size=1000))
        assert len(items) == 10

    def test_with_tag_filter(self, db):
        """Should filter by tag."""
        db.add_tags("conv-001", ["important"])
        db.add_tags("conv-003", ["important"])
        items = list(db.iter_conversations(tag="important"))
        assert len(items) == 2
        ids = {item.id for item in items}
        assert ids == {"conv-001", "conv-003"}

    def test_with_model_filter(self, db):
        """Should filter by model."""
        items = list(db.iter_conversations(model="model-5"))
        assert len(items) == 1
        assert items[0].id == "conv-005"


# =============================================================================
# 2. TestIterSearchResults
# =============================================================================


@pytest.mark.unit
class TestIterSearchResults:
    """Test iter_search_results() generator method."""

    @pytest.fixture
    def db(self):
        return _create_db_with_conversations(10)

    def test_returns_generator(self, db):
        """iter_search_results() should return a generator."""
        result = db.iter_search_results(query_text="python")
        assert hasattr(result, "__next__")
        assert hasattr(result, "__iter__")
        list(result)

    def test_yields_conversation_summaries(self, db):
        """Each yielded item should be a ConversationSummary."""
        items = list(db.iter_search_results(query_text="python"))
        assert all(isinstance(item, ConversationSummary) for item in items)

    def test_search_finds_matching(self, db):
        """Should yield only conversations matching the query."""
        items = list(db.iter_search_results(query_text="python"))
        # Even-numbered conversations have "python" in content
        assert len(items) == 5
        ids = {item.id for item in items}
        expected = {f"conv-{i:03d}" for i in range(0, 10, 2)}
        assert ids == expected

    def test_search_no_matches(self, db):
        """Should yield nothing when no matches found."""
        items = list(db.iter_search_results(query_text="nonexistent"))
        assert len(items) == 0

    def test_search_with_limit(self, db):
        """Should respect limit parameter."""
        items = list(db.iter_search_results(query_text="python", limit=2))
        assert len(items) == 2

    def test_search_with_source_filter(self, db):
        """Should combine text search with source filter."""
        items = list(db.iter_search_results(query_text="Message", source="anthropic"))
        # Odd-numbered conversations are "anthropic" source
        assert len(items) == 5
        assert all(item.source == "anthropic" for item in items)

    def test_partial_iteration(self, db):
        """Partial iteration should not leak sessions."""
        gen = db.iter_search_results(query_text="Message")
        first = next(gen)
        assert isinstance(first, ConversationSummary)
        gen.close()

    def test_with_chunk_size(self, db):
        """Custom chunk_size should still yield all results."""
        items = list(db.iter_search_results(query_text="python", chunk_size=2))
        assert len(items) == 5

    def test_empty_query_yields_all(self, db):
        """Empty/no query should yield all conversations."""
        items = list(db.iter_search_results())
        assert len(items) == 10

    def test_ordered_by_updated_at_desc(self, db):
        """Results should be ordered by updated_at descending by default."""
        items = list(db.iter_search_results(query_text="python"))
        for i in range(len(items) - 1):
            assert items[i].updated_at >= items[i + 1].updated_at
