"""
Unit tests for database operations
"""

import pytest
from datetime import datetime
import json

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationTree, Message, MessageContent,
    MessageRole, ConversationMetadata
)


class TestConversationDB:
    """Test ConversationDB class"""
    
    @pytest.mark.unit
    def test_database_creation(self, temp_dir):
        """Test creating a new database"""
        db_path = temp_dir / "test.db"
        db = ConversationDB(str(db_path))
        
        assert db_path.exists()
        
        # Check tables exist
        from sqlalchemy import text
        with db.Session() as session:
            result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = [row[0] for row in result]
            assert "conversations" in tables
            assert "messages" in tables
            assert "tags" in tables
            assert "conversation_tags" in tables
        
        db.close()
    
    @pytest.mark.unit
    def test_save_conversation(self, temp_db, sample_conversation):
        """Test saving a conversation"""
        conv_id = temp_db.save_conversation(sample_conversation)
        
        assert conv_id == sample_conversation.id
        
        # Verify in database
        from sqlalchemy import text
        with temp_db.Session() as session:
            result = session.execute(
                text("SELECT COUNT(*) FROM conversations WHERE id = :id"),
                {"id": conv_id}
            )
            count = result.scalar()
            assert count == 1
    
    @pytest.mark.unit
    def test_load_conversation(self, temp_db, sample_conversation):
        """Test loading a conversation"""
        # Save first
        temp_db.save_conversation(sample_conversation)
        
        # Load it back
        loaded = temp_db.load_conversation(sample_conversation.id)
        
        assert loaded is not None
        assert loaded.id == sample_conversation.id
        assert loaded.title == sample_conversation.title
        assert len(loaded.message_map) == len(sample_conversation.message_map)
        assert loaded.metadata.source == sample_conversation.metadata.source
    
    @pytest.mark.unit
    def test_load_nonexistent_conversation(self, temp_db):
        """Test loading a conversation that doesn't exist"""
        loaded = temp_db.load_conversation("nonexistent_id")
        assert loaded is None
    
    @pytest.mark.unit
    def test_list_conversations(self, temp_db):
        """Test listing conversations"""
        # Save multiple conversations
        for i in range(5):
            conv = ConversationTree(
                id=f"conv_{i:03d}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(source="test")
            )
            temp_db.save_conversation(conv)
        
        # List all
        conversations = temp_db.list_conversations()
        assert len(conversations) == 5
        
        # List with limit
        limited = temp_db.list_conversations(limit=3)
        assert len(limited) == 3
        
        # Check fields
        first = conversations[0]
        assert "id" in first
        assert "title" in first
        assert "created_at" in first
        assert "updated_at" in first
    
    @pytest.mark.unit
    def test_conversation_with_tags(self, temp_db):
        """Test saving and loading conversations with tags"""
        conv = ConversationTree(
            id="conv_tags",
            title="Tagged Conversation",
            metadata=ConversationMetadata(
                source="test",
                tags=["python", "ai", "chatbot"]
            )
        )
        
        temp_db.save_conversation(conv)
        loaded = temp_db.load_conversation("conv_tags")
        
        assert set(loaded.metadata.tags) == {"python", "ai", "chatbot"}
    
    @pytest.mark.unit
    def test_update_conversation(self, temp_db, sample_conversation):
        """Test updating an existing conversation"""
        # Save initial
        temp_db.save_conversation(sample_conversation)
        
        # Modify and save again
        sample_conversation.title = "Updated Title"
        sample_conversation.metadata.tags = ["updated", "modified"]
        
        # Add a new message
        new_msg = Message(
            id="msg_005",
            role=MessageRole.USER,
            content=MessageContent(text="New message"),
            parent_id="msg_004"
        )
        sample_conversation.add_message(new_msg)
        
        temp_db.save_conversation(sample_conversation)
        
        # Load and verify
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded.title == "Updated Title"
        assert "updated" in loaded.metadata.tags
        assert len(loaded.message_map) == 5  # Original 4 + 1 new
    
    @pytest.mark.unit
    def test_search_conversations(self, temp_db):
        """Test searching conversations"""
        # Create conversations with different content
        conversations = [
            ConversationTree(
                id="conv_python",
                title="Python Programming",
                metadata=ConversationMetadata(source="test")
            ),
            ConversationTree(
                id="conv_javascript",
                title="JavaScript Tutorial",
                metadata=ConversationMetadata(source="test")
            ),
            ConversationTree(
                id="conv_ml",
                title="Machine Learning Basics",
                metadata=ConversationMetadata(source="test")
            )
        ]
        
        # Add messages with searchable content
        for conv in conversations:
            if "python" in conv.id:
                msg = Message(
                    id=f"{conv.id}_msg1",
                    role=MessageRole.USER,
                    content=MessageContent(text="Tell me about Python decorators")
                )
            elif "javascript" in conv.id:
                msg = Message(
                    id=f"{conv.id}_msg1",
                    role=MessageRole.USER,
                    content=MessageContent(text="Explain JavaScript promises")
                )
            else:
                msg = Message(
                    id=f"{conv.id}_msg1",
                    role=MessageRole.USER,
                    content=MessageContent(text="What is neural network training?")
                )
            conv.add_message(msg)
            temp_db.save_conversation(conv)
        
        # Search for Python
        results = temp_db.search_conversations("Python")
        assert len(results) == 1
        assert results[0]["id"] == "conv_python"
        
        # Search for JavaScript
        results = temp_db.search_conversations("JavaScript")
        assert len(results) == 1
        assert results[0]["id"] == "conv_javascript"
        
        # Search in message content
        results = temp_db.search_conversations("neural network")
        assert len(results) == 1
        assert results[0]["id"] == "conv_ml"
    
    @pytest.mark.unit
    def test_get_statistics(self, temp_db):
        """Test getting database statistics"""
        # Add some conversations
        for i in range(3):
            conv = ConversationTree(
                id=f"conv_{i}",
                title=f"Conversation {i}",
                metadata=ConversationMetadata(
                    source="openai" if i == 0 else "anthropic"
                )
            )
            
            # Add messages
            for j in range(4):
                role = MessageRole.USER if j % 2 == 0 else MessageRole.ASSISTANT
                msg = Message(
                    id=f"msg_{i}_{j}",
                    role=role,
                    content=MessageContent(text=f"Message {j}"),
                    parent_id=f"msg_{i}_{j-1}" if j > 0 else None
                )
                conv.add_message(msg)
            
            temp_db.save_conversation(conv)
        
        stats = temp_db.get_statistics()
        
        assert stats["total_conversations"] == 3
        assert stats["total_messages"] == 12  # 3 conversations * 4 messages
        assert stats["messages_by_role"]["user"] == 6
        assert stats["messages_by_role"]["assistant"] == 6
        assert stats["conversations_by_source"]["openai"] == 1
        assert stats["conversations_by_source"]["anthropic"] == 2
    
    @pytest.mark.unit
    def test_branching_conversation_storage(self, temp_db, branching_conversation):
        """Test storing and retrieving branching conversations"""
        temp_db.save_conversation(branching_conversation)
        loaded = temp_db.load_conversation(branching_conversation.id)
        
        # Verify structure is preserved
        assert len(loaded.message_map) == len(branching_conversation.message_map)
        
        # Verify branches
        children = loaded.get_children("msg_001")
        assert len(children) == 2
        
        # Verify paths
        paths = loaded.get_all_paths()
        assert len(paths) == 2
    
    @pytest.mark.unit
    def test_delete_conversation(self, temp_db, sample_conversation):
        """Test deleting a conversation"""
        # Save conversation
        temp_db.save_conversation(sample_conversation)
        
        # Verify it exists
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded is not None
        
        # Delete it
        success = temp_db.delete_conversation(sample_conversation.id)
        assert success
        
        # Verify it's gone
        loaded = temp_db.load_conversation(sample_conversation.id)
        assert loaded is None
        
        # Verify messages are also deleted
        with temp_db.Session() as session:
            from sqlalchemy import text
            result = session.execute(
                text("SELECT COUNT(*) FROM messages WHERE conversation_id = :id"),
                {"id": sample_conversation.id}
            )
            count = result.scalar()
            assert count == 0
    
    @pytest.mark.unit
    def test_conversation_metadata_persistence(self, temp_db):
        """Test that all metadata fields are persisted correctly"""
        meta = ConversationMetadata(
            source="custom",
            model="gpt-4-turbo",
            tags=["test", "metadata"],
            project="test-project",
            custom_data={"key": "value", "number": 42}
        )
        
        conv = ConversationTree(
            id="conv_meta",
            title="Metadata Test",
            metadata=meta
        )
        
        temp_db.save_conversation(conv)
        loaded = temp_db.load_conversation("conv_meta")
        
        assert loaded.metadata.source == "custom"
        assert loaded.metadata.model == "gpt-4-turbo"
        assert set(loaded.metadata.tags) == {"test", "metadata"}
        assert loaded.metadata.project == "test-project"
        assert loaded.metadata.custom_data == {"key": "value", "number": 42}