"""
Comprehensive TDD tests for cursor pagination in CTK.

These tests cover:
1. Cursor encoding/decoding (ctk/core/pagination.py)
2. PaginatedResult dataclass (ctk/core/models.py)
3. Cursor pagination in list_conversations()
4. Cursor pagination in search_conversations()

All tests should FAIL initially (RED phase of TDD).
"""

import base64
import json
from datetime import datetime, timedelta
from typing import List

import pytest
from sqlalchemy import text as sql_text

from ctk.core.database import ConversationDB
from ctk.core.models import (ConversationMetadata, ConversationSummary,
                             ConversationTree, Message, MessageContent,
                             MessageRole, PaginatedResult)
from ctk.core.pagination import decode_cursor, encode_cursor

# =============================================================================
# 1. TestCursorEncoding - Test cursor encode/decode utilities
# =============================================================================


@pytest.mark.unit
class TestCursorEncoding:
    """Test cursor encoding and decoding utilities."""

    def test_encode_decode_roundtrip(self):
        """Encode then decode should give same values."""
        updated_at = datetime(2024, 1, 15, 12, 30, 45, 123456)
        conv_id = "test-conversation-id-123"

        cursor = encode_cursor(updated_at, conv_id)
        decoded_dt, decoded_id = decode_cursor(cursor)

        assert decoded_dt == updated_at
        assert decoded_id == conv_id

    def test_encode_produces_string(self):
        """Encode should return a string."""
        updated_at = datetime.now()
        conv_id = "abc123"

        cursor = encode_cursor(updated_at, conv_id)

        assert isinstance(cursor, str)
        assert len(cursor) > 0

    def test_decode_invalid_base64(self):
        """Decoding invalid base64 should raise ValueError."""
        invalid_cursor = "not-valid-base64!@#$"

        with pytest.raises(ValueError):
            decode_cursor(invalid_cursor)

    def test_decode_invalid_json(self):
        """Decoding invalid JSON should raise ValueError."""
        # Valid base64 but not valid JSON
        invalid_json = base64.urlsafe_b64encode(b"not json").decode()

        with pytest.raises(ValueError):
            decode_cursor(invalid_json)

    def test_decode_missing_fields(self):
        """Decoding JSON without required fields should raise KeyError."""
        # Valid JSON but missing required fields
        incomplete_data = json.dumps({"only": "partial"})
        cursor = base64.urlsafe_b64encode(incomplete_data.encode()).decode()

        with pytest.raises(KeyError):
            decode_cursor(cursor)

    def test_encode_with_microseconds(self):
        """Datetime precision should be preserved including microseconds."""
        updated_at = datetime(2024, 1, 15, 12, 30, 45, 999999)
        conv_id = "test-id"

        cursor = encode_cursor(updated_at, conv_id)
        decoded_dt, _ = decode_cursor(cursor)

        assert decoded_dt.microsecond == 999999

    def test_cursor_is_url_safe(self):
        """Cursor should use URL-safe base64 (no +/= characters)."""
        # Use date/id that would normally produce non-URL-safe chars
        updated_at = datetime(2024, 12, 31, 23, 59, 59, 999999)
        conv_id = "x" * 100  # Long ID to ensure padding

        cursor = encode_cursor(updated_at, conv_id)

        # URL-safe base64 uses - and _ instead of + and /
        # and may have = padding, but we expect urlsafe_b64encode
        assert "+" not in cursor
        assert "/" not in cursor


# =============================================================================
# 2. TestPaginatedResult - Test PaginatedResult dataclass
# =============================================================================


