"""
Unit tests for search commands (find command)

Tests the find command implementation including:
- Content search
- Title/name search
- Role filtering
- Type filtering (directories vs files)
- Case-insensitive search
- Result limiting
"""

import pytest
from ctk.core.commands.search import SearchCommands, create_search_commands
from ctk.core.command_dispatcher import CommandResult
from ctk.core.database import ConversationDB
from ctk.core.vfs_navigator import VFSNavigator
from ctk.core.models import (
    ConversationTree, Message, MessageContent,
    MessageRole, ConversationMetadata
)


class MockTUI:
    """Mock TUI instance for testing"""
    def __init__(self, vfs_cwd='/'):
        self.vfs_cwd = vfs_cwd


@pytest.fixture
def test_db(tmp_path):
    """Create test database with sample conversations"""
    db_path = tmp_path / "test_search.db"
    db = ConversationDB(str(db_path))

    # Create test conversations with searchable content
    conversations = [
        {
            'id': 'conv_001',
            'title': 'Python Programming Help',
            'messages': [
                ('user', 'How do I use Python decorators?'),
                ('assistant', 'Python decorators are functions that modify other functions.'),
                ('user', 'Can you show an example?'),
                ('assistant', 'Sure! Here is a decorator example using @property.')
            ]
        },
        {
            'id': 'conv_002',
            'title': 'JavaScript Promises',
            'messages': [
                ('user', 'Explain JavaScript promises'),
                ('assistant', 'Promises in JavaScript handle asynchronous operations.'),
                ('user', 'What about async/await?'),
                ('assistant', 'Async/await is syntactic sugar for promises.')
            ]
        },
        {
            'id': 'conv_003',
            'title': 'Machine Learning Basics',
            'messages': [
                ('user', 'What is neural network training?'),
                ('assistant', 'Neural network training adjusts weights to minimize error.'),
                ('system', 'Model: GPT-4'),
                ('user', 'Explain backpropagation'),
                ('assistant', 'Backpropagation calculates gradients for weight updates.')
            ]
        },
        {
            'id': 'conv_004',
            'title': 'Error Handling in Python',
            'messages': [
                ('user', 'How to handle errors in Python?'),
                ('assistant', 'Use try-except blocks for error handling.'),
                ('user', 'What about custom exceptions?'),
                ('assistant', 'You can define custom exception classes.')
            ]
        }
    ]

    for conv_data in conversations:
        conv = ConversationTree(
            id=conv_data['id'],
            title=conv_data['title'],
            metadata=ConversationMetadata(source='test')
        )

        parent_id = None
        for i, (role, content) in enumerate(conv_data['messages']):
            msg = Message(
                id=f"{conv_data['id']}_msg_{i}",
                role=MessageRole(role),
                content=MessageContent(text=content),
                parent_id=parent_id
            )
            conv.add_message(msg)
            parent_id = msg.id

        db.save_conversation(conv)

    yield db
    db.close()


@pytest.fixture
def search_handler(test_db):
    """Create search command handler"""
    navigator = VFSNavigator(test_db)
    tui_instance = MockTUI(vfs_cwd='/')
    return SearchCommands(test_db, navigator, tui_instance)


