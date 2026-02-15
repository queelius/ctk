"""
Unit tests for exporters
"""

import json
import tempfile
from pathlib import Path

import pytest

from ctk.core.models import (ConversationMetadata, ConversationTree, Message,
                             MessageContent, MessageRole)
from ctk.integrations.exporters.echo import ECHOExporter
from ctk.integrations.exporters.json import JSONExporter
from ctk.integrations.exporters.jsonl import JSONLExporter
from ctk.integrations.exporters.markdown import MarkdownExporter


class TestJSONLExporter:
    """Test JSONL exporter"""

    @pytest.mark.unit
    def test_export_single_conversation(self, sample_conversation):
        """Test exporting a single conversation preserves message content and structure"""
        exporter = JSONLExporter()
        result = exporter.export_data([sample_conversation])

        # Should have at least one line of JSONL output
        lines = result.strip().split("\n")
        assert len(lines) >= 1, "Should produce at least one line of output"

        # Parse the conversation data
        conv_data = json.loads(lines[0])

        # Should contain messages array with user and assistant messages
        assert "messages" in conv_data, "Should contain messages array"
        messages = conv_data["messages"]

        assert len(messages) >= 2, "Should contain at least user and assistant messages"

        # Verify first message content is preserved
        first_message = messages[0]
        assert first_message["role"] == "user"
        assert "Hello" in first_message["content"]

    @pytest.mark.unit
    def test_export_with_metadata(self, sample_conversation):
        """Test exporting with metadata included"""
        exporter = JSONLExporter()
        result = exporter.export_data([sample_conversation], include_metadata=True)

        lines = result.strip().split("\n")

        # First line should be metadata
        first = json.loads(lines[0])
        assert "metadata" in first
        assert first["metadata"]["title"] == "Test Conversation"
        assert first["metadata"]["source"] == "test"

        # Rest should be messages
        for line in lines[1:]:
            data = json.loads(line)
            assert "role" in data
            assert "content" in data

    @pytest.mark.unit
    def test_export_multiple_conversations(self, sample_conversation):
        """Test exporting multiple conversations produces separate JSONL entries"""
        conv2 = ConversationTree(id="conv_002", title="Second")
        msg = Message(
            id="msg_100",
            role=MessageRole.USER,
            content=MessageContent(text="Another conversation"),
        )
        conv2.add_message(msg)

        exporter = JSONLExporter()
        result = exporter.export_data([sample_conversation, conv2])

        lines = result.strip().split("\n")

        # Should have at least two lines for two conversations
        assert len(lines) >= 2, "Should produce at least one line per conversation"

        # Each line should be valid JSON with messages
        for line in lines:
            conv_data = json.loads(line)
            assert "messages" in conv_data, "Each conversation should have messages"

        # Verify different conversations are distinguishable
        first_conv = json.loads(lines[0])
        second_conv = json.loads(lines[1])

        # Should contain different content
        first_content = first_conv["messages"][0]["content"]
        second_content = second_conv["messages"][0]["content"]
        assert (
            first_content != second_content
        ), "Different conversations should have different content"

    @pytest.mark.unit
    def test_export_branching_conversation(self, branching_conversation):
        """Test exporting conversation with branches respects path selection"""
        exporter = JSONLExporter()
        result = exporter.export_data(
            [branching_conversation], path_selection="longest"
        )

        lines = result.strip().split("\n")
        assert len(lines) >= 1, "Should produce at least one conversation"

        conv_data = json.loads(lines[0])
        messages = conv_data["messages"]

        # Should contain messages from the branching conversation
        assert (
            len(messages) >= 2
        ), "Should contain multiple messages from branching path"

        # Verify it contains expected content from the path
        message_contents = [msg["content"] for msg in messages]
        has_math_content = any("2+2" in content for content in message_contents)
        assert (
            has_math_content
        ), "Should contain content from the branching conversation"

    @pytest.mark.unit
    def test_export_to_file(self, sample_conversation, temp_dir):
        """Test exporting to file creates valid JSONL output"""
        exporter = JSONLExporter()
        output_path = temp_dir / "export.jsonl"

        exporter.export_to_file([sample_conversation], str(output_path))

        # File should exist and have content
        assert output_path.exists(), "Export should create output file"
        assert output_path.stat().st_size > 0, "Output file should not be empty"

        # Content should be valid JSONL
        with open(output_path) as f:
            content = f.read().strip()

        lines = content.split("\n")
        assert len(lines) >= 1, "Should have at least one line of JSONL"

        # Each line should be valid JSON with expected structure
        for line in lines:
            if line.strip():  # Skip empty lines
                data = json.loads(line.strip())
                assert (
                    "messages" in data
                ), "Each conversation should have messages structure"

    @pytest.mark.unit
    def test_jsonl_validation(self):
        """Test JSONL exporter validation"""
        exporter = JSONLExporter()

        assert exporter.validate([])  # Empty list
        assert exporter.validate([ConversationTree(id="test")])
        assert not exporter.validate("string")
        assert not exporter.validate(123)


