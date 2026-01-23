"""
Integration tests for CLI commands
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ctk.cli import main
from ctk.core.database import ConversationDB
from ctk.core.models import ConversationMetadata, ConversationTree


@pytest.fixture(scope="session")
def temp_db():
    """Create temporary database for testing"""
    import shutil

    # Create a temporary directory for the database
    db_path = tempfile.mkdtemp(suffix="_ctk_db")

    try:
        # Create database with sample data
        with ConversationDB(db_path) as db:
            # Add sample conversation
            metadata = ConversationMetadata(
                source="test", model="test-model", tags=["test-tag"]
            )
            conv = ConversationTree(
                id="test-conv-1", title="Test Conversation", metadata=metadata
            )
            db.save_conversation(conv)

        yield db_path
    finally:
        if os.path.exists(db_path):
            shutil.rmtree(db_path)


@pytest.fixture(scope="session")
def sample_jsonl_file():
    """Create sample JSONL file for import testing"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        sample_data = [
            {
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                ],
                "id": "test-1",
                "model": "gpt-4",
            },
            {
                "messages": [
                    {"role": "user", "content": "How are you?"},
                    {"role": "assistant", "content": "I'm doing well!"},
                ],
                "id": "test-2",
                "model": "gpt-4",
            },
        ]
        for item in sample_data:
            json.dump(item, f)
            f.write("\n")

        # Store the filename before closing
        temp_filename = f.name

    # File is now closed and flushed
    yield temp_filename

    # Cleanup
    if os.path.exists(temp_filename):
        os.unlink(temp_filename)


class TestCLIIntegration:
    """Test CLI command integration"""

    def test_cli_help(self):
        """Test CLI help command"""
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["ctk", "--help"]):
                main()

        # Help should exit with code 0
        assert exc_info.value.code == 0

    def test_cli_no_command(self):
        """Test CLI with no command shows help"""
        with patch("sys.argv", ["ctk"]):
            result = main()

        # Should return 1 (error)
        assert result == 1

    def test_import_command(self, sample_jsonl_file, temp_db):
        """Test import command functionality"""
        with patch(
            "sys.argv",
            ["ctk", "import", sample_jsonl_file, "--db", temp_db, "--format", "jsonl"],
        ):
            result = main()

        assert result == 0

        # Verify import worked
        with ConversationDB(temp_db) as db:
            conversations = db.list_conversations()
            # Should have original + 2 imported = 3 total
            assert len(conversations) >= 2

    def test_import_with_tags(self, sample_jsonl_file, temp_db):
        """Test import command with custom tags"""
        with patch(
            "sys.argv",
            [
                "ctk",
                "import",
                sample_jsonl_file,
                "--db",
                temp_db,
                "--format",
                "jsonl",
                "--tags",
                "test,imported",
            ],
        ):
            result = main()

        assert result == 0

        # Verify tags were applied
        with ConversationDB(temp_db) as db:
            conversations = db.list_conversations()
            # Find imported conversation
            imported = [c for c in conversations if "test" in (c.tags or [])]
            assert len(imported) > 0

    def test_export_command(self, temp_db):
        """Test export command functionality"""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as output_file:
            try:
                with patch(
                    "sys.argv",
                    [
                        "ctk",
                        "export",
                        output_file.name,
                        "--db",
                        temp_db,
                        "--format",
                        "jsonl",
                    ],
                ):
                    result = main()

                assert result == 0

                # Verify export file was created
                assert os.path.exists(output_file.name)
                assert os.path.getsize(output_file.name) > 0

                # Verify content is valid JSONL
                with open(output_file.name, "r") as f:
                    content = f.read().strip()
                    assert content  # Should have content

                    # Each line should be valid JSON
                    for line in content.split("\n"):
                        if line.strip():
                            json.loads(line)  # Should not raise exception
            finally:
                if os.path.exists(output_file.name):
                    os.unlink(output_file.name)

    def test_list_command(self, temp_db):
        """Test list command functionality"""
        # Test that list command executes successfully
        # Note: Rich Console output goes through its own mechanism,
        # so we verify success via return code rather than stdout.write
        with patch("sys.argv", ["ctk", "list", "--db", temp_db]):
            result = main()

        assert result == 0

    def test_list_command_json(self, temp_db):
        """Test list command with JSON output"""
        with patch("sys.stdout") as mock_stdout:
            with patch("sys.argv", ["ctk", "list", "--db", temp_db, "--json"]):
                result = main()

            assert result == 0
            mock_stdout.write.assert_called()

    def test_search_command(self, temp_db):
        """Test search command functionality"""
        # Test that search command executes successfully
        # Note: Rich Console output goes through its own mechanism,
        # so we verify success via return code rather than stdout.write
        with patch("sys.argv", ["ctk", "search", "Test", "--db", temp_db]):
            result = main()

        assert result == 0

    def test_stats_command(self, temp_db):
        """Test stats command functionality"""
        with patch("sys.stdout") as mock_stdout:
            with patch("sys.argv", ["ctk", "stats", "--db", temp_db]):
                result = main()

            assert result == 0
            mock_stdout.write.assert_called()

    def test_plugins_command(self):
        """Test plugins command functionality"""
        with patch("sys.stdout") as mock_stdout:
            with patch("sys.argv", ["ctk", "plugins"]):
                result = main()

            assert result == 0
            mock_stdout.write.assert_called()

    def test_invalid_command(self):
        """Test handling of invalid command"""
        with pytest.raises(SystemExit):
            with patch("sys.argv", ["ctk", "invalid_command"]):
                main()

    def test_import_nonexistent_file(self):
        """Test import with nonexistent file"""
        with patch("sys.argv", ["ctk", "import", "/nonexistent/file.json"]):
            result = main()

        # Should return error code
        assert result != 0

    def test_export_invalid_db(self):
        """Test export with invalid database"""
        with tempfile.NamedTemporaryFile(suffix=".jsonl") as output_file:
            with patch(
                "sys.argv",
                [
                    "ctk",
                    "export",
                    output_file.name,
                    "--db",
                    "/nonexistent/database.db",
                    "--format",
                    "jsonl",
                ],
            ):
                result = main()

            # Should return error code
            assert result != 0

    def test_verbose_flag(self, temp_db):
        """Test verbose logging flag"""
        with patch("ctk.cli.setup_logging") as mock_setup_logging:
            with patch("sys.argv", ["ctk", "--verbose", "list", "--db", temp_db]):
                main()

            # Verbose logging should be enabled
            mock_setup_logging.assert_called_with(verbose=True)

    def test_import_auto_detect_format(self, sample_jsonl_file, temp_db):
        """Test import with auto-detected format"""
        with patch(
            "sys.argv",
            [
                "ctk",
                "import",
                sample_jsonl_file,
                "--db",
                temp_db,
                # No --format specified, should auto-detect
            ],
        ):
            result = main()

        assert result == 0

    def test_import_conversion_only(self, sample_jsonl_file):
        """Test import for format conversion without database storage"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as output_file:
            try:
                with patch(
                    "sys.argv",
                    [
                        "ctk",
                        "import",
                        sample_jsonl_file,
                        "--output",
                        output_file.name,
                        "--output-format",
                        "jsonl",
                    ],
                ):
                    result = main()

                assert result == 0
                assert os.path.exists(output_file.name)
                assert os.path.getsize(output_file.name) > 0
            finally:
                if os.path.exists(output_file.name):
                    os.unlink(output_file.name)

    def test_export_with_filters(self, temp_db):
        """Test export command with various filters"""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as output_file:
            try:
                with patch(
                    "sys.argv",
                    [
                        "ctk",
                        "export",
                        output_file.name,
                        "--db",
                        temp_db,
                        "--format",
                        "jsonl",
                        "--filter-source",
                        "test",
                        "--limit",
                        "10",
                    ],
                ):
                    result = main()

                assert result == 0
                assert os.path.exists(output_file.name)
            finally:
                if os.path.exists(output_file.name):
                    os.unlink(output_file.name)


class TestCLIErrorHandling:
    """Test CLI error handling scenarios"""

    def test_import_invalid_json(self):
        """Test import with invalid JSON file"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            invalid_file = f.name

        try:
            with patch(
                "sys.argv", ["ctk", "import", invalid_file, "--format", "jsonl"]
            ):
                result = main()

            # Should handle error gracefully
            assert result != 0
        finally:
            if os.path.exists(invalid_file):
                os.unlink(invalid_file)

    def test_database_permission_error(self, sample_jsonl_file):
        """Test handling of database permission errors"""
        # Try to use a path that would cause permission error
        invalid_db = "/root/readonly.db"

        with patch(
            "sys.argv", ["ctk", "import", sample_jsonl_file, "--db", invalid_db]
        ):
            result = main()

        # Should handle error gracefully
        assert result != 0

    def test_export_permission_error(self, temp_db):
        """Test handling of export file permission errors"""
        # Try to export to a protected location
        protected_output = "/root/protected.jsonl"

        with patch("sys.argv", ["ctk", "export", protected_output, "--db", temp_db]):
            result = main()

        # Should handle error gracefully
        assert result != 0