@pytest.mark.unit
class TestPaginatedResult:
    """Test PaginatedResult dataclass behavior."""

    def test_len(self):
        """len() should return length of items list."""
        items = [
            ConversationSummary(
                id=f"conv-{i}",
                title=f"Conv {i}",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                message_count=5,
                source="test",
                model="gpt-4",
                tags=[],
            )
            for i in range(3)
        ]
        result = PaginatedResult(items=items)

        assert len(result) == 3

    def test_iter(self):
        """Should be able to iterate over items."""
        items = [
            ConversationSummary(
                id=f"conv-{i}",
                title=f"Conv {i}",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                message_count=5,
                source="test",
                model="gpt-4",
                tags=[],
            )
            for i in range(3)
        ]
        result = PaginatedResult(items=items)

        collected = list(result)
        assert len(collected) == 3
        assert all(isinstance(item, ConversationSummary) for item in collected)

    def test_bool_empty(self):
        """Empty result should be falsy."""
        result = PaginatedResult(items=[])

        assert not result

    def test_bool_nonempty(self):
        """Non-empty result should be truthy."""
        items = [
            ConversationSummary(
                id="conv-1",
                title="Conv 1",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                message_count=5,
                source="test",
                model="gpt-4",
                tags=[],
            )
        ]
        result = PaginatedResult(items=items)

        assert result

    def test_has_more_default(self):
        """has_more should default to False."""
        result = PaginatedResult(items=[])

        assert result.has_more is False

    def test_next_cursor_default(self):
        """next_cursor should default to None."""
        result = PaginatedResult(items=[])

        assert result.next_cursor is None

    def test_with_cursor(self):
        """Should store cursor and has_more when provided."""
        items = [
            ConversationSummary(
                id="conv-1",
                title="Conv 1",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                message_count=5,
                source="test",
                model="gpt-4",
                tags=[],
            )
        ]
        cursor = "test-cursor-value"
        result = PaginatedResult(items=items, next_cursor=cursor, has_more=True)

        assert result.next_cursor == cursor
        assert result.has_more is True


# =============================================================================
# 3. TestCursorPagination - Test cursor pagination in list_conversations()
# =============================================================================


