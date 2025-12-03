"""
Quick tests to boost coverage for core modules
"""

import pytest
import tempfile
import os
from pathlib import Path

from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationTree, Message, MessageContent,
    MessageRole, ConversationMetadata
)
from ctk.core.config import Config
from ctk.core.plugin import PluginRegistry, ImporterPlugin, ExporterPlugin


class TestDatabaseAdditionalCoverage:
    """Additional database tests for coverage"""
    
    @pytest.mark.unit
    def test_database_context_manager(self):
        """Test database as context manager"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            with ConversationDB(db_path) as db:
                assert db is not None
                assert os.path.exists(db_path)

            # Database should be closed after context
            assert not hasattr(db, 'session') or db.session is None
    
    @pytest.mark.unit
    def test_get_conversation_by_id(self):
        """Test getting conversation by ID"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            with ConversationDB(db_path) as db:
                # Create a conversation
                conv = ConversationTree(
                    id="test-123",
                    title="Test Conv",
                    metadata=ConversationMetadata(source="test", model="test-model")
                )
                msg = Message(
                    id="msg-1",
                    role=MessageRole.USER,
                    content=MessageContent(text="Hello")
                )
                conv.add_message(msg)
                db.save_conversation(conv)

                # Get it back (use load_conversation not get_conversation)
                retrieved = db.load_conversation("test-123")
                assert retrieved is not None
                assert retrieved.id == "test-123"
                assert retrieved.title == "Test Conv"

                # Try non-existent
                none_conv = db.load_conversation("non-existent")
                assert none_conv is None
    
    @pytest.mark.unit
    def test_update_conversation(self):
        """Test updating a conversation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            with ConversationDB(db_path) as db:
                # Create
                conv = ConversationTree(
                    id="update-test",
                    title="Original",
                    metadata=ConversationMetadata(source="test", model="test-model")
                )
                msg = Message(id="msg-1", role=MessageRole.USER, content=MessageContent(text="Hi"))
                conv.add_message(msg)
                db.save_conversation(conv)

                # Update
                conv.title = "Updated Title"
                msg2 = Message(id="msg-2", role=MessageRole.ASSISTANT, content=MessageContent(text="Hello"))
                conv.add_message(msg2)
                db.save_conversation(conv)

                # Verify (use load_conversation)
                retrieved = db.load_conversation("update-test")
                assert retrieved.title == "Updated Title"
                assert len(retrieved.message_map) == 2
    
    @pytest.mark.unit
    def test_delete_conversation(self):
        """Test deleting a conversation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            with ConversationDB(db_path) as db:
                # Create
                conv = ConversationTree(
                    id="delete-test",
                    title="To Delete",
                    metadata=ConversationMetadata(source="test", model="test-model")
                )
                msg = Message(id="msg-1", role=MessageRole.USER, content=MessageContent(text="Hi"))
                conv.add_message(msg)
                db.save_conversation(conv)

                # Verify it exists (use load_conversation)
                assert db.load_conversation("delete-test") is not None

                # Delete
                result = db.delete_conversation("delete-test")
                assert result is True

                # Verify it's gone
                assert db.load_conversation("delete-test") is None

                # Try deleting non-existent
                result = db.delete_conversation("non-existent")
                assert result is False


class TestConfigCoverage:
    """Test Config class for coverage"""
    
    @pytest.mark.unit
    def test_config_initialization(self):
        """Test Config initialization"""
        config = Config()
        assert config is not None
        assert hasattr(config, 'get')
    
    @pytest.mark.unit
    def test_config_get_with_default(self):
        """Test Config.get with default value"""
        config = Config()
        value = config.get('nonexistent_key', default='default_value')
        assert value == 'default_value'
    
    @pytest.mark.unit
    def test_config_set_and_get(self):
        """Test Config.set and get"""
        config = Config()
        config.set('test_key', 'test_value')
        value = config.get('test_key')
        assert value == 'test_value'


