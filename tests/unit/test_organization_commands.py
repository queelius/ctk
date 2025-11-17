"""
Unit tests for organization commands

Tests the OrganizationCommands class for:
- star/unstar: Star/unstar conversations
- pin/unpin: Pin/unpin conversations
- archive/unarchive: Archive/unarchive conversations
- title: Set conversation titles
"""

import pytest
from unittest.mock import Mock, patch
from ctk.core.commands.organization import OrganizationCommands, create_organization_commands
from ctk.core.command_dispatcher import CommandResult
from ctk.core.vfs_navigator import VFSNavigator
from ctk.core.vfs import VFSPath, VFSPathParser, PathType
from ctk.core.database import ConversationDB


class TestOrganizationCommands:
    """Test OrganizationCommands class"""

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
        tui.vfs_cwd = '/chats/conv_12345678'
        return tui

    @pytest.fixture
    def org_commands(self, mock_db, mock_navigator, mock_tui):
        """Create OrganizationCommands instance with mocks"""
        return OrganizationCommands(mock_db, mock_navigator, mock_tui)

    @pytest.fixture
    def org_commands_no_tui(self, mock_db, mock_navigator):
        """Create OrganizationCommands instance without TUI"""
        return OrganizationCommands(mock_db, mock_navigator, None)

    # Initialization Tests

    @pytest.mark.unit
    def test_init_with_tui(self, mock_db, mock_navigator, mock_tui):
        """Test successful initialization with TUI"""
        org = OrganizationCommands(mock_db, mock_navigator, mock_tui)
        assert org.db is mock_db
        assert org.navigator is mock_navigator
        assert org.tui is mock_tui

    @pytest.mark.unit
    def test_init_without_tui(self, mock_db, mock_navigator):
        """Test initialization without TUI (valid for CLI usage)"""
        org = OrganizationCommands(mock_db, mock_navigator, None)
        assert org.db is mock_db
        assert org.navigator is mock_navigator
        assert org.tui is None

    # _get_conversation_id Tests

    @pytest.mark.unit
    def test_get_conversation_id_from_explicit_id(self, org_commands, mock_navigator):
        """Test getting conversation ID from explicit argument"""
        # Mock resolve_prefix to return None (no prefix match, use as direct ID)
        mock_navigator.resolve_prefix.return_value = None

        conv_id, error = org_commands._get_conversation_id(['conv_12345678'])
        assert conv_id == 'conv_12345678'
        assert error is None

    @pytest.mark.unit
    def test_get_conversation_id_from_absolute_path(self, org_commands):
        """Test getting conversation ID from absolute VFS path"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.conversation_id = 'conv_87654321'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            conv_id, error = org_commands._get_conversation_id(['/chats/conv_87654321'])
            assert conv_id == 'conv_87654321'
            assert error is None

    @pytest.mark.unit
    def test_get_conversation_id_from_non_conversation_path(self, org_commands):
        """Test error when path is not a conversation"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.conversation_id = None

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            conv_id, error = org_commands._get_conversation_id(['/starred'])
            assert conv_id is None
            assert "Not a conversation path" in error

    @pytest.mark.unit
    def test_get_conversation_id_from_prefix_resolution(self, org_commands, mock_navigator):
        """Test getting conversation ID from prefix with TUI"""
        mock_navigator.resolve_prefix.return_value = 'conv_12345678abcdef'

        conv_id, error = org_commands._get_conversation_id(['conv_123'])
        assert conv_id == 'conv_12345678abcdef'
        assert error is None

    @pytest.mark.unit
    def test_get_conversation_id_prefix_resolution_fails(self, org_commands, mock_navigator):
        """Test fallback to direct ID when prefix resolution fails"""
        mock_navigator.resolve_prefix.side_effect = ValueError("No match")

        conv_id, error = org_commands._get_conversation_id(['conv_123'])
        # Should use as direct ID
        assert conv_id == 'conv_123'
        assert error is None

    @pytest.mark.unit
    def test_get_conversation_id_from_current_path_conversation(self, org_commands):
        """Test getting conversation ID from current path when in conversation"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_12345678'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            conv_id, error = org_commands._get_conversation_id([])
            assert conv_id == 'conv_12345678'
            assert error is None

    @pytest.mark.unit
    def test_get_conversation_id_from_current_path_message_node(self, org_commands):
        """Test getting conversation ID from current path when in message node"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_NODE
        mock_parsed.conversation_id = 'conv_12345678'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            conv_id, error = org_commands._get_conversation_id([])
            assert conv_id == 'conv_12345678'
            assert error is None

    @pytest.mark.unit
    def test_get_conversation_id_from_current_path_not_in_conversation(self, org_commands):
        """Test error when current path is not a conversation"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CHATS  # Use CHATS instead of CHATS_ROOT

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            conv_id, error = org_commands._get_conversation_id([])
            assert conv_id is None
            assert "Not in a conversation directory" in error

    @pytest.mark.unit
    def test_get_conversation_id_no_tui_no_args(self, org_commands_no_tui):
        """Test error when no TUI and no args provided"""
        conv_id, error = org_commands_no_tui._get_conversation_id([])
        assert conv_id is None
        assert "No conversation in current context" in error

    @pytest.mark.unit
    def test_get_conversation_id_invalid_path(self, org_commands):
        """Test error handling for invalid path"""
        with patch.object(VFSPathParser, 'parse', side_effect=ValueError("Invalid path")):
            conv_id, error = org_commands._get_conversation_id(['/invalid/path'])
            assert conv_id is None
            assert "Invalid path" in error

    # cmd_star Tests

    @pytest.mark.unit
    def test_star_with_explicit_id(self, org_commands, mock_db, mock_navigator):
        """Test starring conversation with explicit ID"""
        # Mock resolve_prefix to return None (use as direct ID)
        mock_navigator.resolve_prefix.return_value = None
        mock_db.star_conversation.return_value = None

        result = org_commands.cmd_star(['conv_12345678'])

        assert result.success is True
        assert "Starred conversation: conv_123" in result.output  # First 8 chars
        mock_db.star_conversation.assert_called_once_with('conv_12345678')

    @pytest.mark.unit
    def test_star_current_conversation(self, org_commands, mock_db):
        """Test starring current conversation from VFS path"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_87654321'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = org_commands.cmd_star([])

            assert result.success is True
            # Check for the first 8 chars (conv_876)
            assert "conv_876" in result.output
            mock_db.star_conversation.assert_called_once_with('conv_87654321')

    @pytest.mark.unit
    def test_star_not_in_conversation(self, org_commands, mock_db):
        """Test error when trying to star without conversation context"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CHATS  # Use CHATS instead of CHATS_ROOT

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = org_commands.cmd_star([])

            assert result.success is False
            assert "star: Not in a conversation directory" in result.error
            mock_db.star_conversation.assert_not_called()

    @pytest.mark.unit
    def test_star_database_error(self, org_commands, mock_db):
        """Test error handling when database operation fails"""
        mock_db.star_conversation.side_effect = Exception("Database error")

        result = org_commands.cmd_star(['conv_12345678'])

        assert result.success is False
        assert "star: Database error" in result.error

    # cmd_unstar Tests

    @pytest.mark.unit
    def test_unstar_with_explicit_id(self, org_commands, mock_db, mock_navigator):
        """Test unstarring conversation with explicit ID"""
        mock_navigator.resolve_prefix.return_value = None

        result = org_commands.cmd_unstar(['conv_12345678'])

        assert result.success is True
        assert "Unstarred conversation: conv_123" in result.output  # First 8 chars
        mock_db.star_conversation.assert_called_once_with('conv_12345678', star=False)

    @pytest.mark.unit
    def test_unstar_current_conversation(self, org_commands, mock_db):
        """Test unstarring current conversation"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_87654321'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = org_commands.cmd_unstar([])

            assert result.success is True
            mock_db.star_conversation.assert_called_once_with('conv_87654321', star=False)

    @pytest.mark.unit
    def test_unstar_database_error(self, org_commands, mock_db):
        """Test error handling for unstar database failure"""
        mock_db.star_conversation.side_effect = Exception("DB error")

        result = org_commands.cmd_unstar(['conv_12345678'])

        assert result.success is False
        assert "unstar: DB error" in result.error

    # cmd_pin Tests

    @pytest.mark.unit
    def test_pin_with_explicit_id(self, org_commands, mock_db, mock_navigator):
        """Test pinning conversation with explicit ID"""
        mock_navigator.resolve_prefix.return_value = None

        result = org_commands.cmd_pin(['conv_12345678'])

        assert result.success is True
        assert "Pinned conversation: conv_123" in result.output  # First 8 chars
        mock_db.pin_conversation.assert_called_once_with('conv_12345678')

    @pytest.mark.unit
    def test_pin_current_conversation(self, org_commands, mock_db):
        """Test pinning current conversation"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_NODE
        mock_parsed.conversation_id = 'conv_99999999'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = org_commands.cmd_pin([])

            assert result.success is True
            mock_db.pin_conversation.assert_called_once_with('conv_99999999')

    @pytest.mark.unit
    def test_pin_database_error(self, org_commands, mock_db):
        """Test error handling for pin database failure"""
        mock_db.pin_conversation.side_effect = Exception("Pin failed")

        result = org_commands.cmd_pin(['conv_12345678'])

        assert result.success is False
        assert "pin: Pin failed" in result.error

    # cmd_unpin Tests

    @pytest.mark.unit
    def test_unpin_with_explicit_id(self, org_commands, mock_db, mock_navigator):
        """Test unpinning conversation with explicit ID"""
        mock_navigator.resolve_prefix.return_value = None

        result = org_commands.cmd_unpin(['conv_12345678'])

        assert result.success is True
        assert "Unpinned conversation: conv_123" in result.output  # First 8 chars
        mock_db.pin_conversation.assert_called_once_with('conv_12345678', pin=False)

    @pytest.mark.unit
    def test_unpin_current_conversation(self, org_commands, mock_db):
        """Test unpinning current conversation"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_11111111'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = org_commands.cmd_unpin([])

            assert result.success is True
            mock_db.pin_conversation.assert_called_once_with('conv_11111111', pin=False)

    @pytest.mark.unit
    def test_unpin_database_error(self, org_commands, mock_db):
        """Test error handling for unpin database failure"""
        mock_db.pin_conversation.side_effect = Exception("Unpin failed")

        result = org_commands.cmd_unpin(['conv_12345678'])

        assert result.success is False
        assert "unpin: Unpin failed" in result.error

    # cmd_archive Tests

    @pytest.mark.unit
    def test_archive_with_explicit_id(self, org_commands, mock_db, mock_navigator):
        """Test archiving conversation with explicit ID"""
        mock_navigator.resolve_prefix.return_value = None

        result = org_commands.cmd_archive(['conv_12345678'])

        assert result.success is True
        assert "Archived conversation: conv_123" in result.output  # First 8 chars
        mock_db.archive_conversation.assert_called_once_with('conv_12345678')

    @pytest.mark.unit
    def test_archive_current_conversation(self, org_commands, mock_db):
        """Test archiving current conversation"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_22222222'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = org_commands.cmd_archive([])

            assert result.success is True
            mock_db.archive_conversation.assert_called_once_with('conv_22222222')

    @pytest.mark.unit
    def test_archive_database_error(self, org_commands, mock_db):
        """Test error handling for archive database failure"""
        mock_db.archive_conversation.side_effect = Exception("Archive failed")

        result = org_commands.cmd_archive(['conv_12345678'])

        assert result.success is False
        assert "archive: Archive failed" in result.error

    # cmd_unarchive Tests

    @pytest.mark.unit
    def test_unarchive_with_explicit_id(self, org_commands, mock_db, mock_navigator):
        """Test unarchiving conversation with explicit ID"""
        mock_navigator.resolve_prefix.return_value = None

        result = org_commands.cmd_unarchive(['conv_12345678'])

        assert result.success is True
        assert "Unarchived conversation: conv_123" in result.output  # First 8 chars
        mock_db.archive_conversation.assert_called_once_with('conv_12345678', archive=False)

    @pytest.mark.unit
    def test_unarchive_current_conversation(self, org_commands, mock_db):
        """Test unarchiving current conversation"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_33333333'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = org_commands.cmd_unarchive([])

            assert result.success is True
            mock_db.archive_conversation.assert_called_once_with('conv_33333333', archive=False)

    @pytest.mark.unit
    def test_unarchive_database_error(self, org_commands, mock_db):
        """Test error handling for unarchive database failure"""
        mock_db.archive_conversation.side_effect = Exception("Unarchive failed")

        result = org_commands.cmd_unarchive(['conv_12345678'])

        assert result.success is False
        assert "unarchive: Unarchive failed" in result.error

    # cmd_title Tests

    @pytest.mark.unit
    def test_title_no_args_error(self, org_commands):
        """Test error when no title provided"""
        result = org_commands.cmd_title([])

        assert result.success is False
        assert "title: no title provided" in result.error

    @pytest.mark.unit
    def test_title_current_conversation_simple(self, org_commands, mock_db):
        """Test setting title for current conversation"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_12345678'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.update_conversation_metadata.return_value = True

            result = org_commands.cmd_title(['New', 'Title'])

            assert result.success is True
            assert "Set title to: New Title" in result.output
            mock_db.update_conversation_metadata.assert_called_once_with(
                'conv_12345678', title='New Title'
            )

    @pytest.mark.unit
    def test_title_current_conversation_multiword(self, org_commands, mock_db):
        """Test setting multi-word title for current conversation"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_12345678'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.update_conversation_metadata.return_value = True

            result = org_commands.cmd_title(['This', 'is', 'a', 'long', 'title'])

            assert result.success is True
            assert "Set title to: This is a long title" in result.output
            mock_db.update_conversation_metadata.assert_called_once_with(
                'conv_12345678', title='This is a long title'
            )

    @pytest.mark.unit
    def test_title_explicit_id_and_title(self, org_commands, mock_db):
        """Test setting title with explicit conversation ID"""
        # Mock the _get_conversation_id call for the explicit ID
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.conversation_id = 'conv_87654321'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.update_conversation_metadata.return_value = True

            result = org_commands.cmd_title(['/chats/conv_87654321', 'New', 'Title'])

            assert result.success is True
            assert "Set title to: New Title" in result.output
            mock_db.update_conversation_metadata.assert_called_once_with(
                'conv_87654321', title='New Title'
            )

    @pytest.mark.unit
    def test_title_explicit_short_id_and_title(self, org_commands, mock_db, mock_navigator):
        """Test setting title with explicit short conversation ID"""
        # Short IDs (8+ chars) are treated as conversation IDs
        # Mock resolve_prefix to return None (no prefix match, use as direct ID)
        mock_navigator.resolve_prefix.return_value = None
        mock_db.update_conversation_metadata.return_value = True

        result = org_commands.cmd_title(['conv_12345678', 'My', 'New', 'Title'])

        assert result.success is True
        assert "Set title to: My New Title" in result.output
        mock_db.update_conversation_metadata.assert_called_once_with(
            'conv_12345678', title='My New Title'
        )

    @pytest.mark.unit
    def test_title_explicit_id_no_title_error(self, org_commands, mock_db):
        """Test error when providing ID but no title"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.conversation_id = 'conv_12345678'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = org_commands.cmd_title(['/chats/conv_12345678'])

            assert result.success is False
            assert "title: no title provided" in result.error

    @pytest.mark.unit
    def test_title_conversation_not_found(self, org_commands, mock_db):
        """Test error when conversation not found"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_nonexistent'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.update_conversation_metadata.return_value = False

            result = org_commands.cmd_title(['New', 'Title'])

            assert result.success is False
            assert "title: Conversation not found" in result.error

    @pytest.mark.unit
    def test_title_database_error(self, org_commands, mock_db):
        """Test error handling for title database failure"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION_ROOT
        mock_parsed.conversation_id = 'conv_12345678'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.update_conversation_metadata.side_effect = Exception("Update failed")

            result = org_commands.cmd_title(['New', 'Title'])

            assert result.success is False
            assert "title: Update failed" in result.error

    @pytest.mark.unit
    def test_title_not_in_conversation_context(self, org_commands, mock_db):
        """Test error when not in conversation and no ID provided"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CHATS  # Use CHATS instead of CHATS_ROOT

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = org_commands.cmd_title(['Some', 'Title'])

            assert result.success is False
            assert "title: Not in a conversation directory" in result.error

    # create_organization_commands Tests

    @pytest.mark.unit
    def test_create_organization_commands(self, mock_db, mock_navigator, mock_tui):
        """Test factory function creates all command handlers"""
        commands = create_organization_commands(mock_db, mock_navigator, mock_tui)

        assert 'star' in commands
        assert 'unstar' in commands
        assert 'pin' in commands
        assert 'unpin' in commands
        assert 'archive' in commands
        assert 'unarchive' in commands
        assert 'title' in commands

        # Verify commands are callable
        assert callable(commands['star'])
        assert callable(commands['unstar'])
        assert callable(commands['pin'])
        assert callable(commands['unpin'])
        assert callable(commands['archive'])
        assert callable(commands['unarchive'])
        assert callable(commands['title'])

    @pytest.mark.unit
    def test_create_organization_commands_without_tui(self, mock_db, mock_navigator):
        """Test factory function works without TUI"""
        commands = create_organization_commands(mock_db, mock_navigator, None)

        assert len(commands) == 7
        assert 'star' in commands

    # Integration-style Tests

    @pytest.mark.unit
    def test_star_with_prefix_resolution(self, org_commands, mock_db, mock_navigator):
        """Test starring conversation with prefix resolution"""
        mock_navigator.resolve_prefix.return_value = 'conv_12345678abcdef'

        result = org_commands.cmd_star(['conv_123'])

        assert result.success is True
        mock_db.star_conversation.assert_called_once_with('conv_12345678abcdef')

    @pytest.mark.unit
    def test_pin_via_absolute_path(self, org_commands, mock_db):
        """Test pinning conversation via absolute VFS path"""
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.conversation_id = 'conv_pathtest'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = org_commands.cmd_pin(['/starred/conv_pathtest'])

            assert result.success is True
            mock_db.pin_conversation.assert_called_once_with('conv_pathtest')

    @pytest.mark.unit
    def test_archive_handles_stdin_parameter(self, org_commands, mock_db, mock_navigator):
        """Test that archive command accepts but ignores stdin parameter"""
        mock_navigator.resolve_prefix.return_value = None

        result = org_commands.cmd_archive(['conv_12345678'], stdin='ignored input')

        assert result.success is True
        mock_db.archive_conversation.assert_called_once_with('conv_12345678')

    @pytest.mark.unit
    def test_multiple_operations_same_conversation(self, org_commands, mock_db, mock_navigator):
        """Test multiple operations on the same conversation"""
        conv_id = 'conv_12345678'
        mock_navigator.resolve_prefix.return_value = None

        # Star it
        result1 = org_commands.cmd_star([conv_id])
        assert result1.success is True

        # Pin it
        result2 = org_commands.cmd_pin([conv_id])
        assert result2.success is True

        # Set title
        mock_db.update_conversation_metadata.return_value = True
        result3 = org_commands.cmd_title([conv_id, 'Important', 'Conversation'])
        assert result3.success is True

        # Verify all operations called
        mock_db.star_conversation.assert_called_once_with(conv_id)
        mock_db.pin_conversation.assert_called_once_with(conv_id)
        mock_db.update_conversation_metadata.assert_called_once_with(
            conv_id, title='Important Conversation'
        )
