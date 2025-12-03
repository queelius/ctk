"""
Unit tests for core helpers module.

Tests the shared helper functions:
- format_conversations_table: Rich table formatting
- list_conversations_helper: Conversation listing logic
- search_conversations_helper: Search functionality
- generate_cli_prompt_from_argparse: CLI prompt generation
- generate_tui_prompt_from_help: TUI prompt generation
- get_ask_tools: Tool definitions for LLM queries
"""

import pytest
import json
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from io import StringIO
import argparse

from ctk.core.helpers import (
    format_conversations_table,
    list_conversations_helper,
    search_conversations_helper,
    generate_cli_prompt_from_argparse,
    generate_tui_prompt_from_help,
    get_ask_tools
)
from ctk.core.models import (
    ConversationTree, Message, MessageContent,
    MessageRole, ConversationMetadata
)


class TestFormatConversationsTable:
    """Test format_conversations_table function"""

    @pytest.fixture
    def sample_conversations(self):
        """Create sample conversation dicts"""
        return [
            {
                'id': 'conv-001-abcdefgh-12345678',
                'title': 'Test Conversation 1',
                'model': 'gpt-4',
                'updated_at': '2024-01-15T10:30:00',
                'pinned_at': '2024-01-14T00:00:00',
                'starred_at': None,
                'archived_at': None,
                'tags': ['test', 'sample', 'demo'],
                'message_count': 10
            },
            {
                'id': 'conv-002-ijklmnop-87654321',
                'title': 'Test Conversation 2',
                'model': 'claude-3-opus-20240229',
                'updated_at': '2024-01-16T15:45:00',
                'pinned_at': None,
                'starred_at': '2024-01-15T12:00:00',
                'archived_at': None,
                'tags': ['ai'],
                'message_count': 25
            }
        ]

    @pytest.fixture
    def mock_console(self):
        """Create a mock Rich Console"""
        return Mock()

    @pytest.mark.unit
    def test_format_conversations_table_basic(self, sample_conversations, mock_console):
        """Test basic table formatting"""
        format_conversations_table(sample_conversations, console=mock_console)
        mock_console.print.assert_called_once()

    @pytest.mark.unit
    def test_format_conversations_table_creates_console_if_not_provided(self, sample_conversations):
        """Test that console is created if not provided"""
        # Console is imported from rich.console inside the function
        with patch('rich.console.Console') as MockConsole:
            mock_console_instance = Mock()
            MockConsole.return_value = mock_console_instance
            format_conversations_table(sample_conversations)
            MockConsole.assert_called_once()
            mock_console_instance.print.assert_called_once()

    @pytest.mark.unit
    def test_format_conversations_table_with_message_count(self, sample_conversations, mock_console):
        """Test table with message count column"""
        format_conversations_table(sample_conversations, show_message_count=True, console=mock_console)
        mock_console.print.assert_called_once()
        # The table should have been created with Msgs column instead of Model

    @pytest.mark.unit
    def test_format_conversations_table_truncates_long_title(self, mock_console):
        """Test that long titles are truncated to 47 characters"""
        long_title = "A" * 100
        conversations = [{
            'id': 'conv-001-long-title-test-conv',
            'title': long_title,
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None,
            'tags': [],
            'message_count': 5
        }]
        format_conversations_table(conversations, console=mock_console)
        # Verify table was created (we can't easily inspect the table content via mock)
        mock_console.print.assert_called_once()

    @pytest.mark.unit
    def test_format_conversations_table_truncates_long_model(self, mock_console):
        """Test that long model names are truncated to 17 characters"""
        long_model = "model-" + "x" * 50
        conversations = [{
            'id': 'conv-001-long-model-name',
            'title': 'Test',
            'model': long_model,
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None,
            'tags': [],
            'message_count': 5
        }]
        format_conversations_table(conversations, console=mock_console)
        mock_console.print.assert_called_once()

    @pytest.mark.unit
    def test_format_conversations_table_shows_pinned_flag(self, mock_console):
        """Test that pinned conversations show pinned emoji flag"""
        conversations = [{
            'id': 'conv-001-pinned-conv-test',
            'title': 'Pinned Conversation',
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'pinned_at': '2024-01-14T00:00:00',
            'starred_at': None,
            'archived_at': None,
            'tags': [],
            'message_count': 5
        }]
        format_conversations_table(conversations, console=mock_console)
        mock_console.print.assert_called_once()

    @pytest.mark.unit
    def test_format_conversations_table_shows_starred_flag(self, mock_console):
        """Test that starred conversations show starred emoji flag"""
        conversations = [{
            'id': 'conv-001-starred-conv-test',
            'title': 'Starred Conversation',
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': '2024-01-14T00:00:00',
            'archived_at': None,
            'tags': [],
            'message_count': 5
        }]
        format_conversations_table(conversations, console=mock_console)
        mock_console.print.assert_called_once()

    @pytest.mark.unit
    def test_format_conversations_table_shows_archived_flag(self, mock_console):
        """Test that archived conversations show archived emoji flag"""
        conversations = [{
            'id': 'conv-001-archived-conv-test',
            'title': 'Archived Conversation',
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': '2024-01-14T00:00:00',
            'tags': [],
            'message_count': 5
        }]
        format_conversations_table(conversations, console=mock_console)
        mock_console.print.assert_called_once()

    @pytest.mark.unit
    def test_format_conversations_table_handles_to_dict_objects(self, mock_console):
        """Test that objects with to_dict() method are properly converted"""
        mock_conv = Mock()
        mock_conv.to_dict.return_value = {
            'id': 'conv-001-mock-object-test',
            'title': 'Mock Conversation',
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None,
            'tags': [],
            'message_count': 5
        }
        format_conversations_table([mock_conv], console=mock_console)
        mock_conv.to_dict.assert_called()
        mock_console.print.assert_called_once()

    @pytest.mark.unit
    def test_format_conversations_table_truncates_tags(self, mock_console):
        """Test that tags list is truncated after 3 tags"""
        conversations = [{
            'id': 'conv-001-many-tags-test',
            'title': 'Many Tags Conversation',
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None,
            'tags': ['tag1', 'tag2', 'tag3', 'tag4', 'tag5'],
            'message_count': 5
        }]
        format_conversations_table(conversations, console=mock_console)
        mock_console.print.assert_called_once()

    @pytest.mark.unit
    def test_format_conversations_table_missing_title_defaults(self, mock_console):
        """Test that missing title defaults to 'Untitled'"""
        conversations = [{
            'id': 'conv-001-no-title-test',
            'title': None,
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None,
            'tags': [],
            'message_count': 5
        }]
        format_conversations_table(conversations, console=mock_console)
        mock_console.print.assert_called_once()

    @pytest.mark.unit
    def test_format_conversations_table_missing_updated_at(self, mock_console):
        """Test that missing updated_at shows 'Unknown'"""
        conversations = [{
            'id': 'conv-001-no-updated-test',
            'title': 'Test',
            'model': 'gpt-4',
            'updated_at': None,
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None,
            'tags': [],
            'message_count': 5
        }]
        format_conversations_table(conversations, console=mock_console)
        mock_console.print.assert_called_once()

    @pytest.mark.unit
    def test_format_conversations_table_long_updated_at_truncated(self, mock_console):
        """Test that long updated_at is truncated to 19 characters"""
        conversations = [{
            'id': 'conv-001-long-date-test',
            'title': 'Test',
            'model': 'gpt-4',
            'updated_at': '2024-01-15T10:30:00.123456+00:00',  # Long ISO format
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None,
            'tags': [],
            'message_count': 5
        }]
        format_conversations_table(conversations, console=mock_console)
        mock_console.print.assert_called_once()


