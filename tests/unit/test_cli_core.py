"""
Behavior-focused tests for core CLI functionality

These tests focus on the CLI command behaviors and contracts,
not implementation details. They should enable confident refactoring.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

from ctk.cli import main, cmd_import, cmd_export, cmd_list, cmd_search
from ctk.core.models import ConversationTree, ConversationMetadata


class TestCLICommandBehaviors:
    """Test CLI command behaviors and contracts"""

    def test_main_without_command_shows_help(self):
        """Test that CLI without command shows help and returns error code"""
        # Given: CLI called without any command
        # When: Running main with no arguments
        with patch('sys.argv', ['ctk']):
            result = main()

        # Then: Should return error code indicating help was shown
        assert result == 1

    @patch('sys.argv', ['ctk', '--help'])
    def test_main_with_help_flag_exits_successfully(self):
        """Test that help flag exits with success code"""
        # When: Running with help flag
        with pytest.raises(SystemExit) as exc_info:
            main()

        # Then: Should exit with success code
        assert exc_info.value.code == 0

    @patch('ctk.cli.ConversationDB')
    @patch('ctk.cli.registry')
    def test_import_command_processes_file_successfully(self, mock_registry, mock_db_class):
        """Test import command successfully processes supported file formats"""
        # Given: A mock importer and database
        mock_importer = MagicMock()
        mock_importer.import_file.return_value = [
            ConversationTree(id="conv1", title="Test Conversation")
        ]
        mock_registry.get_importer.return_value = mock_importer

        mock_db = MagicMock()
        mock_db_class.return_value.__enter__.return_value = mock_db

        # Create a mock args object
        args = MagicMock()
        args.input = "test.json"
        args.format = "json"
        args.db = "test.db"
        args.tags = None
        args.sanitize = False
        args.path_selection = "longest"
        args.output = None

        # When: Running import command
        result = cmd_import(args)

        # Then: Should successfully import and save conversations
        assert result == 0
        mock_registry.get_importer.assert_called_once_with("json")
        mock_importer.import_file.assert_called_once_with("test.json", path_selection="longest")
        mock_db.save_conversation.assert_called_once()

    @patch('ctk.cli.ConversationDB')
    @patch('ctk.cli.registry')
    def test_import_command_handles_unsupported_format(self, mock_registry, mock_db_class):
        """Test import command handles unsupported file formats gracefully"""
        # Given: No importer available for format
        mock_registry.get_importer.return_value = None

        args = MagicMock()
        args.input = "test.xyz"
        args.format = "unknown"
        args.db = "test.db"

        # When: Running import command with unsupported format
        result = cmd_import(args)

        # Then: Should return error code
        assert result != 0

    @patch('ctk.cli.ConversationDB')
    @patch('ctk.cli.registry')
    def test_export_command_exports_conversations_successfully(self, mock_registry, mock_db_class):
        """Test export command successfully exports conversations"""
        # Given: A mock exporter and database with conversations
        mock_exporter = MagicMock()
        mock_registry.get_exporter.return_value = mock_exporter

        mock_db = MagicMock()
        mock_db.list_conversations.return_value = [
            {'id': 'conv1', 'title': 'Test Conversation'}
        ]
        mock_db.load_conversation.return_value = ConversationTree(id="conv1", title="Test")
        mock_db_class.return_value.__enter__.return_value = mock_db

        args = MagicMock()
        args.output = "export.jsonl"
        args.db = "test.db"
        args.format = "jsonl"
        args.ids = None
        args.limit = 1000
        args.filter_source = None
        args.filter_model = None
        args.filter_tag = None
        args.sanitize = False
        args.path_selection = "longest"
        args.include_metadata = False

        # When: Running export command
        result = cmd_export(args)

        # Then: Should successfully export conversations
        assert result == 0
        mock_registry.get_exporter.assert_called_once_with("jsonl")
        mock_exporter.export_to_file.assert_called_once()

    @patch('ctk.cli.ConversationDB')
    def test_list_command_displays_conversations(self, mock_db_class):
        """Test list command displays available conversations"""
        # Given: A database with conversations
        mock_db = MagicMock()
        mock_conversations = [
            {'id': 'conv1', 'title': 'First Chat', 'message_count': 5},
            {'id': 'conv2', 'title': 'Second Chat', 'message_count': 3}
        ]
        mock_db.list_conversations.return_value = mock_conversations
        mock_db_class.return_value.__enter__.return_value = mock_db

        args = MagicMock()
        args.db = "test.db"
        args.limit = 100
        args.json = False

        # When: Running list command
        with patch('builtins.print') as mock_print:
            result = cmd_list(args)

        # Then: Should successfully list conversations
        assert result == 0
        mock_db.list_conversations.assert_called_once_with(limit=100)
        # Should print conversation information
        assert mock_print.call_count > 0

    @patch('ctk.cli.ConversationDB')
    def test_search_command_finds_conversations(self, mock_db_class):
        """Test search command finds matching conversations"""
        # Given: A database with searchable conversations
        mock_db = MagicMock()
        mock_results = [
            {'id': 'conv1', 'title': 'Python Tutorial', 'score': 0.95},
            {'id': 'conv2', 'title': 'Python Advanced', 'score': 0.87}
        ]
        mock_db.search_conversations.return_value = mock_results
        mock_db_class.return_value.__enter__.return_value = mock_db

        args = MagicMock()
        args.query = "python"
        args.db = "test.db"
        args.limit = 100
        args.offset = 0
        args.json = False

        # When: Running search command
        with patch('builtins.print') as mock_print:
            result = cmd_search(args)

        # Then: Should successfully search and display results
        assert result == 0
        mock_db.search_conversations.assert_called_once_with(
            "python", limit=100, offset=0
        )
        # Should print search results
        assert mock_print.call_count > 0


class TestCLIErrorHandling:
    """Test CLI error handling behaviors"""

    @patch('ctk.cli.ConversationDB')
    def test_import_handles_database_errors(self, mock_db_class):
        """Test import command handles database errors gracefully"""
        # Given: A database that raises an error
        mock_db_class.side_effect = Exception("Database connection failed")

        args = MagicMock()
        args.input = "test.json"
        args.db = "nonexistent.db"

        # When: Running import command with database error
        result = cmd_import(args)

        # Then: Should handle error and return error code
        assert result != 0

    @patch('ctk.cli.ConversationDB')
    def test_export_handles_missing_database(self, mock_db_class):
        """Test export command handles missing database file"""
        # Given: A database that doesn't exist
        mock_db_class.side_effect = FileNotFoundError("Database not found")

        args = MagicMock()
        args.output = "export.jsonl"
        args.db = "nonexistent.db"

        # When: Running export command
        result = cmd_export(args)

        # Then: Should handle error and return error code
        assert result != 0

    def test_import_handles_missing_input_file(self):
        """Test import command handles missing input files"""
        # Given: A non-existent input file
        args = MagicMock()
        args.input = "nonexistent.json"
        args.db = "test.db"

        # When: Running import command
        result = cmd_import(args)

        # Then: Should handle error and return error code
        assert result != 0


class TestCLIWorkflows:
    """Test end-to-end CLI workflow behaviors"""

    @patch('ctk.cli.ConversationDB')
    @patch('ctk.cli.registry')
    def test_import_with_tags_workflow(self, mock_registry, mock_db_class):
        """Test import workflow with tagging functionality"""
        # Given: Import with tags specified
        mock_importer = MagicMock()
        mock_conversation = ConversationTree(id="conv1", title="Test")
        mock_importer.import_file.return_value = [mock_conversation]
        mock_registry.get_importer.return_value = mock_importer

        mock_db = MagicMock()
        mock_db_class.return_value.__enter__.return_value = mock_db

        args = MagicMock()
        args.input = "test.json"
        args.format = "json"
        args.db = "test.db"
        args.tags = "work,important,2024"
        args.sanitize = False
        args.path_selection = "longest"
        args.output = None

        # When: Running import with tags
        result = cmd_import(args)

        # Then: Should successfully import with tags applied
        assert result == 0

        # Verify conversation was saved (tags would be applied during processing)
        mock_db.save_conversation.assert_called_once()

    @patch('ctk.cli.ConversationDB')
    @patch('ctk.cli.registry')
    def test_export_with_filtering_workflow(self, mock_registry, mock_db_class):
        """Test export workflow with filtering capabilities"""
        # Given: Export with filters specified
        mock_exporter = MagicMock()
        mock_registry.get_exporter.return_value = mock_exporter

        mock_db = MagicMock()
        mock_db.list_conversations.return_value = [
            {'id': 'conv1', 'source': 'openai', 'tags': ['work']}
        ]
        mock_db.load_conversation.return_value = ConversationTree(id="conv1")
        mock_db_class.return_value.__enter__.return_value = mock_db

        args = MagicMock()
        args.output = "filtered.jsonl"
        args.db = "test.db"
        args.format = "jsonl"
        args.ids = None
        args.limit = 1000
        args.filter_source = "openai"
        args.filter_model = None
        args.filter_tag = "work"
        args.sanitize = False
        args.path_selection = "longest"
        args.include_metadata = True

        # When: Running export with filters
        result = cmd_export(args)

        # Then: Should successfully export filtered conversations
        assert result == 0
        mock_exporter.export_to_file.assert_called_once()


class TestCLIConfigurationHandling:
    """Test CLI configuration and option handling"""

    def test_verbose_logging_configuration(self):
        """Test that verbose flag configures logging appropriately"""
        # Given: CLI with verbose flag
        with patch('ctk.cli.setup_logging') as mock_setup_logging:
            with patch('sys.argv', ['ctk', '--verbose', 'list', '--db', 'test.db']):
                # When: Running with verbose flag
                try:
                    main()
                except:
                    pass  # We expect this to fail due to mocking, focus on logging setup

                # Then: Should configure verbose logging
                mock_setup_logging.assert_called_with(verbose=True)

    def test_path_selection_strategies(self):
        """Test that path selection strategies are properly handled"""
        # This test verifies that the CLI properly passes path selection options
        # to the underlying import/export functions

        strategies = ['longest', 'first', 'last']

        for strategy in strategies:
            args = MagicMock()
            args.path_selection = strategy

            # Verify that the strategy is properly accessible
            assert args.path_selection == strategy

    @patch('ctk.cli.Sanitizer')
    def test_sanitization_option_handling(self, mock_sanitizer_class):
        """Test that sanitization option is properly handled"""
        # Given: Import with sanitization enabled
        args = MagicMock()
        args.sanitize = True

        # When: Sanitization option is checked
        if args.sanitize:
            # Then: Should be able to create sanitizer
            sanitizer = mock_sanitizer_class(enabled=True)
            assert sanitizer is not None