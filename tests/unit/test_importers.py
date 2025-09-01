"""
Unit tests for importers
"""

import pytest
import json
from datetime import datetime

from ctk.integrations.importers.openai import OpenAIImporter
from ctk.integrations.importers.anthropic import AnthropicImporter
from ctk.integrations.importers.jsonl import JSONLImporter
from ctk.core.models import MessageRole


class TestOpenAIImporter:
    """Test OpenAI/ChatGPT importer"""
    
    @pytest.mark.unit
    def test_import_single_conversation(self, openai_export_data):
        """Test importing a single OpenAI conversation"""
        importer = OpenAIImporter()
        conversations = importer.import_data(openai_export_data)
        
        assert len(conversations) == 1
        conv = conversations[0]
        
        assert conv.id == "conv_openai_001"
        assert conv.title == "ChatGPT Conversation"
        assert conv.metadata.source == "openai"
        assert conv.metadata.model == "gpt-4"
        
        # Check messages
        messages = conv.get_longest_path()
        assert len(messages) == 2
        assert messages[0].role == MessageRole.USER
        assert messages[0].content.text == "Hello ChatGPT"
        assert messages[1].role == MessageRole.ASSISTANT
        assert messages[1].content.text == "Hello! How can I help you today?"
    
    @pytest.mark.unit
    def test_import_with_branches(self):
        """Test importing conversation with regenerated responses"""
        data = {
            "title": "Branching Chat",
            "mapping": {
                "msg_1": {
                    "id": "msg_1",
                    "message": {
                        "author": {"role": "user"},
                        "content": {
                            "content_type": "text",
                            "parts": ["Question"]
                        }
                    },
                    "parent": None,
                    "children": ["msg_2a", "msg_2b"]
                },
                "msg_2a": {
                    "id": "msg_2a",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "text",
                            "parts": ["Answer A"]
                        }
                    },
                    "parent": "msg_1",
                    "children": []
                },
                "msg_2b": {
                    "id": "msg_2b",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "text",
                            "parts": ["Answer B"]
                        }
                    },
                    "parent": "msg_1",
                    "children": []
                }
            },
            "conversation_id": "conv_branch"
        }
        
        importer = OpenAIImporter()
        conversations = importer.import_data(data)
        
        assert len(conversations) == 1
        conv = conversations[0]
        
        # Check that both branches exist
        assert len(conv.message_map) == 3
        children = conv.get_children("msg_1")
        assert len(children) == 2
        
        # Check all paths
        paths = conv.get_all_paths()
        assert len(paths) == 2
    
    @pytest.mark.unit
    def test_import_multiple_conversations(self):
        """Test importing multiple conversations from array"""
        data = [
            {
                "title": "Chat 1",
                "mapping": {
                    "msg_1": {
                        "id": "msg_1",
                        "message": {
                            "author": {"role": "user"},
                            "content": {"content_type": "text", "parts": ["Hello"]}
                        },
                        "parent": None,
                        "children": []
                    }
                },
                "conversation_id": "conv_1"
            },
            {
                "title": "Chat 2",
                "mapping": {
                    "msg_2": {
                        "id": "msg_2",
                        "message": {
                            "author": {"role": "user"},
                            "content": {"content_type": "text", "parts": ["Hi"]}
                        },
                        "parent": None,
                        "children": []
                    }
                },
                "conversation_id": "conv_2"
            }
        ]
        
        importer = OpenAIImporter()
        conversations = importer.import_data(data)
        
        assert len(conversations) == 2
        assert conversations[0].id == "conv_1"
        assert conversations[1].id == "conv_2"
    
    @pytest.mark.unit
    def test_handle_missing_fields(self):
        """Test handling conversations with missing fields"""
        data = {
            "mapping": {
                "msg_1": {
                    "id": "msg_1",
                    "message": {
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["Test"]}
                    },
                    "parent": None,
                    "children": []
                }
            }
            # Missing title and conversation_id
        }
        
        importer = OpenAIImporter()
        conversations = importer.import_data(data)
        
        assert len(conversations) == 1
        conv = conversations[0]
        assert conv.title == "Untitled Conversation"
        assert conv.id is not None  # Should generate an ID
    
    @pytest.mark.unit
    def test_multipart_messages(self):
        """Test handling messages with multiple parts"""
        data = {
            "title": "Multipart",
            "mapping": {
                "msg_1": {
                    "id": "msg_1",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {
                            "content_type": "text",
                            "parts": ["Part 1", "Part 2", "Part 3"]
                        }
                    },
                    "parent": None,
                    "children": []
                }
            },
            "conversation_id": "conv_multi"
        }
        
        importer = OpenAIImporter()
        conversations = importer.import_data(data)
        
        conv = conversations[0]
        messages = conv.get_longest_path()
        # Parts should be joined
        assert "Part 1" in messages[0].content.text
        assert "Part 2" in messages[0].content.text
        assert "Part 3" in messages[0].content.text


