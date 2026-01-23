"""
Unit tests for ConversationIndex.

Tests the in-memory index for O(1) slug and prefix resolution.
"""

import threading
from unittest.mock import MagicMock, Mock, patch

import pytest

from ctk.core.conversation_index import ConversationIndex, IndexEntry


class TestIndexEntry:
    """Tests for IndexEntry dataclass"""

    @pytest.mark.unit
    def test_entry_creation(self):
        """Test creating an index entry"""
        entry = IndexEntry(id="abc123", slug="my-chat", title="My Chat")
        assert entry.id == "abc123"
        assert entry.slug == "my-chat"
        assert entry.title == "My Chat"

    @pytest.mark.unit
    def test_entry_optional_fields(self):
        """Test entry with optional fields"""
        entry = IndexEntry(id="abc123", slug=None)
        assert entry.id == "abc123"
        assert entry.slug is None
        assert entry.title is None


class TestConversationIndexInitialization:
    """Tests for ConversationIndex initialization"""

    @pytest.mark.unit
    def test_init_no_db(self):
        """Test initialization without database"""
        index = ConversationIndex()
        assert index.db is None
        assert not index.is_loaded
        assert index.entry_count == 0

    @pytest.mark.unit
    def test_init_with_db(self):
        """Test initialization with database"""
        mock_db = Mock()
        index = ConversationIndex(db=mock_db)
        assert index.db == mock_db
        assert not index.is_loaded


class TestConversationIndexResolve:
    """Tests for resolve functionality"""

    @pytest.fixture
    def populated_index(self):
        """Create a populated index without database"""
        index = ConversationIndex()
        # Manually populate the index
        index._slug_to_id = {
            "python-chat": "abc12345-1234-5678-9abc-def012345678",
            "rust-tips": "def67890-1234-5678-9abc-def012345678",
        }
        index._id_to_entry = {
            "abc12345-1234-5678-9abc-def012345678": IndexEntry(
                id="abc12345-1234-5678-9abc-def012345678",
                slug="python-chat",
                title="Python Chat",
            ),
            "def67890-1234-5678-9abc-def012345678": IndexEntry(
                id="def67890-1234-5678-9abc-def012345678",
                slug="rust-tips",
                title="Rust Tips",
            ),
        }
        index._id_prefix_4 = {
            "abc1": ["abc12345-1234-5678-9abc-def012345678"],
            "def6": ["def67890-1234-5678-9abc-def012345678"],
        }
        index._id_prefix_8 = {
            "abc12345": ["abc12345-1234-5678-9abc-def012345678"],
            "def67890": ["def67890-1234-5678-9abc-def012345678"],
        }
        index._loaded = True
        index._entry_count = 2
        return index

    @pytest.mark.unit
    def test_resolve_exact_slug(self, populated_index):
        """Test resolving exact slug match"""
        result = populated_index.resolve("python-chat")
        assert result is not None
        conv_id, slug = result
        assert conv_id == "abc12345-1234-5678-9abc-def012345678"
        assert slug == "python-chat"

    @pytest.mark.unit
    def test_resolve_exact_id(self, populated_index):
        """Test resolving exact ID match"""
        result = populated_index.resolve("abc12345-1234-5678-9abc-def012345678")
        assert result is not None
        conv_id, slug = result
        assert conv_id == "abc12345-1234-5678-9abc-def012345678"
        assert slug == "python-chat"

    @pytest.mark.unit
    def test_resolve_slug_prefix(self, populated_index):
        """Test resolving unique slug prefix"""
        result = populated_index.resolve("python")
        assert result is not None
        conv_id, slug = result
        assert conv_id == "abc12345-1234-5678-9abc-def012345678"
        assert slug == "python-chat"

    @pytest.mark.unit
    def test_resolve_id_prefix(self, populated_index):
        """Test resolving unique ID prefix"""
        result = populated_index.resolve("abc1234")
        assert result is not None
        conv_id, _ = result
        assert conv_id == "abc12345-1234-5678-9abc-def012345678"

    @pytest.mark.unit
    def test_resolve_no_match(self, populated_index):
        """Test resolving non-existent identifier"""
        result = populated_index.resolve("nonexistent")
        assert result is None

    @pytest.mark.unit
    def test_resolve_not_loaded(self):
        """Test resolve when index not loaded returns None"""
        index = ConversationIndex()
        result = index.resolve("anything")
        assert result is None


