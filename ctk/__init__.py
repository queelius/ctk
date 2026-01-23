"""
Conversation Toolkit - A robust system for managing tree-based conversations
"""

__version__ = "2.6.0"
__author__ = "Alex Towell"

# Fluent API
from .api import (CTK, ConversationBuilder, ConversationLoader, ExportBuilder,
                  ImportBuilder, QueryBuilder, SearchBuilder, conversation,
                  from_db, load)
from .core.database import ConversationDB
from .core.models import (ContentType, ConversationMetadata, ConversationTree,
                          MediaContent, Message, MessageContent, MessageRole,
                          ToolCall)
from .core.plugin import PluginRegistry

__all__ = [
    # Core models
    "Message",
    "MessageRole",
    "MessageContent",
    "ConversationTree",
    "ConversationMetadata",
    "MediaContent",
    "ToolCall",
    "ContentType",
    "ConversationDB",
    "PluginRegistry",
    # Fluent API
    "CTK",
    "ConversationBuilder",
    "ConversationLoader",
    "ExportBuilder",
    "ImportBuilder",
    "SearchBuilder",
    "QueryBuilder",
    "conversation",
    "load",
    "from_db",
]