class TestAnthropicImporter:
    """Test Anthropic/Claude importer"""
    
    @pytest.mark.unit
    def test_import_single_conversation(self, anthropic_export_data):
        """Test importing a single Anthropic conversation"""
        importer = AnthropicImporter()
        conversations = importer.import_data(anthropic_export_data)
        
        assert len(conversations) == 1
        conv = conversations[0]
        
        assert conv.id == "conv_anthropic_001"
        assert conv.title == "Claude Conversation"
        assert conv.metadata.source == "anthropic"
        assert conv.metadata.model == "claude-3-opus"
        
        # Check messages
        messages = conv.get_longest_path()
        assert len(messages) == 2
        assert messages[0].role == MessageRole.USER
        assert messages[0].content.text == "Hello Claude"
        assert messages[1].role == MessageRole.ASSISTANT
        assert "Claude" in messages[1].content.text
    
    @pytest.mark.unit
    def test_import_multiple_conversations(self):
        """Test importing multiple Anthropic conversations"""
        data = [
            {
                "uuid": "conv_1",
                "name": "Chat 1",
                "chat_messages": [
                    {
                        "uuid": "msg_1",
                        "text": "Question",
                        "sender": "human"
                    }
                ]
            },
            {
                "uuid": "conv_2",
                "name": "Chat 2",
                "chat_messages": [
                    {
                        "uuid": "msg_2",
                        "text": "Another question",
                        "sender": "human"
                    }
                ]
            }
        ]
        
        importer = AnthropicImporter()
        conversations = importer.import_data(data)
        
        assert len(conversations) == 2
        assert conversations[0].id == "conv_1"
        assert conversations[1].id == "conv_2"
    
    @pytest.mark.unit
    def test_handle_attachments(self):
        """Test handling messages with attachments"""
        data = {
            "uuid": "conv_attach",
            "name": "Attachment Test",
            "chat_messages": [
                {
                    "uuid": "msg_1",
                    "text": "Look at this image",
                    "sender": "human",
                    "attachments": [
                        {"file_name": "image.png"},
                        {"file_name": "document.pdf"}
                    ]
                }
            ]
        }
        
        importer = AnthropicImporter()
        conversations = importer.import_data(data)
        
        conv = conversations[0]
        msg = conv.get_longest_path()[0]
        
        # Attachment info should be in text
        assert "Attachments:" in msg.content.text
        assert "image.png" in msg.content.text
        assert "document.pdf" in msg.content.text


class TestJSONLImporter:
    """Test JSONL importer"""
    
    @pytest.mark.unit
    def test_import_jsonl_string(self):
        """Test importing from JSONL string"""
        jsonl_data = """{"role": "user", "content": "Hello"}
{"role": "assistant", "content": "Hi there!"}
{"role": "user", "content": "How are you?"}
{"role": "assistant", "content": "I'm doing well!"}"""
        
        importer = JSONLImporter()
        conversations = importer.import_data(jsonl_data)
        
        assert len(conversations) == 1
        conv = conversations[0]
        
        messages = conv.get_longest_path()
        assert len(messages) == 4
        assert messages[0].role == MessageRole.USER
        assert messages[0].content.text == "Hello"
        assert messages[3].content.text == "I'm doing well!"
    
    @pytest.mark.unit
    def test_import_jsonl_list(self):
        """Test importing from list of dicts"""
        data = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "What's 2+2?"},
            {"role": "assistant", "content": "4"}
        ]
        
        importer = JSONLImporter()
        conversations = importer.import_data(data)
        
        assert len(conversations) == 1
        conv = conversations[0]
        
        messages = conv.get_longest_path()
        assert len(messages) == 3
        assert messages[0].role == MessageRole.SYSTEM
        assert messages[1].content.text == "What's 2+2?"
        assert messages[2].content.text == "4"
    
    @pytest.mark.unit
    def test_conversation_breaks(self):
        """Test handling conversation breaks in JSONL"""
        jsonl_data = """{"role": "user", "content": "First conversation"}
{"role": "assistant", "content": "Response 1"}
{"conversation_break": true}
{"role": "user", "content": "Second conversation"}
{"role": "assistant", "content": "Response 2"}"""
        
        importer = JSONLImporter()
        conversations = importer.import_data(jsonl_data)
        
        # Should create two separate conversations
        assert len(conversations) == 2
        
        # First conversation
        messages1 = conversations[0].get_longest_path()
        assert len(messages1) == 2
        assert messages1[0].content.text == "First conversation"
        
        # Second conversation
        messages2 = conversations[1].get_longest_path()
        assert len(messages2) == 2
        assert messages2[0].content.text == "Second conversation"
    
    @pytest.mark.unit
    def test_metadata_in_jsonl(self):
        """Test handling metadata in JSONL"""
        jsonl_data = """{"metadata": {"title": "Test Chat", "model": "gpt-4"}}
{"role": "user", "content": "Hello"}
{"role": "assistant", "content": "Hi!"}"""
        
        importer = JSONLImporter()
        conversations = importer.import_data(jsonl_data)
        
        conv = conversations[0]
        assert conv.title == "Test Chat"
        assert conv.metadata.model == "gpt-4"
        
        # Metadata line shouldn't be a message
        messages = conv.get_longest_path()
        assert len(messages) == 2