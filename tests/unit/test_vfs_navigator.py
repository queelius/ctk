"""
Unit tests for VFS Navigator

Tests the VFSNavigator class for virtual filesystem navigation with caching.
"""

from datetime import datetime, timedelta
from time import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (ConversationMetadata, ConversationTree, Message,
                             MessageContent, MessageRole)
from ctk.core.vfs import PathType, VFSPath, VFSPathParser
from ctk.core.vfs_navigator import VFSEntry, VFSNavigator


class TestVFSEntry:
    """Test VFSEntry dataclass"""

    @pytest.mark.unit
    def test_entry_creation_directory(self):
        """Test creating a directory entry"""
        entry = VFSEntry(name="chats", is_directory=True)
        assert entry.name == "chats"
        assert entry.is_directory is True
        assert entry.conversation_id is None

    @pytest.mark.unit
    def test_entry_creation_conversation(self):
        """Test creating a conversation entry with full metadata"""
        now = datetime.now()
        entry = VFSEntry(
            name="conv_001",
            is_directory=True,
            conversation_id="conv_001",
            title="Test Chat",
            created_at=now,
            updated_at=now,
            tags=["test", "unit"],
            starred=True,
            pinned=False,
            archived=False,
            source="openai",
            model="gpt-4",
        )
        assert entry.conversation_id == "conv_001"
        assert entry.title == "Test Chat"
        assert entry.starred is True
        assert entry.source == "openai"

    @pytest.mark.unit
    def test_entry_creation_message_node(self):
        """Test creating a message node entry"""
        entry = VFSEntry(
            name="m1",
            is_directory=True,
            conversation_id="conv_001",
            message_id="msg_001",
            role="user",
            content_preview="Hello world...",
            has_children=True,
        )
        assert entry.message_id == "msg_001"
        assert entry.role == "user"
        assert entry.content_preview == "Hello world..."
        assert entry.has_children is True

    @pytest.mark.unit
    def test_entry_creation_metadata_file(self):
        """Test creating a metadata file entry"""
        entry = VFSEntry(
            name="text",
            is_directory=False,
            conversation_id="conv_001",
            message_id="msg_001",
        )
        assert entry.is_directory is False
        assert entry.name == "text"


