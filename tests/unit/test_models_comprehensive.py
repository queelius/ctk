"""
Comprehensive tests for core models
Tests MediaContent, ToolCall, MessageContent, ConversationTree, and serialization
"""

from datetime import datetime

import pytest

from ctk.core.models import (ContentType, ConversationMetadata,
                             ConversationSummary, ConversationTree,
                             MediaContent, Message, MessageContent,
                             MessageRole, ToolCall)


class TestMediaContent:
    """Test MediaContent model"""

    @pytest.mark.unit
    def test_create_image_media(self):
        """Test creating image media content"""
        media = MediaContent(
            type=ContentType.IMAGE,
            url="https://example.com/image.png",
            mime_type="image/png",
            caption="A test image",
        )

        assert media.type == ContentType.IMAGE
        assert media.url == "https://example.com/image.png"
        assert media.mime_type == "image/png"
        assert media.caption == "A test image"

    @pytest.mark.unit
    def test_is_remote(self):
        """Test remote media detection"""
        remote = MediaContent(
            type=ContentType.IMAGE, url="https://example.com/image.png"
        )
        assert remote.is_remote() is True

        local = MediaContent(type=ContentType.IMAGE, path="/local/image.png")
        assert local.is_remote() is False

    @pytest.mark.unit
    def test_is_local(self):
        """Test local media detection"""
        local = MediaContent(type=ContentType.IMAGE, path="/local/image.png")
        assert local.is_local() is True

        remote = MediaContent(
            type=ContentType.IMAGE, url="https://example.com/image.png"
        )
        assert remote.is_local() is False

    @pytest.mark.unit
    def test_is_embedded(self):
        """Test embedded media detection"""
        embedded = MediaContent(type=ContentType.IMAGE, data="base64encodeddata...")
        assert embedded.is_embedded() is True

        remote = MediaContent(
            type=ContentType.IMAGE, url="https://example.com/image.png"
        )
        assert remote.is_embedded() is False

    @pytest.mark.unit
    def test_media_to_dict(self):
        """Test serializing media to dictionary"""
        media = MediaContent(
            type=ContentType.IMAGE,
            url="https://example.com/image.png",
            mime_type="image/png",
            caption="Test",
            metadata={"size": 1024},
        )

        data = media.to_dict()
        assert data["type"] == "image"
        assert data["url"] == "https://example.com/image.png"
        assert data["mime_type"] == "image/png"
        assert data["caption"] == "Test"
        assert data["metadata"] == {"size": 1024}

    @pytest.mark.unit
    def test_media_with_all_fields(self):
        """Test media with all fields populated"""
        media = MediaContent(
            type=ContentType.DOCUMENT,
            url="https://example.com/doc.pdf",
            path="/local/doc.pdf",
            data="base64data",
            mime_type="application/pdf",
            caption="Important document",
            metadata={"pages": 10},
        )

        data = media.to_dict()
        assert "url" in data
        assert "path" in data
        assert "data" in data
        assert data["mime_type"] == "application/pdf"