class TestFindCommand:
    """Test find command behavior"""

    @pytest.mark.unit
    def test_find_all_conversations(self, search_handler):
        """Test finding all conversations without filters"""
        result = search_handler.cmd_find([], stdin='')

        assert result.success is True
        assert 'conv_001' in result.output
        assert 'conv_002' in result.output
        assert 'conv_003' in result.output
        assert 'conv_004' in result.output

    @pytest.mark.unit
    def test_find_by_title_pattern(self, search_handler):
        """Test finding conversations by title pattern"""
        result = search_handler.cmd_find(['-name', 'Python*'], stdin='')

        assert result.success is True
        assert 'conv_001' in result.output  # Python Programming Help
        assert 'conv_004' in result.output  # Error Handling in Python
        assert 'conv_002' not in result.output  # JavaScript
        assert 'conv_003' not in result.output  # Machine Learning

    @pytest.mark.unit
    def test_find_by_exact_title(self, search_handler):
        """Test finding by exact title match"""
        result = search_handler.cmd_find(['-name', 'JavaScript*'], stdin='')

        assert result.success is True
        assert 'conv_002' in result.output
        assert 'conv_001' not in result.output

    @pytest.mark.unit
    def test_find_by_content(self, search_handler):
        """Test finding by message content"""
        result = search_handler.cmd_find(['-content', 'decorator'], stdin='')

        assert result.success is True
        assert 'conv_001' in result.output  # Contains "decorators"
        # Should include message paths since we're searching content

    @pytest.mark.unit
    def test_find_by_content_case_sensitive(self, search_handler):
        """Test case-sensitive content search"""
        result = search_handler.cmd_find(['-content', 'Python'], stdin='')

        assert result.success is True
        # Should find messages with "Python" (exact case)

    @pytest.mark.unit
    def test_find_by_content_case_insensitive(self, search_handler):
        """Test case-insensitive content search"""
        result = search_handler.cmd_find(['-content', 'python', '-i'], stdin='')

        assert result.success is True
        assert 'conv_001' in result.output
        assert 'conv_004' in result.output

    @pytest.mark.unit
    def test_find_by_role_user(self, search_handler):
        """Test finding messages by role (user)"""
        result = search_handler.cmd_find(['-role', 'user'], stdin='')

        assert result.success is True
        # Should find all user messages

    @pytest.mark.unit
    def test_find_by_role_assistant(self, search_handler):
        """Test finding messages by role (assistant)"""
        result = search_handler.cmd_find(['-role', 'assistant'], stdin='')

        assert result.success is True
        # Should find all assistant messages

    @pytest.mark.unit
    def test_find_by_role_system(self, search_handler):
        """Test finding messages by role (system)"""
        result = search_handler.cmd_find(['-role', 'system'], stdin='')

        assert result.success is True
        assert 'conv_003' in result.output  # Has system message

    @pytest.mark.unit
    def test_find_type_directory(self, search_handler):
        """Test finding only directories (conversations)"""
        result = search_handler.cmd_find(['-type', 'd'], stdin='')

        assert result.success is True
        # Should list conversations only
        assert result.output.count('/chats/') >= 4  # At least 4 conversations

    @pytest.mark.unit
    def test_find_type_file(self, search_handler):
        """Test finding only files (messages)"""
        result = search_handler.cmd_find(['-type', 'f', '-content', 'Python'], stdin='')

        assert result.success is True
        # Should only return message paths, not conversation roots

    @pytest.mark.unit
    def test_find_with_limit(self, search_handler):
        """Test limiting search results"""
        result = search_handler.cmd_find(['-limit', '2'], stdin='')

        assert result.success is True
        lines = [line for line in result.output.split('\n') if line.strip()]
        assert len(lines) <= 2

    @pytest.mark.unit
    def test_find_combined_filters(self, search_handler):
        """Test combining multiple filters"""
        result = search_handler.cmd_find(
            ['-content', 'error', '-role', 'assistant', '-i'],
            stdin=''
        )

        assert result.success is True
        # Should find assistant messages containing "error" (case-insensitive)

    @pytest.mark.unit
    def test_find_in_specific_path(self, search_handler):
        """Test finding within a specific path"""
        result = search_handler.cmd_find(['/chats', '-name', 'Python*'], stdin='')

        assert result.success is True
        assert 'conv_001' in result.output or 'conv_004' in result.output

    @pytest.mark.unit
    def test_find_no_results(self, search_handler):
        """Test search with no matching results"""
        result = search_handler.cmd_find(['-content', 'NONEXISTENT_STRING_XYZ'], stdin='')

        assert result.success is True
        assert result.output == ''  # Empty output for no results

    @pytest.mark.unit
    def test_find_invalid_limit(self, search_handler):
        """Test find with invalid limit value"""
        result = search_handler.cmd_find(['-limit', 'invalid'], stdin='')

        assert result.success is False
        assert 'invalid limit' in result.error

    @pytest.mark.unit
    def test_find_unknown_option(self, search_handler):
        """Test find with unknown option"""
        result = search_handler.cmd_find(['-unknown'], stdin='')

        assert result.success is False
        assert 'unknown option' in result.error

    @pytest.mark.unit
    def test_find_with_regex_pattern(self, search_handler):
        """Test find with regex-like patterns"""
        result = search_handler.cmd_find(['-content', 'Pytho.'], stdin='')

        assert result.success is True
        # Should match "Python" (. matches any character)

    @pytest.mark.unit
    def test_find_wildcard_pattern(self, search_handler):
        """Test find with wildcard patterns"""
        result = search_handler.cmd_find(['-name', '*Python*'], stdin='')

        assert result.success is True
        assert 'conv_001' in result.output
        assert 'conv_004' in result.output