class TestVFSNavigatorInitialization:
    """Test VFSNavigator initialization and basic functionality"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.mark.unit
    def test_init(self, mock_db):
        """Test navigator initialization"""
        nav = VFSNavigator(mock_db)
        assert nav.db is mock_db
        assert nav._cache == {}

    @pytest.mark.unit
    def test_cache_ttl_constants(self):
        """Test adaptive cache TTL constants are set correctly"""
        assert VFSNavigator.MIN_CACHE_TTL == 5.0
        assert VFSNavigator.MAX_CACHE_TTL == 60.0

    @pytest.mark.unit
    def test_adaptive_ttl_calculation(self, mock_db):
        """Test adaptive TTL increases with hit count"""
        nav = VFSNavigator(mock_db)

        # TTL should increase with hit count
        ttl_0 = nav._get_adaptive_ttl(0)
        ttl_1 = nav._get_adaptive_ttl(1)
        ttl_2 = nav._get_adaptive_ttl(2)
        ttl_5 = nav._get_adaptive_ttl(5)
        ttl_10 = nav._get_adaptive_ttl(10)  # Should be capped

        assert ttl_0 == 5.0  # MIN_CACHE_TTL
        assert ttl_1 > ttl_0
        assert ttl_2 > ttl_1
        assert ttl_5 > ttl_2
        # TTL should be capped after hit count 5
        assert ttl_5 == ttl_10
        # Should never exceed MAX_CACHE_TTL
        assert ttl_10 <= VFSNavigator.MAX_CACHE_TTL

    @pytest.mark.unit
    def test_selective_cache_invalidation(self, mock_db):
        """Test invalidate_conversation removes only relevant cache entries"""
        nav = VFSNavigator(mock_db)

        # Add cache entries for different conversations
        from time import time

        now = time()
        nav._cache["/chats/conv_abc123"] = (now, [], 1)
        nav._cache["/chats/conv_abc123::msg::m1"] = (now, [], 1)
        nav._cache["/chats/conv_def456"] = (now, [], 1)
        nav._cache["/starred"] = (now, [], 1)

        # Invalidate conv_abc123
        count = nav.invalidate_conversation("conv_abc123")

        # Should have removed 2 entries (both containing conv_abc123)
        assert count == 2
        assert "/chats/conv_abc123" not in nav._cache
        assert "/chats/conv_abc123::msg::m1" not in nav._cache
        # Other entries should remain
        assert "/chats/conv_def456" in nav._cache
        assert "/starred" in nav._cache

    @pytest.mark.unit
    def test_clear_cache(self, mock_db):
        """Test cache clearing"""
        nav = VFSNavigator(mock_db)
        # Add some fake cache data with new (timestamp, entries, hit_count) structure
        nav._cache["test_key"] = (time(), [], 1)
        assert len(nav._cache) > 0

        nav.clear_cache()
        assert len(nav._cache) == 0

    @pytest.mark.unit
    def test_get_cache_key_simple_path(self, mock_db):
        """Test cache key generation for simple paths"""
        nav = VFSNavigator(mock_db)
        vfs_path = Mock(spec=VFSPath)
        vfs_path.normalized_path = "/chats"
        vfs_path.message_path = None

        key = nav._get_cache_key(vfs_path)
        assert key == "/chats"

    @pytest.mark.unit
    def test_get_cache_key_with_message_path(self, mock_db):
        """Test cache key generation includes message path"""
        nav = VFSNavigator(mock_db)
        vfs_path = Mock(spec=VFSPath)
        vfs_path.normalized_path = "/chats/conv_001"
        vfs_path.message_path = ["m1", "m2"]

        key = nav._get_cache_key(vfs_path)
        assert "::msg::m1/m2" in key
        assert "/chats/conv_001" in key


class TestVFSNavigatorPrefixResolution:
    """Test conversation ID prefix resolution"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def navigator(self, mock_db):
        """Create navigator instance"""
        return VFSNavigator(mock_db)

    @pytest.mark.unit
    def test_resolve_prefix_unique_match(self, navigator, mock_db):
        """Test resolving a unique prefix match (slow path)"""
        # Mock list_directory to return test conversations
        mock_entries = [
            VFSEntry(
                name="conv_abc123", is_directory=True, conversation_id="conv_abc123"
            ),
            VFSEntry(
                name="conv_def456", is_directory=True, conversation_id="conv_def456"
            ),
        ]

        vfs_path = Mock(spec=VFSPath)
        vfs_path.normalized_path = "/starred"
        vfs_path.path_type = PathType.STARRED  # Use slow path (non-CHATS)

        with patch.object(navigator, "list_directory", return_value=mock_entries):
            result = navigator.resolve_prefix("conv_abc", vfs_path)
            assert result == "conv_abc123"

    @pytest.mark.unit
    def test_resolve_prefix_no_match(self, navigator):
        """Test resolving prefix with no matches raises ValueError"""
        mock_entries = [
            VFSEntry(
                name="conv_abc123", is_directory=True, conversation_id="conv_abc123"
            ),
        ]

        vfs_path = Mock(spec=VFSPath)
        vfs_path.path_type = PathType.STARRED  # Use slow path (non-CHATS)

        with patch.object(navigator, "list_directory", return_value=mock_entries):
            with pytest.raises(ValueError, match="No conversation found matching"):
                navigator.resolve_prefix("xyz", vfs_path)

    @pytest.mark.unit
    def test_resolve_prefix_multiple_matches(self, navigator):
        """Test resolving ambiguous prefix raises ValueError"""
        mock_entries = [
            VFSEntry(
                name="conv_abc123", is_directory=True, conversation_id="conv_abc123"
            ),
            VFSEntry(
                name="conv_abc456", is_directory=True, conversation_id="conv_abc456"
            ),
            VFSEntry(
                name="conv_abc789", is_directory=True, conversation_id="conv_abc789"
            ),
        ]

        vfs_path = Mock(spec=VFSPath)
        vfs_path.path_type = PathType.STARRED  # Use slow path (non-CHATS)

        with patch.object(navigator, "list_directory", return_value=mock_entries):
            with pytest.raises(ValueError, match="matches 3 conversations"):
                navigator.resolve_prefix("conv_abc", vfs_path)

    @pytest.mark.unit
    def test_resolve_prefix_shows_match_list(self, navigator):
        """Test error message shows list of matching conversations"""
        mock_entries = [
            VFSEntry(name=f"conv_{i}", is_directory=True, conversation_id=f"conv_{i}")
            for i in range(10)
        ]

        vfs_path = Mock(spec=VFSPath)
        vfs_path.path_type = PathType.STARRED  # Use slow path (non-CHATS)

        with patch.object(navigator, "list_directory", return_value=mock_entries):
            with pytest.raises(ValueError) as exc_info:
                navigator.resolve_prefix("conv_", vfs_path)

            error_msg = str(exc_info.value)
            assert "conv_0" in error_msg
            assert "and 5 more" in error_msg  # Shows only first 5

    @pytest.mark.unit
    def test_resolve_prefix_handles_list_error(self, navigator):
        """Test prefix resolution returns None on list error (slow path)"""
        vfs_path = Mock(spec=VFSPath)
        vfs_path.path_type = PathType.STARRED  # Use slow path (non-CHATS)

        with patch.object(
            navigator, "list_directory", side_effect=Exception("DB error")
        ):
            result = navigator.resolve_prefix("conv", vfs_path)
            assert result is None

    @pytest.mark.unit
    def test_resolve_prefix_filters_none_ids(self, navigator):
        """Test prefix resolution ignores entries without conversation_id"""
        mock_entries = [
            VFSEntry(name="chats", is_directory=True, conversation_id=None),
            VFSEntry(
                name="conv_abc123", is_directory=True, conversation_id="conv_abc123"
            ),
        ]

        vfs_path = Mock(spec=VFSPath)
        vfs_path.path_type = PathType.STARRED  # Use slow path (non-CHATS)

        with patch.object(navigator, "list_directory", return_value=mock_entries):
            result = navigator.resolve_prefix("conv_abc", vfs_path)
            assert result == "conv_abc123"


