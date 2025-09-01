"""
End-to-end integration tests
"""

import pytest
import json
import tempfile
from pathlib import Path

from ctk.core.database import ConversationDB
from ctk.core.plugin import registry
from ctk.integrations.importers.openai import OpenAIImporter
from ctk.integrations.importers.anthropic import AnthropicImporter
from ctk.integrations.exporters.jsonl import JSONLExporter
from ctk.integrations.exporters.markdown import MarkdownExporter
from ctk.integrations.taggers.tfidf_tagger import TFIDFTagger


class TestImportExportPipeline:
    """Test complete import/export pipeline"""
    
    @pytest.mark.integration
    def test_openai_to_jsonl_pipeline(self, openai_export_data, temp_dir):
        """Test importing from OpenAI and exporting to JSONL"""
        # Import
        importer = OpenAIImporter()
        conversations = importer.import_data(openai_export_data)
        assert len(conversations) == 1
        
        # Save to database
        db_path = temp_dir / "test.db"
        db = ConversationDB(str(db_path))
        for conv in conversations:
            db.save_conversation(conv)
        
        # Load from database
        loaded = db.load_conversation(conversations[0].id)
        assert loaded is not None
        
        # Export to JSONL
        exporter = JSONLExporter()
        jsonl_data = exporter.export_data([loaded])
        
        # Verify JSONL
        lines = jsonl_data.strip().split('\n')
        assert len(lines) > 0
        for line in lines:
            json.loads(line)  # Should be valid JSON
        
        db.close()
    
    @pytest.mark.integration
    def test_anthropic_to_markdown_pipeline(self, anthropic_export_data, temp_dir):
        """Test importing from Anthropic and exporting to Markdown"""
        # Import
        importer = AnthropicImporter()
        conversations = importer.import_data(anthropic_export_data)
        
        # Export to Markdown
        exporter = MarkdownExporter()
        markdown = exporter.export_data(conversations, include_metadata=True)
        
        assert "# Claude Conversation" in markdown
        assert "Source: anthropic" in markdown
        assert "Hello Claude" in markdown
    
    @pytest.mark.integration
    def test_round_trip_conversion(self, sample_conversation, temp_dir):
        """Test round-trip conversion (export then import)"""
        # Export to JSONL
        exporter = JSONLExporter()
        jsonl_file = temp_dir / "export.jsonl"
        exporter.export_to_file([sample_conversation], str(jsonl_file))
        
        # Import back
        from ctk.integrations.importers.jsonl import JSONLImporter
        importer = JSONLImporter()
        
        with open(jsonl_file) as f:
            data = f.read()
        
        reimported = importer.import_data(data)
        
        assert len(reimported) == 1
        conv = reimported[0]
        
        # Verify content is preserved
        original_messages = sample_conversation.get_longest_path()
        reimported_messages = conv.get_longest_path()
        
        assert len(original_messages) == len(reimported_messages)
        for orig, reimp in zip(original_messages, reimported_messages):
            assert orig.role == reimp.role
            assert orig.content.text == reimp.content.text


class TestDatabaseIntegration:
    """Test database integration with importers/exporters"""
    
    @pytest.mark.integration
    def test_bulk_import_and_search(self, temp_dir):
        """Test importing multiple conversations and searching"""
        db_path = temp_dir / "test.db"
        db = ConversationDB(str(db_path))
        
        # Create test data
        test_convs = []
        for i in range(10):
            data = {
                "title": f"Conversation about {'Python' if i < 5 else 'JavaScript'}",
                "mapping": {
                    f"msg_{i}": {
                        "id": f"msg_{i}",
                        "message": {
                            "author": {"role": "user"},
                            "content": {
                                "content_type": "text",
                                "parts": [f"Tell me about {'Python' if i < 5 else 'JavaScript'}"]
                            }
                        },
                        "parent": None,
                        "children": []
                    }
                },
                "conversation_id": f"conv_{i:03d}"
            }
            test_convs.append(data)
        
        # Import all
        importer = OpenAIImporter()
        conversations = importer.import_data(test_convs)
        
        # Save to database
        for conv in conversations:
            db.save_conversation(conv)
        
        # Search for Python
        python_results = db.search_conversations("Python")
        assert len(python_results) == 5
        
        # Search for JavaScript
        js_results = db.search_conversations("JavaScript")
        assert len(js_results) == 5
        
        # Get statistics
        stats = db.get_statistics()
        assert stats["total_conversations"] == 10
        
        db.close()
    
    @pytest.mark.integration
    def test_tagging_integration(self, temp_db, sample_conversation):
        """Test tagging integration with database"""
        # Save conversation
        temp_db.save_conversation(sample_conversation)
        
        # Load and tag
        loaded = temp_db.load_conversation(sample_conversation.id)
        tagger = TFIDFTagger()
        tags = tagger.tag_conversation(loaded)
        
        # Update tags
        loaded.metadata.tags = tags
        temp_db.save_conversation(loaded)
        
        # Verify tags are persisted
        reloaded = temp_db.load_conversation(sample_conversation.id)
        assert len(reloaded.metadata.tags) > 0
        assert reloaded.metadata.tags == tags


