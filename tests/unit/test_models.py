"""
Unit tests for core models
"""

import pytest
from datetime import datetime
from typing import List

from ctk.core.models import (
    MessageRole, MessageContent, Message, 
    ConversationMetadata, ConversationTree
)


class TestMessageRole:
    """Test MessageRole enum"""
    
    @pytest.mark.unit
    def test_role_values(self):
        """Test role enum values"""
        assert MessageRole.SYSTEM.value == "system"
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.TOOL.value == "tool"
        assert MessageRole.FUNCTION.value == "function"
    
    @pytest.mark.unit
    def test_from_string(self):
        """Test creating role from string"""
        assert MessageRole.from_string("user") == MessageRole.USER
        assert MessageRole.from_string("assistant") == MessageRole.ASSISTANT
        assert MessageRole.from_string("system") == MessageRole.SYSTEM
        
        # Test fallback for unknown roles
        assert MessageRole.from_string("unknown") == MessageRole.USER
        assert MessageRole.from_string(None) == MessageRole.USER
        assert MessageRole.from_string("") == MessageRole.USER


class TestMessageContent:
    """Test MessageContent model"""
    
    @pytest.mark.unit
    def test_text_content(self):
        """Test text-only content"""
        content = MessageContent(text="Hello world")
        assert content.text == "Hello world"
        assert content.get_text() == "Hello world"
        assert content.images == []
        assert content.tool_calls == []
    
    @pytest.mark.unit
    def test_multimodal_content(self):
        """Test content with images"""
        content = MessageContent(
            text="Look at this",
            images=["image1.png", "image2.jpg"]
        )
        assert content.text == "Look at this"
        assert len(content.images) == 2
        assert "image1.png" in content.images
    
    @pytest.mark.unit
    def test_tool_content(self):
        """Test content with tool calls"""
        tool_calls = [
            {"tool": "calculator", "input": "2+2"},
            {"tool": "search", "input": "weather"}
        ]
        content = MessageContent(
            text="Let me help",
            tool_calls=tool_calls
        )
        assert len(content.tool_calls) == 2
        assert content.tool_calls[0]["tool"] == "calculator"
    
    @pytest.mark.unit
    def test_empty_content(self):
        """Test empty content handling"""
        content = MessageContent()
        assert content.text is None  # Default is None
        assert content.get_text() == ""  # But get_text returns empty string
        assert content.images == []


class TestMessage:
    """Test Message model"""
    
    @pytest.mark.unit
    def test_message_creation(self):
        """Test creating a message"""
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            parent_id=None
        )
        assert msg.id == "msg_001"
        assert msg.role == MessageRole.USER
        assert msg.content.text == "Hello"
        assert msg.parent_id is None
    
    @pytest.mark.unit
    def test_message_with_parent(self):
        """Test message with parent reference"""
        msg = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Response"),
            parent_id="msg_001"
        )
        assert msg.parent_id == "msg_001"
    
    @pytest.mark.unit
    def test_message_metadata(self):
        """Test message with metadata"""
        metadata = {"model": "gpt-4", "temperature": 0.7}
        msg = Message(
            id="msg_001",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Response"),
            metadata=metadata
        )
        assert msg.metadata == metadata
        assert msg.metadata["model"] == "gpt-4"


class TestConversationMetadata:
    """Test ConversationMetadata model"""
    
    @pytest.mark.unit
    def test_metadata_creation(self):
        """Test creating conversation metadata"""
        meta = ConversationMetadata(
            source="openai",
            model="gpt-4",
            tags=["test", "sample"],
            project="my-project"
        )
        assert meta.source == "openai"
        assert meta.model == "gpt-4"
        assert "test" in meta.tags
        assert meta.project == "my-project"
    
    @pytest.mark.unit
    def test_metadata_defaults(self):
        """Test metadata default values"""
        meta = ConversationMetadata()
        assert meta.source is None  # Default is None now
        assert meta.model is None
        assert meta.tags == []
        assert meta.project is None
    
    @pytest.mark.unit
    def test_metadata_dict_conversion(self):
        """Test converting metadata to dict"""
        meta = ConversationMetadata(
            source="anthropic",
            model="claude-3",
            tags=["ai", "chat"]
        )
        data = meta.to_dict()  # Changed from model_dump() to to_dict()
        assert data["source"] == "anthropic"
        assert data["model"] == "claude-3"
        assert data["tags"] == ["ai", "chat"]


