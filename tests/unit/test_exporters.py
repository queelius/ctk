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