class TestVFSNavigatorListDirectory:
    """Test list_directory method and caching"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def navigator(self, mock_db):
        """Create navigator instance"""
        return VFSNavigator(mock_db)

    @pytest.mark.unit
    def test_list_directory_not_directory_raises(self, navigator):
        """Test listing a non-directory path raises ValueError"""
        vfs_path = Mock(spec=VFSPath)
        vfs_path.is_directory = False
        vfs_path.normalized_path = "/chats/conv_001/text"

        with pytest.raises(ValueError, match="Not a directory"):
            navigator.list_directory(vfs_path)

    @pytest.mark.unit
    def test_list_directory_uses_cache(self, navigator):
        """Test that list_directory uses cached data when available"""
        vfs_path = Mock(spec=VFSPath)
        vfs_path.is_directory = True
        vfs_path.normalized_path = "/chats"
        vfs_path.message_path = None
        vfs_path.path_type = PathType.CHATS

        # Pre-populate cache with fresh data (timestamp, entries, hit_count)
        cache_key = navigator._get_cache_key(vfs_path)
        cached_entries = [VFSEntry(name="cached", is_directory=True)]
        navigator._cache[cache_key] = (time(), cached_entries, 1)

        # Mock the _list_chats method to ensure it's NOT called
        with patch.object(
            navigator, "_list_chats", side_effect=AssertionError("Should use cache")
        ):
            result = navigator.list_directory(vfs_path)
            assert result == cached_entries

    @pytest.mark.unit
    def test_list_directory_cache_expired(self, navigator, mock_db):
        """Test that expired cache is refreshed"""
        vfs_path = Mock(spec=VFSPath)
        vfs_path.is_directory = True
        vfs_path.normalized_path = "/chats"
        vfs_path.message_path = None
        vfs_path.path_type = PathType.CHATS

        # Pre-populate cache with old data (timestamp, entries, hit_count)
        cache_key = navigator._get_cache_key(vfs_path)
        old_entries = [VFSEntry(name="old", is_directory=True)]
        navigator._cache[cache_key] = (time() - 10, old_entries, 1)  # 10 seconds ago

        # Mock database to return new data
        mock_db.list_conversations.return_value = []

        result = navigator.list_directory(vfs_path)
        # Should fetch fresh data, not use old cache
        assert result != old_entries

    @pytest.mark.unit
    def test_list_directory_routes_to_root(self, navigator):
        """Test routing to _list_root for ROOT path type"""
        vfs_path = Mock(spec=VFSPath)
        vfs_path.is_directory = True
        vfs_path.normalized_path = "/"
        vfs_path.message_path = None
        vfs_path.path_type = PathType.ROOT

        with patch.object(navigator, "_list_root") as mock_list_root:
            mock_list_root.return_value = []
            navigator.list_directory(vfs_path)
            mock_list_root.assert_called_once()

    @pytest.mark.unit
    def test_list_directory_routes_to_chats(self, navigator):
        """Test routing to _list_chats for CHATS path type"""
        vfs_path = Mock(spec=VFSPath)
        vfs_path.is_directory = True
        vfs_path.normalized_path = "/chats"
        vfs_path.path_type = PathType.CHATS
        vfs_path.message_path = None

        with patch.object(navigator, "_list_chats") as mock_method:
            mock_method.return_value = []
            navigator.list_directory(vfs_path)
            mock_method.assert_called_once()

    @pytest.mark.unit
    def test_list_directory_invalid_type_raises(self, navigator):
        """Test that unsupported path types raise ValueError"""
        vfs_path = Mock(spec=VFSPath)
        vfs_path.is_directory = True
        vfs_path.normalized_path = "/unknown"
        vfs_path.message_path = None
        vfs_path.path_type = PathType.CONVERSATION  # CONVERSATION is not listable

        with pytest.raises(ValueError, match="Cannot list directory type"):
            navigator.list_directory(vfs_path)


class TestVFSNavigatorRootListing:
    """Test _list_root method"""

    @pytest.fixture
    def navigator(self):
        """Create navigator instance"""
        mock_db = Mock(spec=ConversationDB)
        return VFSNavigator(mock_db)

    @pytest.mark.unit
    def test_list_root(self, navigator):
        """Test listing root directory shows all top-level directories"""
        entries = navigator._list_root()

        assert len(entries) == 8
        names = [e.name for e in entries]
        assert "chats" in names
        assert "tags" in names
        assert "starred" in names
        assert "pinned" in names
        assert "archived" in names
        assert "recent" in names
        assert "source" in names
        assert "model" in names

        # All should be directories
        assert all(e.is_directory for e in entries)


class TestVFSNavigatorChatsListing:
    """Test _list_chats method"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def navigator(self, mock_db):
        """Create navigator instance"""
        return VFSNavigator(mock_db)

    @pytest.fixture
    def sample_conversation_metadata(self):
        """Create sample conversation metadata"""
        return Mock(
            id="conv_001",
            title="Test Chat",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=["test"],
            starred_at=datetime.now(),
            pinned_at=None,
            archived_at=None,
            source="openai",
            model="gpt-4",
        )

    @pytest.mark.unit
    def test_list_chats_empty(self, navigator, mock_db):
        """Test listing chats when database is empty"""
        mock_db.list_conversations.return_value = []

        entries = navigator._list_chats()
        assert entries == []

    @pytest.mark.unit
    def test_list_chats_single_conversation(
        self, navigator, mock_db, sample_conversation_metadata
    ):
        """Test listing chats with single conversation"""
        mock_db.list_conversations.return_value = [sample_conversation_metadata]

        entries = navigator._list_chats()

        assert len(entries) == 1
        entry = entries[0]
        assert entry.name == "conv_001"
        assert entry.is_directory is True
        assert entry.conversation_id == "conv_001"
        assert entry.title == "Test Chat"
        assert entry.starred is True
        assert entry.pinned is False
        assert entry.archived is False
        assert entry.source == "openai"
        assert entry.model == "gpt-4"

    @pytest.mark.unit
    def test_list_chats_multiple_conversations(self, navigator, mock_db):
        """Test listing multiple conversations"""
        mock_convs = [
            Mock(
                id=f"conv_{i}",
                title=f"Chat {i}",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                tags=[],
                starred_at=None,
                pinned_at=None,
                archived_at=None,
                source="test",
                model="test-model",
            )
            for i in range(5)
        ]
        mock_db.list_conversations.return_value = mock_convs

        entries = navigator._list_chats()

        assert len(entries) == 5
        assert all(e.is_directory for e in entries)