class TestPluginRegistryCoverage:
    """Test PluginRegistry for coverage"""
    
    @pytest.mark.unit
    def test_registry_discover_plugins(self):
        """Test plugin discovery"""
        registry = PluginRegistry()

        # Should discover built-in plugins (use list_importers/list_exporters)
        importers = registry.list_importers()
        assert len(importers) > 0

        exporters = registry.list_exporters()
        assert len(exporters) > 0
    
    @pytest.mark.unit
    def test_get_importer_by_name(self):
        """Test getting importer by name"""
        registry = PluginRegistry()
        
        # Get OpenAI importer
        importer = registry.get_importer('openai')
        assert importer is not None
        assert importer.name == 'openai'
    
    @pytest.mark.unit
    def test_get_exporter_by_name(self):
        """Test getting exporter by name"""
        registry = PluginRegistry()
        
        # Get JSON exporter
        exporter = registry.get_exporter('json')
        assert exporter is not None
        assert exporter.name == 'json'
    
    @pytest.mark.unit
    def test_list_plugin_names(self):
        """Test listing plugin names"""
        registry = PluginRegistry()

        # list_importers returns names directly (list of strings)
        importer_names = registry.list_importers()
        assert 'openai' in importer_names
        assert 'anthropic' in importer_names

        exporter_names = registry.list_exporters()
        assert 'json' in exporter_names
        assert 'jsonl' in exporter_names


class TestModelsCoverage:
    """Additional model tests for coverage"""
    
    @pytest.mark.unit
    def test_message_content_equality(self):
        """Test MessageContent equality"""
        c1 = MessageContent(text="Hello")
        c2 = MessageContent(text="Hello")
        c3 = MessageContent(text="Goodbye")
        
        assert c1 == c2
        assert c1 != c3
    
    @pytest.mark.unit
    def test_message_with_parent(self):
        """Test message with parent relationship"""
        parent = Message(
            id="parent",
            role=MessageRole.USER,
            content=MessageContent(text="Question")
        )
        
        child = Message(
            id="child",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Answer"),
            parent_id="parent"
        )
        
        assert child.parent_id == "parent"
    
    @pytest.mark.unit
    def test_conversation_tree_repr(self):
        """Test ConversationTree string representation"""
        conv = ConversationTree(
            id="test",
            title="Test",
            metadata=ConversationMetadata(source="test", model="test-model")
        )
        
        repr_str = repr(conv)
        assert "ConversationTree" in repr_str
        assert "test" in repr_str
    
    @pytest.mark.unit
    def test_metadata_with_tags(self):
        """Test ConversationMetadata with tags"""
        metadata = ConversationMetadata(
            source="test",
            model="test-model",
            tags=["tag1", "tag2", "tag3"]
        )
        
        assert "tag1" in metadata.tags
        assert "tag2" in metadata.tags
        assert "tag3" in metadata.tags
        assert len(metadata.tags) == 3
    
    @pytest.mark.unit
    def test_conversation_get_children(self):
        """Test getting children of a message"""
        conv = ConversationTree(id="test", title="Test")
        
        parent = Message(id="p1", role=MessageRole.USER, content=MessageContent(text="Q"))
        child1 = Message(id="c1", role=MessageRole.ASSISTANT, content=MessageContent(text="A1"), parent_id="p1")
        child2 = Message(id="c2", role=MessageRole.ASSISTANT, content=MessageContent(text="A2"), parent_id="p1")
        
        conv.add_message(parent)
        conv.add_message(child1)
        conv.add_message(child2)
        
        children = conv.get_children("p1")
        assert len(children) == 2
        assert any(c.id == "c1" for c in children)
        assert any(c.id == "c2" for c in children)
    
    @pytest.mark.unit
    def test_conversation_get_message(self):
        """Test getting a specific message by ID via message_map"""
        conv = ConversationTree(id="test", title="Test")

        msg = Message(id="msg1", role=MessageRole.USER, content=MessageContent(text="Hello"))
        conv.add_message(msg)

        # Use message_map directly (there's no get_message method)
        retrieved = conv.message_map.get("msg1")
        assert retrieved is not None
        assert retrieved.id == "msg1"
        assert retrieved.content.text == "Hello"

        # Non-existent message
        none_msg = conv.message_map.get("nonexistent")
        assert none_msg is None
    
    @pytest.mark.unit
    def test_message_roles(self):
        """Test different message roles"""
        user_msg = Message(id="u", role=MessageRole.USER, content=MessageContent(text="Q"))
        assert user_msg.role == MessageRole.USER
        
        assistant_msg = Message(id="a", role=MessageRole.ASSISTANT, content=MessageContent(text="A"))
        assert assistant_msg.role == MessageRole.ASSISTANT
        
        system_msg = Message(id="s", role=MessageRole.SYSTEM, content=MessageContent(text="S"))
        assert system_msg.role == MessageRole.SYSTEM