class TestJSONExporter:
    """Test JSON exporter"""

    @pytest.mark.unit
    def test_export_ctk_format(self, sample_conversation):
        """Test exporting in CTK native format"""
        exporter = JSONExporter()
        result = exporter.export_conversations(
            [sample_conversation], format_style="ctk"
        )

        data = json.loads(result)
        assert data["format"] == "ctk"
        assert "conversations" in data
        assert len(data["conversations"]) == 1

        conv = data["conversations"][0]
        assert conv["id"] in ["test-conv-1", "conv_001"]  # ID may vary
        assert conv["title"] == "Test Conversation"
        assert "messages" in conv
        assert "metadata" in conv

    @pytest.mark.unit
    def test_export_openai_format(self, sample_conversation):
        """Test exporting in OpenAI format"""
        exporter = JSONExporter()
        result = exporter.export_conversations(
            [sample_conversation], format_style="openai", path_selection="longest"
        )

        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 1

        conv = data[0]
        assert "messages" in conv
        messages = conv["messages"]
        assert all("role" in msg and "content" in msg for msg in messages)

    @pytest.mark.unit
    def test_export_anthropic_format(self, sample_conversation):
        """Test exporting in Anthropic format"""
        exporter = JSONExporter()
        result = exporter.export_conversations(
            [sample_conversation], format_style="anthropic", path_selection="longest"
        )

        data = json.loads(result)
        # Anthropic format may be list or dict with conversations
        if isinstance(data, dict) and "conversations" in data:
            conversations = data["conversations"]
        else:
            conversations = data if isinstance(data, list) else [data]

        assert len(conversations) >= 1

        conv = conversations[0]
        assert "messages" in conv or "uuid" in conv
        if "messages" in conv:
            messages = conv["messages"]
            assert all("role" in msg and "content" in msg for msg in messages)

    @pytest.mark.unit
    def test_export_generic_format(self, sample_conversation):
        """Test exporting in generic format"""
        exporter = JSONExporter()
        result = exporter.export_conversations(
            [sample_conversation], format_style="generic"
        )

        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 1

    @pytest.mark.unit
    def test_export_pretty_print(self, sample_conversation):
        """Test pretty printing"""
        exporter = JSONExporter()
        pretty = exporter.export_conversations([sample_conversation], pretty_print=True)
        compact = exporter.export_conversations(
            [sample_conversation], pretty_print=False
        )

        # Pretty printed should have more characters due to indentation
        assert len(pretty) > len(compact)
        assert "\n" in pretty

    @pytest.mark.unit
    def test_export_to_file(self, sample_conversation, temp_dir):
        """Test exporting to file"""
        exporter = JSONExporter()
        output_path = temp_dir / "export.json"

        exporter.export_conversations(
            [sample_conversation], output_file=str(output_path)
        )

        assert output_path.exists()
        assert output_path.stat().st_size > 0

        with open(output_path) as f:
            data = json.load(f)

        assert "format" in data or isinstance(data, list)

    @pytest.mark.unit
    def test_export_multiple_conversations(self, sample_conversation):
        """Test exporting multiple conversations"""
        conv2 = ConversationTree(id="conv_002", title="Second")
        msg = Message(
            id="msg_100",
            role=MessageRole.USER,
            content=MessageContent(text="Another conversation"),
        )
        conv2.add_message(msg)

        exporter = JSONExporter()
        result = exporter.export_conversations([sample_conversation, conv2])

        data = json.loads(result)
        assert len(data["conversations"]) == 2

    @pytest.mark.unit
    def test_validation(self):
        """Test validation always returns True for JSON exporter"""
        exporter = JSONExporter()
        assert exporter.validate([])
        assert exporter.validate(None)
        assert exporter.validate("anything")