@pytest.mark.integration
class TestCLIWorkflows:
    """Test complete CLI workflows"""

    def test_full_import_export_workflow(self, sample_jsonl_file):
        """Test complete import then export workflow"""
        import shutil

        db_dir = tempfile.mkdtemp(suffix="_ctk_db")
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as export_file:

            try:
                # Step 1: Import
                with patch(
                    "sys.argv",
                    [
                        "ctk",
                        "import",
                        sample_jsonl_file,
                        "--db",
                        db_dir,
                        "--format",
                        "jsonl",
                    ],
                ):
                    result = main()
                    assert result == 0

                # Step 2: Verify data in database
                with patch("sys.argv", ["ctk", "stats", "--db", db_dir]):
                    result = main()
                    assert result == 0

                # Step 3: Export
                with patch(
                    "sys.argv",
                    [
                        "ctk",
                        "export",
                        export_file.name,
                        "--db",
                        db_dir,
                        "--format",
                        "jsonl",
                    ],
                ):
                    result = main()
                    assert result == 0

                # Step 4: Verify export
                assert os.path.exists(export_file.name)
                assert os.path.getsize(export_file.name) > 0

            finally:
                if os.path.exists(export_file.name):
                    os.unlink(export_file.name)
                if os.path.exists(db_dir):
                    shutil.rmtree(db_dir)

    def test_search_workflow(self, sample_jsonl_file):
        """Test search functionality workflow"""
        import shutil

        db_dir = tempfile.mkdtemp(suffix="_ctk_db")
        try:
            # Import data
            with patch(
                "sys.argv", ["ctk", "import", sample_jsonl_file, "--db", db_dir]
            ):
                result = main()
                assert result == 0

            # Search for content
            # Note: Rich Console output goes through its own mechanism,
            # so we verify success via return code rather than stdout.write
            with patch("sys.argv", ["ctk", "search", "Hello", "--db", db_dir]):
                result = main()
                assert result == 0

        finally:
            if os.path.exists(db_dir):
                shutil.rmtree(db_dir)