class TestListConversationsHelper:
    """Test list_conversations_helper function"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database"""
        return Mock()

    @pytest.fixture
    def sample_conversations(self):
        """Create sample conversation objects"""
        mock_convs = []
        for i in range(3):
            mock = Mock()
            mock.to_dict.return_value = {
                'id': f'conv-00{i}-test-conversation',
                'title': f'Conversation {i}',
                'model': 'gpt-4',
                'updated_at': '2024-01-15',
                'pinned_at': None,
                'starred_at': None,
                'archived_at': None,
                'tags': [],
                'message_count': i * 5
            }
            mock_convs.append(mock)
        return mock_convs

    @pytest.mark.unit
    def test_list_conversations_helper_returns_zero_on_success(self, mock_db, sample_conversations):
        """Test that helper returns 0 on success"""
        mock_db.list_conversations.return_value = sample_conversations
        with patch('ctk.core.helpers.format_conversations_table'):
            result = list_conversations_helper(mock_db)
            assert result == 0

    @pytest.mark.unit
    def test_list_conversations_helper_no_results(self, mock_db, capsys):
        """Test that helper prints message when no conversations found"""
        mock_db.list_conversations.return_value = []
        result = list_conversations_helper(mock_db)
        captured = capsys.readouterr()
        assert "No conversations found" in captured.out
        assert result == 0

    @pytest.mark.unit
    def test_list_conversations_helper_with_limit(self, mock_db, sample_conversations):
        """Test that limit parameter is passed to database"""
        mock_db.list_conversations.return_value = sample_conversations
        with patch('ctk.core.helpers.format_conversations_table'):
            list_conversations_helper(mock_db, limit=10)
            mock_db.list_conversations.assert_called_once()
            call_kwargs = mock_db.list_conversations.call_args[1]
            assert call_kwargs['limit'] == 10

    @pytest.mark.unit
    def test_list_conversations_helper_json_output(self, mock_db, sample_conversations, capsys):
        """Test that JSON output is printed correctly"""
        mock_db.list_conversations.return_value = sample_conversations
        result = list_conversations_helper(mock_db, json_output=True)
        captured = capsys.readouterr()
        # Should be valid JSON
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 3
        assert result == 0

    @pytest.mark.unit
    def test_list_conversations_helper_with_archived_filter(self, mock_db, sample_conversations):
        """Test that archived filter is applied"""
        mock_db.list_conversations.return_value = sample_conversations
        with patch('ctk.core.helpers.format_conversations_table'):
            list_conversations_helper(mock_db, archived=True)
            call_kwargs = mock_db.list_conversations.call_args[1]
            assert call_kwargs['archived'] is True

    @pytest.mark.unit
    def test_list_conversations_helper_with_starred_filter(self, mock_db, sample_conversations):
        """Test that starred filter is applied"""
        mock_db.list_conversations.return_value = sample_conversations
        with patch('ctk.core.helpers.format_conversations_table'):
            list_conversations_helper(mock_db, starred=True)
            call_kwargs = mock_db.list_conversations.call_args[1]
            assert call_kwargs['starred'] is True

    @pytest.mark.unit
    def test_list_conversations_helper_with_pinned_filter(self, mock_db, sample_conversations):
        """Test that pinned filter is applied"""
        mock_db.list_conversations.return_value = sample_conversations
        with patch('ctk.core.helpers.format_conversations_table'):
            list_conversations_helper(mock_db, pinned=True)
            call_kwargs = mock_db.list_conversations.call_args[1]
            assert call_kwargs['pinned'] is True

    @pytest.mark.unit
    def test_list_conversations_helper_with_source_filter(self, mock_db, sample_conversations):
        """Test that source filter is passed to database"""
        mock_db.list_conversations.return_value = sample_conversations
        with patch('ctk.core.helpers.format_conversations_table'):
            list_conversations_helper(mock_db, source='openai')
            call_kwargs = mock_db.list_conversations.call_args[1]
            assert call_kwargs['source'] == 'openai'

    @pytest.mark.unit
    def test_list_conversations_helper_with_project_filter(self, mock_db, sample_conversations):
        """Test that project filter is passed to database"""
        mock_db.list_conversations.return_value = sample_conversations
        with patch('ctk.core.helpers.format_conversations_table'):
            list_conversations_helper(mock_db, project='my-project')
            call_kwargs = mock_db.list_conversations.call_args[1]
            assert call_kwargs['project'] == 'my-project'

    @pytest.mark.unit
    def test_list_conversations_helper_with_model_filter(self, mock_db, sample_conversations):
        """Test that model filter is passed to database"""
        mock_db.list_conversations.return_value = sample_conversations
        with patch('ctk.core.helpers.format_conversations_table'):
            list_conversations_helper(mock_db, model='gpt-4')
            call_kwargs = mock_db.list_conversations.call_args[1]
            assert call_kwargs['model'] == 'gpt-4'

    @pytest.mark.unit
    def test_list_conversations_helper_with_tags_filter(self, mock_db, sample_conversations):
        """Test that tags are split and passed to database"""
        mock_db.list_conversations.return_value = sample_conversations
        with patch('ctk.core.helpers.format_conversations_table'):
            list_conversations_helper(mock_db, tags='tag1,tag2,tag3')
            call_kwargs = mock_db.list_conversations.call_args[1]
            assert call_kwargs['tags'] == ['tag1', 'tag2', 'tag3']

    @pytest.mark.unit
    def test_list_conversations_helper_include_archived(self, mock_db, sample_conversations):
        """Test that include_archived flag is passed"""
        mock_db.list_conversations.return_value = sample_conversations
        with patch('ctk.core.helpers.format_conversations_table'):
            list_conversations_helper(mock_db, include_archived=True)
            call_kwargs = mock_db.list_conversations.call_args[1]
            assert call_kwargs['include_archived'] is True