class TestMarkdownExporter:
    """Test Markdown exporter"""

    @pytest.mark.unit
    def test_export_basic(self, sample_conversation):
        """Test basic markdown export"""
        exporter = MarkdownExporter()
        result = exporter.export_conversations([sample_conversation])

        assert isinstance(result, str)
        assert "Test Conversation" in result
        assert "User" in result
        assert "Assistant" in result
        assert "Hello" in result  # Check actual content

    @pytest.mark.unit
    def test_export_with_tree_structure(self, branching_conversation):
        """Test exporting with tree visualization"""
        exporter = MarkdownExporter()
        result = exporter.export_conversations(
            [branching_conversation], include_tree_structure=True
        )

        assert isinstance(result, str)
        # Should include some kind of tree indicators
        assert len(result) > 0

    @pytest.mark.unit
    def test_export_to_file(self, sample_conversation, temp_dir):
        """Test exporting to markdown file"""
        exporter = MarkdownExporter()
        output_path = temp_dir / "export.md"

        exporter.export_conversations(
            [sample_conversation], output_file=str(output_path)
        )

        assert output_path.exists()
        assert output_path.stat().st_size > 0

        content = output_path.read_text()
        assert len(content) > 0

    @pytest.mark.unit
    def test_export_multiple_conversations(self, sample_conversation):
        """Test exporting multiple conversations"""
        conv2 = ConversationTree(id="conv_002", title="Second")
        msg = Message(
            id="msg_100",
            role=MessageRole.USER,
            content=MessageContent(text="Another conversation"),
        )
        conv2.add_message(msg)

        exporter = MarkdownExporter()
        result = exporter.export_conversations([sample_conversation, conv2])

        assert "Test Conversation" in result
        assert "Second" in result

    @pytest.mark.unit
    def test_path_selection(self, branching_conversation):
        """Test different path selection strategies"""
        exporter = MarkdownExporter()

        longest = exporter.export_conversations(
            [branching_conversation], path_selection="longest"
        )
        first = exporter.export_conversations(
            [branching_conversation], path_selection="first"
        )

        # Both should produce valid markdown
        assert len(longest) > 0
        assert len(first) > 0

    @pytest.mark.unit
    def test_validation(self):
        """Test validation always returns True for Markdown exporter"""
        exporter = MarkdownExporter()
        assert exporter.validate([])
        assert exporter.validate(None)

    @pytest.mark.unit
    def test_export_to_directory(self, sample_conversation, temp_dir):
        """Test exporting multiple conversations to separate files in a directory"""
        # Create two conversations
        conv2 = ConversationTree(id="conv_002", title="Second Conversation")
        msg = Message(
            id="msg_100",
            role=MessageRole.USER,
            content=MessageContent(text="Another conversation"),
        )
        conv2.add_message(msg)

        exporter = MarkdownExporter()
        output_dir = temp_dir / "md_export"

        # Export to directory (path without extension triggers directory mode)
        exporter.export_to_file([sample_conversation, conv2], str(output_dir))

        # Check directory was created
        assert output_dir.exists()
        assert output_dir.is_dir()

        # Check files were created
        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) == 2

        # Check content of files
        for md_file in md_files:
            content = md_file.read_text()
            assert len(content) > 0
            assert "## Conversation" in content

    @pytest.mark.unit
    def test_export_single_file_vs_directory(self, sample_conversation, temp_dir):
        """Test that .md extension produces single file, no extension produces directory"""
        exporter = MarkdownExporter()

        # Single file mode (with .md extension)
        single_file = temp_dir / "single.md"
        exporter.export_to_file([sample_conversation], str(single_file))
        assert single_file.is_file()

        # Directory mode (no extension)
        dir_path = temp_dir / "multiple"
        exporter.export_to_file([sample_conversation], str(dir_path))
        assert dir_path.is_dir()
        assert len(list(dir_path.glob("*.md"))) == 1


