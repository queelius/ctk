"""
Unit tests for CSV exporter
"""

import csv
import io
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from ctk.core.models import (
    ConversationMetadata,
    ConversationTree,
    Message,
    MessageContent,
    MessageRole,
)
from ctk.integrations.exporters.csv_exporter import CSVExporter


class TestCSVExporterValidation:
    """Test CSV exporter validation"""

    @pytest.mark.unit
    def test_validate_list_of_conversations(self, sample_conversation):
        """validate() returns True for a list of ConversationTree objects"""
        exporter = CSVExporter()
        assert exporter.validate([sample_conversation]) is True

    @pytest.mark.unit
    def test_validate_single_conversation(self, sample_conversation):
        """validate() returns True for a single ConversationTree"""
        exporter = CSVExporter()
        assert exporter.validate(sample_conversation) is True

    @pytest.mark.unit
    def test_validate_empty_list(self):
        """validate() returns True for an empty list (vacuously true)"""
        exporter = CSVExporter()
        assert exporter.validate([]) is True

    @pytest.mark.unit
    def test_validate_invalid_string(self):
        """validate() returns False for a string"""
        exporter = CSVExporter()
        assert exporter.validate("not a conversation") is False

    @pytest.mark.unit
    def test_validate_invalid_dict(self):
        """validate() returns False for a dict"""
        exporter = CSVExporter()
        assert exporter.validate({"key": "value"}) is False

    @pytest.mark.unit
    def test_validate_invalid_list_contents(self):
        """validate() returns False for a list of non-ConversationTree objects"""
        exporter = CSVExporter()
        assert exporter.validate(["not", "conversations"]) is False

    @pytest.mark.unit
    def test_validate_mixed_list(self, sample_conversation):
        """validate() returns False for a list mixing ConversationTree and other types"""
        exporter = CSVExporter()
        assert exporter.validate([sample_conversation, "not a conversation"]) is False

    @pytest.mark.unit
    def test_validate_none(self):
        """validate() returns False for None"""
        exporter = CSVExporter()
        assert exporter.validate(None) is False


class TestCSVExporterConversationMode:
    """Test CSV exporter in conversation-level mode (default)"""

    @pytest.mark.unit
    def test_conversation_mode_headers(self, sample_conversation):
        """Default mode exports CSV with correct headers"""
        exporter = CSVExporter()
        result = exporter.export_data([sample_conversation])

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)

        expected_headers = [
            "id", "title", "source", "model", "created_at", "updated_at",
            "message_count", "tags", "starred", "pinned", "archived",
        ]
        assert headers == expected_headers

    @pytest.mark.unit
    def test_single_conversation_row(self, sample_conversation):
        """Single conversation produces one data row after headers"""
        exporter = CSVExporter()
        result = exporter.export_data([sample_conversation])

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)

        assert len(rows) == 2  # header + 1 data row

    @pytest.mark.unit
    def test_conversation_fields(self, sample_conversation):
        """Conversation row has correct field values"""
        exporter = CSVExporter()
        result = exporter.export_data([sample_conversation])

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)

        # Map headers to values
        data = dict(zip(headers, row))

        assert data["id"] == "conv_001"
        assert data["title"] == "Test Conversation"
        assert data["source"] == "test"
        assert data["model"] == "test-model"
        assert data["message_count"] == "4"
        assert data["tags"] == "test;sample"
        assert data["starred"] == "false"
        assert data["pinned"] == "false"
        assert data["archived"] == "false"

    @pytest.mark.unit
    def test_multiple_conversations(self, sample_conversation):
        """Multiple conversations produce multiple data rows"""
        conv2 = ConversationTree(id="conv_002", title="Second Conversation")
        msg = Message(
            id="msg_100",
            role=MessageRole.USER,
            content=MessageContent(text="Hello again"),
        )
        conv2.add_message(msg)

        exporter = CSVExporter()
        result = exporter.export_data([sample_conversation, conv2])

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)

        assert len(rows) == 3  # header + 2 data rows
        assert rows[1][0] == "conv_001"
        assert rows[2][0] == "conv_002"

    @pytest.mark.unit
    def test_missing_metadata_fields(self):
        """Missing metadata fields produce empty values"""
        conv = ConversationTree(id="conv_minimal")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
        )
        conv.add_message(msg)

        exporter = CSVExporter()
        result = exporter.export_data([conv])

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)
        data = dict(zip(headers, row))

        assert data["title"] == ""
        assert data["source"] == ""
        assert data["model"] == ""

    @pytest.mark.unit
    def test_tags_joined_with_semicolons(self):
        """Tags are joined with semicolons"""
        conv = ConversationTree(
            id="conv_tags",
            title="Tagged",
            metadata=ConversationMetadata(tags=["python", "data", "csv"]),
        )
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
        )
        conv.add_message(msg)

        exporter = CSVExporter()
        result = exporter.export_data([conv])

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)
        data = dict(zip(headers, row))

        assert data["tags"] == "python;data;csv"

    @pytest.mark.unit
    def test_starred_pinned_archived_flags(self):
        """Starred, pinned, archived flags are correctly exported"""
        now = datetime.now()
        conv = ConversationTree(
            id="conv_flags",
            title="Flagged",
            metadata=ConversationMetadata(
                starred_at=now, pinned_at=now, archived_at=now
            ),
        )
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
        )
        conv.add_message(msg)

        exporter = CSVExporter()
        result = exporter.export_data([conv])

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)
        data = dict(zip(headers, row))

        assert data["starred"] == "true"
        assert data["pinned"] == "true"
        assert data["archived"] == "true"

    @pytest.mark.unit
    def test_created_at_updated_at_iso_format(self):
        """Timestamps are exported in ISO format"""
        ts = datetime(2024, 6, 15, 10, 30, 0)
        conv = ConversationTree(
            id="conv_ts",
            title="Timestamped",
            metadata=ConversationMetadata(created_at=ts, updated_at=ts),
        )
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello"),
        )
        conv.add_message(msg)

        exporter = CSVExporter()
        result = exporter.export_data([conv])

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)
        data = dict(zip(headers, row))

        # created_at should match our explicit timestamp
        assert data["created_at"] == "2024-06-15T10:30:00"
        # updated_at is overwritten by add_message() to datetime.now(),
        # so we just verify it's a valid ISO format datetime string
        assert "T" in data["updated_at"]
        datetime.fromisoformat(data["updated_at"])  # should not raise


