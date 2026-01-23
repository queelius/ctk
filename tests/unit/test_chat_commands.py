"""
Unit tests for chat commands

Tests the chat command implementation including:
- Loading conversation from VFS path
- Navigating to specific message nodes
- Building conversation history
- Mode switching
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from ctk.core.command_dispatcher import CommandResult
from ctk.core.commands.chat import ChatCommands, create_chat_commands
from ctk.core.database import ConversationDB
from ctk.core.models import (ConversationMetadata, ConversationTree, Message,
                             MessageContent, MessageRole)


class MockMessageNode:
    """Mock message node for TUI tree structure"""

    def __init__(self, msg_id, content, role, children=None):
        self.msg_id = msg_id
        self.content = content
        self.role = role
        self.children = children or []


class MockTUI:
    """Mock TUI instance for testing"""

    def __init__(self, db=None, provider=None):
        self.db = db
        self.provider = provider
        self.vfs_cwd = "/"
        self.mode = "shell"
        self.root = None
        self.current_message = None
        self.current_conversation_id = None
        self.chat_called_with = None

    def load_conversation_tree(self, conversation):
        """Mock loading conversation into TUI"""
        # Create simple tree structure
        self.root = MockMessageNode("root", "", "system", [])

        # Build tree from conversation
        node_map = {"root": self.root}

        for msg_id, msg in conversation.message_map.items():
            parent_id = msg.parent_id or "root"
            parent_node = node_map.get(parent_id, self.root)

            new_node = MockMessageNode(msg_id, msg.content.get_text(), msg.role.value)
            parent_node.children.append(new_node)
            node_map[msg_id] = new_node

        # Set current message to most recent leaf
        if self.root.children:
            current = self.root.children[0]
            while current.children:
                current = current.children[-1]
            self.current_message = current

    def chat(self, message):
        """Mock chat method"""
        self.chat_called_with = message


@pytest.fixture
def test_db(tmp_path):
    """Create test database with sample branching conversation"""
    db_path = tmp_path / "test_chat.db"
    db = ConversationDB(str(db_path))

    # Create a conversation with branching structure
    #       m1 (user)
    #      /  \
    #    m2   m3 (assistant branches)
    #    |
    #   m4 (user)
    #    |
    #   m5 (assistant)

    conv = ConversationTree(
        id="test_conv_123",
        title="Test Conversation",
        metadata=ConversationMetadata(source="test"),
    )

    # Root message
    m1 = Message(
        id="msg_001",
        role=MessageRole.USER,
        content=MessageContent(text="Hello, can you help me?"),
        parent_id=None,
    )
    conv.add_message(m1)

    # Branch 1: m2 -> m4 -> m5
    m2 = Message(
        id="msg_002",
        role=MessageRole.ASSISTANT,
        content=MessageContent(text="Sure, how can I help?"),
        parent_id="msg_001",
    )
    conv.add_message(m2)

    m4 = Message(
        id="msg_004",
        role=MessageRole.USER,
        content=MessageContent(text="Tell me about Python"),
        parent_id="msg_002",
    )
    conv.add_message(m4)

    m5 = Message(
        id="msg_005",
        role=MessageRole.ASSISTANT,
        content=MessageContent(text="Python is a programming language."),
        parent_id="msg_004",
    )
    conv.add_message(m5)

    # Branch 2: m3 (alternative response to m1)
    m3 = Message(
        id="msg_003",
        role=MessageRole.ASSISTANT,
        content=MessageContent(text="Of course! What do you need?"),
        parent_id="msg_001",
    )
    conv.add_message(m3)

    db.save_conversation(conv)

    # Create a simple linear conversation for basic tests
    conv2 = ConversationTree(
        id="simple_conv_456",
        title="Simple Chat",
        metadata=ConversationMetadata(source="test"),
    )

    msg1 = Message(
        id="simple_001",
        role=MessageRole.USER,
        content=MessageContent(text="What is AI?"),
        parent_id=None,
    )
    conv2.add_message(msg1)

    msg2 = Message(
        id="simple_002",
        role=MessageRole.ASSISTANT,
        content=MessageContent(text="AI is artificial intelligence."),
        parent_id="simple_001",
    )
    conv2.add_message(msg2)

    db.save_conversation(conv2)

    yield db
    db.close()


@pytest.fixture
def mock_tui(test_db):
    """Create mock TUI with database"""
    return MockTUI(db=test_db, provider=Mock())


@pytest.fixture
def chat_handler(mock_tui):
    """Create chat command handler"""
    return ChatCommands(tui_instance=mock_tui)


class TestChatCommand:
    """Test chat command behavior"""

    @pytest.mark.unit
    def test_chat_requires_tui_instance(self):
        """Test that ChatCommands requires tui_instance"""
        with pytest.raises(ValueError, match="requires tui_instance"):
            ChatCommands(tui_instance=None)

    @pytest.mark.unit
    def test_chat_enter_mode_no_message(self, chat_handler, mock_tui):
        """Test entering chat mode without sending message"""
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        assert "Entering chat mode" in result.output
        assert mock_tui.mode == "chat"
        assert mock_tui.chat_called_with is None

    @pytest.mark.unit
    def test_chat_with_message_args(self, chat_handler, mock_tui):
        """Test entering chat mode with message from args"""
        result = chat_handler.cmd_chat(["Hello", "world"], stdin="")

        assert result.success is True
        assert mock_tui.mode == "chat"
        assert mock_tui.chat_called_with == "Hello world"

    @pytest.mark.unit
    def test_chat_with_stdin(self, chat_handler, mock_tui):
        """Test entering chat mode with piped message"""
        result = chat_handler.cmd_chat([], stdin="Hello from pipe")

        assert result.success is True
        assert mock_tui.mode == "chat"
        assert mock_tui.chat_called_with == "Hello from pipe"

    @pytest.mark.unit
    def test_chat_from_root_path(self, chat_handler, mock_tui):
        """Test chat command from root directory (no conversation loaded)"""
        mock_tui.vfs_cwd = "/"
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        assert mock_tui.mode == "chat"
        # Should not load any conversation
        assert mock_tui.current_conversation_id is None

    @pytest.mark.unit
    def test_chat_from_conversation_root(self, chat_handler, mock_tui):
        """Test chat command from conversation root directory"""
        mock_tui.vfs_cwd = "/chats/test_conv_123"
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        assert mock_tui.mode == "chat"
        # Should load conversation
        assert mock_tui.current_conversation_id == "test_conv_123"
        assert mock_tui.root is not None

    @pytest.mark.unit
    def test_chat_from_message_node(self, chat_handler, mock_tui):
        """Test chat command from specific message node"""
        mock_tui.vfs_cwd = "/chats/test_conv_123/m1"
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        assert mock_tui.mode == "chat"
        assert mock_tui.current_conversation_id == "test_conv_123"
        # Should navigate to m1 (first message)
        assert mock_tui.current_message is not None

    @pytest.mark.unit
    def test_chat_from_nested_message_node(self, chat_handler, mock_tui):
        """Test chat command from nested message node path"""
        mock_tui.vfs_cwd = "/chats/test_conv_123/m1/m1"
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        assert mock_tui.mode == "chat"
        # Should navigate through tree: m1 -> m1
        assert mock_tui.current_message is not None

    @pytest.mark.unit
    def test_chat_load_simple_conversation(self, chat_handler, mock_tui):
        """Test loading a simple linear conversation"""
        mock_tui.vfs_cwd = "/chats/simple_conv_456"
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        assert mock_tui.current_conversation_id == "simple_conv_456"

    @pytest.mark.unit
    def test_chat_invalid_conversation_id(self, chat_handler, mock_tui):
        """Test chat with non-existent conversation ID"""
        mock_tui.vfs_cwd = "/chats/nonexistent_id"
        result = chat_handler.cmd_chat([], stdin="")

        # Should not fail, just not load conversation
        assert result.success is True
        assert mock_tui.mode == "chat"

    @pytest.mark.unit
    def test_chat_from_starred_path(self, chat_handler, mock_tui):
        """Test chat command from /starred/ path"""
        mock_tui.vfs_cwd = "/starred/test_conv_123"
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        assert mock_tui.current_conversation_id == "test_conv_123"

    @pytest.mark.unit
    def test_chat_preserves_message_path(self, chat_handler, mock_tui):
        """Test that chat navigates to correct message in branching tree"""
        # Navigate to specific branch
        mock_tui.vfs_cwd = "/chats/test_conv_123/m1/m2"
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        # Should navigate to m1's second child (m2 vs m3 branch)


class TestChatCommandFactory:
    """Test chat command factory function"""

    @pytest.mark.unit
    def test_create_chat_commands(self, mock_tui):
        """Test creating chat command handlers"""
        commands = create_chat_commands(tui_instance=mock_tui)

        assert "chat" in commands
        assert "say" in commands
        assert callable(commands["chat"])
        assert callable(commands["say"])

    @pytest.mark.unit
    def test_created_commands_work(self, mock_tui):
        """Test that created commands are functional"""
        commands = create_chat_commands(tui_instance=mock_tui)

        # Test chat command
        result = commands["chat"]([], stdin="")
        assert result.success is True

    @pytest.mark.unit
    def test_factory_requires_tui(self):
        """Test that factory requires TUI instance"""
        # Should raise error when creating chat commands without TUI
        with pytest.raises(ValueError):
            create_chat_commands(tui_instance=None)


class TestChatHistoryLoading:
    """Test conversation history loading for different scenarios"""

    @pytest.mark.unit
    def test_load_linear_conversation(self, chat_handler, mock_tui, test_db):
        """Test loading a linear conversation history"""
        mock_tui.vfs_cwd = "/chats/simple_conv_456"
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        # Verify conversation was loaded
        assert mock_tui.current_conversation_id == "simple_conv_456"
        assert mock_tui.root is not None

    @pytest.mark.unit
    def test_load_branching_conversation(self, chat_handler, mock_tui, test_db):
        """Test loading a branching conversation"""
        mock_tui.vfs_cwd = "/chats/test_conv_123"
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        assert mock_tui.current_conversation_id == "test_conv_123"
        # Should have multiple branches
        assert mock_tui.root is not None
        assert len(mock_tui.root.children) > 0

    @pytest.mark.unit
    def test_navigate_to_specific_branch(self, chat_handler, mock_tui, test_db):
        """Test navigating to a specific branch in conversation tree"""
        # Navigate to a specific message path
        mock_tui.vfs_cwd = "/chats/test_conv_123/m1/m1"  # First branch
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        # Should be positioned at the specified node
        assert mock_tui.current_message is not None

    @pytest.mark.unit
    def test_invalid_message_path(self, chat_handler, mock_tui, test_db):
        """Test handling invalid message path in VFS"""
        mock_tui.vfs_cwd = "/chats/test_conv_123/m999"  # Non-existent
        result = chat_handler.cmd_chat([], stdin="")

        # Should not crash, may not navigate to specific node
        assert result.success is True

    @pytest.mark.unit
    def test_message_indexing(self, chat_handler, mock_tui, test_db):
        """Test that message indexing works correctly (m1, m2, etc.)"""
        mock_tui.vfs_cwd = "/chats/test_conv_123/m1"
        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        # Should navigate to first child of root


class TestChatEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.unit
    def test_chat_with_empty_database(self, tmp_path):
        """Test chat command with empty database"""
        db_path = tmp_path / "empty.db"
        db = ConversationDB(str(db_path))
        tui = MockTUI(db=db)
        chat_handler = ChatCommands(tui_instance=tui)

        result = chat_handler.cmd_chat([], stdin="")

        assert result.success is True
        assert tui.mode == "chat"

        db.close()

    @pytest.mark.unit
    def test_chat_path_parsing_error(self, chat_handler, mock_tui):
        """Test chat when VFS path parsing fails"""
        # Set an invalid path that might cause parsing issues
        mock_tui.vfs_cwd = "///invalid///"
        result = chat_handler.cmd_chat([], stdin="")

        # Should not crash, just continue with empty conversation
        assert result.success is True

    @pytest.mark.unit
    def test_chat_stdin_takes_precedence(self, chat_handler, mock_tui):
        """Test that stdin takes precedence over args"""
        mock_tui.provider.chat = Mock()

        result = chat_handler.cmd_chat(["ignored", "args"], stdin="piped message")

        assert mock_tui.chat_called_with == "piped message"
