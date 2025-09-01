"""
Unit tests for exporters
"""

import pytest
import json
import tempfile
from pathlib import Path

from ctk.integrations.exporters.jsonl import JSONLExporter
from ctk.core.models import (
    ConversationTree, Message, MessageContent, 
    MessageRole, ConversationMetadata
)


class TestJSONLExporter:
    """Test JSONL exporter"""
    
    @pytest.mark.unit
    def test_export_single_conversation(self, sample_conversation):
        """Test exporting a single conversation to JSONL"""
        exporter = JSONLExporter()
        result = exporter.export_data([sample_conversation])
        
        lines = result.strip().split('\n')
        assert len(lines) == 4  # 4 messages in sample conversation
        
        # Parse each line
        for line in lines:
            data = json.loads(line)
            assert "role" in data
            assert "content" in data
        
        # Check first message
        first = json.loads(lines[0])
        assert first["role"] == "user"
        assert first["content"] == "Hello"
    
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
        """Test exporting multiple conversations"""
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
        
        # Should have conversation break
        assert any(
            json.loads(line).get("conversation_break") == True 
            for line in lines
        )
    
    @pytest.mark.unit
    def test_export_branching_conversation(self, branching_conversation):
        """Test exporting conversation with branches"""
        exporter = JSONLExporter()
        result = exporter.export_data(
            [branching_conversation],
            path_selection="longest"
        )
        
        lines = result.strip().split('\n')
        messages = [json.loads(line) for line in lines]
        
        # Should export longest path
        assert len(messages) == 4
        assert messages[0]["content"] == "What's 2+2?"
        assert "3+3" in messages[2]["content"]
    
    @pytest.mark.unit
    def test_export_to_file(self, sample_conversation, temp_dir):
        """Test exporting to file"""
        exporter = JSONLExporter()
        output_path = temp_dir / "export.jsonl"
        
        exporter.export_to_file(
            [sample_conversation],
            str(output_path)
        )
        
        assert output_path.exists()
        
        with open(output_path) as f:
            lines = f.readlines()
            assert len(lines) == 4
            
            # Verify it's valid JSONL
            for line in lines:
                json.loads(line)
    
    @pytest.mark.unit
    def test_jsonl_validation(self):
        """Test JSONL exporter validation"""
        exporter = JSONLExporter()
        
        assert exporter.validate([])  # Empty list
        assert exporter.validate([ConversationTree(id="test")])
        assert not exporter.validate("string")
        assert not exporter.validate(123)


# TODO: Add tests for MarkdownExporter when implemented
# TODO: Add tests for LocalLLMExporter when implemented
# TODO: Add tests for other exporters as they are created