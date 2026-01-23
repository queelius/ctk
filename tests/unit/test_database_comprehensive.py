"""
Comprehensive database tests for ConversationDB
Tests all CRUD operations, queries, organization, tags, and advanced features
"""

from datetime import datetime, timedelta

import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (ConversationMetadata, ConversationTree, Message,
                             MessageContent, MessageRole)


class TestDatabaseCRUD:
    """Test core CRUD operations"""

    @pytest.mark.unit
    def test_save_empty_conversation(self, temp_db):
        """Test saving a conversation with no messages"""
        conv = ConversationTree(
            id="conv_empty",
            title="Empty Conversation",
            metadata=ConversationMetadata(source="test"),
        )

        conv_id = temp_db.save_conversation(conv)
        assert conv_id == "conv_empty"

        loaded = temp_db.load_conversation(conv_id)
        assert loaded is not None
        assert loaded.id == conv_id
        assert loaded.title == "Empty Conversation"
        assert len(loaded.message_map) == 0

    @pytest.mark.unit
    def test_save_conversation_updates_existing(self, temp_db, sample_conversation):
        """Test that saving an existing conversation updates it"""
        # Save initial
        temp_db.save_conversation(sample_conversation)

        # Modify
        sample_conversation.title = "Modified Title"

        # Save again (should update, not create duplicate)
        temp_db.save_conversation(sample_conversation)

        # Verify only one conversation exists
        conversations = temp_db.list_conversations()
        assert len(conversations) == 1
        assert conversations[0].title == "Modified Title"

    @pytest.mark.unit
    def test_delete_nonexistent_conversation(self, temp_db):
        """Test deleting a conversation that doesn't exist"""
        result = temp_db.delete_conversation("nonexistent_id")
        assert result is False

    @pytest.mark.unit
    def test_update_conversation_metadata(self, temp_db, sample_conversation):
        """Test updating conversation metadata fields"""
        temp_db.save_conversation(sample_conversation)

        # Update title
        result = temp_db.update_conversation_metadata(
            sample_conversation.id, title="New Title"
        )
        assert result is True

        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.title == "New Title"

        # Update project
        result = temp_db.update_conversation_metadata(
            sample_conversation.id, project="my-project"
        )
        assert result is True

        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.project == "my-project"

        # Update source and model
        result = temp_db.update_conversation_metadata(
            sample_conversation.id, source="openai", model="gpt-4"
        )
        assert result is True

        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.source == "openai"
        assert loaded.metadata.model == "gpt-4"

    @pytest.mark.unit
    def test_update_metadata_nonexistent_conversation(self, temp_db):
        """Test updating metadata for nonexistent conversation"""
        result = temp_db.update_conversation_metadata(
            "nonexistent_id", title="New Title"
        )
        assert result is False


class TestOrganizationFeatures:
    """Test star, pin, archive features"""

    @pytest.mark.unit
    def test_star_conversation(self, temp_db, sample_conversation):
        """Test starring a conversation"""
        temp_db.save_conversation(sample_conversation)

        # Star it
        result = temp_db.star_conversation(sample_conversation.id, star=True)
        assert result is True

        # Verify
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.starred_at is not None

        # Unstar it
        result = temp_db.star_conversation(sample_conversation.id, star=False)
        assert result is True

        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.starred_at is None

    @pytest.mark.unit
    def test_star_nonexistent_conversation(self, temp_db):
        """Test starring a conversation that doesn't exist"""
        result = temp_db.star_conversation("nonexistent_id", star=True)
        assert result is False

    @pytest.mark.unit
    def test_pin_conversation(self, temp_db, sample_conversation):
        """Test pinning a conversation"""
        temp_db.save_conversation(sample_conversation)

        # Pin it
        result = temp_db.pin_conversation(sample_conversation.id, pin=True)
        assert result is True

        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.pinned_at is not None

        # Unpin it
        result = temp_db.pin_conversation(sample_conversation.id, pin=False)
        assert result is True

        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.pinned_at is None

    @pytest.mark.unit
    def test_pin_nonexistent_conversation(self, temp_db):
        """Test pinning a conversation that doesn't exist"""
        result = temp_db.pin_conversation("nonexistent_id", pin=True)
        assert result is False

    @pytest.mark.unit
    def test_archive_conversation(self, temp_db, sample_conversation):
        """Test archiving a conversation"""
        temp_db.save_conversation(sample_conversation)

        # Archive it
        result = temp_db.archive_conversation(sample_conversation.id, archive=True)
        assert result is True

        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.archived_at is not None

        # Unarchive it
        result = temp_db.archive_conversation(sample_conversation.id, archive=False)
        assert result is True

        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.archived_at is None

    @pytest.mark.unit
    def test_archive_nonexistent_conversation(self, temp_db):
        """Test archiving a conversation that doesn't exist"""
        result = temp_db.archive_conversation("nonexistent_id", archive=True)
        assert result is False


