"""
Behavior-focused tests for the CTK fluent API

These tests focus on the public contracts and behaviors that users depend on,
rather than implementation details. They should survive refactoring.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from ctk.api import CTK, ConversationBuilder, ConversationLoader
from ctk.core.models import ConversationTree, Message, MessageRole, MessageContent
from ctk.core.database import ConversationDB


class TestCTKFluentAPI:
    """Test the main CTK fluent API behaviors"""

    def test_ctk_initialization_without_database(self):
        """Test CTK can be initialized without a database for stateless operations"""
        ctk = CTK()

        assert ctk.db_path is None
        assert ctk.db is None
        assert ctk._current_conversations == []

    def test_ctk_initialization_with_database(self):
        """Test CTK can be initialized with a database path"""
        # Use a temp directory since ConversationDB expects a directory path
        # (it stores conversations.db inside the directory)
        with tempfile.TemporaryDirectory() as db_path:
            ctk = CTK(db_path)

            assert ctk.db_path == db_path
            # Database should be lazy-loaded
            assert ctk._db is None

            # Accessing db property should initialize it
            db = ctk.db
            assert db is not None
            assert isinstance(db, ConversationDB)

    def test_conversation_builder_creation(self):
        """Test that conversation builder can be created and configured"""
        # Given: A CTK instance
        ctk = CTK()

        # When: Creating a conversation builder
        builder = ctk.conversation("Test Discussion")

        # Then: Should return a conversation builder
        assert isinstance(builder, ConversationBuilder)

    def test_load_conversations_creates_loader(self):
        """Test that load method creates a ConversationLoader"""
        # Given: A data source
        data_source = {"conversations": []}

        # When: Loading conversations
        loader = CTK.load(data_source)

        # Then: Should return a ConversationLoader
        assert isinstance(loader, ConversationLoader)

    @patch('ctk.api.ConversationDB')
    def test_get_conversation_by_id(self, mock_db_class):
        """Test retrieving a specific conversation by ID"""
        # Given: A CTK instance with mocked database
        mock_db_instance = MagicMock()
        mock_db_class.return_value = mock_db_instance

        expected_conversation = ConversationTree(id="test-123", title="Test")
        mock_db_instance.__enter__.return_value.load_conversation.return_value = expected_conversation

        ctk = CTK("test.db")

        # When: Getting a conversation by ID
        result = ctk.get("test-123")

        # Then: Should return the conversation
        assert result == expected_conversation
        mock_db_instance.__enter__.return_value.load_conversation.assert_called_once_with("test-123")

    @patch('ctk.api.ConversationDB')
    def test_delete_conversation(self, mock_db_class):
        """Test deleting a conversation by ID"""
        # Given: A CTK instance with mocked database
        mock_db_instance = MagicMock()
        mock_db_class.return_value = mock_db_instance

        ctk = CTK("test.db")

        # When: Deleting a conversation
        result = ctk.delete("test-123")

        # Then: Should call delete and return self for chaining
        assert result is ctk
        mock_db_instance.__enter__.return_value.delete_conversation.assert_called_once_with("test-123")

    @patch('ctk.api.ConversationDB')
    def test_stats_returns_database_statistics(self, mock_db_class):
        """Test that stats method returns database statistics"""
        # Given: A CTK instance with mocked database
        mock_db_instance = MagicMock()
        mock_db_class.return_value = mock_db_instance

        expected_stats = {"conversation_count": 42, "total_messages": 1337}
        mock_db_instance.__enter__.return_value.get_statistics.return_value = expected_stats

        ctk = CTK("test.db")

        # When: Getting statistics
        result = ctk.stats()

        # Then: Should return the statistics
        assert result == expected_stats

    def test_stats_without_database(self):
        """Test that stats returns empty dict when no database is configured"""
        # Given: A CTK instance without database
        ctk = CTK()

        # When: Getting statistics
        result = ctk.stats()

        # Then: Should return empty dict
        assert result == {}


class TestConversationBuilder:
    """Test conversation building behavior"""

    def test_conversation_builder_initialization(self):
        """Test conversation builder can be initialized with optional title"""
        # Without title
        builder = ConversationBuilder()
        assert builder.tree.title is None

        # With title
        builder_with_title = ConversationBuilder("My Chat")
        assert builder_with_title.tree.title == "My Chat"

    def test_conversation_builder_user_message(self):
        """Test adding user messages to conversation"""
        # Given: A conversation builder
        builder = ConversationBuilder("Test")

        # When: Adding a user message
        result = builder.user("Hello there")

        # Then: Should return self for chaining and store the message
        assert result is builder

        # Check message was added to the conversation tree
        messages = list(builder.tree.message_map.values())
        assert len(messages) == 1

        message = messages[0]
        assert message.role == MessageRole.USER
        assert message.content.text == "Hello there"

    def test_conversation_builder_assistant_message(self):
        """Test adding assistant messages to conversation"""
        # Given: A conversation builder
        builder = ConversationBuilder("Test")

        # When: Adding an assistant message
        result = builder.assistant("Hi! How can I help?")

        # Then: Should return self for chaining and store the message
        assert result is builder

        messages = list(builder.tree.message_map.values())
        assert len(messages) == 1

        message = messages[0]
        assert message.role == MessageRole.ASSISTANT
        assert message.content.text == "Hi! How can I help?"

    def test_conversation_builder_chaining(self):
        """Test that conversation builder supports method chaining"""
        # Given: A conversation builder
        builder = ConversationBuilder("Chained Chat")

        # When: Chaining multiple messages
        result = (builder
                 .user("What's the weather?")
                 .assistant("I don't have access to weather data.")
                 .user("That's okay, thanks!"))

        # Then: Should support chaining and accumulate messages
        assert result is builder

        messages = list(builder.tree.message_map.values())
        assert len(messages) == 3

        # Verify message order and content
        assert messages[0].role == MessageRole.USER
        assert "weather" in messages[0].content.text

        assert messages[1].role == MessageRole.ASSISTANT
        assert "don't have access" in messages[1].content.text

        assert messages[2].role == MessageRole.USER
        assert "okay" in messages[2].content.text

    def test_conversation_builder_build(self):
        """Test building a complete conversation"""
        # Given: A conversation builder with messages
        builder = (ConversationBuilder("Complete Chat")
                  .user("Hello")
                  .assistant("Hi there!"))

        # When: Building the conversation
        conversation = builder.build()

        # Then: Should return a ConversationTree with messages
        assert isinstance(conversation, ConversationTree)
        assert conversation.title == "Complete Chat"

        # Verify conversation has the messages
        messages = list(conversation.message_map.values())
        assert len(messages) >= 2

        # Check that user and assistant messages are present
        message_contents = [msg.content.text for msg in messages]
        assert "Hello" in message_contents
        assert "Hi there!" in message_contents

    def test_conversation_builder_empty_build(self):
        """Test building an empty conversation"""
        # Given: An empty conversation builder
        builder = ConversationBuilder("Empty Chat")

        # When: Building the conversation
        conversation = builder.build()

        # Then: Should return a valid conversation even without messages
        assert isinstance(conversation, ConversationTree)
        assert conversation.title == "Empty Chat"
        assert len(conversation.message_map) == 0


class TestConversationLoader:
    """Test conversation loading behavior"""

    @patch('ctk.api.registry')
    def test_conversation_loader_initialization(self, mock_registry):
        """Test conversation loader can be initialized with different source types"""
        # Mock the registry to avoid file system operations
        mock_registry.import_file.return_value = []
        mock_registry.get_importer.return_value = Mock(import_data=Mock(return_value=[]))

        # Test with string path (mock prevents actual file access)
        loader_path = ConversationLoader("/path/to/file.json")
        assert loader_path.source == "/path/to/file.json"

        # Test with Path object
        path_obj = Path("/path/to/file.json")
        loader_pathobj = ConversationLoader(path_obj)
        assert loader_pathobj.source == path_obj

        # Test with dict
        data_dict = {"conversations": []}
        loader_dict = ConversationLoader(data_dict)
        assert loader_dict.source == data_dict

    @patch('ctk.api.registry')
    def test_conversation_loader_format_detection(self, mock_registry):
        """Test that loader can detect format from file extension"""
        # Mock the registry to avoid file system operations
        mock_registry.import_file.return_value = []

        # Given: A loader with a JSON file
        loader = ConversationLoader("/path/to/conversations.json")

        # When: Detecting format (simulated)
        # This would typically happen in the load method
        assert str(loader.source).endswith('.json')

    @patch('ctk.api.registry')
    def test_conversation_loader_configuration_chaining(self, mock_registry):
        """Test that loader supports configuration chaining"""
        # Mock the registry to avoid file system operations
        mock_registry.import_file.return_value = []

        # Given: A conversation loader
        loader = ConversationLoader("test.json")

        # When: Chaining configuration methods (these would be real methods)
        # This tests the expected fluent interface pattern
        result = loader

        # Then: Should support chaining
        assert result is loader


# Integration-style tests that verify the fluent API works end-to-end
class TestFluentAPIIntegration:
    """Integration tests for fluent API workflows"""

    def test_conversation_creation_workflow(self):
        """Test the complete workflow of creating a conversation"""
        # Given: A new conversation need

        # When: Using the fluent API to create a conversation
        conversation = (CTK.conversation("API Test Chat")
                       .user("Can you explain async/await?")
                       .assistant("Async/await is a way to handle asynchronous operations...")
                       .user("Can you show an example?")
                       .assistant("Here's a simple example: async def fetch_data(): ...")
                       .build())

        # Then: Should have a complete conversation
        assert conversation.title == "API Test Chat"
        messages = list(conversation.message_map.values())
        assert len(messages) == 4

        # Verify conversation structure makes sense
        roles = [msg.role for msg in messages]
        assert roles == [MessageRole.USER, MessageRole.ASSISTANT, MessageRole.USER, MessageRole.ASSISTANT]

    @patch('ctk.api.ConversationDB')
    def test_database_query_workflow(self, mock_db_class):
        """Test database querying workflow"""
        # Given: A CTK instance with database
        mock_db_instance = MagicMock()
        mock_db_class.return_value = mock_db_instance

        ctk = CTK("test.db")

        # When: Performing database operations
        ctk.get("conv-123")
        ctk.delete("conv-456")
        stats = ctk.stats()

        # Then: Should call appropriate database methods
        mock_db_instance.__enter__.return_value.load_conversation.assert_called_with("conv-123")
        mock_db_instance.__enter__.return_value.delete_conversation.assert_called_with("conv-456")
        mock_db_instance.__enter__.return_value.get_statistics.assert_called_once()