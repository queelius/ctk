"""
Unit tests for VFS Navigator message node listing.

Tests that VFSNavigator correctly lists conversation directories
and message nodes.
"""

from datetime import datetime

import pytest

from ctk.core.models import (ConversationTree, Message, MessageContent,
                             MessageRole)
from ctk.core.vfs import PathType, VFSPathParser
from ctk.core.vfs_navigator import VFSEntry, VFSNavigator


class TestVFSNavigatorMessages:
    """Test VFS Navigator message node listing"""

    @pytest.fixture
    def sample_conversation(self):
        """Create a sample conversation tree for testing"""
        conv = ConversationTree(id="test-conv-123", title="Test Conversation")

        # Create messages: m1 -> m2 -> m3
        #                            -> m4 (branch)
        m1 = Message(
            id="msg-1",
            role=MessageRole.USER,
            content=MessageContent(text="First message from user"),
            timestamp=datetime(2025, 1, 1, 10, 0),
        )

        m2 = Message(
            id="msg-2",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Response from assistant"),
            parent_id="msg-1",
            timestamp=datetime(2025, 1, 1, 10, 5),
        )

        m3 = Message(
            id="msg-3",
            role=MessageRole.USER,
            content=MessageContent(text="Another user message on main branch"),
            parent_id="msg-2",
            timestamp=datetime(2025, 1, 1, 10, 10),
        )

        m4 = Message(
            id="msg-4",
            role=MessageRole.USER,
            content=MessageContent(text="Alternative branch message"),
            parent_id="msg-2",
            timestamp=datetime(2025, 1, 1, 10, 15),
        )

        # Add to tree
        conv.add_message(m1)
        conv.add_message(m2)
        conv.add_message(m3)
        conv.add_message(m4)

        return conv

    @pytest.fixture
    def mock_db(self, sample_conversation):
        """Create a mock database with test conversation"""

        class MockDB:
            def __init__(self, conv):
                self.conv = conv

            def get_conversation(self, conv_id):
                if conv_id == "test-conv-123":
                    return self.conv
                return None

            def load_conversation(self, conv_id):
                """Alias for get_conversation - used by VFSNavigator"""
                return self.get_conversation(conv_id)

            def list_conversations(self, **kwargs):
                return []

        return MockDB(sample_conversation)

    def test_list_conversation_root(self, mock_db, sample_conversation):
        """Test listing /chats/test-conv-123/ shows root message nodes"""
        navigator = VFSNavigator(mock_db)
        path = VFSPathParser.parse("/chats/test-conv-123/")

        entries = navigator.list_directory(path)

        # Should have exactly one root message (m1)
        assert len(entries) == 1
        assert entries[0].name == "m1"
        assert entries[0].is_directory is True
        assert entries[0].message_id == "msg-1"
        assert entries[0].role == "user"
        assert "First message" in entries[0].content_preview
        assert entries[0].has_children is True  # m1 has child m2

    def test_list_message_node_with_children(self, mock_db):
        """Test listing /chats/test-conv-123/m1/ shows children"""
        navigator = VFSNavigator(mock_db)
        path = VFSPathParser.parse("/chats/test-conv-123/m1/")

        entries = navigator.list_directory(path)

        # Filter for child directories only (excludes virtual files like text, role, etc.)
        child_dirs = [e for e in entries if e.is_directory]

        # Should have one child (m2)
        assert len(child_dirs) == 1
        assert child_dirs[0].name == "m1"  # First child is labeled m1
        assert child_dirs[0].message_id == "msg-2"
        assert child_dirs[0].role == "assistant"
        assert "Response from assistant" in child_dirs[0].content_preview
        assert child_dirs[0].has_children is True  # m2 has children (m3 and m4)

    def test_list_message_node_with_branches(self, mock_db):
        """Test listing /chats/test-conv-123/m1/m1/ shows branches"""
        navigator = VFSNavigator(mock_db)
        path = VFSPathParser.parse("/chats/test-conv-123/m1/m1/")

        entries = navigator.list_directory(path)

        # Filter for child directories only (excludes virtual files like text, role, etc.)
        child_dirs = [e for e in entries if e.is_directory]

        # Should have two children (m3 and m4 - the branch point)
        assert len(child_dirs) == 2

        # First entry (m1 -> m3)
        assert child_dirs[0].name == "m1"
        assert child_dirs[0].message_id == "msg-3"
        assert child_dirs[0].role == "user"
        assert "main branch" in child_dirs[0].content_preview
        assert child_dirs[0].has_children is False  # m3 is a leaf

        # Second entry (m2 -> m4)
        assert child_dirs[1].name == "m2"
        assert child_dirs[1].message_id == "msg-4"
        assert child_dirs[1].role == "user"
        assert "Alternative branch" in child_dirs[1].content_preview
        assert child_dirs[1].has_children is False  # m4 is a leaf

    def test_list_leaf_message_node(self, mock_db):
        """Test listing a leaf message node shows metadata files but no child dirs"""
        navigator = VFSNavigator(mock_db)
        path = VFSPathParser.parse("/chats/test-conv-123/m1/m1/m1/")

        entries = navigator.list_directory(path)

        # Filter for child directories only
        child_dirs = [e for e in entries if e.is_directory]

        # Leaf nodes have no child directories (but have metadata files)
        assert len(child_dirs) == 0

        # Should have metadata files (text, role, timestamp, id)
        file_entries = [e for e in entries if not e.is_directory]
        assert len(file_entries) == 4

    def test_message_node_content_preview(self, mock_db):
        """Test that content preview is truncated at 50 chars"""
        # Create conversation with long message
        conv = ConversationTree(id="test-long", title="Long Message Test")
        long_msg = Message(
            id="msg-long",
            role=MessageRole.USER,
            content=MessageContent(text="A" * 100),  # 100 chars
            timestamp=datetime.now(),
        )
        conv.add_message(long_msg)

        class MockDBLong:
            def get_conversation(self, conv_id):
                return conv if conv_id == "test-long" else None

            def load_conversation(self, conv_id):
                return self.get_conversation(conv_id)

        navigator = VFSNavigator(MockDBLong())
        path = VFSPathParser.parse("/chats/test-long/")

        entries = navigator.list_directory(path)

        assert len(entries) == 1
        # Should be truncated to 50 chars + "..."
        assert len(entries[0].content_preview) == 53
        assert entries[0].content_preview.endswith("...")

    def test_message_node_indexing(self, mock_db):
        """Test that message nodes are correctly indexed (m1, m2, m3...)"""
        navigator = VFSNavigator(mock_db)

        # At root level, should be m1
        path = VFSPathParser.parse("/chats/test-conv-123/")
        entries = navigator.list_directory(path)
        child_dirs = [e for e in entries if e.is_directory]
        assert child_dirs[0].name == "m1"

        # At m1/m1/ level (m2's children), should be m1, m2
        path = VFSPathParser.parse("/chats/test-conv-123/m1/m1/")
        entries = navigator.list_directory(path)
        child_dirs = [e for e in entries if e.is_directory]
        assert child_dirs[0].name == "m1"
        assert child_dirs[1].name == "m2"

    def test_invalid_conversation_id(self, mock_db):
        """Test error handling for non-existent conversation"""
        navigator = VFSNavigator(mock_db)
        path = VFSPathParser.parse("/chats/nonexistent/")

        with pytest.raises(ValueError, match="Conversation not found"):
            navigator.list_directory(path)

    def test_invalid_message_node_path(self, mock_db):
        """Test error handling for invalid message node path"""
        navigator = VFSNavigator(mock_db)

        # m99 doesn't exist at root level (only m1 exists)
        path = VFSPathParser.parse("/chats/test-conv-123/m99/")

        with pytest.raises(ValueError, match="out of range"):
            navigator.list_directory(path)

    def test_vfs_entry_fields(self, mock_db):
        """Test that VFSEntry has all required message fields"""
        navigator = VFSNavigator(mock_db)
        path = VFSPathParser.parse("/chats/test-conv-123/")

        entries = navigator.list_directory(path)
        entry = entries[0]

        # Check all message-specific fields are set
        assert entry.name == "m1"
        assert entry.is_directory is True
        assert entry.conversation_id == "test-conv-123"
        assert entry.message_id == "msg-1"
        assert entry.role == "user"
        assert entry.content_preview is not None
        assert entry.created_at is not None
        assert entry.has_children is True

    def test_conversation_root_vs_message_node_path(self, mock_db):
        """Test distinction between CONVERSATION_ROOT and MESSAGE_NODE paths"""
        # CONVERSATION_ROOT: /chats/abc123/
        path_root = VFSPathParser.parse("/chats/test-conv-123/")
        assert path_root.path_type == PathType.CONVERSATION_ROOT
        assert path_root.message_path is None

        # MESSAGE_NODE: /chats/abc123/m1/
        path_node = VFSPathParser.parse("/chats/test-conv-123/m1/")
        assert path_node.path_type == PathType.MESSAGE_NODE
        assert path_node.message_path == ["m1"]

    def test_navigation_deep_tree(self, mock_db):
        """Test navigation through deeply nested message nodes"""
        navigator = VFSNavigator(mock_db)

        # Navigate: root -> m1 -> m1 -> m1 (should reach leaf m3)
        path = VFSPathParser.parse("/chats/test-conv-123/m1/m1/m1/")

        # m3 is a leaf, should have no child directories (but has metadata files)
        entries = navigator.list_directory(path)
        child_dirs = [e for e in entries if e.is_directory]
        assert len(child_dirs) == 0

    def test_timestamp_preserved(self, mock_db):
        """Test that message timestamps are preserved in entries"""
        navigator = VFSNavigator(mock_db)
        path = VFSPathParser.parse("/chats/test-conv-123/")

        entries = navigator.list_directory(path)
        entry = entries[0]

        # Check timestamp matches original message
        assert entry.created_at == datetime(2025, 1, 1, 10, 0)

    def test_empty_conversation(self):
        """Test listing an empty conversation (no messages)"""
        conv = ConversationTree(id="empty-conv", title="Empty")

        class MockDBEmpty:
            def get_conversation(self, conv_id):
                return conv if conv_id == "empty-conv" else None

            def load_conversation(self, conv_id):
                return self.get_conversation(conv_id)

        navigator = VFSNavigator(MockDBEmpty())
        path = VFSPathParser.parse("/chats/empty-conv/")

        entries = navigator.list_directory(path)
        assert len(entries) == 0