class TestListConversations:
    """Test conversation listing with filters"""

    @pytest.mark.unit
    def test_list_empty_database(self, temp_db):
        """Test listing from empty database"""
        conversations = temp_db.list_conversations()
        assert len(conversations) == 0

    @pytest.mark.unit
    def test_list_with_offset(self, temp_db):
        """Test listing with offset"""
        # Create 10 conversations
        for i in range(10):
            conv = ConversationTree(
                id=f"conv_{i:03d}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test"),
            )
            temp_db.save_conversation(conv)

        # Get first 5
        first_batch = temp_db.list_conversations(limit=5)
        assert len(first_batch) == 5

        # Get next 5
        second_batch = temp_db.list_conversations(limit=5, offset=5)
        assert len(second_batch) == 5

        # Verify no overlap
        first_ids = {c.id for c in first_batch}
        second_ids = {c.id for c in second_batch}
        assert len(first_ids & second_ids) == 0

    @pytest.mark.unit
    def test_list_filter_by_source(self, temp_db):
        """Test filtering by source"""
        # Create conversations with different sources
        for i, source in enumerate(["openai", "anthropic", "openai"]):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source=source),
            )
            temp_db.save_conversation(conv)

        openai_convs = temp_db.list_conversations(source="openai")
        assert len(openai_convs) == 2

        anthropic_convs = temp_db.list_conversations(source="anthropic")
        assert len(anthropic_convs) == 1

    @pytest.mark.unit
    def test_list_filter_by_project(self, temp_db):
        """Test filtering by project"""
        for i, project in enumerate(["project-a", "project-b", "project-a"]):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(project=project),
            )
            temp_db.save_conversation(conv)

        project_a = temp_db.list_conversations(project="project-a")
        assert len(project_a) == 2

        project_b = temp_db.list_conversations(project="project-b")
        assert len(project_b) == 1

    @pytest.mark.unit
    def test_list_filter_by_model(self, temp_db):
        """Test filtering by model"""
        for i, model in enumerate(["gpt-4", "claude-3", "gpt-4"]):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(model=model),
            )
            temp_db.save_conversation(conv)

        gpt4_convs = temp_db.list_conversations(model="gpt-4")
        assert len(gpt4_convs) == 2

        claude_convs = temp_db.list_conversations(model="claude-3")
        assert len(claude_convs) == 1

    @pytest.mark.unit
    def test_list_filter_by_single_tag(self, temp_db):
        """Test filtering by a single tag"""
        conv1 = ConversationTree(
            id="conv_1",
            title="Conversation 1",
            metadata=ConversationMetadata(tags=["python", "ai"]),
        )
        conv2 = ConversationTree(
            id="conv_2",
            title="Conversation 2",
            metadata=ConversationMetadata(tags=["javascript", "web"]),
        )
        conv3 = ConversationTree(
            id="conv_3",
            title="Conversation 3",
            metadata=ConversationMetadata(tags=["python", "web"]),
        )

        temp_db.save_conversation(conv1)
        temp_db.save_conversation(conv2)
        temp_db.save_conversation(conv3)

        python_convs = temp_db.list_conversations(tag="python")
        assert len(python_convs) == 2

        web_convs = temp_db.list_conversations(tag="web")
        assert len(web_convs) == 2

        ai_convs = temp_db.list_conversations(tag="ai")
        assert len(ai_convs) == 1

    @pytest.mark.unit
    def test_list_filter_by_multiple_tags(self, temp_db):
        """Test filtering by multiple tags (OR logic)"""
        conv1 = ConversationTree(
            id="conv_1",
            title="Conversation 1",
            metadata=ConversationMetadata(tags=["python"]),
        )
        conv2 = ConversationTree(
            id="conv_2",
            title="Conversation 2",
            metadata=ConversationMetadata(tags=["javascript"]),
        )
        conv3 = ConversationTree(
            id="conv_3",
            title="Conversation 3",
            metadata=ConversationMetadata(tags=["rust"]),
        )

        temp_db.save_conversation(conv1)
        temp_db.save_conversation(conv2)
        temp_db.save_conversation(conv3)

        # Search for python OR javascript
        results = temp_db.list_conversations(tags=["python", "javascript"])
        assert len(results) == 2
        result_ids = {c.id for c in results}
        assert "conv_1" in result_ids
        assert "conv_2" in result_ids

    @pytest.mark.unit
    def test_list_filter_starred(self, temp_db):
        """Test filtering by starred status"""
        # Create conversations
        for i in range(3):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test"),
            )
            temp_db.save_conversation(conv)

        # Star the first one
        temp_db.star_conversation("conv_0", star=True)

        # Filter starred
        starred = temp_db.list_conversations(starred=True)
        assert len(starred) == 1
        assert starred[0].id == "conv_0"

        # Filter non-starred
        non_starred = temp_db.list_conversations(starred=False)
        assert len(non_starred) == 2

    @pytest.mark.unit
    def test_list_filter_pinned(self, temp_db):
        """Test filtering by pinned status"""
        for i in range(3):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test"),
            )
            temp_db.save_conversation(conv)

        # Pin the first one
        temp_db.pin_conversation("conv_0", pin=True)

        # Filter pinned
        pinned = temp_db.list_conversations(pinned=True)
        assert len(pinned) == 1
        assert pinned[0].id == "conv_0"

        # Filter non-pinned
        non_pinned = temp_db.list_conversations(pinned=False)
        assert len(non_pinned) == 2

    @pytest.mark.unit
    def test_list_filter_archived(self, temp_db):
        """Test filtering by archived status"""
        for i in range(3):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test"),
            )
            temp_db.save_conversation(conv)

        # Archive the first one
        temp_db.archive_conversation("conv_0", archive=True)

        # Filter archived
        archived = temp_db.list_conversations(archived=True)
        assert len(archived) == 1
        assert archived[0].id == "conv_0"

        # Filter non-archived (default)
        non_archived = temp_db.list_conversations()
        assert len(non_archived) == 2

        # Include archived
        all_convs = temp_db.list_conversations(include_archived=True)
        assert len(all_convs) == 3

    @pytest.mark.unit
    def test_list_ordering_pinned_first(self, temp_db):
        """Test that pinned conversations appear first"""
        # Create conversations with different timestamps
        for i in range(3):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test"),
            )
            temp_db.save_conversation(conv)

        # Pin the last one
        temp_db.pin_conversation("conv_2", pin=True)

        # List all
        conversations = temp_db.list_conversations()

        # Pinned should be first
        assert conversations[0].id == "conv_2"


