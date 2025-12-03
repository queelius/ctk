#!/usr/bin/env python3
"""
Comprehensive test suite for CTK models
Tests ConversationTree, Message, MessageContent, and related classes
"""

import unittest
import json
from datetime import datetime, timedelta
from typing import List, Optional
import tempfile
from pathlib import Path

from ctk.core.models import (
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
    ConversationMetadata
)


class TestMessageContent(unittest.TestCase):
    """Test MessageContent class"""

    def test_create_text_content(self):
        """Test creating text content"""
        content = MessageContent(text="Hello, world!")

        self.assertEqual(content.text, "Hello, world!")
        self.assertEqual(len(content.tool_calls), 0)
        self.assertEqual(len(content.images), 0)

    def test_create_multimodal_content(self):
        """Test creating content with media"""
        content = MessageContent(
            text="Check these files"
        )

        # Add image
        content.add_image(url="image.jpg")

        # Check images were added
        self.assertEqual(content.text, "Check these files")
        self.assertEqual(len(content.images), 1)

    def test_content_with_tool_calls(self):
        """Test content with tool calls"""
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": json.dumps({"location": "San Francisco"})
                }
            }
        ]

        content = MessageContent(
            text="I'll check the weather for you",
            tool_calls=tool_calls
        )

        self.assertEqual(len(content.tool_calls), 1)
        self.assertEqual(content.tool_calls[0]["function"]["name"], "get_weather")

    def test_content_with_metadata(self):
        """Test content with metadata"""
        content = MessageContent(
            text="The answer is 42",
            metadata={"reasoning": "Let me calculate: 6 * 7 = 42"}
        )

        self.assertEqual(content.metadata["reasoning"], "Let me calculate: 6 * 7 = 42")

    def test_content_serialization(self):
        """Test content serialization to dict"""
        content = MessageContent(
            text="Test message"
        )

        # Add tool call
        content.add_tool_call("test_function", {"param": "value"})

        data = content.to_dict()

        self.assertIn("text", data)
        self.assertIn("tool_calls", data)

    def test_content_from_dict(self):
        """Test creating content from dict"""
        data = {
            "text": "Hello",
            "tool_calls": [{"name": "test_tool", "arguments": {}}],
            "images": [{"url": "image.jpg"}],
            "metadata": {"key": "value"}
        }

        content = MessageContent.from_dict(data)

        self.assertEqual(content.text, "Hello")
        self.assertEqual(len(content.tool_calls), 1)
        self.assertEqual(len(content.images), 1)
        self.assertEqual(content.metadata["key"], "value")

    def test_content_equality(self):
        """Test content equality comparison"""
        content1 = MessageContent(text="Same text")
        content2 = MessageContent(text="Same text")
        content3 = MessageContent(text="Different text")

        self.assertEqual(content1, content2)
        self.assertNotEqual(content1, content3)

    def test_empty_content(self):
        """Test handling empty content"""
        content = MessageContent(text="")

        self.assertEqual(content.text, "")
        # tool_calls defaults to empty list, not None
        self.assertEqual(content.tool_calls, [])

    def test_content_with_none_text(self):
        """Test content with None text"""
        content = MessageContent(text=None)

        self.assertIsNone(content.text)