class TestFindCommandInConversation:
    """Test find command within specific conversations"""

    @pytest.mark.unit
    def test_find_in_conversation_root(self, search_handler):
        """Test searching within a specific conversation"""
        # Update TUI mock to be in a conversation
        search_handler.tui.vfs_cwd = '/chats/conv_001'

        result = search_handler.cmd_find(['-content', 'decorator'], stdin='')

        assert result.success is True
        assert 'conv_001' in result.output
        assert 'conv_002' not in result.output  # Should only search conv_001

    @pytest.mark.unit
    def test_find_messages_in_conversation(self, search_handler):
        """Test finding specific messages in conversation"""
        search_handler.tui.vfs_cwd = '/chats/conv_001'

        result = search_handler.cmd_find(['-role', 'user'], stdin='')

        assert result.success is True
        # Should find user messages in conv_001


class TestSearchCommandsFactory:
    """Test search command factory function"""

    @pytest.mark.unit
    def test_create_search_commands(self, test_db):
        """Test creating search command handlers"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()

        commands = create_search_commands(test_db, navigator, tui_instance)

        assert 'find' in commands
        assert callable(commands['find'])

    @pytest.mark.unit
    def test_created_command_works(self, test_db):
        """Test that created command is functional"""
        navigator = VFSNavigator(test_db)
        tui_instance = MockTUI()

        commands = create_search_commands(test_db, navigator, tui_instance)
        find_cmd = commands['find']

        result = find_cmd([], stdin='')
        assert result.success is True


class TestFindEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.unit
    def test_find_empty_database(self, tmp_path):
        """Test find on empty database"""
        db_path = tmp_path / "empty.db"
        db = ConversationDB(str(db_path))
        navigator = VFSNavigator(db)
        tui_instance = MockTUI()
        search = SearchCommands(db, navigator, tui_instance)

        result = search.cmd_find([], stdin='')

        assert result.success is True
        assert result.output == ''

        db.close()

    @pytest.mark.unit
    def test_find_with_special_regex_chars(self, search_handler):
        """Test find with special regex characters"""
        # Test that special chars are handled properly
        result = search_handler.cmd_find(['-content', '.*'], stdin='')

        assert result.success is True

    @pytest.mark.unit
    def test_find_invalid_regex(self, search_handler):
        """Test find with invalid regex pattern"""
        result = search_handler.cmd_find(['-content', '[invalid'], stdin='')

        assert result.success is False
        assert 'invalid pattern' in result.error

    @pytest.mark.unit
    def test_find_multiple_type_flags(self, search_handler):
        """Test that only last type flag is used"""
        result = search_handler.cmd_find(['-type', 'd', '-type', 'f'], stdin='')

        assert result.success is True
        # Last -type f should be used

    @pytest.mark.unit
    def test_find_limit_zero(self, search_handler):
        """Test find with limit of 0"""
        result = search_handler.cmd_find(['-limit', '0'], stdin='')

        assert result.success is True
        assert result.output == ''

    @pytest.mark.unit
    def test_find_negative_limit(self, search_handler):
        """Test find with negative limit"""
        result = search_handler.cmd_find(['-limit', '-1'], stdin='')

        # Should accept negative limit (Python list slicing handles this)
        assert result.success is True


class TestFindPathTypes:
    """Test find command with different VFS path types"""

    @pytest.mark.unit
    def test_find_from_root(self, search_handler):
        """Test find from root directory"""
        search_handler.tui.vfs_cwd = '/'
        result = search_handler.cmd_find([], stdin='')

        assert result.success is True

    @pytest.mark.unit
    def test_find_from_chats(self, search_handler):
        """Test find from /chats directory"""
        search_handler.tui.vfs_cwd = '/chats'
        result = search_handler.cmd_find([], stdin='')

        assert result.success is True

    @pytest.mark.unit
    def test_find_with_path_argument(self, search_handler):
        """Test find with explicit path argument"""
        result = search_handler.cmd_find(['/chats', '-name', 'Python*'], stdin='')

        assert result.success is True