class TestVFSNavigatorConversationRootListing:
    """Test _list_conversation_root method"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def navigator(self, mock_db):
        """Create navigator instance"""
        return VFSNavigator(mock_db)

    @pytest.fixture
    def linear_conversation(self):
        """Create a linear conversation for testing"""
        conv = ConversationTree(
            id="conv_001",
            title="Linear Chat",
            metadata=ConversationMetadata(source="test"),
        )

        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
            parent_id=None,
        )
        conv.add_message(msg1)

        msg2 = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Hi there!"),
            parent_id="msg_001",
        )
        conv.add_message(msg2)

        return conv

    @pytest.mark.unit
    def test_list_conversation_root_not_found(self, navigator, mock_db):
        """Test listing conversation that doesn't exist"""
        mock_db.load_conversation.return_value = None

        with pytest.raises(ValueError, match="Conversation not found"):
            navigator._list_conversation_root("nonexistent")

    @pytest.mark.unit
    def test_list_conversation_root_single_root(
        self, navigator, mock_db, linear_conversation
    ):
        """Test listing conversation with single root message"""
        mock_db.load_conversation.return_value = linear_conversation

        entries = navigator._list_conversation_root("conv_001")

        assert len(entries) == 1
        entry = entries[0]
        assert entry.name == "m1"
        assert entry.is_directory is True
        assert entry.message_id == "msg_001"
        assert entry.role == "user"
        assert "Hello" in entry.content_preview
        assert entry.has_children is True

    @pytest.mark.unit
    def test_list_conversation_root_multiple_roots(self, navigator, mock_db):
        """Test listing conversation with multiple root messages"""
        conv = ConversationTree(id="conv_multi", title="Multi Root")

        for i in range(3):
            msg = Message(
                id=f"msg_{i:03d}",
                role=MessageRole.USER,
                content=MessageContent(text=f"Message {i}"),
                parent_id=None,
            )
            conv.add_message(msg)

        mock_db.load_conversation.return_value = conv

        entries = navigator._list_conversation_root("conv_multi")

        assert len(entries) == 3
        assert [e.name for e in entries] == ["m1", "m2", "m3"]

    @pytest.mark.unit
    def test_list_conversation_root_truncates_long_content(self, navigator, mock_db):
        """Test that content preview is truncated at 50 chars"""
        conv = ConversationTree(id="conv_long", title="Long Content")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="A" * 100),
            parent_id=None,
        )
        conv.add_message(msg)

        mock_db.load_conversation.return_value = conv

        entries = navigator._list_conversation_root("conv_long")

        assert len(entries) == 1
        assert len(entries[0].content_preview) == 53  # 50 + "..."
        assert entries[0].content_preview.endswith("...")

    @pytest.mark.unit
    def test_list_conversation_root_leaf_node_no_children(self, navigator, mock_db):
        """Test leaf message has has_children=False"""
        conv = ConversationTree(id="conv_leaf", title="Leaf Test")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Leaf message"),
            parent_id=None,
        )
        conv.add_message(msg)

        mock_db.load_conversation.return_value = conv

        entries = navigator._list_conversation_root("conv_leaf")

        assert entries[0].has_children is False