class TestCSVExporterMessageMode:
    """Test CSV exporter in message-level mode"""

    @pytest.mark.unit
    def test_message_mode_headers(self, sample_conversation):
        """Message mode exports CSV with correct headers"""
        exporter = CSVExporter()
        result = exporter.export_data([sample_conversation], mode="messages")

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)

        expected_headers = [
            "conversation_id", "conversation_title", "message_id",
            "role", "content", "timestamp", "parent_id",
        ]
        assert headers == expected_headers

    @pytest.mark.unit
    def test_message_mode_row_count(self, sample_conversation):
        """Each message in the path produces a row"""
        exporter = CSVExporter()
        result = exporter.export_data([sample_conversation], mode="messages")

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)

        # header + 4 messages (longest path of sample_conversation)
        assert len(rows) == 5

    @pytest.mark.unit
    def test_message_mode_field_values(self, sample_conversation):
        """Message rows have correct field values"""
        exporter = CSVExporter()
        result = exporter.export_data([sample_conversation], mode="messages")

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        first_row = next(reader)
        data = dict(zip(headers, first_row))

        assert data["conversation_id"] == "conv_001"
        assert data["conversation_title"] == "Test Conversation"
        assert data["message_id"] == "msg_001"
        assert data["role"] == "user"
        assert data["content"] == "Hello"
        assert data["parent_id"] == ""

    @pytest.mark.unit
    def test_message_mode_parent_ids(self, sample_conversation):
        """Message rows include correct parent_id references"""
        exporter = CSVExporter()
        result = exporter.export_data([sample_conversation], mode="messages")

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        rows = list(reader)

        parent_id_idx = headers.index("parent_id")

        # First message has no parent
        assert rows[0][parent_id_idx] == ""
        # Second message's parent is the first message
        assert rows[1][parent_id_idx] == "msg_001"
        # Third message's parent is the second
        assert rows[2][parent_id_idx] == "msg_002"

    @pytest.mark.unit
    def test_message_mode_longest_path(self, branching_conversation):
        """Longest path selection follows the longest branch"""
        exporter = CSVExporter()
        result = exporter.export_data(
            [branching_conversation], mode="messages", path_selection="longest"
        )

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        rows = list(reader)

        # The longest path is: msg_001 -> msg_002a -> msg_003 -> msg_004 (4 messages)
        assert len(rows) == 4

        # Verify it follows the first branch (which has continuation)
        content_idx = headers.index("content")
        assert rows[0][content_idx] == "What's 2+2?"
        assert rows[1][content_idx] == "2+2 equals 4"
        assert rows[2][content_idx] == "What about 3+3?"
        assert rows[3][content_idx] == "3+3 equals 6"

    @pytest.mark.unit
    def test_message_mode_first_path(self, branching_conversation):
        """First path selection uses the first path"""
        exporter = CSVExporter()
        result = exporter.export_data(
            [branching_conversation], mode="messages", path_selection="first"
        )

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        rows = list(reader)

        # First path should be one of the paths through the tree
        assert len(rows) >= 2  # At least root + one response

    @pytest.mark.unit
    def test_message_mode_last_path(self, branching_conversation):
        """Last path selection uses the last path"""
        exporter = CSVExporter()
        result = exporter.export_data(
            [branching_conversation], mode="messages", path_selection="last"
        )

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        rows = list(reader)

        # Last path should be one of the paths through the tree
        assert len(rows) >= 2  # At least root + one response

    @pytest.mark.unit
    def test_message_mode_role_values(self, sample_conversation):
        """Roles are exported as lowercase strings"""
        exporter = CSVExporter()
        result = exporter.export_data([sample_conversation], mode="messages")

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        rows = list(reader)

        role_idx = headers.index("role")
        assert rows[0][role_idx] == "user"
        assert rows[1][role_idx] == "assistant"
        assert rows[2][role_idx] == "user"
        assert rows[3][role_idx] == "assistant"