class TestPluginRegistry:
    """Test plugin registry and auto-discovery"""
    
    @pytest.mark.integration
    def test_plugin_discovery(self):
        """Test that plugins are discovered correctly"""
        registry.discover_plugins()
        
        # Check importers
        importers = registry.list_importers()
        assert "openai" in importers
        assert "anthropic" in importers
        assert "jsonl" in importers
        
        # Check exporters
        exporters = registry.list_exporters()
        assert "jsonl" in exporters
        assert "markdown" in exporters
        assert "local_llm" in exporters
    
    @pytest.mark.integration
    def test_get_plugin_by_name(self):
        """Test getting plugins by name"""
        registry.discover_plugins()
        
        # Get importer
        openai_importer = registry.get_importer("openai")
        assert openai_importer is not None
        assert isinstance(openai_importer, OpenAIImporter)
        
        # Get exporter
        jsonl_exporter = registry.get_exporter("jsonl")
        assert jsonl_exporter is not None
        assert isinstance(jsonl_exporter, JSONLExporter)
    
    @pytest.mark.integration
    def test_auto_detect_format(self, temp_dir):
        """Test auto-detecting file format"""
        registry.discover_plugins()
        
        # Create test files
        openai_file = temp_dir / "openai.json"
        with open(openai_file, 'w') as f:
            json.dump({
                "title": "Test",
                "mapping": {},
                "conversation_id": "test"
            }, f)
        
        jsonl_file = temp_dir / "messages.jsonl"
        with open(jsonl_file, 'w') as f:
            f.write('{"role": "user", "content": "Hello"}\n')
            f.write('{"role": "assistant", "content": "Hi"}\n')
        
        # Test auto-detection
        openai_convs = registry.import_file(str(openai_file))
        assert len(openai_convs) >= 0  # Should not fail
        
        jsonl_convs = registry.import_file(str(jsonl_file))
        assert len(jsonl_convs) == 1
        assert len(jsonl_convs[0].message_map) == 2


class TestCLIIntegration:
    """Test CLI command integration"""
    
    @pytest.mark.integration
    def test_import_command(self, temp_dir, monkeypatch):
        """Test the import CLI command"""
        # Create test file
        test_file = temp_dir / "test.json"
        with open(test_file, 'w') as f:
            json.dump({
                "title": "Test Import",
                "mapping": {
                    "msg1": {
                        "id": "msg1",
                        "message": {
                            "author": {"role": "user"},
                            "content": {"content_type": "text", "parts": ["Test"]}
                        },
                        "parent": None,
                        "children": []
                    }
                },
                "conversation_id": "test_import"
            }, f)
        
        db_path = temp_dir / "test.db"
        
        # Test import command
        from ctk.cli import cmd_import
        
        class Args:
            input = str(test_file)
            format = "openai"
            db = str(db_path)
            output = None
            output_format = None
            tags = "test,import"
            sanitize = False
            path_selection = "longest"
            verbose = False
        
        result = cmd_import(Args())
        assert result == 0
        
        # Verify in database
        db = ConversationDB(str(db_path))
        conv = db.load_conversation("test_import")
        assert conv is not None
        assert conv.title == "Test Import"
        assert "test" in conv.metadata.tags
        assert "import" in conv.metadata.tags
        db.close()
    
    @pytest.mark.integration
    def test_export_command(self, temp_db, sample_conversation):
        """Test the export CLI command"""
        # Save conversation to database
        temp_db.save_conversation(sample_conversation)
        
        # Test export command
        from ctk.cli import cmd_export
        
        output_file = Path(temp_db.db_path).parent / "export.jsonl"
        
        class Args:
            db = temp_db.db_path
            output = str(output_file)
            format = "jsonl"
            ids = None
            limit = 1000
            filter_source = None
            filter_model = None
            filter_tags = None
            sanitize = False
            path_selection = "longest"
            include_metadata = False
        
        result = cmd_export(Args())
        assert result == 0
        
        # Verify output file
        assert output_file.exists()
        with open(output_file) as f:
            lines = f.readlines()
            assert len(lines) > 0
            for line in lines:
                json.loads(line)  # Should be valid JSON