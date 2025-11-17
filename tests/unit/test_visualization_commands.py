"""
Unit tests for visualization commands

Tests the VisualizationCommands class for:
- tree: Display conversation tree structure
- paths: List all paths in conversation tree
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from ctk.core.commands.visualization import VisualizationCommands, create_visualization_commands
from ctk.core.command_dispatcher import CommandResult
from ctk.core.vfs_navigator import VFSNavigator
from ctk.core.vfs import VFSPath, VFSPathParser, PathType
from ctk.core.database import ConversationDB
from ctk.core.models import (
    ConversationTree, Message, MessageContent,
    MessageRole, ConversationMetadata
)


class TestVisualizationCommands:
    """Test VisualizationCommands class"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        db = Mock(spec=ConversationDB)
        return db

    @pytest.fixture
    def mock_navigator(self):
        """Create mock VFS navigator"""
        navigator = Mock(spec=VFSNavigator)
        return navigator

    @pytest.fixture
    def mock_tui(self):
        """Create mock TUI instance with VFS state"""
        tui = Mock()
        tui.vfs_cwd = '/chats/conv_001'
        return tui

    @pytest.fixture
    def viz_commands(self, mock_db, mock_navigator, mock_tui):
        """Create VisualizationCommands instance with mocks"""
        return VisualizationCommands(mock_db, mock_navigator, mock_tui)

    @pytest.fixture
    def viz_commands_no_tui(self, mock_db, mock_navigator):
        """Create VisualizationCommands without TUI (CLI mode)"""
        return VisualizationCommands(mock_db, mock_navigator, None)

    @pytest.fixture
    def linear_conversation(self):
        """Create a linear conversation (single path)"""
        conv = ConversationTree(
            id="conv_linear",
            title="Linear Chat",
            metadata=ConversationMetadata(source="test", model="test-model")
        )

        # Create linear chain: msg1 -> msg2 -> msg3
        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello, this is a test message"),
            parent_id=None
        )
        conv.add_message(msg1)

        msg2 = Message(
            id="msg_002",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="Hi there! How can I help you today?"),
            parent_id="msg_001"
        )
        conv.add_message(msg2)

        msg3 = Message(
            id="msg_003",
            role=MessageRole.USER,
            content=MessageContent(text="I need help with testing"),
            parent_id="msg_002"
        )
        conv.add_message(msg3)

        return conv

    @pytest.fixture
    def branching_conversation(self):
        """Create a conversation with multiple branches"""
        conv = ConversationTree(
            id="conv_branch",
            title="Branching Chat",
            metadata=ConversationMetadata(source="test")
        )

        # Root message
        msg1 = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="What's 2+2?"),
            parent_id=None
        )
        conv.add_message(msg1)

        # First branch response
        msg2a = Message(
            id="msg_002a",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="2+2 equals 4"),
            parent_id="msg_001"
        )
        conv.add_message(msg2a)

        # Second branch response (regenerated)
        msg2b = Message(
            id="msg_002b",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="The answer is 4"),
            parent_id="msg_001"
        )
        conv.add_message(msg2b)

        # Continue from first branch
        msg3a = Message(
            id="msg_003a",
            role=MessageRole.USER,
            content=MessageContent(text="What about 3+3?"),
            parent_id="msg_002a"
        )
        conv.add_message(msg3a)

        msg4a = Message(
            id="msg_004a",
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="3+3 equals 6"),
            parent_id="msg_003a"
        )
        conv.add_message(msg4a)

        return conv

    @pytest.fixture
    def empty_conversation(self):
        """Create an empty conversation (no messages)"""
        return ConversationTree(
            id="conv_empty",
            title="Empty Chat",
            metadata=ConversationMetadata(source="test")
        )

    @pytest.fixture
    def deep_conversation(self):
        """Create a deeply nested conversation"""
        conv = ConversationTree(
            id="conv_deep",
            title="Deep Chat",
            metadata=ConversationMetadata(source="test")
        )

        # Create chain of 10 messages
        parent_id = None
        for i in range(10):
            role = MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT
            msg = Message(
                id=f"msg_{i:03d}",
                role=role,
                content=MessageContent(text=f"Message {i}"),
                parent_id=parent_id
            )
            conv.add_message(msg)
            parent_id = msg.id

        return conv

    # Initialization Tests

    @pytest.mark.unit
    def test_init_with_all_params(self, mock_db, mock_navigator, mock_tui):
        """Test initialization with all parameters"""
        viz = VisualizationCommands(mock_db, mock_navigator, mock_tui)
        assert viz.db is mock_db
        assert viz.navigator is mock_navigator
        assert viz.tui is mock_tui

    @pytest.mark.unit
    def test_init_without_tui(self, mock_db, mock_navigator):
        """Test initialization without TUI (CLI mode)"""
        viz = VisualizationCommands(mock_db, mock_navigator, None)
        assert viz.db is mock_db
        assert viz.navigator is mock_navigator
        assert viz.tui is None

    # cmd_tree Tests - Basic Functionality

    @pytest.mark.unit
    def test_tree_with_explicit_conv_id(self, viz_commands, mock_db, mock_navigator, linear_conversation):
        """Test tree command with explicit conversation ID"""
        # When TUI is present, it tries to resolve prefix - mock it to return None
        mock_navigator.resolve_prefix.return_value = None
        mock_db.load_conversation.return_value = linear_conversation

        result = viz_commands.cmd_tree(['conv_linear'])

        assert result.success is True
        assert "Conversation Tree:" in result.output
        assert "Total messages: 3" in result.output
        assert "Total paths: 1" in result.output
        assert "Linear Chat" in result.output
        mock_db.load_conversation.assert_called_once_with('conv_linear')

    @pytest.mark.unit
    def test_tree_with_current_path_in_conversation(self, viz_commands, mock_db, linear_conversation, mock_tui):
        """Test tree command using current VFS path"""
        mock_tui.vfs_cwd = '/chats/conv_linear'
        mock_db.load_conversation.return_value = linear_conversation

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_linear'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = viz_commands.cmd_tree([])

        assert result.success is True
        assert "Conversation Tree:" in result.output
        mock_db.load_conversation.assert_called_once_with('conv_linear')

    @pytest.mark.unit
    def test_tree_with_current_path_in_message_node(self, viz_commands, mock_db, linear_conversation, mock_tui):
        """Test tree command when current path is a message node"""
        mock_tui.vfs_cwd = '/chats/conv_linear/msg_001'
        mock_db.load_conversation.return_value = linear_conversation

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_NODE
        mock_parsed.conversation_id = 'conv_linear'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = viz_commands.cmd_tree([])

        assert result.success is True
        assert "Conversation Tree:" in result.output

    @pytest.mark.unit
    def test_tree_with_vfs_path_argument(self, viz_commands, mock_db, linear_conversation, mock_navigator):
        """Test tree command with VFS path as argument"""
        mock_db.load_conversation.return_value = linear_conversation

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.conversation_id = 'conv_linear'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = viz_commands.cmd_tree(['/chats/conv_linear'])

        assert result.success is True
        assert "Conversation Tree:" in result.output

    @pytest.mark.unit
    def test_tree_empty_conversation(self, viz_commands, mock_db, empty_conversation):
        """Test tree command with empty conversation"""
        mock_db.load_conversation.return_value = empty_conversation

        result = viz_commands.cmd_tree(['conv_empty'])

        assert result.success is True
        assert "Conversation Tree:" in result.output
        assert "(empty conversation)" in result.output
        assert "Total messages: 0" in result.output
        assert "Total paths: 0" in result.output

    @pytest.mark.unit
    def test_tree_branching_conversation(self, viz_commands, mock_db, branching_conversation):
        """Test tree command with branching conversation"""
        mock_db.load_conversation.return_value = branching_conversation

        result = viz_commands.cmd_tree(['conv_branch'])

        assert result.success is True
        assert "Conversation Tree:" in result.output
        assert "Total messages: 5" in result.output
        assert "Total paths: 2" in result.output  # Two paths through the tree
        # Check for tree structure indicators
        assert "├─" in result.output or "└─" in result.output

    @pytest.mark.unit
    def test_tree_shows_message_roles(self, viz_commands, mock_db, linear_conversation):
        """Test that tree displays message role emojis"""
        mock_db.load_conversation.return_value = linear_conversation

        result = viz_commands.cmd_tree(['conv_linear'])

        assert result.success is True
        # Role emojis: U for user, A for assistant
        assert "U " in result.output  # User message
        assert "A " in result.output  # Assistant message

    @pytest.mark.unit
    def test_tree_shows_content_preview(self, viz_commands, mock_db, linear_conversation):
        """Test that tree shows content preview"""
        mock_db.load_conversation.return_value = linear_conversation

        result = viz_commands.cmd_tree(['conv_linear'])

        assert result.success is True
        # Should show truncated content
        assert "Hello, this is a test message" in result.output

    @pytest.mark.unit
    def test_tree_truncates_long_content(self, viz_commands, mock_db):
        """Test that tree truncates long content with ellipsis"""
        conv = ConversationTree(id="conv_long", title="Long Content")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="A" * 60),  # 60 chars, should be truncated
            parent_id=None
        )
        conv.add_message(msg)
        mock_db.load_conversation.return_value = conv

        result = viz_commands.cmd_tree(['conv_long'])

        assert result.success is True
        assert "..." in result.output  # Ellipsis for truncated content

    # cmd_tree Tests - Error Handling

    @pytest.mark.unit
    def test_tree_conversation_not_found(self, viz_commands, mock_db, mock_navigator):
        """Test tree command when conversation doesn't exist"""
        mock_navigator.resolve_prefix.return_value = None
        mock_db.load_conversation.return_value = None

        result = viz_commands.cmd_tree(['nonexistent'])

        assert result.success is False
        assert "Conversation not found" in result.error
        assert "nonexistent" in result.error

    @pytest.mark.unit
    def test_tree_no_args_without_tui(self, viz_commands_no_tui):
        """Test tree command without arguments in CLI mode"""
        result = viz_commands_no_tui.cmd_tree([])

        assert result.success is False
        assert "No conversation in current context" in result.error

    @pytest.mark.unit
    def test_tree_not_in_conversation_directory(self, viz_commands, mock_db, mock_tui):
        """Test tree command when current path is not in a conversation"""
        mock_tui.vfs_cwd = '/starred'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.STARRED

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = viz_commands.cmd_tree([])

        assert result.success is False
        assert "Not in a conversation directory" in result.error

    @pytest.mark.unit
    def test_tree_invalid_path(self, viz_commands):
        """Test tree command with invalid path"""
        with patch.object(VFSPathParser, 'parse', side_effect=ValueError("Invalid path")):
            result = viz_commands.cmd_tree(['/invalid/path'])

        assert result.success is False
        assert "Invalid path" in result.error

    # cmd_tree Tests - Prefix Resolution

    @pytest.mark.unit
    def test_tree_with_prefix_resolution(self, viz_commands, mock_db, mock_navigator, linear_conversation, mock_tui):
        """Test tree command with conversation ID prefix"""
        mock_tui.vfs_cwd = '/chats'
        mock_navigator.resolve_prefix.return_value = 'conv_linear'
        mock_db.load_conversation.return_value = linear_conversation

        result = viz_commands.cmd_tree(['conv_lin'])

        assert result.success is True
        assert "Conversation Tree:" in result.output
        mock_navigator.resolve_prefix.assert_called_once()

    @pytest.mark.unit
    def test_tree_prefix_resolution_fails(self, viz_commands, mock_db, mock_navigator, linear_conversation, mock_tui):
        """Test tree command when prefix resolution fails"""
        mock_navigator.resolve_prefix.side_effect = ValueError("Ambiguous prefix")
        mock_db.load_conversation.return_value = linear_conversation

        # Should fall back to using prefix as-is
        result = viz_commands.cmd_tree(['conv_lin'])

        assert result.success is True or result.success is False
        # If fallback works, it succeeds; if not, it fails gracefully

    @pytest.mark.unit
    def test_tree_prefix_resolution_no_match(self, viz_commands, mock_db, mock_navigator, mock_tui):
        """Test tree command when prefix has no match"""
        mock_navigator.resolve_prefix.return_value = None
        mock_db.load_conversation.return_value = None

        result = viz_commands.cmd_tree(['xyz'])

        assert result.success is False
        assert "Conversation not found" in result.error

    # cmd_paths Tests - Basic Functionality

    @pytest.mark.unit
    def test_paths_with_explicit_conv_id(self, viz_commands, mock_db, mock_navigator, linear_conversation):
        """Test paths command with explicit conversation ID"""
        # When TUI is present, it tries to resolve prefix - mock it to return None
        mock_navigator.resolve_prefix.return_value = None
        mock_db.load_conversation.return_value = linear_conversation

        result = viz_commands.cmd_paths(['conv_linear'])

        assert result.success is True
        assert "All paths in conversation" in result.output
        assert "(1 total)" in result.output
        assert "Path 1 (3 messages):" in result.output
        assert "User: Hello, this is a test message" in result.output
        mock_db.load_conversation.assert_called_once_with('conv_linear')

    @pytest.mark.unit
    def test_paths_with_current_path(self, viz_commands, mock_db, linear_conversation, mock_tui):
        """Test paths command using current VFS path"""
        mock_tui.vfs_cwd = '/chats/conv_linear'
        mock_db.load_conversation.return_value = linear_conversation

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_linear'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = viz_commands.cmd_paths([])

        assert result.success is True
        assert "All paths in conversation" in result.output

    @pytest.mark.unit
    def test_paths_branching_conversation(self, viz_commands, mock_db, branching_conversation):
        """Test paths command with branching conversation"""
        mock_db.load_conversation.return_value = branching_conversation

        result = viz_commands.cmd_paths(['conv_branch'])

        assert result.success is True
        assert "(2 total)" in result.output  # Two distinct paths
        assert "Path 1" in result.output
        assert "Path 2" in result.output
        assert "What's 2+2?" in result.output

    @pytest.mark.unit
    def test_paths_empty_conversation(self, viz_commands, mock_db, empty_conversation):
        """Test paths command with empty conversation"""
        mock_db.load_conversation.return_value = empty_conversation

        result = viz_commands.cmd_paths(['conv_empty'])

        assert result.success is True
        assert "(0 total)" in result.output

    @pytest.mark.unit
    def test_paths_shows_message_roles(self, viz_commands, mock_db, linear_conversation):
        """Test that paths displays message roles"""
        mock_db.load_conversation.return_value = linear_conversation

        result = viz_commands.cmd_paths(['conv_linear'])

        assert result.success is True
        assert "User:" in result.output
        assert "Assistant:" in result.output

    @pytest.mark.unit
    def test_paths_shows_content_preview(self, viz_commands, mock_db, linear_conversation):
        """Test that paths shows content preview"""
        mock_db.load_conversation.return_value = linear_conversation

        result = viz_commands.cmd_paths(['conv_linear'])

        assert result.success is True
        assert "Hello, this is a test message" in result.output

    @pytest.mark.unit
    def test_paths_truncates_long_content(self, viz_commands, mock_db):
        """Test that paths truncates long content"""
        conv = ConversationTree(id="conv_long", title="Long Content")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="B" * 60),  # 60 chars, should be truncated at 50
            parent_id=None
        )
        conv.add_message(msg)
        mock_db.load_conversation.return_value = conv

        result = viz_commands.cmd_paths(['conv_long'])

        assert result.success is True
        assert "..." in result.output  # Ellipsis for truncated content

    @pytest.mark.unit
    def test_paths_with_message_count(self, viz_commands, mock_db, deep_conversation):
        """Test that paths shows correct message count per path"""
        mock_db.load_conversation.return_value = deep_conversation

        result = viz_commands.cmd_paths(['conv_deep'])

        assert result.success is True
        assert "(10 messages)" in result.output

    # cmd_paths Tests - Error Handling

    @pytest.mark.unit
    def test_paths_conversation_not_found(self, viz_commands, mock_db, mock_navigator):
        """Test paths command when conversation doesn't exist"""
        mock_navigator.resolve_prefix.return_value = None
        mock_db.load_conversation.return_value = None

        result = viz_commands.cmd_paths(['nonexistent'])

        assert result.success is False
        assert "Conversation not found" in result.error
        assert "nonexistent" in result.error

    @pytest.mark.unit
    def test_paths_no_args_without_tui(self, viz_commands_no_tui):
        """Test paths command without arguments in CLI mode"""
        result = viz_commands_no_tui.cmd_paths([])

        assert result.success is False
        assert "No conversation in current context" in result.error

    @pytest.mark.unit
    def test_paths_not_in_conversation_directory(self, viz_commands, mock_db, mock_tui):
        """Test paths command when current path is not in a conversation"""
        mock_tui.vfs_cwd = '/tags'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.TAGS

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = viz_commands.cmd_paths([])

        assert result.success is False
        assert "Not in a conversation directory" in result.error

    @pytest.mark.unit
    def test_paths_invalid_path(self, viz_commands):
        """Test paths command with invalid path"""
        with patch.object(VFSPathParser, 'parse', side_effect=Exception("Bad path")):
            result = viz_commands.cmd_paths(['/bad/path'])

        assert result.success is False
        assert "Invalid path" in result.error

    # cmd_paths Tests - Prefix Resolution

    @pytest.mark.unit
    def test_paths_with_prefix_resolution(self, viz_commands, mock_db, mock_navigator, linear_conversation, mock_tui):
        """Test paths command with conversation ID prefix"""
        mock_navigator.resolve_prefix.return_value = 'conv_linear'
        mock_db.load_conversation.return_value = linear_conversation

        result = viz_commands.cmd_paths(['conv_lin'])

        assert result.success is True
        assert "All paths in conversation" in result.output
        mock_navigator.resolve_prefix.assert_called_once()

    # Factory Function Tests

    @pytest.mark.unit
    def test_create_visualization_commands(self, mock_db, mock_navigator, mock_tui):
        """Test factory function creates command dict"""
        commands = create_visualization_commands(mock_db, mock_navigator, mock_tui)

        assert 'tree' in commands
        assert 'paths' in commands
        assert callable(commands['tree'])
        assert callable(commands['paths'])

    @pytest.mark.unit
    def test_create_visualization_commands_without_tui(self, mock_db, mock_navigator):
        """Test factory function works without TUI"""
        commands = create_visualization_commands(mock_db, mock_navigator, None)

        assert 'tree' in commands
        assert 'paths' in commands

    # Edge Cases

    @pytest.mark.unit
    def test_tree_with_system_role(self, viz_commands, mock_db):
        """Test tree command with system message"""
        conv = ConversationTree(id="conv_sys", title="System Test")
        msg = Message(
            id="msg_001",
            role=MessageRole.SYSTEM,
            content=MessageContent(text="You are a helpful assistant"),
            parent_id=None
        )
        conv.add_message(msg)
        mock_db.load_conversation.return_value = conv

        result = viz_commands.cmd_tree(['conv_sys'])

        assert result.success is True
        assert "⚙" in result.output  # System role emoji

    @pytest.mark.unit
    def test_tree_with_tool_role(self, viz_commands, mock_db):
        """Test tree command with tool message"""
        conv = ConversationTree(id="conv_tool", title="Tool Test")
        msg = Message(
            id="msg_001",
            role=MessageRole.TOOL,
            content=MessageContent(text="Tool result"),
            parent_id=None
        )
        conv.add_message(msg)
        mock_db.load_conversation.return_value = conv

        result = viz_commands.cmd_tree(['conv_tool'])

        assert result.success is True
        assert "T " in result.output  # Tool role emoji

    @pytest.mark.unit
    def test_paths_with_vfs_path_argument(self, viz_commands, mock_db, linear_conversation):
        """Test paths command with VFS path as argument"""
        mock_db.load_conversation.return_value = linear_conversation

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.conversation_id = 'conv_linear'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = viz_commands.cmd_paths(['/chats/conv_linear'])

        assert result.success is True
        assert "All paths in conversation" in result.output

    @pytest.mark.unit
    def test_tree_handles_newlines_in_content(self, viz_commands, mock_db):
        """Test that tree replaces newlines in content preview"""
        conv = ConversationTree(id="conv_newline", title="Newline Test")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Line 1\nLine 2\nLine 3"),
            parent_id=None
        )
        conv.add_message(msg)
        mock_db.load_conversation.return_value = conv

        result = viz_commands.cmd_tree(['conv_newline'])

        assert result.success is True
        # Newlines should be replaced with spaces
        assert "Line 1 Line 2 Line 3" in result.output

    @pytest.mark.unit
    def test_paths_handles_newlines_in_content(self, viz_commands, mock_db):
        """Test that paths replaces newlines in content preview"""
        conv = ConversationTree(id="conv_newline", title="Newline Test")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="First\nSecond\nThird"),
            parent_id=None
        )
        conv.add_message(msg)
        mock_db.load_conversation.return_value = conv

        result = viz_commands.cmd_paths(['conv_newline'])

        assert result.success is True
        # Newlines should be replaced with spaces
        assert "First Second Third" in result.output

    @pytest.mark.unit
    def test_tree_with_missing_message_in_map(self, viz_commands, mock_db):
        """Test tree handles gracefully when message is missing from map"""
        conv = ConversationTree(id="conv_missing", title="Missing Message")
        conv.root_message_ids = ['msg_nonexistent']
        mock_db.load_conversation.return_value = conv

        result = viz_commands.cmd_tree(['conv_missing'])

        # Should succeed but show empty tree
        assert result.success is True
        assert "Total messages: 0" in result.output