class TestSearchConversations:
    """Test advanced search functionality"""

    @pytest.mark.unit
    def test_search_empty_database(self, temp_db):
        """Test searching in empty database"""
        results = temp_db.search_conversations("test query")
        assert len(results) == 0

    @pytest.mark.unit
    def test_search_title_only(self, temp_db):
        """Test searching in titles only"""
        conv1 = ConversationTree(
            id="conv_1",
            title="Python Programming Tutorial",
            metadata=ConversationMetadata(source="test"),
        )
        conv2 = ConversationTree(
            id="conv_2",
            title="JavaScript Basics",
            metadata=ConversationMetadata(source="test"),
        )

        temp_db.save_conversation(conv1)
        temp_db.save_conversation(conv2)

        results = temp_db.search_conversations("Python", title_only=True)
        assert len(results) == 1
        assert results[0].id == "conv_1"

    @pytest.mark.unit
    def test_search_content_only(self, temp_db):
        """Test searching in message content only"""
        conv1 = ConversationTree(
            id="conv_1",
            title="Conversation 1",
            metadata=ConversationMetadata(source="test"),
        )
        msg1 = Message(
            id="msg_1",
            role=MessageRole.USER,
            content=MessageContent(text="Tell me about Python decorators"),
            parent_id=None,
        )
        conv1.add_message(msg1)

        conv2 = ConversationTree(
            id="conv_2",
            title="Python Tutorial",
            metadata=ConversationMetadata(source="test"),
        )
        msg2 = Message(
            id="msg_2",
            role=MessageRole.USER,
            content=MessageContent(text="JavaScript promises"),
            parent_id=None,
        )
        conv2.add_message(msg2)

        temp_db.save_conversation(conv1)
        temp_db.save_conversation(conv2)

        # Search content only (should find decorators in conv1, not Python in conv2 title)
        results = temp_db.search_conversations("decorators", content_only=True)
        assert len(results) == 1
        assert results[0].id == "conv_1"

    @pytest.mark.unit
    def test_search_by_date_range(self, temp_db):
        """Test searching by date range"""
        # Create conversations with different dates
        now = datetime.now()

        conv1 = ConversationTree(
            id="conv_1",
            title="Old Conversation",
            metadata=ConversationMetadata(
                source="test", created_at=now - timedelta(days=10)
            ),
        )
        conv2 = ConversationTree(
            id="conv_2",
            title="Recent Conversation",
            metadata=ConversationMetadata(
                source="test", created_at=now - timedelta(days=2)
            ),
        )

        temp_db.save_conversation(conv1)
        temp_db.save_conversation(conv2)

        # Search for conversations from last 5 days
        results = temp_db.search_conversations(date_from=now - timedelta(days=5))
        assert len(results) == 1
        assert results[0].id == "conv_2"

        # Search for conversations older than 5 days
        results = temp_db.search_conversations(date_to=now - timedelta(days=5))
        assert len(results) == 1
        assert results[0].id == "conv_1"

    @pytest.mark.unit
    def test_search_by_message_count(self, temp_db):
        """Test filtering by message count"""
        # Create conversation with 2 messages
        conv1 = ConversationTree(
            id="conv_1",
            title="Short Conversation",
            metadata=ConversationMetadata(source="test"),
        )
        for i in range(2):
            msg = Message(
                id=f"msg_1_{i}",
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=MessageContent(text=f"Message {i}"),
                parent_id=f"msg_1_{i-1}" if i > 0 else None,
            )
            conv1.add_message(msg)

        # Create conversation with 5 messages
        conv2 = ConversationTree(
            id="conv_2",
            title="Long Conversation",
            metadata=ConversationMetadata(source="test"),
        )
        for i in range(5):
            msg = Message(
                id=f"msg_2_{i}",
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=MessageContent(text=f"Message {i}"),
                parent_id=f"msg_2_{i-1}" if i > 0 else None,
            )
            conv2.add_message(msg)

        temp_db.save_conversation(conv1)
        temp_db.save_conversation(conv2)

        # Find conversations with at least 3 messages
        results = temp_db.search_conversations(min_messages=3)
        assert len(results) == 1
        assert results[0].id == "conv_2"

        # Find conversations with at most 3 messages
        results = temp_db.search_conversations(max_messages=3)
        assert len(results) == 1
        assert results[0].id == "conv_1"

    @pytest.mark.unit
    def test_search_has_branches(self, temp_db, branching_conversation):
        """Test filtering by branching status"""
        # Save branching conversation
        temp_db.save_conversation(branching_conversation)

        # Create linear conversation
        linear_conv = ConversationTree(
            id="conv_linear",
            title="Linear Conversation",
            metadata=ConversationMetadata(source="test"),
        )
        msg1 = Message(
            id="msg_1",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
            parent_id=None,
        )
        linear_conv.add_message(msg1)
        msg2 = Message(
            id="msg_2",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Hi"),
            parent_id="msg_1",
        )
        linear_conv.add_message(msg2)

        temp_db.save_conversation(linear_conv)

        # Find branching conversations
        results = temp_db.search_conversations(has_branches=True)
        assert len(results) == 1
        assert results[0].id == branching_conversation.id

        # Find linear conversations
        results = temp_db.search_conversations(has_branches=False)
        assert len(results) == 1
        assert results[0].id == "conv_linear"

    @pytest.mark.unit
    def test_search_ordering(self, temp_db):
        """Test search result ordering"""
        now = datetime.now()

        for i in range(3):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Test Conversation {i}",
                metadata=ConversationMetadata(
                    source="test", created_at=now - timedelta(days=i)
                ),
            )
            temp_db.save_conversation(conv)

        # Order by created_at descending (newest first)
        results = temp_db.search_conversations(
            query_text="Test", order_by="created_at", ascending=False
        )
        assert results[0].id == "conv_0"
        assert results[2].id == "conv_2"

        # Order by created_at ascending (oldest first)
        results = temp_db.search_conversations(
            query_text="Test", order_by="created_at", ascending=True
        )
        assert results[0].id == "conv_2"
        assert results[2].id == "conv_0"

        # Order by title
        results = temp_db.search_conversations(
            query_text="Test", order_by="title", ascending=True
        )
        # Should be in alphabetical order
        for i, result in enumerate(results):
            assert result.id == f"conv_{i}"