class TestCSVExporterFileIO:
    """Test CSV exporter file I/O"""

    @pytest.mark.unit
    def test_export_to_file(self, sample_conversation):
        """export_to_file() writes valid CSV to disk"""
        exporter = CSVExporter()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            filepath = f.name

        try:
            exporter.export_to_file([sample_conversation], filepath)

            with open(filepath, "r") as f:
                content = f.read()

            assert len(content) > 0
            assert "id,title,source" in content
        finally:
            Path(filepath).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_export_to_file_readable_by_csv_reader(self, sample_conversation):
        """Exported file is readable by csv.reader"""
        exporter = CSVExporter()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as f:
            filepath = f.name

        try:
            exporter.export_to_file([sample_conversation], filepath)

            with open(filepath, "r", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)

            assert len(rows) == 2  # header + 1 data row
            assert rows[0][0] == "id"
        finally:
            Path(filepath).unlink(missing_ok=True)

    @pytest.mark.unit
    def test_export_tsv_mode(self, sample_conversation):
        """TSV mode uses tab delimiter"""
        exporter = CSVExporter()
        result = exporter.export_data([sample_conversation], delimiter="\t")

        reader = csv.reader(io.StringIO(result), delimiter="\t")
        rows = list(reader)

        assert len(rows) == 2
        assert rows[0][0] == "id"
        assert rows[1][0] == "conv_001"

    @pytest.mark.unit
    def test_export_tsv_to_file(self, sample_conversation):
        """TSV export to file is readable with tab delimiter"""
        exporter = CSVExporter()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tsv", delete=False
        ) as f:
            filepath = f.name

        try:
            exporter.export_to_file(
                [sample_conversation], filepath, delimiter="\t"
            )

            with open(filepath, "r", newline="") as f:
                reader = csv.reader(f, delimiter="\t")
                rows = list(reader)

            assert len(rows) == 2
            assert rows[0][0] == "id"
        finally:
            Path(filepath).unlink(missing_ok=True)


