"""
Conversation Toolkit - A robust system for managing tree-based conversations
"""

__version__ = "2.5.0"
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

# Fluent API
from .api import (
    CTK,
    ConversationBuilder,
    ConversationLoader,
    ExportBuilder,
    ImportBuilder,
    SearchBuilder,
    QueryBuilder,
    conversation,
    load,
    from_db,
)

__all__ = [
    # Core models
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
    # Fluent API
    'CTK',
    'ConversationBuilder',
    'ConversationLoader',
    'ExportBuilder',
    'ImportBuilder',
    'SearchBuilder',
    'QueryBuilder',
    'conversation',
    'load',
    'from_db',
]