class TestConversationTree:
    """Test ConversationTree model"""
    
    @pytest.mark.unit
    def test_empty_conversation(self):
        """Test creating empty conversation"""
        conv = ConversationTree(
            id="conv_001",
            title="Test"
        )
        assert conv.id == "conv_001"
        assert conv.title == "Test"
        assert len(conv.message_map) == 0
        assert conv.root_message_ids == []
    
    @pytest.mark.unit
    def test_add_message(self, sample_message):
        """Test adding messages to conversation"""
        conv = ConversationTree(id="conv_001")
        conv.add_message(sample_message)
        
        assert len(conv.message_map) == 1
        assert sample_message.id in conv.message_map
        assert sample_message.id in conv.root_message_ids
    
    @pytest.mark.unit
    def test_linear_conversation(self):
        """Test linear conversation structure"""
        conv = ConversationTree(id="conv_001")
        
        # Add messages in sequence
        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="First"),
            parent_id=None
        )
        conv.add_message(msg1)
        
        msg2 = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Second"),
            parent_id="msg_001"
        )
        conv.add_message(msg2)
        
        msg3 = Message(
            id="msg_003",
            role=MessageRole.USER,
            content=MessageContent(text="Third"),
            parent_id="msg_002"
        )
        conv.add_message(msg3)
        
        # Check structure
        assert len(conv.message_map) == 3
        assert len(conv.root_message_ids) == 1
        assert conv.root_message_ids[0] == "msg_001"
        
        # Test get_longest_path
        path = conv.get_longest_path()
        assert len(path) == 3
        assert path[0].id == "msg_001"
        assert path[1].id == "msg_002"
        assert path[2].id == "msg_003"
    
    @pytest.mark.unit
    def test_branching_conversation(self, branching_conversation):
        """Test conversation with branches"""
        conv = branching_conversation
        
        # Check structure
        assert len(conv.message_map) == 5
        assert len(conv.root_message_ids) == 1
        
        # Check branches
        paths = conv.get_all_paths()
        assert len(paths) == 2  # Two possible paths
        
        # Check longest path
        longest = conv.get_longest_path()
        assert len(longest) == 4  # The path with continuation
        
        # Check that both responses are children of the first message
        children = conv.get_children("msg_001")
        assert len(children) == 2
        child_ids = [c.id for c in children]
        assert "msg_002a" in child_ids
        assert "msg_002b" in child_ids
    
    @pytest.mark.unit
    def test_get_children(self):
        """Test getting children of a message"""
        conv = ConversationTree(id="conv_001")
        
        msg1 = Message(id="msg_001", role=MessageRole.USER, 
                      content=MessageContent(text="Parent"))
        conv.add_message(msg1)
        
        msg2 = Message(id="msg_002", role=MessageRole.ASSISTANT,
                      content=MessageContent(text="Child1"),
                      parent_id="msg_001")
        conv.add_message(msg2)
        
        msg3 = Message(id="msg_003", role=MessageRole.ASSISTANT,
                      content=MessageContent(text="Child2"),
                      parent_id="msg_001")
        conv.add_message(msg3)
        
        children = conv.get_children("msg_001")
        assert len(children) == 2
        child_ids = [c.id for c in children]
        assert "msg_002" in child_ids
        assert "msg_003" in child_ids
    
    @pytest.mark.unit
    def test_get_all_paths(self):
        """Test getting all paths in a conversation"""
        conv = ConversationTree(id="conv_001")
        
        # Create a simple tree with two branches
        msg1 = Message(id="msg_001", role=MessageRole.USER,
                      content=MessageContent(text="Start"))
        conv.add_message(msg1)
        
        msg2a = Message(id="msg_002a", role=MessageRole.ASSISTANT,
                       content=MessageContent(text="Branch A"),
                       parent_id="msg_001")
        conv.add_message(msg2a)
        
        msg2b = Message(id="msg_002b", role=MessageRole.ASSISTANT,
                       content=MessageContent(text="Branch B"),
                       parent_id="msg_001")
        conv.add_message(msg2b)
        
        paths = conv.get_all_paths()
        assert len(paths) == 2
        
        # Check each path
        path_ids = [[msg.id for msg in path] for path in paths]
        assert ["msg_001", "msg_002a"] in path_ids or ["msg_001", "msg_002b"] in path_ids
    
    @pytest.mark.unit
    def test_conversation_with_metadata(self):
        """Test conversation with metadata"""
        meta = ConversationMetadata(
            source="openai",
            model="gpt-4",
            tags=["test", "ai"],
            project="research"
        )
        conv = ConversationTree(
            id="conv_001",
            title="Test Chat",
            metadata=meta
        )
        
        assert conv.metadata.source == "openai"
        assert conv.metadata.model == "gpt-4"
        assert "test" in conv.metadata.tags
        assert conv.metadata.project == "research"