class TestConversationIndexCompletions:
    """Tests for get_completions functionality"""

    @pytest.fixture
    def populated_index(self):
        """Create a populated index"""
        index = ConversationIndex()
        index._slug_to_id = {
            "python-chat": "abc12345",
            "python-tips": "def67890",
            "rust-basics": "ghi11111",
        }
        index._id_to_entry = {
            "abc12345": IndexEntry(
                id="abc12345", slug="python-chat", title="Python Chat"
            ),
            "def67890": IndexEntry(
                id="def67890", slug="python-tips", title="Python Tips"
            ),
            "ghi11111": IndexEntry(
                id="ghi11111", slug="rust-basics", title="Rust Basics"
            ),
        }
        index._id_prefix_4 = {
            "abc1": ["abc12345"],
            "def6": ["def67890"],
            "ghi1": ["ghi11111"],
        }
        index._id_prefix_8 = {
            "abc12345": ["abc12345"],
            "def67890": ["def67890"],
            "ghi11111": ["ghi11111"],
        }
        index._loaded = True
        index._entry_count = 3
        return index

    @pytest.mark.unit
    def test_get_completions_slug_prefix(self, populated_index):
        """Test getting completions by slug prefix"""
        completions = populated_index.get_completions("python")
        assert len(completions) == 2
        display_texts = [c[0] for c in completions]
        assert "python-chat" in display_texts
        assert "python-tips" in display_texts

    @pytest.mark.unit
    def test_get_completions_limit(self, populated_index):
        """Test completions respect limit"""
        completions = populated_index.get_completions("", limit=2)
        assert len(completions) == 2

    @pytest.mark.unit
    def test_get_completions_not_loaded(self):
        """Test completions when index not loaded"""
        index = ConversationIndex()
        completions = index.get_completions("python")
        assert completions == []


class TestConversationIndexMutations:
    """Tests for add/remove functionality"""

    @pytest.mark.unit
    def test_add_entry(self):
        """Test adding an entry to loaded index"""
        index = ConversationIndex()
        index._loaded = True

        index.add("new-id-1234", "new-slug", "New Title")

        assert "new-slug" in index._slug_to_id
        assert "new-id-1234" in index._id_to_entry
        assert index.entry_count == 1

    @pytest.mark.unit
    def test_add_entry_not_loaded(self):
        """Test adding entry when not loaded is no-op"""
        index = ConversationIndex()
        index.add("new-id", "new-slug", "Title")
        assert index.entry_count == 0

    @pytest.mark.unit
    def test_remove_entry(self):
        """Test removing an entry"""
        index = ConversationIndex()
        index._loaded = True
        index.add("id-to-remove", "slug-to-remove", "Title")

        index.remove("id-to-remove")

        assert "slug-to-remove" not in index._slug_to_id
        assert "id-to-remove" not in index._id_to_entry
        assert index.entry_count == 0

    @pytest.mark.unit
    def test_invalidate_clears_index(self):
        """Test invalidate clears the index"""
        index = ConversationIndex()
        index._loaded = True
        index.add("some-id", "some-slug", "Title")

        index.invalidate()

        assert not index.is_loaded
        assert index.entry_count == 0
        assert len(index._slug_to_id) == 0


class TestConversationIndexStats:
    """Tests for get_stats functionality"""

    @pytest.mark.unit
    def test_get_stats(self):
        """Test getting index statistics"""
        index = ConversationIndex()
        index._loaded = True
        index._entry_count = 100
        index._load_time = 0.5
        index._slug_to_id = {"a": "1", "b": "2"}
        index._id_prefix_4 = {"abc1": [], "def2": []}
        index._id_prefix_8 = {"abc12345": []}

        stats = index.get_stats()

        assert stats["loaded"] is True
        assert stats["entry_count"] == 100
        assert stats["load_time"] == 0.5
        assert stats["slug_count"] == 2
        assert stats["prefix_4_buckets"] == 2
        assert stats["prefix_8_buckets"] == 1