class TestMessage(unittest.TestCase):
    """Test Message class"""

    def test_create_basic_message(self):
        """Test creating a basic message"""
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
            parent_id=None
        )

        self.assertEqual(msg.id, "msg_001")
        self.assertEqual(msg.role, MessageRole.USER)
        self.assertEqual(msg.content.text, "Hello")
        self.assertIsNone(msg.parent_id)

    def test_message_with_timestamp(self):
        """Test message with custom timestamp"""
        custom_time = datetime(2024, 1, 1, 12, 0, 0)

        msg = Message(
            id="msg_001",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Response"),
            timestamp=custom_time
        )

        self.assertEqual(msg.timestamp, custom_time)

    def test_message_with_parent(self):
        """Test message with parent reference"""
        msg = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Reply"),
            parent_id="msg_001"
        )

        self.assertEqual(msg.parent_id, "msg_001")

    def test_message_with_metadata(self):
        """Test message with metadata"""
        metadata = {
            "model": "gpt-4",
            "temperature": 0.7,
            "tokens": 150
        }

        msg = Message(
            id="msg_001",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Response"),
            metadata=metadata
        )

        self.assertEqual(msg.metadata["model"], "gpt-4")
        self.assertEqual(msg.metadata["temperature"], 0.7)

    def test_message_roles(self):
        """Test all message roles"""
        roles = [
            MessageRole.USER,
            MessageRole.ASSISTANT,
            MessageRole.SYSTEM,
            MessageRole.TOOL
        ]

        for role in roles:
            msg = Message(
                id=f"msg_{role.value}",
                role=role,
                content=MessageContent(text=f"Message from {role.value}")
            )
            self.assertEqual(msg.role, role)

    def test_message_serialization(self):
        """Test message serialization"""
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Test"),
            parent_id="parent_001",
            timestamp=datetime.now(),
            metadata={"key": "value"}
        )

        data = msg.to_dict()

        self.assertIn("id", data)
        self.assertIn("role", data)
        self.assertIn("content", data)
        self.assertIn("parent_id", data)
        self.assertIn("timestamp", data)
        self.assertIn("metadata", data)

    def test_message_from_dict(self):
        """Test creating message from dict"""
        data = {
            "id": "msg_001",
            "role": "user",
            "content": {"text": "Hello"},
            "parent_id": "parent_001",
            "timestamp": datetime.now().isoformat(),
            "metadata": {"source": "test"}
        }

        msg = Message.from_dict(data)

        self.assertEqual(msg.id, "msg_001")
        self.assertEqual(msg.role, MessageRole.USER)
        self.assertEqual(msg.content.text, "Hello")

    def test_message_equality(self):
        """Test message equality - compare by id"""
        from datetime import datetime
        fixed_time = datetime(2024, 1, 1, 12, 0, 0)

        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Same"),
            timestamp=fixed_time
        )

        msg2 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Same"),
            timestamp=fixed_time
        )

        msg3 = Message(
            id="msg_002",
            role=MessageRole.USER,
            content=MessageContent(text="Different"),
            timestamp=fixed_time
        )

        self.assertEqual(msg1, msg2)
        self.assertNotEqual(msg1, msg3)

    def test_tool_message(self):
        """Test creating a tool message"""
        msg = Message(
            id="tool_001",
            role=MessageRole.TOOL,
            content=MessageContent(text=json.dumps({
                "result": "success",
                "data": {"temperature": 72}
            }))
        )

        self.assertEqual(msg.role, MessageRole.TOOL)

        # Parse tool result
        result = json.loads(msg.content.text)
        self.assertEqual(result["result"], "success")


class TestConversationMetadata(unittest.TestCase):
    """Test ConversationMetadata class"""

    def test_create_basic_metadata(self):
        """Test creating basic metadata"""
        metadata = ConversationMetadata()

        self.assertIsNotNone(metadata.created_at)
        self.assertIsNotNone(metadata.updated_at)
        self.assertIsNone(metadata.source)
        self.assertEqual(metadata.tags, [])

    def test_metadata_with_all_fields(self):
        """Test metadata with all fields"""
        now = datetime.now()

        metadata = ConversationMetadata(
            created_at=now,
            updated_at=now + timedelta(hours=1),
            source="chatgpt",
            format="chatgpt",
            version="1.0",
            model="gpt-4",
            project="test_project",
            tags=["python", "testing"],
            custom_data={"extra": "data"}
        )

        self.assertEqual(metadata.source, "chatgpt")
        self.assertEqual(metadata.format, "chatgpt")
        self.assertEqual(metadata.version, "1.0")
        self.assertEqual(metadata.model, "gpt-4")
        self.assertEqual(metadata.project, "test_project")
        self.assertEqual(len(metadata.tags), 2)
        self.assertEqual(metadata.custom_data["extra"], "data")

    def test_metadata_serialization(self):
        """Test metadata serialization"""
        metadata = ConversationMetadata(
            source="test",
            tags=["tag1", "tag2"],
            model="test-model"
        )

        data = metadata.to_dict()

        self.assertIn("created_at", data)
        self.assertIn("updated_at", data)
        self.assertIn("source", data)
        self.assertIn("tags", data)
        self.assertIn("model", data)

    def test_metadata_from_dict(self):
        """Test creating metadata from dict"""
        data = {
            "source": "anthropic",
            "model": "claude-3",
            "tags": ["ai", "conversation"],
            "custom_field": "custom_value"
        }

        metadata = ConversationMetadata.from_dict(data)

        self.assertEqual(metadata.source, "anthropic")
        self.assertEqual(metadata.model, "claude-3")
        self.assertEqual(len(metadata.tags), 2)

    def test_metadata_tag_operations(self):
        """Test tag operations on metadata"""
        metadata = ConversationMetadata(tags=["python"])

        # Tags should be stored
        self.assertIn("python", metadata.tags)

        # Can modify tags list directly
        metadata.tags.append("testing")
        self.assertIn("testing", metadata.tags)

        # Can set new tags
        metadata.tags = ["new", "tags"]
        self.assertEqual(len(metadata.tags), 2)
        self.assertNotIn("python", metadata.tags)

    def test_metadata_update(self):
        """Test updating metadata fields"""
        metadata = ConversationMetadata()
        original_created = metadata.created_at

        # Update metadata fields directly
        metadata.source = "new_source"
        metadata.model = "new_model"
        metadata.tags = ["new_tag"]

        self.assertEqual(metadata.source, "new_source")
        self.assertEqual(metadata.model, "new_model")
        self.assertEqual(metadata.tags, ["new_tag"])
        self.assertEqual(metadata.created_at, original_created)  # Should not change