class TestVFSNavigatorMessageNodeListing:
    """Test _list_message_node method"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def navigator(self, mock_db):
        """Create navigator instance"""
        return VFSNavigator(mock_db)

    @pytest.fixture
    def branching_conversation(self):
        """Create a conversation with branches"""
        conv = ConversationTree(id="conv_branch", title="Branching")

        # Root message
        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Root message"),
            parent_id=None,
        )
        conv.add_message(msg1)

        # Two child messages (branch point)
        msg2a = Message(
            id="msg_002a",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="First response"),
            parent_id="msg_001",
        )
        conv.add_message(msg2a)

        msg2b = Message(
            id="msg_002b",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Second response"),
            parent_id="msg_001",
        )
        conv.add_message(msg2b)

        # Continue from first branch
        msg3 = Message(
            id="msg_003",
            role=MessageRole.USER,
            content=MessageContent(text="Follow-up"),
            parent_id="msg_002a",
        )
        conv.add_message(msg3)

        return conv

    @pytest.mark.unit
    def test_list_message_node_not_found(self, navigator, mock_db):
        """Test listing message node when conversation not found"""
        mock_db.load_conversation.return_value = None

        with pytest.raises(ValueError, match="Conversation not found"):
            navigator._list_message_node("nonexistent", ["m1"])

    @pytest.mark.unit
    def test_list_message_node_invalid_node_name(self, navigator, mock_db):
        """Test invalid message node name raises ValueError"""
        conv = ConversationTree(id="conv_001", title="Test")
        mock_db.load_conversation.return_value = conv

        with pytest.raises(ValueError, match="Invalid message node"):
            navigator._list_message_node("conv_001", ["invalid"])

    @pytest.mark.unit
    def test_list_message_node_invalid_node_index(self, navigator, mock_db):
        """Test non-numeric message node index raises ValueError"""
        conv = ConversationTree(id="conv_001", title="Test")
        mock_db.load_conversation.return_value = conv

        with pytest.raises(ValueError, match="Invalid message node"):
            navigator._list_message_node("conv_001", ["mXYZ"])

    @pytest.mark.unit
    def test_list_message_node_out_of_range(self, navigator, mock_db):
        """Test message node index out of range raises ValueError"""
        conv = ConversationTree(id="conv_001", title="Test")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Test"),
            parent_id=None,
        )
        conv.add_message(msg)

        mock_db.load_conversation.return_value = conv

        with pytest.raises(ValueError, match="out of range"):
            navigator._list_message_node("conv_001", ["m5"])  # Only m1 exists

    @pytest.mark.unit
    def test_list_message_node_shows_metadata_files(self, navigator, mock_db):
        """Test message node shows metadata files"""
        conv = ConversationTree(id="conv_001", title="Test")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Test"),
            parent_id=None,
        )
        conv.add_message(msg)

        mock_db.load_conversation.return_value = conv

        entries = navigator._list_message_node("conv_001", ["m1"])

        # Should show metadata files
        file_names = [e.name for e in entries if not e.is_directory]
        assert "text" in file_names
        assert "role" in file_names
        assert "timestamp" in file_names
        assert "id" in file_names

    @pytest.mark.unit
    def test_list_message_node_shows_children(
        self, navigator, mock_db, branching_conversation
    ):
        """Test message node shows child messages"""
        mock_db.load_conversation.return_value = branching_conversation

        entries = navigator._list_message_node("conv_branch", ["m1"])

        # Should show 2 children (m1 and m2) plus metadata files
        child_dirs = [e for e in entries if e.is_directory]
        assert len(child_dirs) == 2
        assert child_dirs[0].name == "m1"
        assert child_dirs[1].name == "m2"

    @pytest.mark.unit
    def test_list_message_node_nested_navigation(
        self, navigator, mock_db, branching_conversation
    ):
        """Test navigating to nested message node"""
        mock_db.load_conversation.return_value = branching_conversation

        # Navigate to m1/m1 (first child of first root)
        entries = navigator._list_message_node("conv_branch", ["m1", "m1"])

        # Should show metadata files and any children
        assert any(e.name == "text" for e in entries)
        # This node has a child
        child_dirs = [e for e in entries if e.is_directory]
        assert len(child_dirs) == 1

    @pytest.mark.unit
    def test_list_message_node_content_preview(self, navigator, mock_db):
        """Test message node shows content preview for children"""
        conv = ConversationTree(id="conv_001", title="Test")
        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Parent"),
            parent_id=None,
        )
        conv.add_message(msg1)

        msg2 = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Child message content"),
            parent_id="msg_001",
        )
        conv.add_message(msg2)

        mock_db.load_conversation.return_value = conv

        entries = navigator._list_message_node("conv_001", ["m1"])

        child_entries = [e for e in entries if e.is_directory]
        assert len(child_entries) == 1
        assert "Child message content" in child_entries[0].content_preview


class TestVFSNavigatorFilteredListings:
    """Test starred, pinned, archived listings"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def navigator(self, mock_db):
        """Create navigator instance"""
        return VFSNavigator(mock_db)

    @pytest.mark.unit
    def test_list_starred(self, navigator, mock_db):
        """Test listing starred conversations"""
        mock_conv = Mock(
            id="conv_001",
            title="Starred",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=[],
            starred_at=datetime.now(),
            pinned_at=None,
            archived_at=None,
            source="test",
            model="test",
        )
        mock_db.list_conversations.return_value = [mock_conv]

        entries = navigator._list_starred()

        assert len(entries) == 1
        assert entries[0].starred is True
        mock_db.list_conversations.assert_called_once_with(starred=True)

    @pytest.mark.unit
    def test_list_pinned(self, navigator, mock_db):
        """Test listing pinned conversations"""
        mock_conv = Mock(
            id="conv_001",
            title="Pinned",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=[],
            starred_at=None,
            pinned_at=datetime.now(),
            archived_at=None,
            source="test",
            model="test",
        )
        mock_db.list_conversations.return_value = [mock_conv]

        entries = navigator._list_pinned()

        assert len(entries) == 1
        assert entries[0].pinned is True
        mock_db.list_conversations.assert_called_once_with(pinned=True)

    @pytest.mark.unit
    def test_list_archived(self, navigator, mock_db):
        """Test listing archived conversations"""
        mock_conv = Mock(
            id="conv_001",
            title="Archived",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=[],
            starred_at=None,
            pinned_at=None,
            archived_at=datetime.now(),
            source="test",
            model="test",
        )
        mock_db.list_conversations.return_value = [mock_conv]

        entries = navigator._list_archived()

        assert len(entries) == 1
        assert entries[0].archived is True
        mock_db.list_conversations.assert_called_once_with(archived=True)


