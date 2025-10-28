"""
Unit tests for message node path parsing in VFS.

Tests that the unified path parser correctly handles message nodes
in conversation trees.
"""

import pytest
from ctk.core.vfs import VFSPathParser, VFSPath, PathType


class TestMessageNodePaths:
    """Test message node path parsing"""

    def test_is_message_node(self):
        """Test message node pattern matching"""
        # Valid message nodes
        assert VFSPathParser.is_message_node("m1")
        assert VFSPathParser.is_message_node("m2")
        assert VFSPathParser.is_message_node("m100")
        assert VFSPathParser.is_message_node("m999")
        assert VFSPathParser.is_message_node("M1")  # Case insensitive
        assert VFSPathParser.is_message_node("M100")

        # Invalid message nodes
        assert not VFSPathParser.is_message_node("m")  # No number
        assert not VFSPathParser.is_message_node("m0a")  # Not just digits
        assert not VFSPathParser.is_message_node("message1")  # Too long
        assert not VFSPathParser.is_message_node("1m")  # Wrong order
        assert not VFSPathParser.is_message_node("abc123")  # Not a message node

    def test_conversation_root_with_trailing_slash(self):
        """Test /chats/abc123/ is CONVERSATION_ROOT"""
        path = VFSPathParser.parse("/chats/abc123/")

        assert path.path_type == PathType.CONVERSATION_ROOT
        assert path.conversation_id == "abc123"
        assert path.is_directory is True
        assert path.message_path is None
        assert len(path.segments) == 2

    def test_conversation_reference_without_trailing_slash(self):
        """Test /chats/abc123 is CONVERSATION (reference)"""
        path = VFSPathParser.parse("/chats/abc123")

        assert path.path_type == PathType.CONVERSATION
        assert path.conversation_id == "abc123"
        assert path.is_directory is False
        assert path.message_path is None

    def test_single_message_node(self):
        """Test /chats/abc123/m5/"""
        path = VFSPathParser.parse("/chats/abc123/m5")

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.conversation_id == "abc123"
        assert path.message_path == ["m5"]
        assert path.is_directory is True
        assert len(path.segments) == 3

    def test_nested_message_nodes(self):
        """Test /chats/abc123/m1/m2/m5/"""
        path = VFSPathParser.parse("/chats/abc123/m1/m2/m5")

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.conversation_id == "abc123"
        assert path.message_path == ["m1", "m2", "m5"]
        assert path.is_directory is True
        assert len(path.segments) == 5

    def test_deeply_nested_message_nodes(self):
        """Test very deep nesting /chats/abc123/m1/m2/m3/m4/m5/m6/"""
        path = VFSPathParser.parse("/chats/abc123/m1/m2/m3/m4/m5/m6")

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.conversation_id == "abc123"
        assert path.message_path == ["m1", "m2", "m3", "m4", "m5", "m6"]
        assert len(path.segments) == 8

    def test_invalid_message_node_name(self):
        """Test that invalid message node names raise error"""
        with pytest.raises(ValueError, match="Invalid message node"):
            VFSPathParser.parse("/chats/abc123/invalid")

        with pytest.raises(ValueError, match="Invalid message node"):
            VFSPathParser.parse("/chats/abc123/m5/not_a_message")

    def test_message_nodes_in_tagged_conversation(self):
        """Test /tags/physics/abc123/m5/"""
        path = VFSPathParser.parse("/tags/physics/abc123/m5")

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.conversation_id == "abc123"
        assert path.tag_path == "physics"
        assert path.message_path == ["m5"]
        assert path.is_directory is True

    def test_nested_message_nodes_in_tagged_conversation(self):
        """Test /tags/physics/simulator/abc123/m1/m2/"""
        path = VFSPathParser.parse("/tags/physics/simulator/abc123/m1/m2")

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.conversation_id == "abc123"
        assert path.tag_path == "physics/simulator"
        assert path.message_path == ["m1", "m2"]

    def test_relative_path_to_message_node(self):
        """Test relative paths to message nodes"""
        # From conversation root to message node
        path = VFSPathParser.parse("m5", current_dir="/chats/abc123/")

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.conversation_id == "abc123"
        assert path.message_path == ["m5"]

    def test_relative_path_between_message_nodes(self):
        """Test navigating between message nodes with relative paths"""
        # From m1 to m2 (sibling)
        path = VFSPathParser.parse("../m2", current_dir="/chats/abc123/m1/")

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.message_path == ["m2"]

    def test_parent_directory_from_message_node(self):
        """Test .. from message node goes to parent message or conversation"""
        # From /chats/abc123/m1/m2/ go up one level
        path = VFSPathParser.parse("..", current_dir="/chats/abc123/m1/m2/")

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.message_path == ["m1"]

        # From /chats/abc123/m1/ go up to conversation
        # Note: Without trailing slash, this is CONVERSATION (not ROOT)
        # To get CONVERSATION_ROOT, use: VFSPathParser.parse("../", current_dir="/chats/abc123/m1/")
        path = VFSPathParser.parse("..", current_dir="/chats/abc123/m1/")

        assert path.path_type == PathType.CONVERSATION
        assert path.conversation_id == "abc123"
        assert path.message_path is None
        assert path.is_directory is False  # Without trailing slash

    def test_message_node_normalization(self):
        """Test path normalization with message nodes"""
        # Redundant path elements
        path = VFSPathParser.parse("/chats/abc123/./m1/../m2")

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.message_path == ["m2"]
        assert path.normalized_path == "/chats/abc123/m2"

    def test_case_insensitive_message_nodes(self):
        """Test that message nodes are case-insensitive"""
        path1 = VFSPathParser.parse("/chats/abc123/m5")
        path2 = VFSPathParser.parse("/chats/abc123/M5")

        assert path1.message_path == ["m5"]
        assert path2.message_path == ["M5"]
        # Both should be recognized as message nodes
        assert path1.path_type == PathType.MESSAGE_NODE
        assert path2.path_type == PathType.MESSAGE_NODE

    def test_conversation_vs_message_node_disambiguation(self):
        """Test that conversation IDs and message nodes don't conflict"""
        # Conversation ID (looks like hash)
        conv_path = VFSPathParser.parse("/chats/abc123def456")
        assert conv_path.path_type == PathType.CONVERSATION

        # Message node (m + digits)
        msg_path = VFSPathParser.parse("/chats/abc123/m5")
        assert msg_path.path_type == PathType.MESSAGE_NODE

    def test_message_path_string_representation(self):
        """Test that VFSPath string representation is correct"""
        path = VFSPathParser.parse("/chats/abc123/m1/m2/m5")

        assert str(path) == "/chats/abc123/m1/m2/m5"
        assert path.normalized_path == "/chats/abc123/m1/m2/m5"

    def test_empty_message_path_for_non_message_nodes(self):
        """Test that message_path is None for non-message paths"""
        path = VFSPathParser.parse("/chats/abc123")
        assert path.message_path is None

        path = VFSPathParser.parse("/tags/physics")
        assert path.message_path is None

        path = VFSPathParser.parse("/starred/")
        assert path.message_path is None

    def test_large_message_numbers(self):
        """Test message nodes with large numbers"""
        path = VFSPathParser.parse("/chats/abc123/m999999")

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.message_path == ["m999999"]

    def test_mixed_tag_and_message_navigation(self):
        """Test complex path with tags and messages"""
        path = VFSPathParser.parse("/tags/research/ml/transformers/abc123/m1/m5/m10")

        assert path.path_type == PathType.MESSAGE_NODE
        assert path.conversation_id == "abc123"
        assert path.tag_path == "research/ml/transformers"
        assert path.message_path == ["m1", "m5", "m10"]