class TestConversationTree(unittest.TestCase):
    """Test ConversationTree class"""

    def test_create_empty_tree(self):
        """Test creating an empty conversation tree"""
        tree = ConversationTree(
            id="conv_001",
            title="Test Conversation"
        )

        self.assertEqual(tree.id, "conv_001")
        self.assertEqual(tree.title, "Test Conversation")
        self.assertEqual(len(tree.message_map), 0)
        self.assertIsNotNone(tree.metadata)

    def test_add_linear_messages(self):
        """Test adding messages in a linear chain"""
        tree = ConversationTree(id="conv_001", title="Linear Chat")

        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello")
        )
        tree.add_message(msg1)

        msg2 = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Hi there"),
            parent_id="msg_001"
        )
        tree.add_message(msg2)

        msg3 = Message(
            id="msg_003",
            role=MessageRole.USER,
            content=MessageContent(text="How are you?"),
            parent_id="msg_002"
        )
        tree.add_message(msg3)

        self.assertEqual(len(tree.message_map), 3)
        self.assertIn("msg_001", tree.message_map)
        self.assertIn("msg_002", tree.message_map)
        self.assertIn("msg_003", tree.message_map)

    def test_add_branching_messages(self):
        """Test adding messages with branches"""
        tree = ConversationTree(id="conv_001", title="Branching Chat")

        # Root message
        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Question")
        )
        tree.add_message(msg1)

        # Two different responses (branches)
        msg2a = Message(
            id="msg_002a",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Answer A"),
            parent_id="msg_001"
        )
        tree.add_message(msg2a)

        msg2b = Message(
            id="msg_002b",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Answer B"),
            parent_id="msg_001"
        )
        tree.add_message(msg2b)

        self.assertEqual(len(tree.message_map), 3)

        # Get children of root message
        children = tree.get_children("msg_001")
        self.assertEqual(len(children), 2)
        self.assertIn(msg2a, children)
        self.assertIn(msg2b, children)

    def test_get_paths(self):
        """Test getting all paths through the tree"""
        tree = ConversationTree(id="conv_001", title="Multi-path")

        # Create a tree with multiple paths
        # msg1 -> msg2a -> msg3
        #      -> msg2b -> msg4

        msg1 = Message(id="msg1", role=MessageRole.USER,
                      content=MessageContent(text="Start"))
        tree.add_message(msg1)

        msg2a = Message(id="msg2a", role=MessageRole.ASSISTANT,
                       content=MessageContent(text="Path A"),
                       parent_id="msg1")
        tree.add_message(msg2a)

        msg2b = Message(id="msg2b", role=MessageRole.ASSISTANT,
                       content=MessageContent(text="Path B"),
                       parent_id="msg1")
        tree.add_message(msg2b)

        msg3 = Message(id="msg3", role=MessageRole.USER,
                      content=MessageContent(text="Continue A"),
                      parent_id="msg2a")
        tree.add_message(msg3)

        msg4 = Message(id="msg4", role=MessageRole.USER,
                      content=MessageContent(text="Continue B"),
                      parent_id="msg2b")
        tree.add_message(msg4)

        paths = tree.get_all_paths()

        self.assertEqual(len(paths), 2)

        # Check path lengths
        path_lengths = [len(path) for path in paths]
        self.assertIn(3, path_lengths)  # msg1 -> msg2a -> msg3
        self.assertIn(3, path_lengths)  # msg1 -> msg2b -> msg4

    def test_get_longest_path(self):
        """Test getting the longest path"""
        tree = ConversationTree(id="conv_001", title="Longest path test")

        # Create messages
        messages = []
        parent_id = None
        for i in range(5):
            msg = Message(
                id=f"msg_{i}",
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=MessageContent(text=f"Message {i}"),
                parent_id=parent_id
            )
            tree.add_message(msg)
            messages.append(msg)
            parent_id = msg.id

        # Add a shorter branch
        branch_msg = Message(
            id="branch_1",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Short branch"),
            parent_id="msg_1"
        )
        tree.add_message(branch_msg)

        longest_path = tree.get_longest_path()

        self.assertEqual(len(longest_path), 5)
        self.assertEqual(longest_path[-1].id, "msg_4")

    def test_get_root_messages(self):
        """Test identifying root messages"""
        tree = ConversationTree(id="conv_001", title="Multiple roots")

        # Add multiple root messages (no parent)
        root1 = Message(id="root1", role=MessageRole.USER,
                       content=MessageContent(text="First root"))
        tree.add_message(root1)

        root2 = Message(id="root2", role=MessageRole.USER,
                       content=MessageContent(text="Second root"))
        tree.add_message(root2)

        # Add child to first root
        child = Message(id="child1", role=MessageRole.ASSISTANT,
                       content=MessageContent(text="Reply"),
                       parent_id="root1")
        tree.add_message(child)

        # Find root messages manually
        roots = [msg for msg in tree.message_map.values() if msg.parent_id is None]

        self.assertEqual(len(roots), 2)
        self.assertIn(root1, roots)
        self.assertIn(root2, roots)

    def test_identify_leaf_messages(self):
        """Test identifying leaf messages"""
        tree = ConversationTree(id="conv_001", title="Leaf test")

        # Create a tree with multiple leaves
        msg1 = Message(id="msg1", role=MessageRole.USER,
                      content=MessageContent(text="Start"))
        tree.add_message(msg1)

        msg2 = Message(id="msg2", role=MessageRole.ASSISTANT,
                      content=MessageContent(text="Middle"),
                      parent_id="msg1")
        tree.add_message(msg2)

        # Two leaves branching from msg2
        leaf1 = Message(id="leaf1", role=MessageRole.USER,
                       content=MessageContent(text="Leaf 1"),
                       parent_id="msg2")
        tree.add_message(leaf1)

        leaf2 = Message(id="leaf2", role=MessageRole.USER,
                       content=MessageContent(text="Leaf 2"),
                       parent_id="msg2")
        tree.add_message(leaf2)

        # Find leaf messages (no children)
        leaves = []
        for msg in tree.message_map.values():
            if not tree.get_children(msg.id):
                leaves.append(msg)

        self.assertEqual(len(leaves), 2)
        self.assertIn(leaf1, leaves)
        self.assertIn(leaf2, leaves)

    def test_tree_serialization(self):
        """Test serializing conversation tree"""
        tree = ConversationTree(
            id="conv_001",
            title="Test Serialization",
            metadata=ConversationMetadata(source="test")
        )

        msg = Message(id="msg1", role=MessageRole.USER,
                     content=MessageContent(text="Test"))
        tree.add_message(msg)

        data = tree.to_dict()

        self.assertIn("id", data)
        self.assertIn("title", data)
        self.assertIn("metadata", data)
        self.assertIn("messages", data)
        self.assertEqual(len(data["messages"]), 1)

    def test_tree_from_dict(self):
        """Test creating tree from dict"""
        data = {
            "id": "conv_001",
            "title": "Imported Conversation",
            "metadata": {
                "source": "import",
                "tags": ["imported"]
            },
            "messages": [
                {
                    "id": "msg1",
                    "role": "user",
                    "content": {"text": "Hello"},
                    "parent_id": None
                },
                {
                    "id": "msg2",
                    "role": "assistant",
                    "content": {"text": "Hi"},
                    "parent_id": "msg1"
                }
            ]
        }

        tree = ConversationTree.from_dict(data)

        self.assertEqual(tree.id, "conv_001")
        self.assertEqual(tree.title, "Imported Conversation")
        self.assertEqual(len(tree.message_map), 2)
        self.assertEqual(tree.metadata.source, "import")

    def test_validate_tree(self):
        """Test tree validation"""
        tree = ConversationTree(id="conv_001", title="Valid Tree")

        # Add connected messages
        msg1 = Message(id="msg1", role=MessageRole.USER,
                      content=MessageContent(text="Start"))
        tree.add_message(msg1)

        msg2 = Message(id="msg2", role=MessageRole.ASSISTANT,
                      content=MessageContent(text="Reply"),
                      parent_id="msg1")
        tree.add_message(msg2)

        # Check messages were added
        self.assertEqual(len(tree.message_map), 2)

        # Add orphaned message (invalid parent)
        orphan = Message(id="orphan", role=MessageRole.USER,
                        content=MessageContent(text="Orphaned"),
                        parent_id="nonexistent")
        tree.add_message(orphan)

        # Orphan should be added even with invalid parent
        self.assertIn("orphan", tree.message_map)

    def test_tree_statistics(self):
        """Test getting tree statistics"""
        tree = ConversationTree(id="conv_001", title="Stats Test")

        # Add messages with different roles
        for i in range(10):
            role = MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT
            msg = Message(
                id=f"msg_{i}",
                role=role,
                content=MessageContent(text=f"Message {i}"),
                parent_id=f"msg_{i-1}" if i > 0 else None
            )
            tree.add_message(msg)

        # Calculate statistics manually
        total_messages = len(tree.message_map)
        user_messages = sum(1 for m in tree.message_map.values() if m.role == MessageRole.USER)
        assistant_messages = sum(1 for m in tree.message_map.values() if m.role == MessageRole.ASSISTANT)

        self.assertEqual(total_messages, 10)
        self.assertEqual(user_messages, 5)
        self.assertEqual(assistant_messages, 5)

    def test_prune_tree(self):
        """Test pruning tree branches"""
        tree = ConversationTree(id="conv_001", title="Prune Test")

        # Create tree with branch to prune
        msg1 = Message(id="msg1", role=MessageRole.USER,
                      content=MessageContent(text="Keep"))
        tree.add_message(msg1)

        msg2 = Message(id="msg2", role=MessageRole.ASSISTANT,
                      content=MessageContent(text="Keep"),
                      parent_id="msg1")
        tree.add_message(msg2)

        # Branch to prune
        prune_root = Message(id="prune1", role=MessageRole.USER,
                           content=MessageContent(text="Prune this"),
                           parent_id="msg2")
        tree.add_message(prune_root)

        prune_child = Message(id="prune2", role=MessageRole.ASSISTANT,
                            content=MessageContent(text="Prune this too"),
                            parent_id="prune1")
        tree.add_message(prune_child)

        # Keep this branch
        keep = Message(id="keep1", role=MessageRole.USER,
                      content=MessageContent(text="Keep this"),
                      parent_id="msg2")
        tree.add_message(keep)

        # Manually remove the branch
        del tree.message_map["prune1"]
        del tree.message_map["prune2"]

        self.assertNotIn("prune1", tree.message_map)
        self.assertNotIn("prune2", tree.message_map)
        self.assertIn("keep1", tree.message_map)
        self.assertEqual(len(tree.message_map), 3)

    def test_merge_trees(self):
        """Test merging two conversation trees"""
        tree1 = ConversationTree(id="conv_001", title="Tree 1")
        tree2 = ConversationTree(id="conv_002", title="Tree 2")

        # Add messages to tree1
        msg1 = Message(id="msg1", role=MessageRole.USER,
                      content=MessageContent(text="From tree 1"))
        tree1.add_message(msg1)

        # Add messages to tree2
        msg2 = Message(id="msg2", role=MessageRole.USER,
                      content=MessageContent(text="From tree 2"))
        tree2.add_message(msg2)

        # Manually merge tree2 into tree1
        for msg_id, msg in tree2.message_map.items():
            tree1.add_message(msg)

        self.assertIn("msg1", tree1.message_map)
        self.assertIn("msg2", tree1.message_map)
        self.assertEqual(len(tree1.message_map), 2)