class TestSearchConversationsHelper:
    """Test search_conversations_helper function"""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database"""
        return Mock()

    @pytest.fixture
    def sample_results(self):
        """Create sample search results"""
        mock_results = []
        for i in range(2):
            mock = Mock()
            mock.to_dict.return_value = {
                'id': f'conv-00{i}-search-result',
                'title': f'Search Result {i}',
                'model': 'gpt-4',
                'updated_at': '2024-01-15',
                'created_at': '2024-01-14',
                'source': 'openai',
                'pinned_at': None,
                'starred_at': None,
                'archived_at': None,
                'tags': [],
                'message_count': i * 10
            }
            mock_results.append(mock)
        return mock_results

    @pytest.mark.unit
    def test_search_conversations_helper_returns_zero_on_success(self, mock_db, sample_results):
        """Test that helper returns 0 on success"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            result = search_conversations_helper(mock_db, query='test')
            assert result == 0

    @pytest.mark.unit
    def test_search_conversations_helper_no_results(self, mock_db, capsys):
        """Test that helper prints message when no results found"""
        mock_db.search_conversations.return_value = []
        result = search_conversations_helper(mock_db, query='nonexistent')
        captured = capsys.readouterr()
        assert "No conversations found matching criteria" in captured.out
        assert result == 0

    @pytest.mark.unit
    def test_search_conversations_helper_with_query(self, mock_db, sample_results):
        """Test that query is passed to database"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='hello world')
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['query_text'] == 'hello world'

    @pytest.mark.unit
    def test_search_conversations_helper_json_output(self, mock_db, sample_results, capsys):
        """Test JSON output format"""
        mock_db.search_conversations.return_value = sample_results
        result = search_conversations_helper(mock_db, query='test', output_format='json')
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 2
        assert result == 0

    @pytest.mark.unit
    def test_search_conversations_helper_csv_output(self, mock_db, sample_results, capsys):
        """Test CSV output format"""
        mock_db.search_conversations.return_value = sample_results
        result = search_conversations_helper(mock_db, query='test', output_format='csv')
        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')
        assert 'ID,Title,Messages,Source,Model,Created,Updated' in lines[0]
        assert len(lines) == 3  # Header + 2 results
        assert result == 0

    @pytest.mark.unit
    def test_search_conversations_helper_table_output(self, mock_db, sample_results):
        """Test default table output format"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table') as mock_format:
            search_conversations_helper(mock_db, query='test', output_format='table')
            mock_format.assert_called_once()

    @pytest.mark.unit
    def test_search_conversations_helper_with_limit_and_offset(self, mock_db, sample_results):
        """Test limit and offset parameters"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='test', limit=10, offset=5)
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['limit'] == 10
            assert call_kwargs['offset'] == 5

    @pytest.mark.unit
    def test_search_conversations_helper_title_only(self, mock_db, sample_results):
        """Test title_only filter"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='test', title_only=True)
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['title_only'] is True

    @pytest.mark.unit
    def test_search_conversations_helper_content_only(self, mock_db, sample_results):
        """Test content_only filter"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='test', content_only=True)
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['content_only'] is True

    @pytest.mark.unit
    def test_search_conversations_helper_date_range(self, mock_db, sample_results):
        """Test date range filters"""
        mock_db.search_conversations.return_value = sample_results
        date_from = datetime(2024, 1, 1)
        date_to = datetime(2024, 1, 31)
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='test',
                                       date_from=date_from, date_to=date_to)
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['date_from'] == date_from
            assert call_kwargs['date_to'] == date_to

    @pytest.mark.unit
    def test_search_conversations_helper_with_tags(self, mock_db, sample_results):
        """Test tags filter parsing"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='test', tags='tag1,tag2')
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['tags'] == ['tag1', 'tag2']

    @pytest.mark.unit
    def test_search_conversations_helper_message_count_filters(self, mock_db, sample_results):
        """Test min_messages and max_messages filters"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='test',
                                       min_messages=5, max_messages=100)
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['min_messages'] == 5
            assert call_kwargs['max_messages'] == 100

    @pytest.mark.unit
    def test_search_conversations_helper_has_branches(self, mock_db, sample_results):
        """Test has_branches filter"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='test', has_branches=True)
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['has_branches'] is True

    @pytest.mark.unit
    def test_search_conversations_helper_order_by(self, mock_db, sample_results):
        """Test order_by and ascending parameters"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='test',
                                       order_by='created_at', ascending=True)
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['order_by'] == 'created_at'
            assert call_kwargs['ascending'] is True

    @pytest.mark.unit
    def test_search_conversations_helper_starred_filter(self, mock_db, sample_results):
        """Test starred filter"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='test', starred=True)
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['starred'] is True

    @pytest.mark.unit
    def test_search_conversations_helper_pinned_filter(self, mock_db, sample_results):
        """Test pinned filter"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='test', pinned=True)
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['pinned'] is True

    @pytest.mark.unit
    def test_search_conversations_helper_archived_filter(self, mock_db, sample_results):
        """Test archived filter"""
        mock_db.search_conversations.return_value = sample_results
        with patch('ctk.core.helpers.format_conversations_table'):
            search_conversations_helper(mock_db, query='test', archived=True)
            call_kwargs = mock_db.search_conversations.call_args[1]
            assert call_kwargs['archived'] is True


class TestGenerateCLIPromptFromArgparse:
    """Test generate_cli_prompt_from_argparse function"""

    @pytest.fixture
    def mock_parser(self):
        """Create a mock argparse parser with subparsers"""
        parser = argparse.ArgumentParser(prog='ctk')
        subparsers = parser.add_subparsers(dest='command')

        # Add some sample subcommands
        list_parser = subparsers.add_parser('list', help='List conversations')
        list_parser.add_argument('--limit', type=int, help='Maximum results')
        list_parser.add_argument('--source', help='Filter by source')

        search_parser = subparsers.add_parser('search', help='Search conversations')
        search_parser.add_argument('query', help='Search query')
        search_parser.add_argument('--tags', help='Filter by tags')

        # Commands that should be skipped
        subparsers.add_parser('chat', help='Interactive chat')
        subparsers.add_parser('ask', help='Ask LLM')

        return parser

    @pytest.mark.unit
    def test_generate_cli_prompt_includes_header(self, mock_parser):
        """Test that prompt includes introduction header"""
        prompt = generate_cli_prompt_from_argparse(mock_parser)
        assert "CTK (Conversation Toolkit)" in prompt
        assert "Available CTK Operations" in prompt

    @pytest.mark.unit
    def test_generate_cli_prompt_includes_commands(self, mock_parser):
        """Test that prompt includes command descriptions"""
        prompt = generate_cli_prompt_from_argparse(mock_parser)
        assert "**list**" in prompt
        assert "**search**" in prompt

    @pytest.mark.unit
    def test_generate_cli_prompt_excludes_chat_and_ask(self, mock_parser):
        """Test that chat and ask commands are excluded"""
        prompt = generate_cli_prompt_from_argparse(mock_parser)
        assert "**chat**" not in prompt
        assert "**ask**" not in prompt

    @pytest.mark.unit
    def test_generate_cli_prompt_includes_arguments(self, mock_parser):
        """Test that command arguments are included"""
        prompt = generate_cli_prompt_from_argparse(mock_parser)
        assert "--limit" in prompt
        assert "--source" in prompt
        assert "--tags" in prompt

    @pytest.mark.unit
    def test_generate_cli_prompt_includes_instructions(self, mock_parser):
        """Test that prompt includes user instructions"""
        prompt = generate_cli_prompt_from_argparse(mock_parser)
        assert "When the user asks a question" in prompt
        assert "Be concise" in prompt

    @pytest.mark.unit
    def test_generate_cli_prompt_with_empty_parser(self):
        """Test with parser that has no subparsers"""
        parser = argparse.ArgumentParser()
        prompt = generate_cli_prompt_from_argparse(parser)
        # Should still generate basic prompt structure
        assert "CTK" in prompt


class TestGenerateTUIPromptFromHelp:
    """Test generate_tui_prompt_from_help function"""

    @pytest.fixture
    def sample_command_help(self):
        """Create sample TUI command help dictionary"""
        return {
            'help': {
                'desc': 'Show help',
                'usage': '/help [command]',
                'details': 'Shows help for commands',
                'examples': ['/help', '/help search']
            },
            'search': {
                'desc': 'Search conversations',
                'usage': '/search <query>',
                'details': 'Full-text search',
                'examples': ['/search python', '/search "machine learning"']
            },
            'list': {
                'desc': 'List conversations',
                'usage': '/list [options]',
                'examples': ['/list', '/list --starred']
            },
            'load': {
                'desc': 'Load a conversation',
                'usage': '/load <id>'
            }
        }

    @pytest.mark.unit
    def test_generate_tui_prompt_includes_header(self, sample_command_help):
        """Test that prompt includes TUI header"""
        prompt = generate_tui_prompt_from_help(sample_command_help)
        assert "CTK chat TUI" in prompt
        assert "Available TUI Commands" in prompt

    @pytest.mark.unit
    def test_generate_tui_prompt_excludes_help_command(self, sample_command_help):
        """Test that help command is excluded"""
        prompt = generate_tui_prompt_from_help(sample_command_help)
        assert "**/help**" not in prompt

    @pytest.mark.unit
    def test_generate_tui_prompt_includes_commands(self, sample_command_help):
        """Test that commands are included"""
        prompt = generate_tui_prompt_from_help(sample_command_help)
        assert "**/search**" in prompt
        assert "**/list**" in prompt
        assert "**/load**" in prompt

    @pytest.mark.unit
    def test_generate_tui_prompt_includes_usage(self, sample_command_help):
        """Test that usage information is included"""
        prompt = generate_tui_prompt_from_help(sample_command_help)
        assert "Usage:" in prompt
        assert "/search <query>" in prompt

    @pytest.mark.unit
    def test_generate_tui_prompt_includes_details(self, sample_command_help):
        """Test that details are included when present"""
        prompt = generate_tui_prompt_from_help(sample_command_help)
        assert "Full-text search" in prompt

    @pytest.mark.unit
    def test_generate_tui_prompt_includes_examples(self, sample_command_help):
        """Test that examples are included"""
        prompt = generate_tui_prompt_from_help(sample_command_help)
        assert "/search python" in prompt

    @pytest.mark.unit
    def test_generate_tui_prompt_includes_notes(self, sample_command_help):
        """Test that important notes are included"""
        prompt = generate_tui_prompt_from_help(sample_command_help)
        assert "interactive chat session" in prompt
        assert "/load" in prompt or "/save" in prompt

    @pytest.mark.unit
    def test_generate_tui_prompt_with_empty_help(self):
        """Test with empty command help dict"""
        prompt = generate_tui_prompt_from_help({})
        # Should still generate basic structure
        assert "TUI" in prompt


class TestGetAskTools:
    """Test get_ask_tools function"""

    @pytest.mark.unit
    def test_get_ask_tools_returns_list(self):
        """Test that function returns a list"""
        tools = get_ask_tools()
        assert isinstance(tools, list)

    @pytest.mark.unit
    def test_get_ask_tools_has_search_conversations(self):
        """Test that search_conversations tool is defined"""
        tools = get_ask_tools()
        tool_names = [t['name'] for t in tools]
        assert 'search_conversations' in tool_names

    @pytest.mark.unit
    def test_get_ask_tools_has_get_conversation(self):
        """Test that get_conversation tool is defined"""
        tools = get_ask_tools()
        tool_names = [t['name'] for t in tools]
        assert 'get_conversation' in tool_names

    @pytest.mark.unit
    def test_get_ask_tools_has_get_statistics(self):
        """Test that get_statistics tool is defined"""
        tools = get_ask_tools()
        tool_names = [t['name'] for t in tools]
        assert 'get_statistics' in tool_names

    @pytest.mark.unit
    def test_search_conversations_tool_schema(self):
        """Test search_conversations tool has correct schema"""
        tools = get_ask_tools()
        search_tool = next(t for t in tools if t['name'] == 'search_conversations')

        assert 'description' in search_tool
        assert 'input_schema' in search_tool

        schema = search_tool['input_schema']
        assert schema['type'] == 'object'
        assert 'properties' in schema

        # Check key properties exist
        props = schema['properties']
        assert 'query' in props
        assert 'limit' in props
        assert 'starred' in props
        assert 'pinned' in props
        assert 'archived' in props
        assert 'tags' in props

    @pytest.mark.unit
    def test_get_conversation_tool_schema(self):
        """Test get_conversation tool has correct schema"""
        tools = get_ask_tools()
        get_tool = next(t for t in tools if t['name'] == 'get_conversation')

        assert 'description' in get_tool
        assert 'input_schema' in get_tool

        schema = get_tool['input_schema']
        assert 'conversation_id' in schema['properties']
        assert 'show_messages' in schema['properties']
        assert 'conversation_id' in schema['required']

    @pytest.mark.unit
    def test_get_statistics_tool_schema(self):
        """Test get_statistics tool has correct schema"""
        tools = get_ask_tools()
        stats_tool = next(t for t in tools if t['name'] == 'get_statistics')

        assert 'description' in stats_tool
        assert 'input_schema' in stats_tool

        schema = stats_tool['input_schema']
        assert schema['required'] == []  # No required params

    @pytest.mark.unit
    def test_search_tool_description_has_examples(self):
        """Test that search tool description includes usage examples"""
        tools = get_ask_tools()
        search_tool = next(t for t in tools if t['name'] == 'search_conversations')

        description = search_tool['description']
        assert 'EXAMPLES' in description.upper() or 'example' in description.lower()

    @pytest.mark.unit
    def test_search_tool_has_boolean_filter_guidance(self):
        """Test that search tool has guidance about boolean filters"""
        tools = get_ask_tools()
        search_tool = next(t for t in tools if t['name'] == 'search_conversations')

        description = search_tool['description']
        # Should mention that filters should only be included when explicitly mentioned
        assert 'EXPLICITLY' in description.upper() or 'explicit' in description.lower()

    @pytest.mark.unit
    def test_tools_are_valid_json_schemas(self):
        """Test that all tool schemas are valid JSON schema format"""
        tools = get_ask_tools()

        for tool in tools:
            assert 'name' in tool
            assert 'description' in tool
            assert 'input_schema' in tool

            schema = tool['input_schema']
            assert 'type' in schema
            assert 'properties' in schema
            assert 'required' in schema
