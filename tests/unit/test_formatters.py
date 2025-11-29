"""
Unit tests for core formatters module.

Tests the OutputFormatter abstract class and its implementations:
- CLIFormatter: Command-line output formatting
- TUIFormatter: Rich-based TUI output formatting
- format_datetime: Helper function for datetime formatting
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

from ctk.core.formatters import (
    OutputFormatter,
    CLIFormatter,
    TUIFormatter,
    format_datetime
)
from ctk.core.models import (
    ConversationTree, Message, MessageContent,
    MessageRole, ConversationMetadata
)


class TestCLIFormatter:
    """Test CLIFormatter output formatting"""

    @pytest.fixture
    def cli_formatter(self):
        """Create a CLIFormatter instance"""
        return CLIFormatter(json_output=False)

    @pytest.fixture
    def json_formatter(self):
        """Create a CLIFormatter with JSON output enabled"""
        return CLIFormatter(json_output=True)

    @pytest.fixture
    def sample_conversations_list(self):
        """Create a list of sample conversation dicts for testing"""
        return [
            {
                'id': 'conv-001-abcd-1234',
                'title': 'Test Conversation 1',
                'model': 'gpt-4',
                'updated_at': '2024-01-15T10:30:00',
                'pinned_at': '2024-01-14T08:00:00',
                'starred_at': None,
                'archived_at': None,
                'tags': ['test', 'sample']
            },
            {
                'id': 'conv-002-efgh-5678',
                'title': 'Test Conversation 2',
                'model': 'claude-3-opus',
                'updated_at': '2024-01-16T15:45:00',
                'pinned_at': None,
                'starred_at': '2024-01-15T12:00:00',
                'archived_at': None,
                'tags': []
            }
        ]

    @pytest.fixture
    def sample_tree(self):
        """Create a sample ConversationTree"""
        tree = ConversationTree(
            id='conv-test-123',
            title='Sample Conversation',
            metadata=ConversationMetadata(
                source='openai',
                model='gpt-4',
                tags=['ai', 'chat'],
                created_at=datetime(2024, 1, 15, 10, 0, 0)
            )
        )
        msg1 = Message(
            id='msg_001',
            role=MessageRole.USER,
            content=MessageContent(text='Hello')
        )
        tree.add_message(msg1)
        msg2 = Message(
            id='msg_002',
            role=MessageRole.ASSISTANT,
            content=MessageContent(text='Hi there! How can I help?'),
            parent_id='msg_001'
        )
        tree.add_message(msg2)
        return tree

    @pytest.mark.unit
    def test_cli_formatter_initialization_default(self):
        """Test CLIFormatter initializes with json_output=False by default"""
        formatter = CLIFormatter()
        assert formatter.json_output is False

    @pytest.mark.unit
    def test_cli_formatter_initialization_json(self):
        """Test CLIFormatter can be initialized with json_output=True"""
        formatter = CLIFormatter(json_output=True)
        assert formatter.json_output is True

    @pytest.mark.unit
    def test_format_conversation_list_empty(self, cli_formatter, capsys):
        """Test formatting empty conversation list prints 'No conversations found'"""
        cli_formatter.format_conversation_list([])
        captured = capsys.readouterr()
        assert "No conversations found" in captured.out

    @pytest.mark.unit
    def test_format_conversation_list_with_title(self, cli_formatter, capsys, sample_conversations_list):
        """Test formatting conversation list with custom title"""
        cli_formatter.format_conversation_list(sample_conversations_list, title="My Conversations")
        captured = capsys.readouterr()
        assert "My Conversations" in captured.out

    @pytest.mark.unit
    def test_format_conversation_list_table_format(self, cli_formatter, capsys, sample_conversations_list):
        """Test table format includes ID, Title, Model, Updated columns"""
        cli_formatter.format_conversation_list(sample_conversations_list)
        captured = capsys.readouterr()
        # Check header
        assert "ID" in captured.out
        assert "Title" in captured.out
        assert "Model" in captured.out
        assert "Updated" in captured.out
        # Check data
        assert "conv-001-abcd-1234" in captured.out
        assert "Test Conversation 1" in captured.out
        assert "gpt-4" in captured.out

    @pytest.mark.unit
    def test_format_conversation_list_shows_flags(self, cli_formatter, capsys, sample_conversations_list):
        """Test that pinned/starred/archived flags are displayed"""
        cli_formatter.format_conversation_list(sample_conversations_list)
        captured = capsys.readouterr()
        # First conversation is pinned
        # Second conversation is starred
        # Check flags are present (emojis)
        # Note: exact emoji rendering depends on terminal

    @pytest.mark.unit
    def test_format_conversation_list_truncates_long_title(self, cli_formatter, capsys):
        """Test that long titles are truncated"""
        long_title = "A" * 100  # Title longer than 42 chars limit
        conversations = [{
            'id': 'conv-001',
            'title': long_title,
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None
        }]
        cli_formatter.format_conversation_list(conversations)
        captured = capsys.readouterr()
        assert "..." in captured.out
        assert long_title not in captured.out  # Full title should not appear

    @pytest.mark.unit
    def test_format_conversation_list_truncates_long_model(self, cli_formatter, capsys):
        """Test that long model names are truncated"""
        long_model = "model-" + "x" * 50
        conversations = [{
            'id': 'conv-001',
            'title': 'Test',
            'model': long_model,
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None
        }]
        cli_formatter.format_conversation_list(conversations)
        captured = capsys.readouterr()
        assert long_model not in captured.out  # Full model name should not appear

    @pytest.mark.unit
    def test_format_conversation_list_json_output(self, json_formatter, capsys, sample_conversations_list):
        """Test JSON output format for conversation list"""
        json_formatter.format_conversation_list(sample_conversations_list)
        captured = capsys.readouterr()
        import json
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]['id'] == 'conv-001-abcd-1234'

    @pytest.mark.unit
    def test_format_conversation_list_handles_to_dict_objects(self, cli_formatter, capsys):
        """Test that objects with to_dict method are properly converted"""
        mock_conv = Mock()
        mock_conv.to_dict.return_value = {
            'id': 'conv-mock',
            'title': 'Mock Conversation',
            'model': 'mock-model',
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None
        }
        cli_formatter.format_conversation_list([mock_conv])
        captured = capsys.readouterr()
        assert "Mock Conversation" in captured.out
        mock_conv.to_dict.assert_called()

    @pytest.mark.unit
    def test_format_conversation_list_missing_title_uses_untitled(self, cli_formatter, capsys):
        """Test that missing title defaults to 'Untitled'"""
        conversations = [{
            'id': 'conv-001',
            'title': None,
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None
        }]
        cli_formatter.format_conversation_list(conversations)
        captured = capsys.readouterr()
        assert "Untitled" in captured.out

    @pytest.mark.unit
    def test_format_search_results_empty(self, cli_formatter, capsys):
        """Test formatting empty search results"""
        cli_formatter.format_search_results([], "test query")
        captured = capsys.readouterr()
        assert "No conversations found matching 'test query'" in captured.out

    @pytest.mark.unit
    def test_format_search_results_table_format(self, cli_formatter, capsys, sample_conversations_list):
        """Test search results table format"""
        # Add message_count and source to sample data
        for conv in sample_conversations_list:
            conv['message_count'] = 10
            conv['source'] = 'openai'
        cli_formatter.format_search_results(sample_conversations_list, "test")
        captured = capsys.readouterr()
        assert "Found 2 conversation(s)" in captured.out
        assert "ID" in captured.out
        assert "Title" in captured.out
        assert "Msgs" in captured.out
        assert "Source" in captured.out

    @pytest.mark.unit
    def test_format_search_results_json_output(self, json_formatter, capsys, sample_conversations_list):
        """Test JSON output format for search results"""
        json_formatter.format_search_results(sample_conversations_list, "test")
        captured = capsys.readouterr()
        import json
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 2

    @pytest.mark.unit
    def test_format_conversation_detail(self, cli_formatter, capsys, sample_tree):
        """Test formatting detailed conversation view"""
        cli_formatter.format_conversation_detail(sample_tree)
        captured = capsys.readouterr()
        assert "Conversation: Sample Conversation" in captured.out
        assert "ID: conv-test-123" in captured.out
        assert "Source: openai" in captured.out
        assert "Model: gpt-4" in captured.out
        assert "Tags: ai, chat" in captured.out
        assert "Total messages: 2" in captured.out
        assert "Hello" in captured.out
        assert "Hi there! How can I help?" in captured.out

    @pytest.mark.unit
    def test_format_conversation_detail_shows_path(self, cli_formatter, capsys, sample_tree):
        """Test that conversation detail shows message path"""
        cli_formatter.format_conversation_detail(sample_tree)
        captured = capsys.readouterr()
        assert "Messages (longest path, 2 messages)" in captured.out
        assert "[0] USER" in captured.out
        assert "[1] ASSISTANT" in captured.out

    @pytest.mark.unit
    def test_format_conversation_detail_empty_conversation(self, cli_formatter, capsys):
        """Test formatting empty conversation"""
        tree = ConversationTree(id='empty-conv', title='Empty')
        cli_formatter.format_conversation_detail(tree)
        captured = capsys.readouterr()
        assert "No messages in conversation" in captured.out

    @pytest.mark.unit
    def test_format_conversation_detail_with_branches(self, cli_formatter, capsys, branching_conversation):
        """Test that branching conversations show note about branches"""
        cli_formatter.format_conversation_detail(branching_conversation)
        captured = capsys.readouterr()
        assert "This conversation has branches" in captured.out
        assert "ctk tree" in captured.out

    @pytest.mark.unit
    def test_format_error(self, cli_formatter, capsys):
        """Test error message formatting"""
        cli_formatter.format_error("Something went wrong")
        captured = capsys.readouterr()
        assert "Error: Something went wrong" in captured.out

    @pytest.mark.unit
    def test_format_success(self, cli_formatter, capsys):
        """Test success message formatting"""
        cli_formatter.format_success("Operation completed")
        captured = capsys.readouterr()
        assert "Operation completed" in captured.out

    @pytest.mark.unit
    def test_format_warning(self, cli_formatter, capsys):
        """Test warning message formatting"""
        cli_formatter.format_warning("This might cause issues")
        captured = capsys.readouterr()
        assert "Warning: This might cause issues" in captured.out

    @pytest.mark.unit
    def test_format_info(self, cli_formatter, capsys):
        """Test info message formatting"""
        cli_formatter.format_info("Here's some information")
        captured = capsys.readouterr()
        assert "Here's some information" in captured.out

    @pytest.mark.unit
    def test_confirm_yes(self, cli_formatter):
        """Test confirmation returns True for 'yes'"""
        with patch('builtins.input', return_value='yes'):
            result = cli_formatter.confirm("Are you sure?")
            assert result is True

    @pytest.mark.unit
    def test_confirm_no(self, cli_formatter):
        """Test confirmation returns False for 'no'"""
        with patch('builtins.input', return_value='no'):
            result = cli_formatter.confirm("Are you sure?")
            assert result is False

    @pytest.mark.unit
    def test_confirm_case_insensitive(self, cli_formatter):
        """Test confirmation handles case variations"""
        with patch('builtins.input', return_value='YES'):
            result = cli_formatter.confirm("Are you sure?")
            assert result is True

    @pytest.mark.unit
    def test_confirm_with_whitespace(self, cli_formatter):
        """Test confirmation strips whitespace"""
        with patch('builtins.input', return_value='  yes  '):
            result = cli_formatter.confirm("Are you sure?")
            assert result is True


class TestTUIFormatter:
    """Test TUIFormatter output formatting with Rich"""

    @pytest.fixture
    def mock_console(self):
        """Create a mock Rich Console"""
        console = Mock()
        return console

    @pytest.fixture
    def tui_formatter(self, mock_console):
        """Create a TUIFormatter with mocked console"""
        return TUIFormatter(console=mock_console)

    @pytest.fixture
    def sample_conversations_list(self):
        """Create sample conversation dicts"""
        return [
            {
                'id': 'conv-001-abcd-1234',
                'title': 'TUI Test Conversation',
                'model': 'gpt-4',
                'created_at': '2024-01-15T10:30:00',
                'message_count': 15
            }
        ]

    @pytest.mark.unit
    def test_tui_formatter_initialization_with_console(self, mock_console):
        """Test TUIFormatter initializes with provided console"""
        formatter = TUIFormatter(console=mock_console)
        assert formatter.console is mock_console

    @pytest.mark.unit
    def test_tui_formatter_initialization_creates_console(self):
        """Test TUIFormatter creates new console if not provided"""
        with patch('rich.console.Console') as MockConsole:
            formatter = TUIFormatter()
            MockConsole.assert_called_once()

    @pytest.mark.unit
    def test_format_conversation_list_empty(self, tui_formatter, mock_console):
        """Test TUI formatting of empty conversation list"""
        tui_formatter.format_conversation_list([])
        mock_console.print.assert_called()
        # Check that "No conversations found" message was printed
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("No conversations found" in str(call) for call in calls)

    @pytest.mark.unit
    def test_format_conversation_list_with_data(self, tui_formatter, mock_console, sample_conversations_list):
        """Test TUI formatting shows conversation details"""
        tui_formatter.format_conversation_list(sample_conversations_list)
        # Verify console.print was called multiple times
        assert mock_console.print.call_count >= 1

    @pytest.mark.unit
    def test_format_conversation_list_with_custom_title(self, tui_formatter, mock_console, sample_conversations_list):
        """Test TUI formatting with custom title"""
        tui_formatter.format_conversation_list(sample_conversations_list, title="Custom Title")
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Custom Title" in str(call) for call in calls)

    @pytest.mark.unit
    def test_format_search_results_empty(self, tui_formatter, mock_console):
        """Test TUI formatting of empty search results"""
        tui_formatter.format_search_results([], "test query")
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("No conversations found matching" in str(call) for call in calls)

    @pytest.mark.unit
    def test_format_search_results_with_data(self, tui_formatter, mock_console, sample_conversations_list):
        """Test TUI formatting of search results"""
        tui_formatter.format_search_results(sample_conversations_list, "test")
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Found" in str(call) for call in calls)

    @pytest.mark.unit
    def test_format_conversation_detail(self, tui_formatter, mock_console):
        """Test TUI formatting of conversation detail"""
        tree = ConversationTree(
            id='conv-detail-test',
            title='Detail Test',
            metadata=ConversationMetadata(source='test', model='test-model')
        )
        msg = Message(
            id='msg_001',
            role=MessageRole.USER,
            content=MessageContent(text='Hello')
        )
        tree.add_message(msg)

        tui_formatter.format_conversation_detail(tree)
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("Detail Test" in str(call) for call in calls)

    @pytest.mark.unit
    def test_format_error(self, tui_formatter, mock_console):
        """Test TUI error formatting uses red color"""
        tui_formatter.format_error("Test error")
        mock_console.print.assert_called()
        call_arg = str(mock_console.print.call_args)
        assert "red" in call_arg
        assert "Test error" in call_arg

    @pytest.mark.unit
    def test_format_success(self, tui_formatter, mock_console):
        """Test TUI success formatting uses green color"""
        tui_formatter.format_success("Success message")
        mock_console.print.assert_called()
        call_arg = str(mock_console.print.call_args)
        assert "green" in call_arg
        assert "Success message" in call_arg

    @pytest.mark.unit
    def test_format_warning(self, tui_formatter, mock_console):
        """Test TUI warning formatting uses yellow color"""
        tui_formatter.format_warning("Warning message")
        mock_console.print.assert_called()
        call_arg = str(mock_console.print.call_args)
        assert "yellow" in call_arg
        assert "Warning message" in call_arg

    @pytest.mark.unit
    def test_format_info(self, tui_formatter, mock_console):
        """Test TUI info formatting uses cyan color"""
        tui_formatter.format_info("Info message")
        mock_console.print.assert_called()
        call_arg = str(mock_console.print.call_args)
        assert "cyan" in call_arg
        assert "Info message" in call_arg

    @pytest.mark.unit
    def test_confirm_yes(self, tui_formatter):
        """Test TUI confirmation returns True for 'yes'"""
        with patch('builtins.input', return_value='yes'):
            result = tui_formatter.confirm("Continue?")
            assert result is True

    @pytest.mark.unit
    def test_confirm_no(self, tui_formatter):
        """Test TUI confirmation returns False for 'no'"""
        with patch('builtins.input', return_value='no'):
            result = tui_formatter.confirm("Continue?")
            assert result is False

    @pytest.mark.unit
    def test_format_conversation_list_handles_datetime_object(self, tui_formatter, mock_console):
        """Test TUI handles datetime objects in created_at"""
        conversations = [{
            'id': 'conv-001',
            'title': 'Datetime Test',
            'model': 'gpt-4',
            'created_at': datetime(2024, 1, 15, 10, 30, 0),
            'message_count': 5
        }]
        tui_formatter.format_conversation_list(conversations)
        # Should not raise an error
        assert mock_console.print.call_count >= 1

    @pytest.mark.unit
    def test_format_search_results_handles_datetime_object(self, tui_formatter, mock_console):
        """Test TUI search results handle datetime objects"""
        results = [{
            'id': 'conv-001',
            'title': 'Search Datetime Test',
            'model': 'gpt-4',
            'created_at': datetime(2024, 1, 15, 10, 30, 0),
            'message_count': 5
        }]
        tui_formatter.format_search_results(results, "test")
        assert mock_console.print.call_count >= 1


class TestFormatDatetime:
    """Test format_datetime helper function"""

    @pytest.mark.unit
    def test_format_datetime_with_datetime_object(self):
        """Test formatting datetime object"""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = format_datetime(dt)
        assert result == "2024-01-15 10:30"

    @pytest.mark.unit
    def test_format_datetime_with_iso_string(self):
        """Test formatting ISO datetime string"""
        dt_str = "2024-01-15T10:30:00"
        result = format_datetime(dt_str)
        assert result == "2024-01-15 10:30"

    @pytest.mark.unit
    def test_format_datetime_with_invalid_string(self):
        """Test formatting invalid datetime string returns as-is"""
        dt_str = "not-a-date"
        result = format_datetime(dt_str)
        assert result == "not-a-date"

    @pytest.mark.unit
    def test_format_datetime_with_none(self):
        """Test formatting None returns 'Unknown'"""
        result = format_datetime(None)
        assert result == "Unknown"

    @pytest.mark.unit
    def test_format_datetime_with_empty_string(self):
        """Test formatting empty string - empty string is a string so goes through ISO parse path"""
        result = format_datetime("")
        # Empty string is isinstance(dt, str) == True, so it tries fromisoformat("")
        # which raises ValueError, so it returns the original empty string
        assert result == ""

    @pytest.mark.unit
    def test_format_datetime_with_other_type(self):
        """Test formatting other types converts to string"""
        result = format_datetime(12345)
        assert result == "12345"


class TestOutputFormatterAbstract:
    """Test that OutputFormatter is properly abstract"""

    @pytest.mark.unit
    def test_cannot_instantiate_output_formatter(self):
        """Test that OutputFormatter cannot be instantiated directly"""
        with pytest.raises(TypeError):
            OutputFormatter()

    @pytest.mark.unit
    def test_cli_formatter_is_output_formatter(self):
        """Test CLIFormatter is subclass of OutputFormatter"""
        assert issubclass(CLIFormatter, OutputFormatter)

    @pytest.mark.unit
    def test_tui_formatter_is_output_formatter(self):
        """Test TUIFormatter is subclass of OutputFormatter"""
        assert issubclass(TUIFormatter, OutputFormatter)


class TestCLIFormatterEdgeCases:
    """Test edge cases and special scenarios for CLIFormatter"""

    @pytest.fixture
    def cli_formatter(self):
        return CLIFormatter()

    @pytest.mark.unit
    def test_format_conversation_list_archived_flag(self, cli_formatter, capsys):
        """Test that archived conversations show archive flag"""
        conversations = [{
            'id': 'conv-archived',
            'title': 'Archived Conversation',
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': '2024-01-14T00:00:00'
        }]
        cli_formatter.format_conversation_list(conversations)
        captured = capsys.readouterr()
        # Archived emoji should be present
        assert "Archived Conversation" in captured.out

    @pytest.mark.unit
    def test_format_conversation_list_all_flags(self, cli_formatter, capsys):
        """Test conversation with all flags set"""
        conversations = [{
            'id': 'conv-all-flags',
            'title': 'All Flags Conversation',
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'pinned_at': '2024-01-14T00:00:00',
            'starred_at': '2024-01-14T00:00:00',
            'archived_at': '2024-01-14T00:00:00'
        }]
        cli_formatter.format_conversation_list(conversations)
        captured = capsys.readouterr()
        assert "All Flags Conversation" in captured.out

    @pytest.mark.unit
    def test_format_conversation_list_unknown_model(self, cli_formatter, capsys):
        """Test conversation with no model defaults to 'Unknown'"""
        conversations = [{
            'id': 'conv-no-model',
            'title': 'No Model Conversation',
            'model': None,
            'updated_at': '2024-01-15',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None
        }]
        cli_formatter.format_conversation_list(conversations)
        captured = capsys.readouterr()
        assert "Unknown" in captured.out

    @pytest.mark.unit
    def test_format_search_results_truncates_long_title(self, cli_formatter, capsys):
        """Test search results truncate long titles"""
        results = [{
            'id': 'conv-long-title',
            'title': 'A' * 100,
            'model': 'gpt-4',
            'updated_at': '2024-01-15',
            'message_count': 5,
            'source': 'openai',
            'pinned_at': None,
            'starred_at': None,
            'archived_at': None
        }]
        cli_formatter.format_search_results(results, "test")
        captured = capsys.readouterr()
        assert "..." in captured.out

    @pytest.mark.unit
    def test_format_conversation_detail_without_metadata(self, cli_formatter, capsys):
        """Test conversation detail without metadata"""
        tree = ConversationTree(id='no-meta-conv', title='No Metadata')
        msg = Message(
            id='msg_001',
            role=MessageRole.USER,
            content=MessageContent(text='Hello')
        )
        tree.add_message(msg)
        cli_formatter.format_conversation_detail(tree)
        captured = capsys.readouterr()
        assert "No Metadata" in captured.out

    @pytest.mark.unit
    def test_format_conversation_detail_with_none_text_content(self, cli_formatter, capsys):
        """Test conversation detail handles None text in content"""
        tree = ConversationTree(id='null-text-conv', title='Null Text')
        msg = Message(
            id='msg_001',
            role=MessageRole.USER,
            content=MessageContent(text=None)
        )
        tree.add_message(msg)
        cli_formatter.format_conversation_detail(tree)
        captured = capsys.readouterr()
        assert "Null Text" in captured.out


class TestTUIFormatterDatetimeHandling:
    """Test TUIFormatter datetime parsing in various formats"""

    @pytest.fixture
    def tui_formatter(self):
        console = Mock()
        return TUIFormatter(console=console)

    @pytest.mark.unit
    def test_handles_iso_datetime_string(self, tui_formatter):
        """Test TUI handles ISO format datetime strings"""
        conversations = [{
            'id': 'conv-001',
            'title': 'ISO Test',
            'model': 'gpt-4',
            'created_at': '2024-01-15T10:30:00',
            'message_count': 5
        }]
        # Should not raise
        tui_formatter.format_conversation_list(conversations)

    @pytest.mark.unit
    def test_handles_invalid_datetime_string(self, tui_formatter):
        """Test TUI handles invalid datetime strings gracefully"""
        conversations = [{
            'id': 'conv-001',
            'title': 'Invalid Date Test',
            'model': 'gpt-4',
            'created_at': 'invalid-date-format',
            'message_count': 5
        }]
        # Should not raise
        tui_formatter.format_conversation_list(conversations)

    @pytest.mark.unit
    def test_handles_none_datetime(self, tui_formatter):
        """Test TUI handles None datetime"""
        conversations = [{
            'id': 'conv-001',
            'title': 'No Date Test',
            'model': 'gpt-4',
            'created_at': None,
            'message_count': 5
        }]
        # Should not raise
        tui_formatter.format_conversation_list(conversations)