class TestToolCall:
    """Test ToolCall model"""

    @pytest.mark.unit
    def test_create_tool_call(self):
        """Test creating a tool call"""
        tool = ToolCall(
            id="tool_001",
            name="calculator",
            arguments={"expression": "2+2"},
            status="pending",
        )

        assert tool.id == "tool_001"
        assert tool.name == "calculator"
        assert tool.arguments == {"expression": "2+2"}
        assert tool.status == "pending"

    @pytest.mark.unit
    def test_tool_call_with_result(self):
        """Test tool call with result"""
        tool = ToolCall(
            name="calculator",
            arguments={"expression": "2+2"},
            result=4,
            status="completed",
        )

        assert tool.result == 4
        assert tool.status == "completed"
        assert tool.error is None

    @pytest.mark.unit
    def test_tool_call_with_error(self):
        """Test tool call with error"""
        tool = ToolCall(
            name="calculator",
            arguments={"expression": "invalid"},
            status="failed",
            error="Invalid expression",
        )

        assert tool.status == "failed"
        assert tool.error == "Invalid expression"

    @pytest.mark.unit
    def test_tool_call_to_dict(self):
        """Test serializing tool call to dictionary"""
        tool = ToolCall(
            id="tool_001",
            name="search",
            arguments={"query": "weather"},
            result={"temp": 72},
            status="completed",
            metadata={"provider": "google"},
        )

        data = tool.to_dict()
        assert data["id"] == "tool_001"
        assert data["name"] == "search"
        assert data["arguments"] == {"query": "weather"}
        assert data["result"] == {"temp": 72}
        assert data["status"] == "completed"
        assert data["metadata"] == {"provider": "google"}

    @pytest.mark.unit
    def test_tool_call_from_dict(self):
        """Test creating tool call from dictionary"""
        data = {
            "id": "tool_001",
            "name": "calculator",
            "arguments": {"expression": "2+2"},
            "result": 4,
            "status": "completed",
        }

        tool = ToolCall.from_dict(data)
        assert tool.id == "tool_001"
        assert tool.name == "calculator"
        assert tool.arguments == {"expression": "2+2"}
        assert tool.result == 4
        assert tool.status == "completed"

    @pytest.mark.unit
    def test_tool_call_default_id(self):
        """Test that tool call generates default ID"""
        tool = ToolCall(name="test")
        assert tool.id is not None
        assert len(tool.id) > 0


class TestMessageContentAdvanced:
    """Test advanced MessageContent features"""

    @pytest.mark.unit
    def test_add_image(self):
        """Test adding images to content"""
        content = MessageContent(text="Check this out")
        img = content.add_image(
            url="https://example.com/image.png",
            caption="Test image",
            mime_type="image/png",
        )

        assert len(content.images) == 1
        assert content.images[0].url == "https://example.com/image.png"
        assert content.images[0].caption == "Test image"
        assert content.has_media() is True

    @pytest.mark.unit
    def test_add_tool_call(self):
        """Test adding tool calls to content"""
        content = MessageContent(text="Let me calculate that")
        tool = content.add_tool_call(name="calculator", arguments={"expression": "2+2"})

        assert len(content.tool_calls) == 1
        assert content.tool_calls[0].name == "calculator"
        assert content.has_tools() is True

    @pytest.mark.unit
    def test_has_media(self):
        """Test media detection"""
        content = MessageContent(text="Hello")
        assert content.has_media() is False

        content.add_image(url="https://example.com/image.png")
        assert content.has_media() is True

    @pytest.mark.unit
    def test_has_tools(self):
        """Test tool detection"""
        content = MessageContent(text="Hello")
        assert content.has_tools() is False

        content.add_tool_call(name="search", arguments={})
        assert content.has_tools() is True

    @pytest.mark.unit
    def test_get_text_from_parts(self):
        """Test extracting text from parts (legacy format)"""
        content = MessageContent(parts=["Hello", "world", {"text": "from parts"}])

        text = content.get_text()
        assert "Hello" in text
        assert "world" in text
        assert "from parts" in text

    @pytest.mark.unit
    def test_content_to_dict_complete(self):
        """Test serializing content with all features"""
        content = MessageContent(text="Test message")
        content.add_image(url="https://example.com/img.png", caption="Image")
        content.add_tool_call(name="search", arguments={"q": "test"})

        data = content.to_dict()
        assert data["text"] == "Test message"
        assert "images" in data
        assert len(data["images"]) == 1
        assert "tool_calls" in data
        assert len(data["tool_calls"]) == 1

    @pytest.mark.unit
    def test_content_from_dict_complete(self):
        """Test creating content from dictionary"""
        data = {
            "text": "Test message",
            "images": [
                {
                    "type": "image",
                    "url": "https://example.com/img.png",
                    "caption": "Test image",
                }
            ],
            "tool_calls": [
                {
                    "id": "tool_001",
                    "name": "search",
                    "arguments": {"q": "test"},
                    "status": "pending",
                }
            ],
        }

        content = MessageContent.from_dict(data)
        assert content.text == "Test message"
        assert len(content.images) == 1
        assert content.images[0].url == "https://example.com/img.png"
        assert len(content.tool_calls) == 1
        assert content.tool_calls[0].name == "search"


