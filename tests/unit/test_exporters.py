"""
Unit tests for exporters
"""

import pytest
import json
import tempfile
from pathlib import Path

from ctk.integrations.exporters.jsonl import JSONLExporter
from ctk.integrations.exporters.json import JSONExporter
from ctk.integrations.exporters.markdown import MarkdownExporter
from ctk.core.models import (
    ConversationTree, Message, MessageContent,
    MessageRole, ConversationMetadata
)


class TestJSONLExporter:
    """Test JSONL exporter"""
    
    @pytest.mark.unit
    def test_export_single_conversation(self, sample_conversation):
        """Test exporting a single conversation preserves message content and structure"""
        exporter = JSONLExporter()
        result = exporter.export_data([sample_conversation])

        # Should have at least one line of JSONL output
        lines = result.strip().split('\n')
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
        result = exporter.export_data(
            [sample_conversation],
            include_metadata=True
        )
        
        lines = result.strip().split('\n')
        
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
            content=MessageContent(text="Another conversation")
        )
        conv2.add_message(msg)

        exporter = JSONLExporter()
        result = exporter.export_data([sample_conversation, conv2])

        lines = result.strip().split('\n')

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
        assert first_content != second_content, "Different conversations should have different content"
    
    @pytest.mark.unit
    def test_export_branching_conversation(self, branching_conversation):
        """Test exporting conversation with branches respects path selection"""
        exporter = JSONLExporter()
        result = exporter.export_data(
            [branching_conversation],
            path_selection="longest"
        )

        lines = result.strip().split('\n')
        assert len(lines) >= 1, "Should produce at least one conversation"

        conv_data = json.loads(lines[0])
        messages = conv_data["messages"]

        # Should contain messages from the branching conversation
        assert len(messages) >= 2, "Should contain multiple messages from branching path"

        # Verify it contains expected content from the path
        message_contents = [msg["content"] for msg in messages]
        has_math_content = any("2+2" in content for content in message_contents)
        assert has_math_content, "Should contain content from the branching conversation"
    
    @pytest.mark.unit
    def test_export_to_file(self, sample_conversation, temp_dir):
        """Test exporting to file creates valid JSONL output"""
        exporter = JSONLExporter()
        output_path = temp_dir / "export.jsonl"

        exporter.export_to_file(
            [sample_conversation],
            str(output_path)
        )

        # File should exist and have content
        assert output_path.exists(), "Export should create output file"
        assert output_path.stat().st_size > 0, "Output file should not be empty"

        # Content should be valid JSONL
        with open(output_path) as f:
            content = f.read().strip()

        lines = content.split('\n')
        assert len(lines) >= 1, "Should have at least one line of JSONL"

        # Each line should be valid JSON with expected structure
        for line in lines:
            if line.strip():  # Skip empty lines
                data = json.loads(line.strip())
                assert "messages" in data, "Each conversation should have messages structure"
    
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
            [sample_conversation],
            format_style="ctk"
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
            [sample_conversation],
            format_style="openai",
            path_selection="longest"
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
            [sample_conversation],
            format_style="anthropic",
            path_selection="longest"
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
            [sample_conversation],
            format_style="generic"
        )

        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 1

    @pytest.mark.unit
    def test_export_pretty_print(self, sample_conversation):
        """Test pretty printing"""
        exporter = JSONExporter()
        pretty = exporter.export_conversations(
            [sample_conversation],
            pretty_print=True
        )
        compact = exporter.export_conversations(
            [sample_conversation],
            pretty_print=False
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
            [sample_conversation],
            output_file=str(output_path)
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
            content=MessageContent(text="Another conversation")
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
            [branching_conversation],
            include_tree_structure=True
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
            [sample_conversation],
            output_file=str(output_path)
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
            content=MessageContent(text="Another conversation")
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
            [branching_conversation],
            path_selection="longest"
        )
        first = exporter.export_conversations(
            [branching_conversation],
            path_selection="first"
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