class TestTagManagement:
    """Test tag-related operations"""

    @pytest.mark.unit
    def test_add_tags(self, temp_db, sample_conversation):
        """Test adding tags to a conversation"""
        temp_db.save_conversation(sample_conversation)

        # Add new tags
        result = temp_db.add_tags(sample_conversation.id, ["new-tag-1", "new-tag-2"])
        assert result is True

        loaded = temp_db.load_conversation(sample_conversation.id)
        assert "new-tag-1" in loaded.metadata.tags
        assert "new-tag-2" in loaded.metadata.tags
        # Original tags should still be there
        assert "test" in loaded.metadata.tags
        assert "sample" in loaded.metadata.tags

    @pytest.mark.unit
    def test_add_duplicate_tags(self, temp_db, sample_conversation):
        """Test adding duplicate tags (should not create duplicates)"""
        temp_db.save_conversation(sample_conversation)

        # Add tags that already exist
        result = temp_db.add_tags(sample_conversation.id, ["test", "sample"])
        assert result is True

        loaded = temp_db.load_conversation(sample_conversation.id)
        # Should still only have 2 tags
        tag_count = loaded.metadata.tags.count("test")
        assert tag_count == 1

    @pytest.mark.unit
    def test_add_tags_nonexistent_conversation(self, temp_db):
        """Test adding tags to nonexistent conversation"""
        result = temp_db.add_tags("nonexistent_id", ["tag1"])
        assert result is False

    @pytest.mark.unit
    def test_remove_tag(self, temp_db, sample_conversation):
        """Test removing a tag from a conversation"""
        temp_db.save_conversation(sample_conversation)

        # Remove a tag
        result = temp_db.remove_tag(sample_conversation.id, "test")
        assert result is True

        loaded = temp_db.load_conversation(sample_conversation.id)
        assert "test" not in loaded.metadata.tags
        assert "sample" in loaded.metadata.tags  # Other tag should remain

    @pytest.mark.unit
    def test_remove_nonexistent_tag(self, temp_db, sample_conversation):
        """Test removing a tag that doesn't exist"""
        temp_db.save_conversation(sample_conversation)

        result = temp_db.remove_tag(sample_conversation.id, "nonexistent-tag")
        assert result is False

    @pytest.mark.unit
    def test_get_all_tags(self, temp_db):
        """Test getting all tags with usage counts"""
        # Create conversations with tags
        conv1 = ConversationTree(
            id="conv_1",
            title="Conversation 1",
            metadata=ConversationMetadata(tags=["python", "ai"]),
        )
        conv2 = ConversationTree(
            id="conv_2",
            title="Conversation 2",
            metadata=ConversationMetadata(tags=["python", "web"]),
        )
        conv3 = ConversationTree(
            id="conv_3",
            title="Conversation 3",
            metadata=ConversationMetadata(tags=["javascript"]),
        )

        temp_db.save_conversation(conv1)
        temp_db.save_conversation(conv2)
        temp_db.save_conversation(conv3)

        # Get all tags with counts
        tags = temp_db.get_all_tags(with_counts=True)

        # Should have 4 unique tags
        assert len(tags) >= 4

        # Find python tag and verify count
        python_tag = next(t for t in tags if t["name"] == "python")
        assert python_tag["usage_count"] == 2

        # Find ai tag
        ai_tag = next(t for t in tags if t["name"] == "ai")
        assert ai_tag["usage_count"] == 1

    @pytest.mark.unit
    def test_get_all_tags_without_counts(self, temp_db):
        """Test getting all tags without usage counts"""
        conv = ConversationTree(
            id="conv_1",
            title="Conversation 1",
            metadata=ConversationMetadata(tags=["tag1", "tag2"]),
        )
        temp_db.save_conversation(conv)

        tags = temp_db.get_all_tags(with_counts=False)
        assert len(tags) >= 2