class TestMessageSerializationRoundtrip:
    """Test message serialization round-trips"""

    @pytest.mark.unit
    def test_simple_message_roundtrip(self):
        """Test simple message serialization roundtrip"""
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )

        # Serialize
        data = msg.to_dict()

        # Deserialize
        restored = Message.from_dict(data)

        assert restored.id == msg.id
        assert restored.role == msg.role
        assert restored.content.text == msg.content.text
        assert restored.timestamp == msg.timestamp

    @pytest.mark.unit
    def test_complex_message_roundtrip(self):
        """Test complex message with media and tools"""
        msg = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Here's the result"),
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
            parent_id="msg_001",
            metadata={"model": "gpt-4"},
        )
        msg.content.add_image(url="https://example.com/result.png")
        msg.content.add_tool_call(name="calculator", arguments={"expr": "2+2"})

        # Serialize
        data = msg.to_dict()

        # Deserialize
        restored = Message.from_dict(data)

        assert restored.id == msg.id
        assert restored.parent_id == msg.parent_id
        assert len(restored.content.images) == 1
        assert len(restored.content.tool_calls) == 1
        assert restored.metadata == {"model": "gpt-4"}


class TestConversationTreeOperations:
    """Test ConversationTree operations"""

    @pytest.mark.unit
    def test_add_root_message(self):
        """Test adding a root message"""
        conv = ConversationTree(id="conv_001", title="Test")

        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
            parent_id=None,
        )
        conv.add_message(msg)

        assert "msg_001" in conv.message_map
        assert "msg_001" in conv.root_message_ids
        assert len(conv.root_message_ids) == 1

    @pytest.mark.unit
    def test_add_child_message(self):
        """Test adding a child message"""
        conv = ConversationTree(id="conv_001", title="Test")

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
            content=MessageContent(text="Hi"),
            parent_id="msg_001",
        )
        conv.add_message(msg2)

        assert len(conv.message_map) == 2
        assert len(conv.root_message_ids) == 1
        children = conv.get_children("msg_001")
        assert len(children) == 1
        assert children[0].id == "msg_002"

    @pytest.mark.unit
    def test_get_children_ordering(self):
        """Test that children are ordered by timestamp"""
        conv = ConversationTree(id="conv_001", title="Test")

        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
            parent_id=None,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )
        conv.add_message(msg1)

        # Add children in reverse chronological order
        msg3 = Message(
            id="msg_003",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Third"),
            parent_id="msg_001",
            timestamp=datetime(2024, 1, 1, 12, 2, 0),
        )
        conv.add_message(msg3)

        msg2 = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Second"),
            parent_id="msg_001",
            timestamp=datetime(2024, 1, 1, 12, 1, 0),
        )
        conv.add_message(msg2)

        children = conv.get_children("msg_001")
        # Should be ordered by timestamp
        assert children[0].id == "msg_002"
        assert children[1].id == "msg_003"

    @pytest.mark.unit
    def test_get_all_paths_single_path(self):
        """Test getting all paths from linear conversation"""
        conv = ConversationTree(id="conv_001", title="Test")

        # Create linear conversation
        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="1"),
            parent_id=None,
        )
        msg2 = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="2"),
            parent_id="msg_001",
        )
        msg3 = Message(
            id="msg_003",
            role=MessageRole.USER,
            content=MessageContent(text="3"),
            parent_id="msg_002",
        )

        conv.add_message(msg1)
        conv.add_message(msg2)
        conv.add_message(msg3)

        paths = conv.get_all_paths()
        assert len(paths) == 1
        assert len(paths[0]) == 3
        assert paths[0][0].id == "msg_001"
        assert paths[0][2].id == "msg_003"

    @pytest.mark.unit
    def test_get_all_paths_branching(self):
        """Test getting all paths from branching conversation"""
        conv = ConversationTree(id="conv_001", title="Test")

        # Create branching conversation
        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Question"),
            parent_id=None,
        )
        msg2a = Message(
            id="msg_002a",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Answer A"),
            parent_id="msg_001",
        )
        msg2b = Message(
            id="msg_002b",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Answer B"),
            parent_id="msg_001",
        )

        conv.add_message(msg1)
        conv.add_message(msg2a)
        conv.add_message(msg2b)

        paths = conv.get_all_paths()
        assert len(paths) == 2
        # Both paths should start with msg_001
        assert paths[0][0].id == "msg_001"
        assert paths[1][0].id == "msg_001"
        # Paths should end with different messages
        endings = {paths[0][-1].id, paths[1][-1].id}
        assert endings == {"msg_002a", "msg_002b"}

    @pytest.mark.unit
    def test_get_all_paths_cache_hit(self):
        """Test that get_all_paths uses cache on repeated calls"""
        conv = ConversationTree(id="conv_cache", title="Cache Test")

        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="1"),
            parent_id=None,
        )
        msg2 = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="2"),
            parent_id="msg_001",
        )
        conv.add_message(msg1)
        conv.add_message(msg2)

        # First call - cache miss
        assert conv._paths_cache is None
        paths1 = conv.get_all_paths()
        assert conv._paths_cache is not None
        cache_hash1 = conv._paths_cache_hash

        # Second call - cache hit
        paths2 = conv.get_all_paths()
        assert conv._paths_cache_hash == cache_hash1
        assert paths1 == paths2

    @pytest.mark.unit
    def test_get_all_paths_cache_invalidation(self):
        """Test that cache is invalidated when tree structure changes"""
        conv = ConversationTree(id="conv_cache_inv", title="Cache Invalidation Test")

        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="1"),
            parent_id=None,
        )
        conv.add_message(msg1)

        # First call - populate cache
        paths1 = conv.get_all_paths()
        assert len(paths1) == 1
        cache_hash1 = conv._paths_cache_hash

        # Add a message - cache should be invalidated
        msg2 = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="2"),
            parent_id="msg_001",
        )
        conv.add_message(msg2)
        assert conv._paths_cache is None  # Cache was invalidated

        # Next call should recompute
        paths2 = conv.get_all_paths()
        assert len(paths2) == 1
        assert len(paths2[0]) == 2  # Now has 2 messages
        assert conv._paths_cache_hash != cache_hash1

    @pytest.mark.unit
    def test_get_all_paths_cache_not_in_to_dict(self):
        """Test that cache fields are not included in serialization"""
        conv = ConversationTree(id="conv_serial", title="Serialization Test")

        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="1"),
            parent_id=None,
        )
        conv.add_message(msg1)

        # Populate cache
        conv.get_all_paths()
        assert conv._paths_cache is not None

        # Serialize
        data = conv.to_dict()

        # Cache fields should not be present
        assert "_paths_cache" not in data
        assert "_paths_cache_hash" not in data

    @pytest.mark.unit
    def test_get_longest_path(self):
        """Test getting longest path"""
        conv = ConversationTree(id="conv_001", title="Test")

        # Create conversation with branches of different lengths
        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Q"),
            parent_id=None,
        )
        msg2a = Message(
            id="msg_002a",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Short"),
            parent_id="msg_001",
        )
        msg2b = Message(
            id="msg_002b",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Long path start"),
            parent_id="msg_001",
        )
        msg3 = Message(
            id="msg_003",
            role=MessageRole.USER,
            content=MessageContent(text="Continue"),
            parent_id="msg_002b",
        )
        msg4 = Message(
            id="msg_004",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="End"),
            parent_id="msg_003",
        )

        conv.add_message(msg1)
        conv.add_message(msg2a)
        conv.add_message(msg2b)
        conv.add_message(msg3)
        conv.add_message(msg4)

        longest = conv.get_longest_path()
        assert len(longest) == 4  # msg_001 -> msg_002b -> msg_003 -> msg_004
        assert longest[-1].id == "msg_004"

    @pytest.mark.unit
    def test_get_linear_history(self):
        """Test getting linear history to specific message"""
        conv = ConversationTree(id="conv_001", title="Test")

        # Create branching conversation
        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Q"),
            parent_id=None,
        )
        msg2 = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="A"),
            parent_id="msg_001",
        )
        msg3a = Message(
            id="msg_003a",
            role=MessageRole.USER,
            content=MessageContent(text="Branch A"),
            parent_id="msg_002",
        )
        msg3b = Message(
            id="msg_003b",
            role=MessageRole.USER,
            content=MessageContent(text="Branch B"),
            parent_id="msg_002",
        )

        conv.add_message(msg1)
        conv.add_message(msg2)
        conv.add_message(msg3a)
        conv.add_message(msg3b)

        # Get history to specific leaf
        history = conv.get_linear_history("msg_003a")
        assert len(history) == 3
        assert history[0].id == "msg_001"
        assert history[1].id == "msg_002"
        assert history[2].id == "msg_003a"

    @pytest.mark.unit
    def test_count_branches(self):
        """Test counting branch points"""
        conv = ConversationTree(id="conv_001", title="Test")

        # Linear conversation - no branches
        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Q"),
            parent_id=None,
        )
        msg2 = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="A"),
            parent_id="msg_001",
        )
        conv.add_message(msg1)
        conv.add_message(msg2)

        assert conv.count_branches() == 0

        # Add a branch
        msg3a = Message(
            id="msg_003a",
            role=MessageRole.USER,
            content=MessageContent(text="Branch A"),
            parent_id="msg_002",
        )
        msg3b = Message(
            id="msg_003b",
            role=MessageRole.USER,
            content=MessageContent(text="Branch B"),
            parent_id="msg_002",
        )
        conv.add_message(msg3a)
        conv.add_message(msg3b)

        assert conv.count_branches() == 1  # One branch point at msg_002