class TestVFSNavigatorTagsListing:
    """Test tags directory listings"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def navigator(self, mock_db):
        """Create navigator instance"""
        return VFSNavigator(mock_db)

    @pytest.mark.unit
    def test_list_tags_root(self, navigator, mock_db):
        """Test listing root-level tags"""
        mock_db.list_tag_children.return_value = ["python", "javascript", "testing"]

        entries = navigator._list_tags_root()

        assert len(entries) == 3
        assert all(e.is_directory for e in entries)
        assert [e.name for e in entries] == ["python", "javascript", "testing"]
        mock_db.list_tag_children.assert_called_once_with(parent_tag=None)

    @pytest.mark.unit
    def test_list_tag_directory_with_children(self, navigator, mock_db):
        """Test listing tag directory with child tags"""
        mock_db.list_tag_children.return_value = ["python/web", "python/data"]
        mock_db.list_conversations_by_tag.return_value = []

        entries = navigator._list_tag_directory("python")

        assert len(entries) == 2
        assert all(e.is_directory for e in entries)

    @pytest.mark.unit
    def test_list_tag_directory_with_conversations(self, navigator, mock_db):
        """Test listing tag directory with conversations"""
        mock_db.list_tag_children.return_value = []
        mock_conv = Mock(
            id="conv_001",
            title="Test",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=["testing"],
            starred_at=None,
            pinned_at=None,
            archived_at=None,
            source="test",
            model="test",
        )
        mock_db.list_conversations_by_tag.return_value = [mock_conv]

        entries = navigator._list_tag_directory("testing")

        assert len(entries) == 1
        assert entries[0].conversation_id == "conv_001"

    @pytest.mark.unit
    def test_list_tag_directory_mixed_content(self, navigator, mock_db):
        """Test listing tag directory with both tags and conversations"""
        mock_db.list_tag_children.return_value = ["python/web"]
        mock_conv = Mock(
            id="conv_001",
            title="Test",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=["python"],
            starred_at=None,
            pinned_at=None,
            archived_at=None,
            source="test",
            model="test",
        )
        mock_db.list_conversations_by_tag.return_value = [mock_conv]

        entries = navigator._list_tag_directory("python")

        assert len(entries) == 2
        # One tag directory, one conversation
        dirs = [e for e in entries if e.conversation_id is None]
        convs = [e for e in entries if e.conversation_id is not None]
        assert len(dirs) == 1
        assert len(convs) == 1


class TestVFSNavigatorRecentListing:
    """Test recent directory listings"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def navigator(self, mock_db):
        """Create navigator instance"""
        return VFSNavigator(mock_db)

    @pytest.mark.unit
    def test_list_recent_root_shows_periods(self, navigator):
        """Test /recent shows time period directories"""
        entries = navigator._list_recent(["recent"])

        assert len(entries) == 4
        names = [e.name for e in entries]
        assert "today" in names
        assert "this-week" in names
        assert "this-month" in names
        assert "older" in names

    @pytest.mark.unit
    def test_list_recent_today(self, navigator, mock_db):
        """Test /recent/today shows today's conversations"""
        now = datetime.now()
        today_conv = Mock(
            id="conv_today",
            title="Today",
            created_at=now,
            updated_at=now,
            tags=[],
            starred_at=None,
            pinned_at=None,
            archived_at=None,
            source="test",
            model="test",
        )
        mock_db.search_conversations.return_value = [today_conv]

        entries = navigator._list_recent(["recent", "today"])

        mock_db.search_conversations.assert_called_once()
        call_kwargs = mock_db.search_conversations.call_args[1]
        assert "date_from" in call_kwargs
        assert len(entries) == 1
        assert entries[0].conversation_id == "conv_today"

    @pytest.mark.unit
    def test_list_recent_this_week(self, navigator, mock_db):
        """Test /recent/this-week shows this week's conversations"""
        now = datetime.now()
        this_week_conv = Mock(
            id="conv_week",
            title="This Week",
            created_at=now - timedelta(days=3),
            updated_at=now - timedelta(days=3),
            tags=[],
            starred_at=None,
            pinned_at=None,
            archived_at=None,
            source="test",
            model="test",
        )
        mock_db.search_conversations.return_value = [this_week_conv]

        entries = navigator._list_recent(["recent", "this-week"])

        mock_db.search_conversations.assert_called_once()
        call_kwargs = mock_db.search_conversations.call_args[1]
        assert "date_from" in call_kwargs
        assert "date_to" in call_kwargs
        assert len(entries) == 1

    @pytest.mark.unit
    def test_list_recent_this_month(self, navigator, mock_db):
        """Test /recent/this-month shows this month's conversations"""
        now = datetime.now()
        this_month_conv = Mock(
            id="conv_month",
            title="This Month",
            created_at=now - timedelta(days=15),
            updated_at=now - timedelta(days=15),
            tags=[],
            starred_at=None,
            pinned_at=None,
            archived_at=None,
            source="test",
            model="test",
        )
        mock_db.search_conversations.return_value = [this_month_conv]

        entries = navigator._list_recent(["recent", "this-month"])

        mock_db.search_conversations.assert_called_once()
        call_kwargs = mock_db.search_conversations.call_args[1]
        assert "date_from" in call_kwargs
        assert "date_to" in call_kwargs
        assert len(entries) == 1

    @pytest.mark.unit
    def test_list_recent_older(self, navigator, mock_db):
        """Test /recent/older shows old conversations"""
        now = datetime.now()
        old_conv = Mock(
            id="conv_old",
            title="Old",
            created_at=now - timedelta(days=60),
            updated_at=now - timedelta(days=60),
            tags=[],
            starred_at=None,
            pinned_at=None,
            archived_at=None,
            source="test",
            model="test",
        )
        mock_db.search_conversations.return_value = [old_conv]

        entries = navigator._list_recent(["recent", "older"])

        mock_db.search_conversations.assert_called_once()
        call_kwargs = mock_db.search_conversations.call_args[1]
        assert "date_to" in call_kwargs
        assert len(entries) == 1
        assert entries[0].conversation_id == "conv_old"

    @pytest.mark.unit
    def test_list_recent_handles_none_dates(self, navigator, mock_db):
        """Test recent listing handles conversations with None dates"""
        # DB-level filtering now handles date filtering, so if the DB
        # returns a conversation with None dates, it gets included
        conv_no_date = Mock(
            id="conv_none",
            title="No Date",
            created_at=None,
            updated_at=None,
            tags=[],
            starred_at=None,
            pinned_at=None,
            archived_at=None,
            source="test",
            model="test",
        )
        mock_db.search_conversations.return_value = [conv_no_date]

        entries = navigator._list_recent(["recent", "today"])

        # DB handles filtering; results from search_conversations are used directly
        mock_db.search_conversations.assert_called_once()
        assert isinstance(entries, list)


