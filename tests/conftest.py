"""
Pytest configuration and shared fixtures
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List

import pytest

from ctk.core.database import ConversationDB
from ctk.core.models import (ConversationMetadata, ConversationTree, Message,
                             MessageContent, MessageRole)


@pytest.fixture
def temp_dir():
    """Create a temporary directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_db(temp_dir):
    """Create a temporary database"""
    db_path = temp_dir / "test.db"
    db = ConversationDB(str(db_path))
    yield db
    db.close()


@pytest.fixture
def sample_message():
    """Create a sample message"""
    return Message(
        id="msg_001",
        role=MessageRole.USER,
        content=MessageContent(text="Hello, how are you?"),
        timestamp=datetime.now(),
        parent_id=None,
    )


@pytest.fixture
def sample_conversation():
    """Create a sample conversation tree"""
    conv = ConversationTree(
        id="conv_001",
        title="Test Conversation",
        metadata=ConversationMetadata(
            source="test", model="test-model", tags=["test", "sample"]
        ),
    )

    # Add messages
    msg1 = Message(
        id="msg_001",
        role=MessageRole.USER,
        content=MessageContent(text="Hello"),
        parent_id=None,
    )
    conv.add_message(msg1)

    msg2 = Message(
        id="msg_002",
        role=MessageRole.ASSISTANT,
        content=MessageContent(text="Hi there!"),
        parent_id="msg_001",
    )
    conv.add_message(msg2)

    msg3 = Message(
        id="msg_003",
        role=MessageRole.USER,
        content=MessageContent(text="How are you?"),
        parent_id="msg_002",
    )
    conv.add_message(msg3)

    msg4 = Message(
        id="msg_004",
        role=MessageRole.ASSISTANT,
        content=MessageContent(text="I'm doing great, thanks!"),
        parent_id="msg_003",
    )
    conv.add_message(msg4)

    return conv


@pytest.fixture
def branching_conversation():
    """Create a conversation with branches (regenerated responses)"""
    conv = ConversationTree(
        id="conv_branch",
        title="Branching Conversation",
        metadata=ConversationMetadata(source="test"),
    )

    # Initial exchange
    msg1 = Message(
        id="msg_001",
        role=MessageRole.USER,
        content=MessageContent(text="What's 2+2?"),
        parent_id=None,
    )
    conv.add_message(msg1)

    # First response
    msg2a = Message(
        id="msg_002a",
        role=MessageRole.ASSISTANT,
        content=MessageContent(text="2+2 equals 4"),
        parent_id="msg_001",
    )
    conv.add_message(msg2a)

    # Alternative response (regenerated)
    msg2b = Message(
        id="msg_002b",
        role=MessageRole.ASSISTANT,
        content=MessageContent(text="The answer is 4"),
        parent_id="msg_001",
    )
    conv.add_message(msg2b)

    # Continue from first branch
    msg3 = Message(
        id="msg_003",
        role=MessageRole.USER,
        content=MessageContent(text="What about 3+3?"),
        parent_id="msg_002a",
    )
    conv.add_message(msg3)

    msg4 = Message(
        id="msg_004",
        role=MessageRole.ASSISTANT,
        content=MessageContent(text="3+3 equals 6"),
        parent_id="msg_003",
    )
    conv.add_message(msg4)

    return conv


@pytest.fixture
def openai_export_data():
    """Sample OpenAI export data"""
    return {
        "title": "ChatGPT Conversation",
        "create_time": 1700000000.0,
        "update_time": 1700001000.0,
        "mapping": {
            "msg_001": {
                "id": "msg_001",
                "message": {
                    "id": "msg_001",
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Hello ChatGPT"]},
                    "create_time": 1700000000.0,
                },
                "parent": None,
                "children": ["msg_002"],
            },
            "msg_002": {
                "id": "msg_002",
                "message": {
                    "id": "msg_002",
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "text",
                        "parts": ["Hello! How can I help you today?"],
                    },
                    "create_time": 1700000100.0,
                    "metadata": {"model_slug": "gpt-4"},
                },
                "parent": "msg_001",
                "children": [],
            },
        },
        "conversation_id": "conv_openai_001",
    }


@pytest.fixture
def anthropic_export_data():
    """Sample Anthropic export data"""
    return {
        "uuid": "conv_anthropic_001",
        "name": "Claude Conversation",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T01:00:00Z",
        "model": "claude-3-opus-20240229",
        "chat_messages": [
            {
                "uuid": "msg_001",
                "text": "Hello Claude",
                "sender": "human",
                "created_at": "2024-01-01T00:00:00Z",
            },
            {
                "uuid": "msg_002",
                "text": "Hello! I'm Claude, an AI assistant. How can I help you today?",
                "sender": "assistant",
                "created_at": "2024-01-01T00:00:10Z",
            },
        ],
    }


@pytest.fixture
def mock_config(temp_dir):
    """Create a mock configuration"""
    config_path = temp_dir / "config.json"
    config_data = {
        "providers": {
            "ollama": {"base_url": "http://localhost:11434", "default_model": "llama2"},
            "openai": {
                "base_url": "https://api.openai.com",
                "default_model": "gpt-3.5-turbo",
            },
        },
        "tagging": {"default_provider": "tfidf", "max_tags": 10},
    }
    with open(config_path, "w") as f:
        json.dump(config_data, f)
    return config_path