class TestConversationTreeSerialization:
    """Test ConversationTree serialization"""

    @pytest.mark.unit
    def test_conversation_to_dict(self):
        """Test serializing conversation to dictionary"""
        conv = ConversationTree(
            id="conv_001",
            title="Test Conversation",
            metadata=ConversationMetadata(
                source="test", model="gpt-4", tags=["test", "sample"]
            ),
        )

        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
            parent_id=None,
        )
        conv.add_message(msg1)

        data = conv.to_dict()
        assert data["id"] == "conv_001"
        assert data["title"] == "Test Conversation"
        assert "metadata" in data
        assert "messages" in data
        assert len(data["messages"]) == 1
        assert data["root_message_ids"] == ["msg_001"]

    @pytest.mark.unit
    def test_conversation_from_dict(self):
        """Test creating conversation from dictionary"""
        data = {
            "id": "conv_001",
            "title": "Test Conversation",
            "metadata": {"source": "test", "model": "gpt-4", "tags": ["test"]},
            "messages": [
                {
                    "id": "msg_001",
                    "role": "user",
                    "content": {"text": "Hello"},
                    "timestamp": "2024-01-01T12:00:00",
                    "parent_id": None,
                }
            ],
            "root_message_ids": ["msg_001"],
        }

        conv = ConversationTree.from_dict(data)
        assert conv.id == "conv_001"
        assert conv.title == "Test Conversation"
        assert len(conv.message_map) == 1
        assert "msg_001" in conv.message_map
        assert conv.root_message_ids == ["msg_001"]

    @pytest.mark.unit
    def test_conversation_roundtrip(self, branching_conversation):
        """Test conversation serialization roundtrip"""
        # Serialize
        data = branching_conversation.to_dict()

        # Deserialize
        restored = ConversationTree.from_dict(data)

        # Verify
        assert restored.id == branching_conversation.id
        assert restored.title == branching_conversation.title
        assert len(restored.message_map) == len(branching_conversation.message_map)
        assert len(restored.get_all_paths()) == len(
            branching_conversation.get_all_paths()
        )