class TestVFSNavigatorSourceListing:
    """Test source directory listings"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def navigator(self, mock_db):
        """Create navigator instance"""
        return VFSNavigator(mock_db)

    @pytest.mark.unit
    def test_list_source_root_shows_sources(self, navigator, mock_db):
        """Test /source shows all unique sources"""
        mock_db.get_distinct_sources.return_value = ["anthropic", "openai"]

        entries = navigator._list_source(["source"])

        mock_db.get_distinct_sources.assert_called_once()
        assert len(entries) == 2  # openai and anthropic
        names = [e.name for e in entries]
        assert "openai" in names
        assert "anthropic" in names

    @pytest.mark.unit
    def test_list_source_specific(self, navigator, mock_db):
        """Test /source/<name> shows conversations from that source"""
        mock_conv = Mock(
            id="conv_001",
            title="Test",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=[],
            starred_at=None,
            pinned_at=None,
            archived_at=None,
            source="openai",
            model="gpt-4",
        )
        mock_db.list_conversations.return_value = [mock_conv]

        entries = navigator._list_source(["source", "openai"])

        assert len(entries) == 1
        assert entries[0].source == "openai"
        mock_db.list_conversations.assert_called_once_with(source="openai")

    @pytest.mark.unit
    def test_list_source_root_filters_none(self, navigator, mock_db):
        """Test source listing filters out None sources (handled by DB method)"""
        mock_db.get_distinct_sources.return_value = ["openai"]

        entries = navigator._list_source(["source"])

        assert len(entries) == 1
        assert entries[0].name == "openai"


class TestVFSNavigatorModelListing:
    """Test model directory listings"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def navigator(self, mock_db):
        """Create navigator instance"""
        return VFSNavigator(mock_db)

    @pytest.mark.unit
    def test_list_model_root_shows_models(self, navigator, mock_db):
        """Test /model shows all unique models"""
        mock_db.get_distinct_models.return_value = ["gpt-3.5", "gpt-4"]

        entries = navigator._list_model(["model"])

        mock_db.get_distinct_models.assert_called_once()
        assert len(entries) == 2  # gpt-4 and gpt-3.5
        names = [e.name for e in entries]
        assert "gpt-4" in names
        assert "gpt-3.5" in names

    @pytest.mark.unit
    def test_list_model_specific(self, navigator, mock_db):
        """Test /model/<name> shows conversations using that model"""
        mock_conv = Mock(
            id="conv_001",
            title="Test",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            tags=[],
            starred_at=None,
            pinned_at=None,
            archived_at=None,
            source="openai",
            model="gpt-4",
        )
        mock_db.list_conversations.return_value = [mock_conv]

        entries = navigator._list_model(["model", "gpt-4"])

        assert len(entries) == 1
        assert entries[0].model == "gpt-4"
        mock_db.list_conversations.assert_called_once_with(model="gpt-4")

    @pytest.mark.unit
    def test_list_model_root_filters_none(self, navigator, mock_db):
        """Test model listing filters out None models (handled by DB method)"""
        mock_db.get_distinct_models.return_value = ["gpt-4"]

        entries = navigator._list_model(["model"])

        assert len(entries) == 1
        assert entries[0].name == "gpt-4"

    @pytest.mark.unit
    def test_list_model_root_sorted(self, navigator, mock_db):
        """Test model listing is sorted alphabetically"""
        mock_db.get_distinct_models.return_value = ["alpha", "beta", "zeta"]

        entries = navigator._list_model(["model"])

        names = [e.name for e in entries]
        assert names == ["alpha", "beta", "zeta"]