class TestCSVExporterEdgeCases:
    """Test CSV exporter edge cases"""

    @pytest.mark.unit
    def test_empty_conversation_list(self):
        """Empty conversation list produces header-only CSV"""
        exporter = CSVExporter()
        result = exporter.export_data([])

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)

        assert len(rows) == 1  # headers only
        assert rows[0][0] == "id"

    @pytest.mark.unit
    def test_empty_conversation_list_message_mode(self):
        """Empty conversation list in message mode produces header-only CSV"""
        exporter = CSVExporter()
        result = exporter.export_data([], mode="messages")

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)

        assert len(rows) == 1  # headers only
        assert rows[0][0] == "conversation_id"

    @pytest.mark.unit
    def test_content_with_commas(self):
        """Content containing commas is properly escaped"""
        conv = ConversationTree(id="conv_comma", title="Commas, in, title")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello, world, how are you?"),
        )
        conv.add_message(msg)

        exporter = CSVExporter()
        result = exporter.export_data([conv])

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)
        data = dict(zip(headers, row))

        assert data["title"] == "Commas, in, title"

    @pytest.mark.unit
    def test_content_with_quotes(self):
        """Content containing quotes is properly escaped"""
        conv = ConversationTree(id="conv_quote", title='Title with "quotes"')
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text='She said "hello"'),
        )
        conv.add_message(msg)

        exporter = CSVExporter()
        result = exporter.export_data([conv], mode="messages")

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)
        data = dict(zip(headers, row))

        assert data["content"] == 'She said "hello"'

    @pytest.mark.unit
    def test_content_with_newlines(self):
        """Content containing newlines is properly escaped"""
        conv = ConversationTree(id="conv_newline", title="Newline Test")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Line 1\nLine 2\nLine 3"),
        )
        conv.add_message(msg)

        exporter = CSVExporter()
        result = exporter.export_data([conv], mode="messages")

        # Parse the CSV output - the newlines should be properly quoted
        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)
        data = dict(zip(headers, row))

        assert data["content"] == "Line 1\nLine 2\nLine 3"

    @pytest.mark.unit
    def test_unicode_content(self):
        """Unicode content is correctly handled"""
        conv = ConversationTree(id="conv_unicode", title="Unicode Test")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Bonjour le monde! Hola mundo!"),
        )
        conv.add_message(msg)

        exporter = CSVExporter()
        result = exporter.export_data([conv], mode="messages")

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)
        data = dict(zip(headers, row))

        assert data["content"] == "Bonjour le monde! Hola mundo!"

    @pytest.mark.unit
    def test_unicode_emoji_content(self):
        """Emoji and special unicode content is correctly handled"""
        conv = ConversationTree(id="conv_emoji", title="Emoji Test")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(text="Hello \U0001f600 \U0001f30d \u2603"),
        )
        conv.add_message(msg)

        exporter = CSVExporter()
        result = exporter.export_data([conv], mode="messages")

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)
        data = dict(zip(headers, row))

        assert data["content"] == "Hello \U0001f600 \U0001f30d \u2603"

    @pytest.mark.unit
    def test_conversation_with_no_messages(self):
        """Conversation with no messages still produces a row with zero count"""
        conv = ConversationTree(id="conv_empty", title="Empty")

        exporter = CSVExporter()
        result = exporter.export_data([conv])

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)
        data = dict(zip(headers, row))

        assert data["message_count"] == "0"

    @pytest.mark.unit
    def test_message_mode_empty_conversation(self):
        """Empty conversation in message mode produces no message rows"""
        conv = ConversationTree(id="conv_empty", title="Empty")

        exporter = CSVExporter()
        result = exporter.export_data([conv], mode="messages")

        reader = csv.reader(io.StringIO(result))
        rows = list(reader)

        assert len(rows) == 1  # headers only

    @pytest.mark.unit
    def test_content_with_commas_quotes_newlines_combined(self):
        """Content with commas, quotes, and newlines combined"""
        conv = ConversationTree(id="conv_complex", title="Complex Content")
        msg = Message(
            id="msg_001",
            role=MessageRole.USER,
            content=MessageContent(
                text='He said, "hello"\nShe replied, "hi"'
            ),
        )
        conv.add_message(msg)

        exporter = CSVExporter()
        result = exporter.export_data([conv], mode="messages")

        reader = csv.reader(io.StringIO(result))
        headers = next(reader)
        row = next(reader)
        data = dict(zip(headers, row))

        assert data["content"] == 'He said, "hello"\nShe replied, "hi"'


class TestCSVExporterPluginAttributes:
    """Test CSV exporter plugin registration attributes"""

    @pytest.mark.unit
    def test_exporter_name(self):
        """Exporter has correct name"""
        exporter = CSVExporter()
        assert exporter.name == "csv"

    @pytest.mark.unit
    def test_exporter_description(self):
        """Exporter has a non-empty description"""
        exporter = CSVExporter()
        assert len(exporter.description) > 0

    @pytest.mark.unit
    def test_exporter_version(self):
        """Exporter has a version"""
        exporter = CSVExporter()
        assert exporter.version == "1.0.0"

    @pytest.mark.unit
    def test_supported_formats(self):
        """Exporter supports csv and tsv formats"""
        exporter = CSVExporter()
        assert "csv" in exporter.supported_formats
        assert "tsv" in exporter.supported_formats