class TestConversationSummary:
    """Test ConversationSummary model"""

    @pytest.mark.unit
    def test_summary_creation(self):
        """Test creating conversation summary"""
        summary = ConversationSummary(
            id="conv_001",
            title="Test Conversation",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            updated_at=datetime(2024, 1, 1, 13, 0, 0),
            message_count=5,
            source="openai",
            model="gpt-4",
            tags=["test"],
            project="my-project",
        )

        assert summary.id == "conv_001"
        assert summary.title == "Test Conversation"
        assert summary.message_count == 5
        assert summary.source == "openai"
        assert summary.model == "gpt-4"
        assert summary.tags == ["test"]
        assert summary.project == "my-project"

    @pytest.mark.unit
    def test_summary_to_dict(self):
        """Test serializing summary to dictionary"""
        summary = ConversationSummary(
            id="conv_001",
            title="Test",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
            updated_at=datetime(2024, 1, 1, 13, 0, 0),
            message_count=5,
            starred_at=datetime(2024, 1, 1, 14, 0, 0),
        )

        data = summary.to_dict()
        assert data["id"] == "conv_001"
        assert data["title"] == "Test"
        assert data["message_count"] == 5
        assert "starred_at" in data
        assert "created_at" in data

    @pytest.mark.unit
    def test_summary_from_dict(self):
        """Test creating summary from dictionary"""
        data = {
            "id": "conv_001",
            "title": "Test",
            "created_at": "2024-01-01T12:00:00",
            "updated_at": "2024-01-01T13:00:00",
            "message_count": 5,
            "source": "openai",
            "model": "gpt-4",
            "tags": ["test"],
            "project": "my-project",
        }

        summary = ConversationSummary.from_dict(data)
        assert summary.id == "conv_001"
        assert summary.title == "Test"
        assert summary.message_count == 5
        assert summary.source == "openai"