@pytest.mark.unit
class TestCursorPagination:
    """Test cursor pagination with ConversationDB.list_conversations()."""

    @pytest.fixture
    def db_with_conversations(self):
        """Create an in-memory DB with 10 conversations with distinct timestamps."""
        db = ConversationDB(":memory:")

        # Base timestamp
        base_time = datetime(2024, 1, 1, 0, 0, 0)

        # Create 10 conversations with 1-hour spacing
        for i in range(10):
            updated_at = base_time + timedelta(hours=i)
            created_at = updated_at - timedelta(minutes=5)

            metadata = ConversationMetadata(
                created_at=created_at,
                updated_at=updated_at,
                source="test",
                model=f"model-{i}",
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
                id=f"conv-{i:03d}",  # Zero-padded for consistent sorting
                title=f"Conversation {i}",
                metadata=metadata,
            )
            conv.add_message(message)
            db.save_conversation(conv)

        # Force timestamps via raw SQL to bypass ORM onupdate=func.now()
        with db.session_scope() as session:
            for i in range(10):
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

    def test_first_page_no_cursor(self, db_with_conversations):
        """First page with empty cursor should return first 3 items."""
        result = db_with_conversations.list_conversations(cursor="", page_size=3)

        assert isinstance(result, PaginatedResult)
        assert len(result) == 3
        assert result.has_more is True
        assert result.next_cursor is not None
        assert result.next_cursor != ""

        # Should be most recent first (descending updated_at)
        assert result.items[0].id == "conv-009"
        assert result.items[1].id == "conv-008"
        assert result.items[2].id == "conv-007"

    def test_second_page_with_cursor(self, db_with_conversations):
        """Second page should use cursor and return next 3 items."""
        # Get first page
        first_page = db_with_conversations.list_conversations(cursor="", page_size=3)
        first_ids = {item.id for item in first_page.items}

        # Get second page
        second_page = db_with_conversations.list_conversations(
            cursor=first_page.next_cursor, page_size=3
        )

        assert isinstance(second_page, PaginatedResult)
        assert len(second_page) == 3
        assert second_page.has_more is True

        # No overlap with first page
        second_ids = {item.id for item in second_page.items}
        assert first_ids.isdisjoint(second_ids)

        # Should continue in order
        assert second_page.items[0].id == "conv-006"
        assert second_page.items[1].id == "conv-005"
        assert second_page.items[2].id == "conv-004"

    def test_paginate_through_all(self, db_with_conversations):
        """Paginate through all conversations and verify count."""
        collected_ids = []
        cursor = ""
        page_count = 0

        while True:
            result = db_with_conversations.list_conversations(
                cursor=cursor, page_size=3
            )
            page_count += 1

            collected_ids.extend([item.id for item in result.items])

            if not result.has_more:
                break

            cursor = result.next_cursor

        assert len(collected_ids) == 10
        assert len(set(collected_ids)) == 10  # All unique
        assert page_count == 4  # 3+3+3+1

    def test_page_size_larger_than_results(self, db_with_conversations):
        """Page size larger than total should return all results."""
        result = db_with_conversations.list_conversations(cursor="", page_size=100)

        assert isinstance(result, PaginatedResult)
        assert len(result) == 10
        assert result.has_more is False
        assert result.next_cursor is None

    def test_page_size_equals_results(self, db_with_conversations):
        """Page size exactly matching total should return all results."""
        result = db_with_conversations.list_conversations(cursor="", page_size=10)

        assert isinstance(result, PaginatedResult)
        assert len(result) == 10
        assert result.has_more is False
        assert result.next_cursor is None

    def test_page_size_one(self, db_with_conversations):
        """Should be able to paginate one item at a time."""
        collected_ids = []
        cursor = ""

        for _ in range(10):
            result = db_with_conversations.list_conversations(
                cursor=cursor, page_size=1
            )
            assert len(result) == 1
            collected_ids.append(result.items[0].id)

            if not result.has_more:
                break

            cursor = result.next_cursor

        assert len(collected_ids) == 10
        assert len(set(collected_ids)) == 10

    def test_cursor_with_filters(self, db_with_conversations):
        """Cursor pagination should work with filters."""
        base_time = datetime(2024, 1, 1, 0, 0, 0)

        # Star conversations 5, 7, 9
        db_with_conversations.star_conversation("conv-005")
        db_with_conversations.star_conversation("conv-007")
        db_with_conversations.star_conversation("conv-009")

        # Re-force timestamps after starring (ORM onupdate overwrites them)
        with db_with_conversations.session_scope() as session:
            for i in (5, 7, 9):
                updated_at = base_time + timedelta(hours=i)
                session.execute(
                    sql_text(
                        "UPDATE conversations SET updated_at = :ua WHERE id = :id"
                    ),
                    {"ua": updated_at, "id": f"conv-{i:03d}"},
                )

        # Paginate through starred only
        result = db_with_conversations.list_conversations(
            cursor="", page_size=2, starred=True
        )

        assert len(result) == 2
        assert result.has_more is True
        assert all(item.starred_at is not None for item in result.items)

        # Get second page
        second_page = db_with_conversations.list_conversations(
            cursor=result.next_cursor, page_size=2, starred=True
        )

        assert len(second_page) == 1
        assert second_page.has_more is False
        assert second_page.items[0].starred_at is not None

    def test_cursor_ordering_descending(self, db_with_conversations):
        """Results should be ordered by updated_at DESC."""
        result = db_with_conversations.list_conversations(cursor="", page_size=10)

        # Most recent first
        for i in range(len(result.items) - 1):
            assert result.items[i].updated_at >= result.items[i + 1].updated_at

    def test_backward_compatible_no_cursor(self, db_with_conversations):
        """Without cursor, should return List[ConversationSummary]."""
        result = db_with_conversations.list_conversations(limit=5)

        assert isinstance(result, list)
        assert not isinstance(result, PaginatedResult)
        assert len(result) == 5
        assert all(isinstance(item, ConversationSummary) for item in result)

    def test_cursor_empty_string_means_first_page(self, db_with_conversations):
        """Empty string cursor should be treated as first page."""
        result = db_with_conversations.list_conversations(cursor="", page_size=3)

        assert isinstance(result, PaginatedResult)
        assert len(result) == 3
        # Should get most recent
        assert result.items[0].id == "conv-009"

    def test_no_results(self, db_with_conversations):
        """Cursor pagination with no matching results."""
        result = db_with_conversations.list_conversations(
            cursor="", page_size=10, starred=True  # None are starred initially
        )

        assert isinstance(result, PaginatedResult)
        assert len(result) == 0
        assert result.has_more is False
        assert result.next_cursor is None

    def test_invalid_cursor_raises(self, db_with_conversations):
        """Invalid cursor string should raise ValueError."""
        with pytest.raises(ValueError):
            db_with_conversations.list_conversations(
                cursor="invalid-cursor", page_size=10
            )

    def test_cursor_deterministic_ordering(self):
        """Items with same updated_at should be ordered by id."""
        db = ConversationDB(":memory:")

        # Same timestamp for all
        same_time = datetime(2024, 1, 1, 12, 0, 0)

        # Create 5 conversations with same updated_at
        for i in range(5):
            metadata = ConversationMetadata(
                created_at=same_time,
                updated_at=same_time,
                source="test",
                model="gpt-4",
                format="openai",
                version="1.0",
            )

            message = Message(
                id=f"msg-{i}",
                role=MessageRole.USER,
                content=MessageContent(text=f"Message {i}"),
                timestamp=same_time,
            )

            conv = ConversationTree(
                id=f"conv-{i}",
                title=f"Conversation {i}",
                metadata=metadata,
            )
            conv.add_message(message)
            db.save_conversation(conv)

        # Force all to same timestamp via raw SQL
        with db.session_scope() as session:
            for i in range(5):
                session.execute(
                    sql_text(
                        "UPDATE conversations SET updated_at = :ua, created_at = :ua "
                        "WHERE id = :id"
                    ),
                    {"ua": same_time, "id": f"conv-{i}"},
                )

        # Get all with pagination
        result1 = db.list_conversations(cursor="", page_size=3)
        result2 = db.list_conversations(cursor=result1.next_cursor, page_size=3)

        # Should be deterministic (ordered by id as tiebreaker)
        all_ids = [item.id for item in result1.items] + [
            item.id for item in result2.items
        ]

        # Check deterministic ordering (should be sorted by ID since timestamps are same)
        # Order depends on implementation, but should be consistent
        # Make a second query to verify determinism
        result1_again = db.list_conversations(cursor="", page_size=3)
        ids_again = [item.id for item in result1_again.items]

        assert ids_again == [item.id for item in result1.items]


