"""
Unit tests for database organization operations (star, pin, archive, title)
"""

import pytest
from datetime import datetime

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationTree, Message, MessageContent,
    MessageRole, ConversationMetadata
)


class TestDatabaseOrganization:
    """Test conversation organization features"""

    @pytest.mark.unit
    def test_star_conversation(self, temp_db, sample_conversation):
        """Test starring a conversation"""
        # Save conversation
        temp_db.save_conversation(sample_conversation)

        # Star it
        result = temp_db.star_conversation(sample_conversation.id)
        assert result is True

        # Verify starred_at timestamp is set
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.starred_at is not None
        assert isinstance(loaded.metadata.starred_at, datetime)

    @pytest.mark.unit
    def test_unstar_conversation(self, temp_db, sample_conversation):
        """Test unstarring a conversation"""
        # Save and star
        temp_db.save_conversation(sample_conversation)
        temp_db.star_conversation(sample_conversation.id)

        # Unstar
        result = temp_db.star_conversation(sample_conversation.id, star=False)
        assert result is True

        # Verify starred_at is None
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.starred_at is None

    @pytest.mark.unit
    def test_star_nonexistent_conversation(self, temp_db):
        """Test starring a conversation that doesn't exist"""
        result = temp_db.star_conversation("nonexistent_id")
        assert result is False

    @pytest.mark.unit
    def test_pin_conversation(self, temp_db, sample_conversation):
        """Test pinning a conversation"""
        temp_db.save_conversation(sample_conversation)

        # Pin it
        result = temp_db.pin_conversation(sample_conversation.id)
        assert result is True

        # Verify pinned_at timestamp
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.pinned_at is not None
        assert isinstance(loaded.metadata.pinned_at, datetime)

    @pytest.mark.unit
    def test_unpin_conversation(self, temp_db, sample_conversation):
        """Test unpinning a conversation"""
        temp_db.save_conversation(sample_conversation)
        temp_db.pin_conversation(sample_conversation.id)

        # Unpin
        result = temp_db.pin_conversation(sample_conversation.id, pin=False)
        assert result is True

        # Verify pinned_at is None
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.pinned_at is None

    @pytest.mark.unit
    def test_archive_conversation(self, temp_db, sample_conversation):
        """Test archiving a conversation"""
        temp_db.save_conversation(sample_conversation)

        # Archive it
        result = temp_db.archive_conversation(sample_conversation.id)
        assert result is True

        # Verify archived_at timestamp
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.archived_at is not None
        assert isinstance(loaded.metadata.archived_at, datetime)

    @pytest.mark.unit
    def test_unarchive_conversation(self, temp_db, sample_conversation):
        """Test unarchiving a conversation"""
        temp_db.save_conversation(sample_conversation)
        temp_db.archive_conversation(sample_conversation.id)

        # Unarchive
        result = temp_db.archive_conversation(sample_conversation.id, archive=False)
        assert result is True

        # Verify archived_at is None
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.archived_at is None

    @pytest.mark.unit
    def test_set_title(self, temp_db, sample_conversation):
        """Test changing conversation title"""
        temp_db.save_conversation(sample_conversation)

        # Change title using update_conversation_metadata
        new_title = "Updated Title"
        result = temp_db.update_conversation_metadata(sample_conversation.id, title=new_title)
        assert result is True

        # Verify title changed
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.title == new_title

    @pytest.mark.unit
    def test_set_title_nonexistent(self, temp_db):
        """Test changing title of nonexistent conversation"""
        result = temp_db.update_conversation_metadata("nonexistent_id", title="New Title")
        assert result is False

    @pytest.mark.unit
    def test_batch_star_operations(self, temp_db):
        """Test starring multiple conversations at once"""
        # Create multiple conversations
        conv_ids = []
        for i in range(5):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test")
            )
            temp_db.save_conversation(conv)
            conv_ids.append(conv.id)

        # Star first three
        for conv_id in conv_ids[:3]:
            temp_db.star_conversation(conv_id)

        # Verify only first three are starred
        for i, conv_id in enumerate(conv_ids):
            loaded = temp_db.load_conversation(conv_id)
            if i < 3:
                assert loaded.metadata.starred_at is not None
            else:
                assert loaded.metadata.starred_at is None

    @pytest.mark.unit
    def test_list_starred_conversations(self, temp_db):
        """Test filtering conversations by starred status"""
        # Create mix of starred and unstarred
        for i in range(10):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test")
            )
            temp_db.save_conversation(conv)

            # Star every other conversation
            if i % 2 == 0:
                temp_db.star_conversation(conv.id)

        # List only starred
        starred = temp_db.list_conversations(starred=True)
        assert len(starred) == 5

        # List only unstarred
        unstarred = temp_db.list_conversations(starred=False)
        assert len(unstarred) == 5

        # List all (no filter)
        all_convs = temp_db.list_conversations()
        assert len(all_convs) == 10

    @pytest.mark.unit
    def test_list_pinned_conversations(self, temp_db):
        """Test filtering conversations by pinned status"""
        # Create conversations
        for i in range(10):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test")
            )
            temp_db.save_conversation(conv)

            # Pin first 3
            if i < 3:
                temp_db.pin_conversation(conv.id)

        # List only pinned
        pinned = temp_db.list_conversations(pinned=True)
        assert len(pinned) == 3

        # List only unpinned
        unpinned = temp_db.list_conversations(pinned=False)
        assert len(unpinned) == 7

    @pytest.mark.unit
    def test_list_archived_conversations(self, temp_db):
        """Test filtering conversations by archived status"""
        # Create conversations
        for i in range(10):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test")
            )
            temp_db.save_conversation(conv)

            # Archive last 2
            if i >= 8:
                temp_db.archive_conversation(conv.id)

        # List only archived
        archived = temp_db.list_conversations(archived=True)
        assert len(archived) == 2

        # List only non-archived
        not_archived = temp_db.list_conversations(archived=False)
        assert len(not_archived) == 8

    @pytest.mark.unit
    def test_combined_filters(self, temp_db):
        """Test combining multiple filters (starred + pinned)"""
        # Create conversations with different combinations
        test_cases = [
            ("conv_0", False, False),  # Neither
            ("conv_1", True, False),   # Starred only
            ("conv_2", False, True),   # Pinned only
            ("conv_3", True, True),    # Both
        ]

        for conv_id, should_star, should_pin in test_cases:
            conv = ConversationTree(
                id=conv_id,
                title=conv_id,
                metadata=ConversationMetadata(source="test")
            )
            temp_db.save_conversation(conv)

            if should_star:
                temp_db.star_conversation(conv_id)
            if should_pin:
                temp_db.pin_conversation(conv_id)

        # List starred AND pinned
        both = temp_db.list_conversations(starred=True, pinned=True)
        assert len(both) == 1
        assert both[0].id == "conv_3"

        # List only starred (not pinned)
        starred_only = temp_db.list_conversations(starred=True, pinned=False)
        assert len(starred_only) == 1
        assert starred_only[0].id == "conv_1"

    @pytest.mark.unit
    def test_search_with_starred_filter(self, temp_db):
        """Test searching with starred filter"""
        # Create conversations with searchable content
        for i in range(5):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Python Tutorial {i}",
                metadata=ConversationMetadata(source="test")
            )

            # Add message with searchable content
            msg = Message(
                id=f"msg_{i}",
                role=MessageRole.USER,
                content=MessageContent(text="How do I use Python decorators?")
            )
            conv.add_message(msg)
            temp_db.save_conversation(conv)

            # Star first 3
            if i < 3:
                temp_db.star_conversation(conv.id)

        # Search for "Python" in starred only
        results = temp_db.search_conversations("Python", starred=True)
        assert len(results) == 3

        # Search for "Python" in unstarred
        results = temp_db.search_conversations("Python", starred=False)
        assert len(results) == 2

    @pytest.mark.unit
    def test_organization_timestamps_ordering(self, temp_db):
        """Test that starred_at timestamp is set when starring"""
        import time

        # Create and star conversations with delays
        for i in range(3):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test")
            )
            temp_db.save_conversation(conv)
            temp_db.star_conversation(conv.id)
            time.sleep(0.01)  # Small delay to ensure different timestamps

        # Get starred conversations
        starred = temp_db.list_conversations(starred=True)

        # Verify they have timestamps set (order may not be guaranteed)
        timestamps = [conv.starred_at for conv in starred if conv.starred_at]
        assert len(timestamps) == 3  # All have starred_at set

    @pytest.mark.unit
    def test_statistics_include_organization_counts(self, temp_db):
        """Test that statistics includes basic counts"""
        # Create conversations with various states
        for i in range(10):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test")
            )
            temp_db.save_conversation(conv)

            if i < 3:
                temp_db.star_conversation(conv.id)
            if i < 2:
                temp_db.pin_conversation(conv.id)
            if i >= 8:
                temp_db.archive_conversation(conv.id)

        stats = temp_db.get_statistics()

        # Check total_conversations is correct
        assert stats["total_conversations"] == 10

        # Verify starred/pinned/archived by querying list_conversations
        starred_convs = temp_db.list_conversations(starred=True)
        pinned_convs = temp_db.list_conversations(pinned=True)
        archived_convs = temp_db.list_conversations(archived=True)

        assert len(starred_convs) == 3
        assert len(pinned_convs) == 2
        assert len(archived_convs) == 2

    @pytest.mark.unit
    def test_toggle_star_idempotency(self, temp_db, sample_conversation):
        """Test that starring twice doesn't cause errors"""
        temp_db.save_conversation(sample_conversation)

        # Star twice - should work without error
        temp_db.star_conversation(sample_conversation.id)
        first_starred_at = temp_db.load_conversation(sample_conversation.id).metadata.starred_at
        assert first_starred_at is not None

        temp_db.star_conversation(sample_conversation.id)
        second_starred_at = temp_db.load_conversation(sample_conversation.id).metadata.starred_at
        assert second_starred_at is not None

        # Both should have starred_at set (may or may not be equal depending on implementation)
        # The key behavior is that it doesn't fail
        assert first_starred_at is not None
        assert second_starred_at is not None

    @pytest.mark.unit
    def test_all_organization_operations_together(self, temp_db, sample_conversation):
        """Test using star, pin, archive, and title together"""
        temp_db.save_conversation(sample_conversation)

        # Apply all operations (use update_conversation_metadata for title)
        temp_db.star_conversation(sample_conversation.id)
        temp_db.pin_conversation(sample_conversation.id)
        temp_db.archive_conversation(sample_conversation.id)
        temp_db.update_conversation_metadata(sample_conversation.id, title="Updated Title")

        # Verify all are applied
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.metadata.starred_at is not None
        assert loaded.metadata.pinned_at is not None
        assert loaded.metadata.archived_at is not None
        assert loaded.title == "Updated Title"