class TestConversationMetadata:
    """Test ConversationMetadata model"""

    @pytest.mark.unit
    def test_metadata_defaults(self):
        """Test metadata default values"""
        meta = ConversationMetadata()

        assert meta.version == "2.0.0"
        assert meta.format == "ctk"
        assert meta.created_at is not None
        assert meta.updated_at is not None
        assert meta.tags == []
        assert meta.custom_data == {}

    @pytest.mark.unit
    def test_metadata_custom_fields(self):
        """Test metadata with custom fields"""
        meta = ConversationMetadata(
            source="openai",
            model="gpt-4",
            tags=["python", "ai"],
            project="my-project",
            custom_data={"key": "value", "number": 42},
        )

        assert meta.source == "openai"
        assert meta.model == "gpt-4"
        assert meta.tags == ["python", "ai"]
        assert meta.project == "my-project"
        assert meta.custom_data == {"key": "value", "number": 42}

    @pytest.mark.unit
    def test_metadata_organization_fields(self):
        """Test metadata organization fields"""
        meta = ConversationMetadata(
            starred_at=datetime(2024, 1, 1, 12, 0, 0),
            pinned_at=datetime(2024, 1, 1, 13, 0, 0),
            archived_at=datetime(2024, 1, 1, 14, 0, 0),
        )

        assert meta.starred_at is not None
        assert meta.pinned_at is not None
        assert meta.archived_at is not None

    @pytest.mark.unit
    def test_metadata_roundtrip(self):
        """Test metadata serialization roundtrip"""
        meta = ConversationMetadata(
            source="test",
            model="test-model",
            tags=["tag1", "tag2"],
            custom_data={"key": "value"},
        )

        # Serialize
        data = meta.to_dict()

        # Deserialize
        restored = ConversationMetadata.from_dict(data)

        assert restored.source == meta.source
        assert restored.model == meta.model
        assert restored.tags == meta.tags
        assert restored.custom_data == meta.custom_data