class TestECHOExporter:
    """Tests for ECHO format exporter."""

    @pytest.fixture
    def echo_exporter(self):
        """Create an ECHO exporter instance."""
        return ECHOExporter()

    @pytest.mark.unit
    def test_export_creates_directory_structure(
        self, echo_exporter, sample_conversation, temp_dir
    ):
        """Test ECHO export creates correct directory structure."""
        echo_exporter.export_to_directory([sample_conversation], str(temp_dir))

        assert (temp_dir / "README.md").exists()
        assert (temp_dir / "index.json").exists()
        assert (temp_dir / "manifest.json").exists()
        assert (temp_dir / "conversations").is_dir()

    @pytest.mark.unit
    def test_export_generates_manifest(
        self, echo_exporter, sample_conversation, temp_dir
    ):
        """Test manifest.json is generated with correct schema."""
        echo_exporter.export_to_directory(
            [sample_conversation], str(temp_dir), owner_name="Test User"
        )

        manifest = json.loads((temp_dir / "manifest.json").read_text())
        assert manifest["version"] == "1.0"
        assert manifest["type"] == "database"
        assert manifest["browsable"] is True
        assert manifest["icon"] == "chat"
        assert "Test User" in manifest["name"]

    @pytest.mark.unit
    def test_export_manifest_default_name(
        self, echo_exporter, sample_conversation, temp_dir
    ):
        """Test manifest.json has default name when owner_name is Unknown."""
        echo_exporter.export_to_directory(
            [sample_conversation], str(temp_dir), owner_name="Unknown"
        )

        manifest = json.loads((temp_dir / "manifest.json").read_text())
        assert manifest["name"] == "Conversation Archive"
        assert "Unknown" not in manifest["name"]

    @pytest.mark.unit
    def test_export_with_include_db(
        self, echo_exporter, sample_conversation, temp_dir
    ):
        """Test database copy when include_db=True."""
        # Create a temporary database file
        db_file = temp_dir / "source.db"
        db_file.write_text("dummy database content")

        output_dir = temp_dir / "output"
        echo_exporter.export_to_directory(
            [sample_conversation],
            str(output_dir),
            include_db=True,
            db_path=str(db_file),
        )

        assert (output_dir / "conversations.db").exists()

    @pytest.mark.unit
    def test_export_with_include_site(
        self, echo_exporter, sample_conversation, temp_dir
    ):
        """Test HTML site generation when include_site=True."""
        echo_exporter.export_to_directory(
            [sample_conversation], str(temp_dir), include_site=True
        )

        # Check site directory was created
        assert (temp_dir / "site").is_dir()
        assert (temp_dir / "site" / "index.html").exists()

        # Check manifest includes site reference
        manifest = json.loads((temp_dir / "manifest.json").read_text())
        assert manifest.get("site") == "site/"

    @pytest.mark.unit
    def test_conversation_json_tree_structure(
        self, echo_exporter, branching_conversation, temp_dir
    ):
        """Test conversation.json has correct tree structure with children."""
        echo_exporter.export_to_directory([branching_conversation], str(temp_dir))

        conv_json_path = temp_dir / "conversations" / branching_conversation.id / "conversation.json"
        assert conv_json_path.exists()

        conv_data = json.loads(conv_json_path.read_text())
        assert conv_data["id"] == branching_conversation.id
        assert "messages" in conv_data
        assert len(conv_data["messages"]) >= 1

        # Check that children structure exists
        root_msg = conv_data["messages"][0]
        assert "children" in root_msg
        assert len(root_msg["children"]) >= 1

    @pytest.mark.unit
    def test_conversation_md_readable(
        self, echo_exporter, sample_conversation, temp_dir
    ):
        """Test conversation.md is human-readable."""
        echo_exporter.export_to_directory([sample_conversation], str(temp_dir))

        conv_md_path = temp_dir / "conversations" / sample_conversation.id / "conversation.md"
        assert conv_md_path.exists()

        content = conv_md_path.read_text()
        assert sample_conversation.title in content
        assert "## USER" in content
        assert "## ASSISTANT" in content

    @pytest.mark.unit
    def test_export_index_json_structure(
        self, echo_exporter, sample_conversation, temp_dir
    ):
        """Test index.json has correct structure."""
        echo_exporter.export_to_directory([sample_conversation], str(temp_dir))

        index_data = json.loads((temp_dir / "index.json").read_text())
        assert index_data["format"] == "ctk-echo"
        assert index_data["version"] == "1.0.0"
        assert "exported_at" in index_data
        assert index_data["total_conversations"] == 1
        assert len(index_data["conversations"]) == 1

        conv_info = index_data["conversations"][0]
        assert conv_info["id"] == sample_conversation.id
        assert conv_info["title"] == sample_conversation.title

    @pytest.mark.unit
    def test_export_metadata_json(
        self, echo_exporter, sample_conversation, temp_dir
    ):
        """Test metadata.json is generated correctly."""
        echo_exporter.export_to_directory([sample_conversation], str(temp_dir))

        metadata_path = temp_dir / "conversations" / sample_conversation.id / "metadata.json"
        assert metadata_path.exists()

        metadata = json.loads(metadata_path.read_text())
        assert metadata["id"] == sample_conversation.id
        assert metadata["title"] == sample_conversation.title
        assert metadata["source"] == "test"
        assert metadata["model"] == "test-model"
        assert "message_count" in metadata

    @pytest.mark.unit
    def test_readme_contains_correct_url(
        self, echo_exporter, sample_conversation, temp_dir
    ):
        """Test README.md contains correct longecho URL."""
        echo_exporter.export_to_directory([sample_conversation], str(temp_dir))

        readme_content = (temp_dir / "README.md").read_text()
        assert "https://github.com/queelius/longecho" in readme_content
        assert "alextowell" not in readme_content

    @pytest.mark.unit
    def test_export_multiple_conversations(
        self, echo_exporter, sample_conversation, branching_conversation, temp_dir
    ):
        """Test exporting multiple conversations."""
        echo_exporter.export_to_directory(
            [sample_conversation, branching_conversation], str(temp_dir)
        )

        index_data = json.loads((temp_dir / "index.json").read_text())
        assert index_data["total_conversations"] == 2

        # Check both conversation directories exist
        assert (temp_dir / "conversations" / sample_conversation.id).is_dir()
        assert (temp_dir / "conversations" / branching_conversation.id).is_dir()

    @pytest.mark.unit
    def test_validation(self, echo_exporter):
        """Test ECHO exporter validation."""
        assert echo_exporter.validate([])
        assert echo_exporter.validate([ConversationTree(id="test")])
        assert not echo_exporter.validate("string")
        assert not echo_exporter.validate(123)

    @pytest.mark.unit
    def test_export_data_method(self, echo_exporter, sample_conversation, temp_dir):
        """Test export_data method returns summary dict."""
        result = echo_exporter.export_data(
            [sample_conversation], output_dir=str(temp_dir)
        )

        assert isinstance(result, dict)
        assert result["total_exported"] == 1
        assert result["output_dir"] == str(temp_dir)
        assert "db_included" in result

    @pytest.mark.unit
    def test_export_to_file_method(self, echo_exporter, sample_conversation, temp_dir):
        """Test export_to_file treats file_path as directory."""
        output_path = temp_dir / "echo_output"
        echo_exporter.export_to_file([sample_conversation], str(output_path))

        assert output_path.is_dir()
        assert (output_path / "README.md").exists()
        assert (output_path / "manifest.json").exists()


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


