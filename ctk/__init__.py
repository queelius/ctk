"""
Conversation Toolkit - A robust system for managing tree-based conversations
"""

__version__ = "2.0.0"
__author__ = "CTK Contributors"

from .core.models import (
    Message,
    MessageRole,
    MessageContent,
    ConversationTree,
    ConversationMetadata,
    MediaContent,
    ToolCall,
    ContentType,
)
from .core.database import ConversationDB
from .core.plugin import PluginRegistry

__all__ = [
    'Message',
    'MessageRole',
    'MessageContent',
    'ConversationTree',
    'ConversationMetadata',
    'MediaContent',
    'ToolCall',
    'ContentType',
    'ConversationDB',
    'PluginRegistry',
]