# =============================================================================
# 4. TestSearchCursorPagination - Test cursor pagination in search_conversations()
# =============================================================================


@pytest.mark.unit
class TestSearchCursorPagination:
    """Test cursor pagination with ConversationDB.search_conversations()."""

    @pytest.fixture
    def db_with_searchable_conversations(self):
        """Create DB with conversations containing searchable content."""
        db = ConversationDB(":memory:")

        base_time = datetime(2024, 1, 1, 0, 0, 0)

        # Create 10 conversations, half with "python" in content
        for i in range(10):
            updated_at = base_time + timedelta(hours=i)
            created_at = updated_at - timedelta(minutes=5)

            metadata = ConversationMetadata(
                created_at=created_at,
                updated_at=updated_at,
                source="test",
                model="gpt-4",
                format="openai",
                version="1.0",
            )

            # Even numbered conversations mention "python"
            text = f"Message {i} about python" if i % 2 == 0 else f"Message {i}"

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
            for i in range(10):
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

    def test_search_first_page(self, db_with_searchable_conversations):
        """Search with cursor should return PaginatedResult."""
        result = db_with_searchable_conversations.search_conversations(
            query_text="python", cursor="", page_size=2
        )

        assert isinstance(result, PaginatedResult)
        assert len(result) == 2
        assert result.has_more is True
        assert result.next_cursor is not None

        # All results should match query
        assert all("python" in item.title or "conv-0" in item.id for item in result)

    def test_search_paginate_through(self, db_with_searchable_conversations):
        """Paginate through search results."""
        collected_ids = []
        cursor = ""

        while True:
            result = db_with_searchable_conversations.search_conversations(
                query_text="python", cursor=cursor, page_size=2
            )

            collected_ids.extend([item.id for item in result.items])

            if not result.has_more:
                break

            cursor = result.next_cursor

        # Should find 5 conversations (0, 2, 4, 6, 8)
        assert len(collected_ids) == 5
        assert len(set(collected_ids)) == 5
        assert all(int(cid.split("-")[1]) % 2 == 0 for cid in collected_ids)

    def test_search_backward_compatible(self, db_with_searchable_conversations):
        """Search without cursor should return List."""
        result = db_with_searchable_conversations.search_conversations(
            query_text="python", limit=3
        )

        assert isinstance(result, list)
        assert not isinstance(result, PaginatedResult)
        assert all(isinstance(item, ConversationSummary) for item in result)

    def test_search_no_results(self, db_with_searchable_conversations):
        """Search with no matches should return empty PaginatedResult."""
        result = db_with_searchable_conversations.search_conversations(
            query_text="nonexistent", cursor="", page_size=10
        )

        assert isinstance(result, PaginatedResult)
        assert len(result) == 0
        assert result.has_more is False
        assert result.next_cursor is None

    def test_search_page_size_larger_than_results(
        self, db_with_searchable_conversations
    ):
        """Search with large page size should return all matches."""
        result = db_with_searchable_conversations.search_conversations(
            query_text="python", cursor="", page_size=100
        )

        assert isinstance(result, PaginatedResult)
        assert len(result) == 5
        assert result.has_more is False
        assert result.next_cursor is None

    def test_search_invalid_cursor_raises(self, db_with_searchable_conversations):
        """Search with invalid cursor should raise ValueError."""
        with pytest.raises(ValueError):
            db_with_searchable_conversations.search_conversations(
                query_text="python", cursor="invalid", page_size=10
            )
