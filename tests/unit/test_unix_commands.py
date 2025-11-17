"""
Unit tests for Unix commands

Tests the UnixCommands class for:
- cat: Display message content and metadata files
- head: First N lines
- tail: Last N lines
- echo: Echo text
- grep: Search patterns with -i, -n flags
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from ctk.core.commands.unix import UnixCommands, create_unix_commands
from ctk.core.command_dispatcher import CommandResult
from ctk.core.vfs_navigator import VFSNavigator
from ctk.core.database import ConversationDB
from ctk.core.models import ConversationTree, Message, MessageContent, MessageRole
from ctk.core.vfs import VFSPath, VFSPathParser, PathType


class TestUnixCommands:
    """Test UnixCommands class"""

    @pytest.fixture
    def mock_db(self):
        """Create mock database"""
        return Mock(spec=ConversationDB)

    @pytest.fixture
    def mock_navigator(self):
        """Create mock VFS navigator"""
        return Mock(spec=VFSNavigator)

    @pytest.fixture
    def mock_tui(self):
        """Create mock TUI instance"""
        tui = Mock()
        tui.vfs_cwd = '/chats'
        return tui

    @pytest.fixture
    def unix_commands(self, mock_db, mock_navigator, mock_tui):
        """Create UnixCommands instance with mocks"""
        return UnixCommands(mock_db, mock_navigator, mock_tui)

    @pytest.fixture
    def sample_conversation(self):
        """Create sample conversation for testing"""
        conv = Mock(spec=ConversationTree)
        conv.id = 'abc123'
        conv.title = 'Test Conversation'
        conv.root_message_ids = ['msg1']

        # Create messages
        msg1 = Mock(spec=Message)
        msg1.id = 'msg1'
        msg1.role = MessageRole.USER
        msg1.content = Mock(spec=MessageContent)
        msg1.content.get_text.return_value = 'Hello, world!'
        msg1.content.text = 'Hello, world!'
        msg1.timestamp = datetime(2025, 1, 1, 12, 0, 0)

        msg2 = Mock(spec=Message)
        msg2.id = 'msg2'
        msg2.role = MessageRole.ASSISTANT
        msg2.content = Mock(spec=MessageContent)
        msg2.content.get_text.return_value = 'Hi there!'
        msg2.content.text = 'Hi there!'
        msg2.timestamp = datetime(2025, 1, 1, 12, 0, 1)

        conv.message_map = {'msg1': msg1, 'msg2': msg2}
        conv.get_children.return_value = [msg2]
        conv.get_longest_path.return_value = [msg1, msg2]

        return conv

    # cmd_cat Tests - Basic Usage

    @pytest.mark.unit
    def test_cat_stdin(self, unix_commands):
        """Test cat with stdin returns stdin"""
        result = unix_commands.cmd_cat([], stdin="Hello from stdin\n")

        assert result.success is True
        assert result.output == "Hello from stdin\n"

    @pytest.mark.unit
    def test_cat_no_args_no_stdin(self, unix_commands):
        """Test cat with no args and no stdin fails"""
        result = unix_commands.cmd_cat([])

        assert result.success is False
        assert "missing operand" in result.error

    @pytest.mark.unit
    def test_cat_message_file_text(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test cat on message text file"""
        mock_tui.vfs_cwd = '/chats/abc123'

        # Mock path parser
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_FILE
        mock_parsed.conversation_id = 'abc123'
        mock_parsed.message_path = ['m1']
        mock_parsed.file_name = 'text'
        mock_parsed.normalized_path = '/chats/abc123/m1/text'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = sample_conversation

            result = unix_commands.cmd_cat(['m1/text'])

            assert result.success is True
            assert 'Hello, world!' in result.output

    @pytest.mark.unit
    def test_cat_message_file_role(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test cat on message role file"""
        mock_tui.vfs_cwd = '/chats/abc123'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_FILE
        mock_parsed.conversation_id = 'abc123'
        mock_parsed.message_path = ['m1']
        mock_parsed.file_name = 'role'
        mock_parsed.normalized_path = '/chats/abc123/m1/role'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = sample_conversation

            result = unix_commands.cmd_cat(['m1/role'])

            assert result.success is True
            assert 'user' in result.output.lower()

    @pytest.mark.unit
    def test_cat_message_file_timestamp(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test cat on message timestamp file"""
        mock_tui.vfs_cwd = '/chats/abc123'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_FILE
        mock_parsed.conversation_id = 'abc123'
        mock_parsed.message_path = ['m1']
        mock_parsed.file_name = 'timestamp'
        mock_parsed.normalized_path = '/chats/abc123/m1/timestamp'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = sample_conversation

            result = unix_commands.cmd_cat(['m1/timestamp'])

            assert result.success is True
            assert '2025' in result.output

    @pytest.mark.unit
    def test_cat_message_file_id(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test cat on message id file"""
        mock_tui.vfs_cwd = '/chats/abc123'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_FILE
        mock_parsed.conversation_id = 'abc123'
        mock_parsed.message_path = ['m1']
        mock_parsed.file_name = 'id'
        mock_parsed.normalized_path = '/chats/abc123/m1/id'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = sample_conversation

            result = unix_commands.cmd_cat(['m1/id'])

            assert result.success is True
            assert 'msg1' in result.output

    @pytest.mark.unit
    def test_cat_message_file_empty_text(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test cat on empty message text shows [empty]"""
        mock_tui.vfs_cwd = '/chats/abc123'

        # Modify message to have empty content
        sample_conversation.message_map['msg1'].content.get_text.return_value = ''

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_FILE
        mock_parsed.conversation_id = 'abc123'
        mock_parsed.message_path = ['m1']
        mock_parsed.file_name = 'text'
        mock_parsed.normalized_path = '/chats/abc123/m1/text'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = sample_conversation

            result = unix_commands.cmd_cat(['m1/text'])

            assert result.success is True
            assert '[empty]' in result.output

    @pytest.mark.unit
    def test_cat_message_node(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test cat on message node displays message with role"""
        mock_tui.vfs_cwd = '/chats/abc123'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_NODE
        mock_parsed.conversation_id = 'abc123'
        mock_parsed.message_path = ['m1']
        mock_parsed.normalized_path = '/chats/abc123/m1'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = sample_conversation

            result = unix_commands.cmd_cat(['m1'])

            assert result.success is True
            assert 'User:' in result.output or 'user:' in result.output.lower()
            assert 'Hello, world!' in result.output

    @pytest.mark.unit
    def test_cat_conversation(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test cat on conversation displays all messages on longest path"""
        mock_tui.vfs_cwd = '/chats'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.CONVERSATION
        mock_parsed.conversation_id = 'abc123'
        mock_parsed.normalized_path = '/chats/abc123'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = sample_conversation

            result = unix_commands.cmd_cat(['abc123'])

            assert result.success is True
            assert 'Hello, world!' in result.output
            assert 'Hi there!' in result.output

    @pytest.mark.unit
    def test_cat_absolute_path(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test cat with absolute path"""
        mock_tui.vfs_cwd = '/chats'

        # Absolute paths are simpler - no relative path resolution
        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_NODE
        mock_parsed.conversation_id = 'abc123'
        mock_parsed.message_path = ['m1']
        mock_parsed.normalized_path = '/chats/abc123/m1'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = sample_conversation

            result = unix_commands.cmd_cat(['/chats/abc123/m1'])

            assert result.success is True
            assert 'Hello, world!' in result.output

    # cmd_cat Tests - Error Cases

    @pytest.mark.unit
    def test_cat_conversation_not_found(self, unix_commands, mock_db, mock_tui):
        """Test cat with non-existent conversation"""
        mock_tui.vfs_cwd = '/chats'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_FILE
        mock_parsed.conversation_id = 'nonexistent'
        mock_parsed.message_path = ['m1']
        mock_parsed.file_name = 'text'
        mock_parsed.normalized_path = '/chats/nonexistent/m1/text'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = None

            result = unix_commands.cmd_cat(['nonexistent/m1/text'])

            assert result.success is False
            assert 'not found' in result.error.lower()

    @pytest.mark.unit
    def test_cat_invalid_message_node(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test cat with invalid message node format"""
        mock_tui.vfs_cwd = '/chats/abc123'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_FILE
        mock_parsed.conversation_id = 'abc123'
        mock_parsed.message_path = ['invalid']  # Doesn't start with 'm'
        mock_parsed.file_name = 'text'
        mock_parsed.normalized_path = '/chats/abc123/invalid/text'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = sample_conversation

            result = unix_commands.cmd_cat(['invalid/text'])

            assert result.success is False
            assert 'Invalid message node' in result.error

    @pytest.mark.unit
    def test_cat_message_out_of_range(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test cat with message index out of range"""
        mock_tui.vfs_cwd = '/chats/abc123'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_FILE
        mock_parsed.conversation_id = 'abc123'
        mock_parsed.message_path = ['m99']  # Out of range
        mock_parsed.file_name = 'text'
        mock_parsed.normalized_path = '/chats/abc123/m99/text'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = sample_conversation

            result = unix_commands.cmd_cat(['m99/text'])

            assert result.success is False
            assert 'out of range' in result.error.lower()

    @pytest.mark.unit
    def test_cat_unknown_metadata_file(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test cat with unknown metadata file"""
        mock_tui.vfs_cwd = '/chats/abc123'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.MESSAGE_FILE
        mock_parsed.conversation_id = 'abc123'
        mock_parsed.message_path = ['m1']
        mock_parsed.file_name = 'unknown'  # Invalid file name
        mock_parsed.normalized_path = '/chats/abc123/m1/unknown'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            mock_db.load_conversation.return_value = sample_conversation

            result = unix_commands.cmd_cat(['m1/unknown'])

            assert result.success is False
            assert 'Unknown metadata file' in result.error

    @pytest.mark.unit
    def test_cat_not_message_or_conversation(self, unix_commands, mock_db, mock_tui):
        """Test cat on path that is not a message or conversation"""
        mock_tui.vfs_cwd = '/'

        mock_parsed = Mock(spec=VFSPath)
        mock_parsed.path_type = PathType.ROOT  # Not a message or conversation
        mock_parsed.normalized_path = '/'

        with patch.object(VFSPathParser, 'parse', return_value=mock_parsed):
            result = unix_commands.cmd_cat(['/'])

            assert result.success is False
            assert 'Not a message or conversation' in result.error

    # cmd_head Tests

    @pytest.mark.unit
    def test_head_default_10_lines(self, unix_commands):
        """Test head defaults to 10 lines"""
        stdin = '\n'.join([f'line{i}' for i in range(20)])

        result = unix_commands.cmd_head([], stdin=stdin)

        assert result.success is True
        lines = result.output.strip().split('\n')
        assert len(lines) == 10
        assert lines[0] == 'line0'
        assert lines[9] == 'line9'

    @pytest.mark.unit
    def test_head_custom_n(self, unix_commands):
        """Test head with custom line count"""
        stdin = '\n'.join([f'line{i}' for i in range(20)])

        result = unix_commands.cmd_head(['5'], stdin=stdin)

        assert result.success is True
        lines = result.output.strip().split('\n')
        assert len(lines) == 5
        assert lines[0] == 'line0'
        assert lines[4] == 'line4'

    @pytest.mark.unit
    def test_head_empty_input(self, unix_commands):
        """Test head with empty input"""
        result = unix_commands.cmd_head([], stdin='')

        assert result.success is True
        assert result.output == ''

    @pytest.mark.unit
    def test_head_fewer_lines_than_requested(self, unix_commands):
        """Test head when input has fewer lines than requested"""
        stdin = 'line1\nline2\nline3'

        result = unix_commands.cmd_head(['10'], stdin=stdin)

        assert result.success is True
        assert result.output == stdin + '\n'

    @pytest.mark.unit
    def test_head_from_path(self, unix_commands, mock_db, mock_tui, sample_conversation):
        """Test head reading from path"""
        mock_tui.vfs_cwd = '/chats/abc123'

        # Mock cat to return multi-line content
        with patch.object(unix_commands, 'cmd_cat') as mock_cat:
            mock_cat.return_value = CommandResult(
                success=True,
                output='line1\nline2\nline3\nline4\nline5\n'
            )

            result = unix_commands.cmd_head(['m1/text', '3'])

            assert result.success is True
            lines = result.output.strip().split('\n')
            assert len(lines) == 3
            assert lines[0] == 'line1'

    @pytest.mark.unit
    def test_head_path_error_propagates(self, unix_commands):
        """Test head propagates cat errors"""
        with patch.object(unix_commands, 'cmd_cat') as mock_cat:
            mock_cat.return_value = CommandResult(
                success=False,
                output='',
                error='File not found'
            )

            result = unix_commands.cmd_head(['nonexistent'])

            assert result.success is False
            assert result.error == 'File not found'

    # cmd_tail Tests

    @pytest.mark.unit
    def test_tail_default_10_lines(self, unix_commands):
        """Test tail defaults to 10 lines"""
        stdin = '\n'.join([f'line{i}' for i in range(20)])

        result = unix_commands.cmd_tail([], stdin=stdin)

        assert result.success is True
        lines = result.output.strip().split('\n')
        assert len(lines) == 10
        assert lines[0] == 'line10'
        assert lines[9] == 'line19'

    @pytest.mark.unit
    def test_tail_custom_n(self, unix_commands):
        """Test tail with custom line count"""
        stdin = '\n'.join([f'line{i}' for i in range(20)])

        result = unix_commands.cmd_tail(['5'], stdin=stdin)

        assert result.success is True
        lines = result.output.strip().split('\n')
        assert len(lines) == 5
        assert lines[0] == 'line15'
        assert lines[4] == 'line19'

    @pytest.mark.unit
    def test_tail_empty_input(self, unix_commands):
        """Test tail with empty input"""
        result = unix_commands.cmd_tail([], stdin='')

        assert result.success is True
        assert result.output == ''

    @pytest.mark.unit
    def test_tail_fewer_lines_than_requested(self, unix_commands):
        """Test tail when input has fewer lines than requested"""
        stdin = 'line1\nline2\nline3'

        result = unix_commands.cmd_tail(['10'], stdin=stdin)

        assert result.success is True
        assert 'line1' in result.output
        assert 'line3' in result.output

    @pytest.mark.unit
    def test_tail_from_path(self, unix_commands):
        """Test tail reading from path"""
        with patch.object(unix_commands, 'cmd_cat') as mock_cat:
            mock_cat.return_value = CommandResult(
                success=True,
                output='line1\nline2\nline3\nline4\nline5\n'
            )

            result = unix_commands.cmd_tail(['m1/text', '3'])

            assert result.success is True
            lines = result.output.strip().split('\n')
            assert len(lines) == 3
            assert lines[2] == 'line5'

    # cmd_echo Tests

    @pytest.mark.unit
    def test_echo_simple_text(self, unix_commands):
        """Test echo with simple text"""
        result = unix_commands.cmd_echo(['hello', 'world'])

        assert result.success is True
        assert result.output == 'hello world\n'

    @pytest.mark.unit
    def test_echo_no_args(self, unix_commands):
        """Test echo with no args prints newline"""
        result = unix_commands.cmd_echo([])

        assert result.success is True
        assert result.output == '\n'

    @pytest.mark.unit
    def test_echo_single_arg(self, unix_commands):
        """Test echo with single argument"""
        result = unix_commands.cmd_echo(['hello'])

        assert result.success is True
        assert result.output == 'hello\n'

    @pytest.mark.unit
    def test_echo_multiple_args(self, unix_commands):
        """Test echo with multiple arguments"""
        result = unix_commands.cmd_echo(['one', 'two', 'three'])

        assert result.success is True
        assert result.output == 'one two three\n'

    @pytest.mark.unit
    def test_echo_ignores_stdin(self, unix_commands):
        """Test echo ignores stdin"""
        result = unix_commands.cmd_echo(['hello'], stdin='ignored')

        assert result.success is True
        assert result.output == 'hello\n'
        assert 'ignored' not in result.output

    # cmd_grep Tests

    @pytest.mark.unit
    def test_grep_no_pattern(self, unix_commands):
        """Test grep without pattern fails"""
        result = unix_commands.cmd_grep([], stdin='some text')

        assert result.success is False
        assert 'no pattern specified' in result.error.lower()

    @pytest.mark.unit
    def test_grep_simple_pattern(self, unix_commands):
        """Test grep with simple pattern"""
        stdin = 'hello\nworld\nhello again\nfoo'

        result = unix_commands.cmd_grep(['hello'], stdin=stdin)

        assert result.success is True
        assert 'hello' in result.output
        assert 'hello again' in result.output
        assert 'world' not in result.output
        assert 'foo' not in result.output

    @pytest.mark.unit
    def test_grep_case_sensitive(self, unix_commands):
        """Test grep is case sensitive by default"""
        stdin = 'Hello\nhello\nHELLO'

        result = unix_commands.cmd_grep(['hello'], stdin=stdin)

        assert result.success is True
        lines = result.output.strip().split('\n')
        assert len(lines) == 1
        assert lines[0] == 'hello'

    @pytest.mark.unit
    def test_grep_case_insensitive(self, unix_commands):
        """Test grep -i flag for case insensitive"""
        stdin = 'Hello\nhello\nHELLO\nworld'

        result = unix_commands.cmd_grep(['-i', 'hello'], stdin=stdin)

        assert result.success is True
        lines = result.output.strip().split('\n')
        assert len(lines) == 3
        assert 'world' not in result.output

    @pytest.mark.unit
    def test_grep_line_numbers(self, unix_commands):
        """Test grep -n flag shows line numbers"""
        stdin = 'line one\nline two\nline three'

        result = unix_commands.cmd_grep(['-n', 'two'], stdin=stdin)

        assert result.success is True
        assert '2:line two' in result.output

    @pytest.mark.unit
    def test_grep_combined_flags(self, unix_commands):
        """Test grep with combined flags -in"""
        stdin = 'Hello\nworld\nHELLO again'

        result = unix_commands.cmd_grep(['-in', 'hello'], stdin=stdin)

        assert result.success is True
        assert '1:Hello' in result.output
        assert '3:HELLO again' in result.output

    @pytest.mark.unit
    def test_grep_regex_pattern(self, unix_commands):
        """Test grep with regex pattern"""
        stdin = 'hello123\nhello456\nworld'

        result = unix_commands.cmd_grep(['hello[0-9]+'], stdin=stdin)

        assert result.success is True
        assert 'hello123' in result.output
        assert 'hello456' in result.output
        assert 'world' not in result.output

    @pytest.mark.unit
    def test_grep_invalid_regex(self, unix_commands):
        """Test grep with invalid regex pattern"""
        result = unix_commands.cmd_grep(['[invalid'], stdin='text')

        assert result.success is False
        assert 'invalid pattern' in result.error.lower()

    @pytest.mark.unit
    def test_grep_empty_input(self, unix_commands):
        """Test grep with empty input"""
        result = unix_commands.cmd_grep(['pattern'], stdin='')

        assert result.success is True
        assert result.output == ''

    @pytest.mark.unit
    def test_grep_no_matches(self, unix_commands):
        """Test grep with no matches"""
        stdin = 'hello\nworld'

        result = unix_commands.cmd_grep(['nomatch'], stdin=stdin)

        assert result.success is True
        # Output should be empty or just newline
        assert result.output.strip() == ''

    @pytest.mark.unit
    def test_grep_from_path(self, unix_commands):
        """Test grep reading from path"""
        with patch.object(unix_commands, 'cmd_cat') as mock_cat:
            mock_cat.return_value = CommandResult(
                success=True,
                output='hello\nworld\nhello again\n'
            )

            result = unix_commands.cmd_grep(['hello', 'm1/text'])

            assert result.success is True
            assert 'hello' in result.output
            assert 'world' not in result.output

    @pytest.mark.unit
    def test_grep_path_error_propagates(self, unix_commands):
        """Test grep propagates cat errors"""
        with patch.object(unix_commands, 'cmd_cat') as mock_cat:
            mock_cat.return_value = CommandResult(
                success=False,
                output='',
                error='File not found'
            )

            result = unix_commands.cmd_grep(['pattern', 'nonexistent'])

            assert result.success is False
            assert result.error == 'File not found'

    # cmd_grep Tests - Flag parsing

    @pytest.mark.unit
    def test_grep_flags_before_pattern(self, unix_commands):
        """Test grep with flags before pattern"""
        stdin = 'HELLO\nworld'

        result = unix_commands.cmd_grep(['-i', 'hello'], stdin=stdin)

        assert result.success is True
        assert 'HELLO' in result.output

    @pytest.mark.unit
    def test_grep_flags_only_no_pattern(self, unix_commands):
        """Test grep with only flags and no pattern fails"""
        result = unix_commands.cmd_grep(['-i', '-n'], stdin='text')

        assert result.success is False
        assert 'no pattern specified' in result.error.lower()


class TestCreateUnixCommands:
    """Test create_unix_commands factory function"""

    @pytest.mark.unit
    def test_create_unix_commands(self):
        """Test factory creates command dictionary"""
        mock_db = Mock(spec=ConversationDB)
        mock_navigator = Mock(spec=VFSNavigator)
        mock_tui = Mock()
        mock_tui.vfs_cwd = '/'

        commands = create_unix_commands(mock_db, mock_navigator, mock_tui)

        assert 'cat' in commands
        assert 'head' in commands
        assert 'tail' in commands
        assert 'echo' in commands
        assert 'grep' in commands
        assert callable(commands['cat'])
        assert callable(commands['head'])
        assert callable(commands['tail'])
        assert callable(commands['echo'])
        assert callable(commands['grep'])

    @pytest.mark.unit
    def test_created_commands_are_bound(self):
        """Test that created commands are bound to same instance"""
        mock_db = Mock(spec=ConversationDB)
        mock_navigator = Mock(spec=VFSNavigator)
        mock_tui = Mock()
        mock_tui.vfs_cwd = '/'

        commands = create_unix_commands(mock_db, mock_navigator, mock_tui)

        # All commands should be methods of the same instance
        assert commands['cat'].__self__ is commands['head'].__self__
        assert commands['head'].__self__ is commands['tail'].__self__
        assert commands['tail'].__self__ is commands['echo'].__self__
        assert commands['echo'].__self__ is commands['grep'].__self__


# Integration-style Tests

class TestUnixCommandIntegration:
    """Integration tests for Unix command workflows"""

    @pytest.fixture
    def setup_integration(self):
        """Setup for integration tests"""
        mock_db = Mock(spec=ConversationDB)
        mock_navigator = Mock(spec=VFSNavigator)
        mock_tui = Mock()
        mock_tui.vfs_cwd = '/chats'
        unix = UnixCommands(mock_db, mock_navigator, mock_tui)
        return unix, mock_db

    @pytest.mark.unit
    def test_cat_pipe_grep(self, setup_integration):
        """Test cat | grep workflow"""
        unix, mock_db = setup_integration

        # Simulate cat output
        cat_output = 'hello world\nfoo bar\nhello again\n'

        # Pipe to grep
        result = unix.cmd_grep(['hello'], stdin=cat_output)

        assert result.success is True
        assert 'hello world' in result.output
        assert 'hello again' in result.output
        assert 'foo bar' not in result.output

    @pytest.mark.unit
    def test_cat_pipe_head(self, setup_integration):
        """Test cat | head workflow"""
        unix, mock_db = setup_integration

        # Simulate cat output
        cat_output = '\n'.join([f'line{i}' for i in range(20)])

        # Pipe to head
        result = unix.cmd_head(['5'], stdin=cat_output)

        assert result.success is True
        lines = result.output.strip().split('\n')
        assert len(lines) == 5
        assert lines[0] == 'line0'

    @pytest.mark.unit
    def test_cat_pipe_grep_pipe_head(self, setup_integration):
        """Test cat | grep | head workflow"""
        unix, mock_db = setup_integration

        # Create input with many matching lines
        cat_output = '\n'.join([f'error {i}' for i in range(20)])

        # Pipe through grep and head
        grep_result = unix.cmd_grep(['error'], stdin=cat_output)
        head_result = unix.cmd_head(['5'], stdin=grep_result.output)

        assert head_result.success is True
        lines = head_result.output.strip().split('\n')
        assert len(lines) == 5

    @pytest.mark.unit
    def test_echo_pipe_grep(self, setup_integration):
        """Test echo | grep workflow"""
        unix, mock_db = setup_integration

        echo_result = unix.cmd_echo(['hello', 'world', 'foo'])
        grep_result = unix.cmd_grep(['world'], stdin=echo_result.output)

        assert grep_result.success is True
        assert 'world' in grep_result.output