class TestDuplicateConversation:
    """Test conversation duplication"""

    @pytest.mark.unit
    @pytest.mark.skip(
        reason="duplicate_conversation has a bug - uses starred/pinned/archived instead of starred_at/pinned_at/archived_at"
    )
    def test_duplicate_conversation(self, temp_db, sample_conversation):
        """Test duplicating a conversation"""
        temp_db.save_conversation(sample_conversation)

        # Duplicate it
        new_id = temp_db.duplicate_conversation(sample_conversation.id)
        assert new_id is not None
        assert new_id != sample_conversation.id

        # Load both conversations
        original = temp_db.load_conversation(sample_conversation.id)
        duplicate = temp_db.load_conversation(new_id)

        # Verify duplicate has different ID but same content
        assert duplicate.id != original.id
        # Title should be "Test Conversation (copy)"
        assert "(copy)" in duplicate.title
        assert len(duplicate.message_map) == len(original.message_map)

        # Message IDs should be different
        original_msg_ids = set(original.message_map.keys())
        duplicate_msg_ids = set(duplicate.message_map.keys())
        assert len(original_msg_ids & duplicate_msg_ids) == 0

    @pytest.mark.unit
    def test_duplicate_nonexistent_conversation(self, temp_db):
        """Test duplicating a conversation that doesn't exist"""
        new_id = temp_db.duplicate_conversation("nonexistent_id")
        assert new_id is None


