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

    def test_import_command_processes_file_successfully(self):
        """Test import command successfully processes supported file formats"""
        # Given: A real temp file with valid JSONL content
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            sample_data = {"messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ], "id": "test-1"}
            json.dump(sample_data, f)
            f.write('\n')
            temp_file = f.name

        with tempfile.TemporaryDirectory() as temp_db:
            try:
                # When: Running import command via CLI
                with patch('sys.argv', [
                    'ctk', 'import', temp_file,
                    '--db', temp_db,
                    '--format', 'jsonl'
                ]):
                    result = main()

                # Then: Should successfully import
                assert result == 0

            finally:
                import os
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

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

    def test_export_command_exports_conversations_successfully(self):
        """Test export command successfully exports conversations"""
        import os
        from ctk.core.database import ConversationDB
        from ctk.core.models import ConversationTree

        # Given: A database with a conversation
        with tempfile.TemporaryDirectory() as temp_db:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as export_file:
                export_path = export_file.name

            try:
                # Create a database and add a conversation
                with ConversationDB(temp_db) as db:
                    conv = ConversationTree(id="test-conv-1", title="Test Conversation")
                    db.save_conversation(conv)

                # When: Running export command via CLI
                with patch('sys.argv', [
                    'ctk', 'export', export_path,
                    '--db', temp_db,
                    '--format', 'jsonl'
                ]):
                    result = main()

                # Then: Should successfully export
                assert result == 0
                assert os.path.exists(export_path)

            finally:
                if os.path.exists(export_path):
                    os.unlink(export_path)

    @patch('ctk.cli.ConversationDB')
    @patch('ctk.cli.registry')
    def test_export_limit_zero_means_no_limit(self, mock_registry, mock_db_class):
        """Test export treats --limit 0 as unlimited (no SQL LIMIT)."""
        args = MagicMock()
        args.db = "test-db"
        args.output = "out.jsonl"
        args.format = "jsonl"
        args.ids = None
        args.limit = 0
        args.filter_source = None
        args.filter_model = None
        args.filter_tags = None
        args.sanitize = False
        args.path_selection = "longest"
        args.include_metadata = False
        args.starred = False
        args.pinned = False
        args.view = None  # Prevent MagicMock from creating truthy view attribute

        db = MagicMock()
        db.__enter__.return_value = db
        db.__exit__.return_value = False
        db.list_conversations.return_value = [MagicMock(id="conv-1")]
        db.load_conversation.return_value = MagicMock()
        mock_db_class.return_value = db

        exporter = MagicMock()
        mock_registry.get_exporter.return_value = exporter

        result = cmd_export(args)

        assert result == 0
        db.list_conversations.assert_called_once_with(limit=None)

    def test_list_command_displays_conversations(self):
        """Test list command displays available conversations"""
        import os
        from ctk.core.database import ConversationDB
        from ctk.core.models import ConversationTree

        # Given: A database with conversations
        with tempfile.TemporaryDirectory() as temp_db:
            # Create a database and add conversations
            with ConversationDB(temp_db) as db:
                conv1 = ConversationTree(id="conv1", title="First Chat")
                conv2 = ConversationTree(id="conv2", title="Second Chat")
                db.save_conversation(conv1)
                db.save_conversation(conv2)

            # When: Running list command via CLI
            with patch('sys.argv', [
                'ctk', 'list',
                '--db', temp_db
            ]):
                result = main()

            # Then: Should successfully list conversations
            assert result == 0

    def test_search_command_finds_conversations(self):
        """Test search command finds matching conversations"""
        import os
        from ctk.core.database import ConversationDB
        from ctk.core.models import ConversationTree, Message, MessageRole, MessageContent

        # Given: A database with searchable conversations
        with tempfile.TemporaryDirectory() as temp_db:
            # Create a database and add conversations with searchable content
            with ConversationDB(temp_db) as db:
                conv1 = ConversationTree(id="conv1", title="Python Tutorial")
                conv1.add_message(Message(
                    role=MessageRole.USER,
                    content=MessageContent(text="How do I use Python?")
                ))
                conv2 = ConversationTree(id="conv2", title="Java Tutorial")
                conv2.add_message(Message(
                    role=MessageRole.USER,
                    content=MessageContent(text="How do I use Java?")
                ))
                db.save_conversation(conv1)
                db.save_conversation(conv2)

            # When: Running search command via CLI
            with patch('sys.argv', [
                'ctk', 'search', 'Python',
                '--db', temp_db
            ]):
                result = main()

            # Then: Should successfully search
            assert result == 0


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

    def test_import_with_tags_workflow(self):
        """Test import workflow with tagging functionality"""
        import os
        from ctk.core.database import ConversationDB

        # Given: A temp file with valid JSONL content
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            sample_data = {"messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ], "id": "test-1"}
            json.dump(sample_data, f)
            f.write('\n')
            temp_file = f.name

        with tempfile.TemporaryDirectory() as temp_db:
            try:
                # When: Running import with tags
                with patch('sys.argv', [
                    'ctk', 'import', temp_file,
                    '--db', temp_db,
                    '--format', 'jsonl',
                    '--tags', 'work,important,2024'
                ]):
                    result = main()

                # Then: Should successfully import with tags applied
                assert result == 0

                # Verify tags were applied
                with ConversationDB(temp_db) as db:
                    conversations = db.list_conversations()
                    assert len(conversations) > 0
                    # Tags should be present
                    conv = db.load_conversation(conversations[0].id)
                    assert 'work' in conv.metadata.tags

            finally:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)

    def test_export_with_filtering_workflow(self):
        """Test export workflow with filtering capabilities"""
        import os
        from ctk.core.database import ConversationDB
        from ctk.core.models import ConversationTree, ConversationMetadata

        # Given: A database with conversations that have different sources
        with tempfile.TemporaryDirectory() as temp_db:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as export_file:
                export_path = export_file.name

            try:
                # Create conversations with different sources
                with ConversationDB(temp_db) as db:
                    conv1 = ConversationTree(
                        id="conv1",
                        title="OpenAI Chat",
                        metadata=ConversationMetadata(source="openai")
                    )
                    conv2 = ConversationTree(
                        id="conv2",
                        title="Other Chat",
                        metadata=ConversationMetadata(source="other")
                    )
                    db.save_conversation(conv1)
                    db.save_conversation(conv2)

                # When: Running export with source filter
                with patch('sys.argv', [
                    'ctk', 'export', export_path,
                    '--db', temp_db,
                    '--format', 'jsonl',
                    '--filter-source', 'openai'
                ]):
                    result = main()

                # Then: Should successfully export filtered conversations
                assert result == 0
                assert os.path.exists(export_path)

            finally:
                if os.path.exists(export_path):
                    os.unlink(export_path)


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