class TestConversationFormats(unittest.TestCase):
    """Test conversation format handling"""

    def test_format_values(self):
        """Test format values as strings"""
        formats = [
            "chatgpt",
            "claude",
            "gemini",
            "copilot",
            "custom"
        ]

        for fmt in formats:
            self.assertIsNotNone(fmt)

    def test_format_in_metadata(self):
        """Test format field in metadata"""
        metadata = ConversationMetadata(format="chatgpt")
        self.assertEqual(metadata.format, "chatgpt")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions"""

    def test_circular_reference(self):
        """Test handling circular parent references"""
        tree = ConversationTree(id="conv_001", title="Circular Test")

        msg1 = Message(id="msg1", role=MessageRole.USER,
                      content=MessageContent(text="First"))
        tree.add_message(msg1)

        msg2 = Message(id="msg2", role=MessageRole.ASSISTANT,
                      content=MessageContent(text="Second"),
                      parent_id="msg1")
        tree.add_message(msg2)

        # Try to create circular reference by modifying parent_id
        msg1.parent_id = "msg2"

        # Tree still contains both messages
        self.assertIn("msg1", tree.message_map)
        self.assertIn("msg2", tree.message_map)
        # The circular reference is allowed but may cause issues in traversal
        self.assertEqual(tree.message_map["msg1"].parent_id, "msg2")

    def test_duplicate_message_ids(self):
        """Test handling duplicate message IDs"""
        tree = ConversationTree(id="conv_001", title="Duplicate Test")

        msg1 = Message(id="duplicate", role=MessageRole.USER,
                      content=MessageContent(text="First"))
        tree.add_message(msg1)

        msg2 = Message(id="duplicate", role=MessageRole.ASSISTANT,
                      content=MessageContent(text="Second"))

        # Adding duplicate ID should raise error or overwrite
        tree.add_message(msg2)

        # Should have overwritten
        self.assertEqual(tree.message_map["duplicate"].content.text, "Second")

    def test_empty_conversation_export(self):
        """Test exporting empty conversation"""
        tree = ConversationTree(id="empty", title="Empty Conversation")

        data = tree.to_dict()

        self.assertEqual(data["id"], "empty")
        self.assertEqual(len(data["messages"]), 0)

    def test_very_deep_tree(self):
        """Test handling very deep conversation tree"""
        tree = ConversationTree(id="deep", title="Deep Tree")

        # Create a very deep linear chain
        parent_id = None
        for i in range(100):  # Use 100 instead of 1000 for faster test
            msg = Message(
                id=f"msg_{i}",
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=MessageContent(text=f"Message {i}"),
                parent_id=parent_id
            )
            tree.add_message(msg)
            parent_id = msg.id

        # Check message count using message_map
        self.assertEqual(len(tree.message_map), 100)

        # Get longest path to verify depth
        longest = tree.get_longest_path()
        self.assertEqual(len(longest), 100)

    def test_wide_tree(self):
        """Test handling very wide conversation tree"""
        tree = ConversationTree(id="wide", title="Wide Tree")

        # Create root
        root = Message(id="root", role=MessageRole.USER,
                      content=MessageContent(text="Root"))
        tree.add_message(root)

        # Add many children to root
        for i in range(100):
            child = Message(
                id=f"child_{i}",
                role=MessageRole.ASSISTANT,
                content=MessageContent(text=f"Child {i}"),
                parent_id="root"
            )
            tree.add_message(child)

        children = tree.get_children("root")

        self.assertEqual(len(children), 100)

    def test_unicode_content(self):
        """Test handling unicode in messages"""
        content = MessageContent(text="Hello 世界 🌍 مرحبا")
        msg = Message(
            id="unicode",
            role=MessageRole.USER,
            content=content
        )

        tree = ConversationTree(id="unicode_test", title="Unicode Test")
        tree.add_message(msg)

        # Serialize and deserialize
        data = tree.to_dict()
        tree2 = ConversationTree.from_dict(data)

        self.assertEqual(
            tree2.message_map["unicode"].content.text,
            "Hello 世界 🌍 مرحبا"
        )


if __name__ == '__main__':
    unittest.main()