class TestVFSNavigatorViewsListing:
    """Test views directory listings"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def mock_view_store(self):
        """Create mock view store"""
        from ctk.core.views import ViewStore

        return Mock(spec=ViewStore)

    @pytest.fixture
    def navigator_with_views(self, mock_db, mock_view_store):
        """Create navigator with view store"""
        nav = VFSNavigator(mock_db)
        nav._view_store = mock_view_store
        return nav

    @pytest.mark.unit
    def test_list_root_includes_views_when_store_available(
        self, mock_db, mock_view_store
    ):
        """Test root listing includes views when view store is available"""
        nav = VFSNavigator(mock_db)
        nav._view_store = mock_view_store

        entries = nav._list_root()

        names = [e.name for e in entries]
        assert "views" in names
        assert "chats" in names

    @pytest.mark.unit
    def test_list_root_excludes_views_when_no_store(self, mock_db):
        """Test root listing excludes views when no view store"""
        nav = VFSNavigator(mock_db)
        # Don't set view store

        entries = nav._list_root()

        names = [e.name for e in entries]
        assert "views" not in names
        assert "chats" in names

    @pytest.mark.unit
    def test_list_views_shows_all_views(self, navigator_with_views, mock_view_store):
        """Test /views shows all available views"""
        from ctk.core.views import View

        mock_view = Mock(spec=View)
        mock_view.title = "Test View"
        mock_view.created_at = datetime.now()
        mock_view.updated_at = datetime.now()

        mock_view_store.list_views.return_value = ["test-view", "another-view"]
        mock_view_store.load.return_value = mock_view

        entries = navigator_with_views._list_views()

        assert len(entries) == 2
        names = [e.name for e in entries]
        assert "test-view" in names
        assert "another-view" in names
        assert all(e.is_directory for e in entries)

    @pytest.mark.unit
    def test_list_views_empty_when_no_views(
        self, navigator_with_views, mock_view_store
    ):
        """Test /views returns empty list when no views exist"""
        mock_view_store.list_views.return_value = []

        entries = navigator_with_views._list_views()

        assert len(entries) == 0

    @pytest.mark.unit
    def test_list_views_returns_empty_when_no_store(self, mock_db):
        """Test _list_views returns empty when no view store"""
        nav = VFSNavigator(mock_db)
        # Don't set view store

        entries = nav._list_views()

        assert len(entries) == 0

    @pytest.mark.unit
    def test_list_view_contents_shows_conversations(
        self, navigator_with_views, mock_view_store, mock_db
    ):
        """Test /views/<name> shows conversations in the view"""
        from ctk.core.views import EvaluatedView, EvaluatedViewItem

        # Setup evaluated view with items
        mock_item = Mock(spec=EvaluatedViewItem)
        mock_item.conversation_id = "conv_001"
        mock_item.title_override = None

        mock_evaluated = Mock(spec=EvaluatedView)
        mock_evaluated.items = [mock_item]

        mock_view_store.evaluate.return_value = mock_evaluated

        # Setup conversation in database
        mock_conv = Mock()
        mock_conv.title = "Test Conversation"
        mock_conv.created_at = datetime.now()
        mock_conv.updated_at = datetime.now()
        mock_conv.tags = []
        mock_conv.starred_at = None
        mock_conv.pinned_at = None
        mock_conv.archived_at = None
        mock_conv.source = "openai"
        mock_conv.model = "gpt-4"

        mock_db.load_conversation.return_value = mock_conv

        entries = navigator_with_views._list_view_contents("test-view")

        assert len(entries) == 1
        assert entries[0].conversation_id == "conv_001"
        assert entries[0].title == "Test Conversation"
        assert entries[0].is_directory is True
        mock_view_store.evaluate.assert_called_once_with("test-view", mock_db)

    @pytest.mark.unit
    def test_list_view_contents_uses_title_override(
        self, navigator_with_views, mock_view_store, mock_db
    ):
        """Test view contents use title override when available"""
        from ctk.core.views import EvaluatedView, EvaluatedViewItem

        mock_item = Mock(spec=EvaluatedViewItem)
        mock_item.conversation_id = "conv_001"
        mock_item.title_override = "Custom Title"

        mock_evaluated = Mock(spec=EvaluatedView)
        mock_evaluated.items = [mock_item]

        mock_view_store.evaluate.return_value = mock_evaluated

        mock_conv = Mock()
        mock_conv.title = "Original Title"
        mock_conv.created_at = datetime.now()
        mock_conv.updated_at = datetime.now()
        mock_conv.tags = []
        mock_conv.starred_at = None
        mock_conv.pinned_at = None
        mock_conv.archived_at = None
        mock_conv.source = "openai"
        mock_conv.model = "gpt-4"

        mock_db.load_conversation.return_value = mock_conv

        entries = navigator_with_views._list_view_contents("test-view")

        assert entries[0].title == "Custom Title"

    @pytest.mark.unit
    def test_list_view_contents_skips_missing_conversations(
        self, navigator_with_views, mock_view_store, mock_db
    ):
        """Test view contents silently skip conversations that no longer exist"""
        from ctk.core.views import EvaluatedView, EvaluatedViewItem

        mock_item = Mock(spec=EvaluatedViewItem)
        mock_item.conversation_id = "nonexistent"
        mock_item.title_override = None

        mock_evaluated = Mock(spec=EvaluatedView)
        mock_evaluated.items = [mock_item]

        mock_view_store.evaluate.return_value = mock_evaluated
        mock_db.load_conversation.return_value = None  # Conversation not found

        entries = navigator_with_views._list_view_contents("test-view")

        assert len(entries) == 0

    @pytest.mark.unit
    def test_list_view_contents_raises_when_view_not_found(
        self, navigator_with_views, mock_view_store, mock_db
    ):
        """Test view contents raises error when view not found"""
        mock_view_store.evaluate.return_value = None

        with pytest.raises(ValueError, match="View not found"):
            navigator_with_views._list_view_contents("nonexistent")

    @pytest.mark.unit
    def test_list_view_contents_raises_when_no_store(self, mock_db):
        """Test view contents raises error when no view store"""
        nav = VFSNavigator(mock_db)
        # Don't set view store

        with pytest.raises(ValueError, match="View store not available"):
            nav._list_view_contents("test-view")