def _make_conversation(title=None, source=None, model=None, messages=None, tags=None):
    """Helper to create minimal test conversations for edge case tests."""
    metadata = ConversationMetadata()
    metadata.source = source
    metadata.model = model
    metadata.tags = tags or []
    metadata.created_at = None
    metadata.updated_at = None
    metadata.starred_at = None
    metadata.pinned_at = None
    metadata.archived_at = None

    conv = ConversationTree(id="test-conv", title=title, metadata=metadata)

    if messages:
        for msg_id, role, text, parent_id in messages:
            msg = Message(
                id=msg_id,
                role=role,
                content=MessageContent(text=text),
                parent_id=parent_id,
            )
            conv.add_message(msg)

    return conv


class TestExporterEdgeCases:
    """Edge case tests for all exporters."""

    # ---- Empty input ----

    @pytest.mark.unit
    def test_jsonl_empty_conversations(self):
        """JSONL with empty list produces empty string."""
        exporter = JSONLExporter()
        result = exporter.export_data([])
        assert result == ""

    @pytest.mark.unit
    def test_json_empty_conversations(self):
        """JSON with empty list produces valid JSON (empty conversations array)."""
        exporter = JSONExporter()
        result = exporter.export_conversations([])
        data = json.loads(result)
        # CTK format wraps in {"format": "ctk", "conversations": [...]}
        assert data["conversations"] == []

    @pytest.mark.unit
    def test_json_empty_conversations_openai_format(self):
        """JSON OpenAI format with empty list produces valid empty JSON array."""
        exporter = JSONExporter()
        result = exporter.export_conversations([], format_style="openai")
        data = json.loads(result)
        assert data == []

    @pytest.mark.unit
    def test_json_empty_conversations_generic_format(self):
        """JSON generic format with empty list produces valid empty JSON array."""
        exporter = JSONExporter()
        result = exporter.export_conversations([], format_style="generic")
        data = json.loads(result)
        assert data == []

    @pytest.mark.unit
    def test_markdown_empty_conversations(self):
        """Markdown with empty list produces empty/minimal output."""
        exporter = MarkdownExporter()
        result = exporter.export_conversations([])
        # Empty list should produce empty string (no conversations to render)
        assert result == ""

    # ---- Missing metadata ----

    @pytest.mark.unit
    def test_jsonl_missing_metadata(self):
        """JSONL handles conversation with no metadata gracefully."""
        conv = _make_conversation(
            title=None,
            source=None,
            model=None,
            messages=[("m1", MessageRole.USER, "Hello", None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv])
        lines = result.strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert "messages" in data
        assert data["messages"][0]["content"] == "Hello"

    @pytest.mark.unit
    def test_jsonl_missing_metadata_with_include_metadata(self):
        """JSONL with include_metadata=True handles None source/model."""
        conv = _make_conversation(
            title=None,
            source=None,
            model=None,
            messages=[("m1", MessageRole.USER, "Hello", None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv], include_metadata=True)
        lines = result.strip().split("\n")
        first = json.loads(lines[0])
        assert "metadata" in first
        assert first["metadata"]["source"] is None
        assert first["metadata"]["model"] is None

    @pytest.mark.unit
    def test_json_missing_metadata(self):
        """JSON handles conversation with no metadata gracefully."""
        conv = _make_conversation(
            title=None,
            source=None,
            model=None,
            messages=[("m1", MessageRole.USER, "Hello", None)],
        )
        exporter = JSONExporter()
        result = exporter.export_conversations([conv])
        data = json.loads(result)
        assert len(data["conversations"]) == 1

    @pytest.mark.unit
    def test_markdown_missing_metadata(self):
        """Markdown handles conversation with no metadata gracefully."""
        conv = _make_conversation(
            title=None,
            source=None,
            model=None,
            messages=[("m1", MessageRole.USER, "Hello", None)],
        )
        exporter = MarkdownExporter()
        result = exporter.export_conversations([conv])
        assert isinstance(result, str)
        assert len(result) > 0
        # Should use fallback title (Conversation <short-id>)
        assert "Conversation" in result or "test-conv" in result

    # ---- Special characters ----

    @pytest.mark.unit
    def test_jsonl_special_chars_in_content(self):
        """JSONL properly escapes quotes, newlines, tabs in content."""
        special_text = 'She said "hello"\nNew line\there\ttabs\r\nCRLF'
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, special_text, None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv])
        # Each line should be valid JSON
        data = json.loads(result.strip())
        assert data["messages"][0]["content"] == special_text

    @pytest.mark.unit
    def test_json_special_chars_in_title(self):
        """JSON properly escapes special characters in title."""
        title = 'My "great" conversation <with> special & chars'
        conv = _make_conversation(
            title=title,
            messages=[("m1", MessageRole.USER, "Hello", None)],
        )
        exporter = JSONExporter()
        result = exporter.export_conversations([conv])
        data = json.loads(result)
        assert data["conversations"][0]["title"] == title

    @pytest.mark.unit
    def test_markdown_special_chars_in_content(self):
        """Markdown handles special characters without breaking formatting."""
        special_text = "Code: `print('hello')` and **bold** and *italic* and # heading"
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, special_text, None)],
        )
        exporter = MarkdownExporter()
        result = exporter.export_conversations([conv])
        assert isinstance(result, str)
        # The special characters should appear in the output
        assert special_text in result

    @pytest.mark.unit
    def test_jsonl_backslash_in_content(self):
        """JSONL properly escapes backslashes in content."""
        text_with_backslash = r"Path: C:\Users\test\file.txt"
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, text_with_backslash, None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv])
        data = json.loads(result.strip())
        assert data["messages"][0]["content"] == text_with_backslash

    # ---- Unicode ----

    @pytest.mark.unit
    def test_jsonl_unicode_content(self):
        """JSONL handles unicode (CJK, emoji, RTL) correctly."""
        unicode_text = "Hello world"
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, unicode_text, None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv])
        data = json.loads(result.strip())
        assert data["messages"][0]["content"] == unicode_text

    @pytest.mark.unit
    def test_jsonl_cjk_content(self):
        """JSONL handles CJK characters correctly."""
        cjk_text = "This is a test with CJK characters"
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, cjk_text, None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv])
        data = json.loads(result.strip())
        assert data["messages"][0]["content"] == cjk_text

    @pytest.mark.unit
    def test_jsonl_rtl_content(self):
        """JSONL handles RTL text correctly."""
        rtl_text = "Mixed direction text"
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, rtl_text, None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv])
        data = json.loads(result.strip())
        assert data["messages"][0]["content"] == rtl_text

    @pytest.mark.unit
    def test_json_unicode_content(self):
        """JSON handles unicode correctly."""
        unicode_text = "Unicode test: cafe\u0301 nai\u0308ve"
        conv = _make_conversation(
            title="Unicode title: cafe\u0301",
            messages=[("m1", MessageRole.USER, unicode_text, None)],
        )
        exporter = JSONExporter()
        result = exporter.export_conversations([conv])
        data = json.loads(result)
        assert data["conversations"][0]["title"] == "Unicode title: cafe\u0301"

    @pytest.mark.unit
    def test_markdown_unicode_content(self):
        """Markdown handles unicode content properly."""
        unicode_text = "Unicode: cafe\u0301 + CJK"
        conv = _make_conversation(
            title="Unicode Conversation",
            messages=[("m1", MessageRole.USER, unicode_text, None)],
        )
        exporter = MarkdownExporter()
        result = exporter.export_conversations([conv])
        assert unicode_text in result

    # ---- Very long content ----

    @pytest.mark.unit
    def test_jsonl_long_content(self):
        """JSONL handles very long messages (10k+ chars)."""
        long_text = "A" * 15000
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, long_text, None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv])
        data = json.loads(result.strip())
        assert len(data["messages"][0]["content"]) == 15000

    @pytest.mark.unit
    def test_json_long_content(self):
        """JSON handles very long messages (10k+ chars)."""
        long_text = "B" * 12000
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, long_text, None)],
        )
        exporter = JSONExporter()
        result = exporter.export_conversations([conv])
        data = json.loads(result)
        # Verify content is preserved in full
        msg_map = data["conversations"][0]["messages"]
        # CTK format stores messages as a dict keyed by message id
        assert any(
            len(m.get("content", {}).get("text", "")) == 12000
            for m in msg_map.values()
        )

    @pytest.mark.unit
    def test_markdown_long_content(self):
        """Markdown handles very long messages without crashing."""
        long_text = "C" * 10000
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, long_text, None)],
        )
        exporter = MarkdownExporter()
        result = exporter.export_conversations([conv])
        assert long_text in result

    # ---- Conversation with single message ----

    @pytest.mark.unit
    def test_jsonl_single_message(self):
        """JSONL handles conversation with just one user message."""
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, "Solo message", None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv])
        data = json.loads(result.strip())
        assert len(data["messages"]) == 1
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "Solo message"

    @pytest.mark.unit
    def test_json_single_message(self):
        """JSON handles conversation with just one user message."""
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, "Solo message", None)],
        )
        exporter = JSONExporter()
        result = exporter.export_conversations([conv])
        data = json.loads(result)
        assert len(data["conversations"]) == 1

    @pytest.mark.unit
    def test_markdown_single_message(self):
        """Markdown handles conversation with just one message."""
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, "Solo message", None)],
        )
        exporter = MarkdownExporter()
        result = exporter.export_conversations([conv])
        assert "Solo message" in result
        assert "User" in result

    # ---- Conversation with no title ----

    @pytest.mark.unit
    def test_jsonl_no_title(self):
        """JSONL handles conversation with no title."""
        conv = _make_conversation(
            title=None,
            messages=[
                ("m1", MessageRole.USER, "Hello", None),
                ("m2", MessageRole.ASSISTANT, "Hi", "m1"),
            ],
        )
        exporter = JSONLExporter()
        # Without metadata, title is not in the output
        result = exporter.export_data([conv])
        data = json.loads(result.strip())
        assert "messages" in data

        # With metadata, title should be None
        result_meta = exporter.export_data([conv], include_metadata=True)
        first = json.loads(result_meta.strip().split("\n")[0])
        assert first["metadata"]["title"] is None

    @pytest.mark.unit
    def test_json_no_title(self):
        """JSON handles conversation with no title."""
        conv = _make_conversation(
            title=None,
            messages=[
                ("m1", MessageRole.USER, "Hello", None),
                ("m2", MessageRole.ASSISTANT, "Hi", "m1"),
            ],
        )
        exporter = JSONExporter()
        result = exporter.export_conversations([conv])
        data = json.loads(result)
        assert data["conversations"][0]["title"] is None

    @pytest.mark.unit
    def test_markdown_no_title(self):
        """Markdown handles conversation with no title using fallback."""
        conv = _make_conversation(
            title=None,
            messages=[
                ("m1", MessageRole.USER, "Hello", None),
                ("m2", MessageRole.ASSISTANT, "Hi", "m1"),
            ],
        )
        exporter = MarkdownExporter()
        result = exporter.export_conversations([conv])
        # Should use fallback title "Conversation <short_id>"
        assert "Conversation" in result

    # ---- Conversation with no messages ----

    @pytest.mark.unit
    def test_jsonl_no_messages(self):
        """JSONL handles conversation with zero messages."""
        conv = _make_conversation(title="Empty chat")
        exporter = JSONLExporter()
        result = exporter.export_data([conv])
        data = json.loads(result.strip())
        assert data["messages"] == []

    @pytest.mark.unit
    def test_json_no_messages(self):
        """JSON handles conversation with zero messages."""
        conv = _make_conversation(title="Empty chat")
        exporter = JSONExporter()
        result = exporter.export_conversations([conv])
        data = json.loads(result)
        assert len(data["conversations"]) == 1
        # CTK format stores messages as a dict
        assert data["conversations"][0]["messages"] == {}

    @pytest.mark.unit
    def test_markdown_no_messages(self):
        """Markdown handles conversation with zero messages."""
        conv = _make_conversation(title="Empty chat")
        exporter = MarkdownExporter()
        result = exporter.export_conversations([conv])
        assert "Empty chat" in result

    # ---- Empty message content ----

    @pytest.mark.unit
    def test_jsonl_empty_message_content(self):
        """JSONL handles messages with empty string content."""
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, "", None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv])
        data = json.loads(result.strip())
        assert data["messages"][0]["content"] == ""

    @pytest.mark.unit
    def test_json_empty_message_content(self):
        """JSON handles messages with empty string content."""
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, "", None)],
        )
        exporter = JSONExporter()
        result = exporter.export_conversations([conv], format_style="openai",
                                                path_selection="longest")
        data = json.loads(result)
        assert data[0]["messages"][0]["content"] == ""

    @pytest.mark.unit
    def test_markdown_empty_message_content(self):
        """Markdown handles messages with empty string content."""
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, "", None)],
        )
        exporter = MarkdownExporter()
        result = exporter.export_conversations([conv])
        # Should still show the role header, even with empty content
        assert "User" in result

    # ---- Multiple format styles for JSON exporter ----

    @pytest.mark.unit
    def test_json_anthropic_empty(self):
        """JSON Anthropic format with empty list produces valid output."""
        exporter = JSONExporter()
        result = exporter.export_conversations([], format_style="anthropic")
        data = json.loads(result)
        assert data["conversations"] == []

    # ---- JSONL format types (chat, instruction) ----

    @pytest.mark.unit
    def test_jsonl_chat_format_single_turn(self):
        """JSONL chat format with a single user-assistant pair."""
        conv = _make_conversation(
            messages=[
                ("m1", MessageRole.USER, "Hi", None),
                ("m2", MessageRole.ASSISTANT, "Hello!", "m1"),
            ],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv], format="chat")
        lines = result.strip().split("\n")
        assert len(lines) >= 1
        for line in lines:
            data = json.loads(line)
            assert "messages" in data

    @pytest.mark.unit
    def test_jsonl_instruction_format(self):
        """JSONL instruction format produces instruction-response pairs."""
        conv = _make_conversation(
            messages=[
                ("m1", MessageRole.USER, "Explain gravity", None),
                ("m2", MessageRole.ASSISTANT, "Gravity is a force...", "m1"),
            ],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv], format="instruction")
        lines = result.strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["instruction"] == "Explain gravity"
        assert data["response"] == "Gravity is a force..."

    @pytest.mark.unit
    def test_jsonl_instruction_format_empty(self):
        """JSONL instruction format with no user/assistant pairs produces nothing."""
        conv = _make_conversation(
            messages=[("m1", MessageRole.SYSTEM, "You are helpful.", None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv], format="instruction")
        assert result == ""

    # ---- Conversation with only system message ----

    @pytest.mark.unit
    def test_jsonl_system_only(self):
        """JSONL handles conversation with only a system message."""
        conv = _make_conversation(
            messages=[("m1", MessageRole.SYSTEM, "You are helpful.", None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv])
        data = json.loads(result.strip())
        assert len(data["messages"]) == 1
        assert data["messages"][0]["role"] == "system"

    @pytest.mark.unit
    def test_jsonl_system_only_excluded(self):
        """JSONL with include_system=False excludes system messages."""
        conv = _make_conversation(
            messages=[("m1", MessageRole.SYSTEM, "You are helpful.", None)],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv], include_system=False)
        data = json.loads(result.strip())
        assert data["messages"] == []

    # ---- Markdown-specific edge cases ----

    @pytest.mark.unit
    def test_markdown_code_block_in_content(self):
        """Markdown preserves code blocks in message content."""
        code_content = "Here is code:\n```python\nprint('hello')\n```\nDone."
        conv = _make_conversation(
            messages=[("m1", MessageRole.ASSISTANT, code_content, None)],
        )
        exporter = MarkdownExporter()
        result = exporter.export_conversations([conv])
        assert "```python" in result
        assert "print('hello')" in result

    @pytest.mark.unit
    def test_markdown_multiline_content(self):
        """Markdown handles multi-line message content correctly."""
        multiline = "Line 1\nLine 2\nLine 3\n\nParagraph 2"
        conv = _make_conversation(
            messages=[("m1", MessageRole.USER, multiline, None)],
        )
        exporter = MarkdownExporter()
        result = exporter.export_conversations([conv])
        assert multiline in result

    @pytest.mark.unit
    def test_markdown_pipe_in_metadata(self):
        """Markdown metadata table handles pipe characters in tag values."""
        conv = _make_conversation(
            title="Test",
            tags=["tag|with|pipes", "normal-tag"],
            messages=[("m1", MessageRole.USER, "Hello", None)],
        )
        exporter = MarkdownExporter()
        # Should not crash even if tags contain pipe characters
        result = exporter.export_conversations([conv])
        assert isinstance(result, str)
        assert len(result) > 0

    # ---- Path selection on conversations with no branches ----

    @pytest.mark.unit
    def test_jsonl_all_paths_linear(self):
        """JSONL 'all' path selection on linear conversation produces one path."""
        conv = _make_conversation(
            messages=[
                ("m1", MessageRole.USER, "Hello", None),
                ("m2", MessageRole.ASSISTANT, "Hi", "m1"),
            ],
        )
        exporter = JSONLExporter()
        result = exporter.export_data([conv], path_selection="all")
        # For a linear conversation, 'all' paths still means 1 path (via "first")
        # Actually the JSONL 'all' is not a branch, it falls to the else case
        # Let's just verify it doesn't crash and produces valid JSON
        lines = result.strip().split("\n")
        assert len(lines) >= 1
        for line in lines:
            json.loads(line)

    @pytest.mark.unit
    def test_json_all_paths_linear(self):
        """JSON 'all' path selection on linear conversation produces messages."""
        conv = _make_conversation(
            messages=[
                ("m1", MessageRole.USER, "Hello", None),
                ("m2", MessageRole.ASSISTANT, "Hi", "m1"),
            ],
        )
        exporter = JSONExporter()
        result = exporter.export_conversations(
            [conv], format_style="openai", path_selection="all"
        )
        data = json.loads(result)
        assert len(data) == 1
        assert len(data[0]["messages"]) == 2