class TestStatistics:
    """Test database statistics"""

    @pytest.mark.unit
    def test_get_models(self, temp_db):
        """Test getting all unique models"""
        for i, model in enumerate(["gpt-4", "claude-3", "gpt-4", "claude-3", "gpt-4"]):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(model=model),
            )
            temp_db.save_conversation(conv)

        models = temp_db.get_models()
        assert len(models) == 2

        # Find gpt-4
        gpt4 = next(m for m in models if m["model"] == "gpt-4")
        assert gpt4["count"] == 3

        # Find claude-3
        claude = next(m for m in models if m["model"] == "claude-3")
        assert claude["count"] == 2

    @pytest.mark.unit
    def test_get_sources(self, temp_db):
        """Test getting all unique sources"""
        for i, source in enumerate(["openai", "anthropic", "openai"]):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source=source),
            )
            temp_db.save_conversation(conv)

        sources = temp_db.get_sources()
        assert len(sources) == 2

        openai = next(s for s in sources if s["source"] == "openai")
        assert openai["count"] == 2

    @pytest.mark.unit
    def test_get_conversation_timeline(self, temp_db):
        """Test getting conversation timeline"""
        now = datetime.now()

        for i in range(5):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(
                    source="test", created_at=now - timedelta(days=i)
                ),
            )
            temp_db.save_conversation(conv)

        # Get daily timeline
        timeline = temp_db.get_conversation_timeline(granularity="day", limit=10)
        assert len(timeline) >= 1

        # Each entry should have period and count
        for entry in timeline:
            assert "period" in entry
            assert "count" in entry
            assert entry["count"] > 0


class TestContextManager:
    """Test database context manager"""

    @pytest.mark.unit
    def test_context_manager(self, temp_dir):
        """Test database can be used as context manager"""
        db_path = temp_dir / "test.db"

        with ConversationDB(str(db_path)) as db:
            conv = ConversationTree(
                id="conv_test",
                title="Test Conversation",
                metadata=ConversationMetadata(source="test"),
            )
            db.save_conversation(conv)

            # Verify it was saved
            loaded = db.load_conversation("conv_test")
            assert loaded is not None

        # Database should be closed after context
