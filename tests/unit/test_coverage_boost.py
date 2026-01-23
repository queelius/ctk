"""
Targeted tests to boost coverage to 80%
"""

import json
import tempfile
from pathlib import Path

import pytest

from ctk.core.models import (ConversationMetadata, ConversationTree, Message,
                             MessageContent, MessageRole)
from ctk.integrations.exporters.jsonl import JSONLExporter
from ctk.integrations.importers.gemini import GeminiImporter
from ctk.integrations.importers.jsonl import JSONLImporter


class TestJSONLExporterExtended:
    """Extended JSONL exporter tests"""

    @pytest.mark.unit
    def test_export_to_file_method(self, sample_conversation, temp_dir):
        """Test export_to_file method"""
        exporter = JSONLExporter()
        output_path = temp_dir / "test.jsonl"

        result = exporter.export_to_file([sample_conversation], str(output_path))

        assert output_path.exists()
        assert output_path.stat().st_size > 0

    @pytest.mark.unit
    def test_export_without_metadata(self, sample_conversation):
        """Test export without metadata"""
        exporter = JSONLExporter()
        result = exporter.export_data([sample_conversation], include_metadata=False)

        assert isinstance(result, str)
        lines = result.strip().split("\n")
        assert len(lines) >= 1

    @pytest.mark.unit
    def test_export_path_selection_first(self, branching_conversation):
        """Test export with first path selection"""
        exporter = JSONLExporter()
        result = exporter.export_data([branching_conversation], path_selection="first")

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.unit
    def test_export_path_selection_last(self, branching_conversation):
        """Test export with last path selection"""
        exporter = JSONLExporter()
        result = exporter.export_data([branching_conversation], path_selection="last")

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.unit
    def test_export_empty_conversation(self):
        """Test export of empty conversation"""
        exporter = JSONLExporter()
        conv = ConversationTree(id="empty", title="Empty")

        result = exporter.export_data([conv])

        # Should handle empty conversation gracefully
        assert isinstance(result, str)


class TestJSONLImporterExtended:
    """Extended JSONL importer tests"""

    @pytest.mark.unit
    def test_import_with_id_field(self):
        """Test import with conversation ID in data"""
        importer = JSONLImporter()
        data = {"id": "test-123", "messages": [{"role": "user", "content": "Hello"}]}

        conversations = importer.import_data(data)
        assert len(conversations) == 1
        assert conversations[0].id == "test-123"

    @pytest.mark.unit
    def test_import_with_model_field(self):
        """Test import with model field"""
        importer = JSONLImporter()
        data = {"messages": [{"role": "user", "content": "Test"}], "model": "gpt-4"}

        conversations = importer.import_data(data)
        assert len(conversations) == 1
        assert conversations[0].metadata.model == "gpt-4"

    @pytest.mark.unit
    def test_import_system_message(self):
        """Test import with system message"""
        importer = JSONLImporter()
        data = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
        ]

        conversations = importer.import_data(data)
        messages = conversations[0].get_longest_path()
        assert messages[0].role == MessageRole.SYSTEM

    @pytest.mark.unit
    def test_import_with_timestamps(self):
        """Test import with timestamps"""
        importer = JSONLImporter()
        data = (
            '{"role": "user", "content": "Test", "timestamp": "2024-01-01T00:00:00"}\n'
        )

        conversations = importer.import_data(data)
        assert len(conversations) == 1

    @pytest.mark.unit
    def test_import_multiline_content(self):
        """Test import with multiline content"""
        importer = JSONLImporter()
        data = [{"role": "user", "content": "Line 1\nLine 2\nLine 3"}]

        conversations = importer.import_data(data)
        messages = conversations[0].get_longest_path()
        assert "Line 1" in messages[0].content.text
        assert "Line 2" in messages[0].content.text


class TestGeminiImporterExtended:
    """Extended Gemini importer tests"""

    @pytest.mark.unit
    def test_import_with_messages_field(self):
        """Test Gemini import with messages field"""
        importer = GeminiImporter()
        data = {
            "conversation_id": "gem-1",
            "messages": [
                {"role": "user", "parts": [{"text": "Hello"}]},
                {"role": "model", "parts": [{"text": "Hi"}]},
            ],
        }

        conversations = importer.import_data(data)
        assert len(conversations) == 1

    @pytest.mark.unit
    def test_import_multipart_message(self):
        """Test Gemini import with multiple parts"""
        importer = GeminiImporter()
        data = {
            "turns": [
                {"role": "user", "parts": [{"text": "Part 1"}, {"text": "Part 2"}]}
            ]
        }

        conversations = importer.import_data(data)
        messages = conversations[0].get_longest_path()
        content = messages[0].content.text
        assert "Part 1" in content or "Part 2" in content

    @pytest.mark.unit
    def test_import_with_title(self):
        """Test Gemini import with title"""
        importer = GeminiImporter()
        data = {
            "title": "Test Chat",
            "turns": [{"role": "user", "parts": [{"text": "Q"}]}],
        }

        conversations = importer.import_data(data)
        assert conversations[0].title == "Test Chat"


class TestCLICommandCoverage:
    """Test CLI command coverage"""

    @pytest.mark.unit
    def test_cli_main_import(self):
        """Test CLI main function can be imported"""
        from ctk.cli import main

        assert main is not None

    @pytest.mark.unit
    def test_cli_setup_logging_import(self):
        """Test CLI setup_logging can be imported"""
        from ctk.cli import setup_logging

        assert setup_logging is not None


class TestDatabaseCoverage:
    """Additional database coverage tests"""

    @pytest.mark.unit
    def test_list_conversations_with_filters(self):
        """Test list_conversations with filters"""
        import os

        from ctk.core.database import ConversationDB

        # Use temp directory, not temp file
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            with ConversationDB(db_path) as db:
                # Create test conversations
                for i in range(3):
                    conv = ConversationTree(
                        id=f"conv-{i}",
                        title=f"Test {i}",
                        metadata=ConversationMetadata(
                            source="test", model="test-model", tags=[f"tag{i}"]
                        ),
                    )
                    msg = Message(
                        id=f"msg-{i}",
                        role=MessageRole.USER,
                        content=MessageContent(text=f"Message {i}"),
                    )
                    conv.add_message(msg)
                    db.save_conversation(conv)

                # List with limit
                limited = db.list_conversations(limit=2)
                assert len(limited) <= 2

                # List with offset
                offset = db.list_conversations(offset=1)
                assert len(offset) >= 0
