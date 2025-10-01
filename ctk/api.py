"""
Fluent Python API for CTK - A pythonic interface for conversation management
"""

from typing import List, Dict, Any, Optional, Union, Callable, Iterator
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
import json

from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole,
    ConversationMetadata
)
from ctk.core.database import ConversationDB
from ctk.core import registry


class CTK:
    """
    Main entry point for the fluent CTK API.

    Examples:
        # Quick import and export
        CTK.load("export.json").export_as("markdown").save("output.md")

        # Database operations
        ctk = CTK("conversations.db")
        ctk.import_from("chat.json").with_tags("work", "2024").save()

        # Search and filter
        results = ctk.search("python async").limit(10).get()

        # Build new conversation
        conv = (CTK.conversation("Technical Discussion")
                .user("How does async work in Python?")
                .assistant("Python's async/await allows...")
                .user("Can you show an example?")
                .assistant("Here's a simple example...")
                .build())
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize CTK with optional database"""
        self.db_path = db_path
        self._db = None
        self._current_conversations: List[ConversationTree] = []

    @property
    def db(self) -> Optional[ConversationDB]:
        """Lazy-load database connection"""
        if self.db_path and not self._db:
            self._db = ConversationDB(self.db_path)
        return self._db

    @classmethod
    def load(cls, source: Union[str, Path, Dict, List]) -> 'ConversationLoader':
        """Load conversations from a file or data structure"""
        return ConversationLoader(source)

    @classmethod
    def conversation(cls, title: Optional[str] = None) -> 'ConversationBuilder':
        """Start building a new conversation"""
        return ConversationBuilder(title)

    def import_from(self, source: Union[str, Path]) -> 'ImportBuilder':
        """Import conversations into the database"""
        return ImportBuilder(self, source)

    def search(self, query: str) -> 'SearchBuilder':
        """Search conversations in the database"""
        return SearchBuilder(self, query)

    def conversations(self) -> 'QueryBuilder':
        """Query all conversations"""
        return QueryBuilder(self)

    def get(self, conversation_id: str) -> Optional[ConversationTree]:
        """Get a specific conversation by ID"""
        if self.db:
            with self.db as db:
                return db.load_conversation(conversation_id)
        return None

    def delete(self, conversation_id: str) -> 'CTK':
        """Delete a conversation"""
        if self.db:
            with self.db as db:
                db.delete_conversation(conversation_id)
        return self

    def stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        if self.db:
            with self.db as db:
                return db.get_statistics()
        return {}

    @contextmanager
    def batch(self):
        """Context manager for batch operations"""
        # Collect operations
        yield self
        # Execute all at once
        if self._current_conversations and self.db:
            with self.db as db:
                for conv in self._current_conversations:
                    db.save_conversation(conv)
            self._current_conversations.clear()


class ConversationBuilder:
    """
    Fluent builder for creating conversations.

    Example:
        conv = (ConversationBuilder("My Chat")
                .system("You are a helpful assistant")
                .user("Hello!")
                .assistant("Hi there! How can I help?")
                .with_metadata(model="gpt-4", source="manual")
                .build())
    """

    def __init__(self, title: Optional[str] = None):
        self.tree = ConversationTree(title=title)
        self._current_parent_id: Optional[str] = None
        self._last_message_id: Optional[str] = None

    def system(self, text: str, **kwargs) -> 'ConversationBuilder':
        """Add a system message"""
        return self._add_message(MessageRole.SYSTEM, text, **kwargs)

    def user(self, text: str, **kwargs) -> 'ConversationBuilder':
        """Add a user message"""
        return self._add_message(MessageRole.USER, text, **kwargs)

    def assistant(self, text: str, **kwargs) -> 'ConversationBuilder':
        """Add an assistant message"""
        return self._add_message(MessageRole.ASSISTANT, text, **kwargs)

    def message(self, role: Union[str, MessageRole], text: str, **kwargs) -> 'ConversationBuilder':
        """Add a message with explicit role"""
        if isinstance(role, str):
            role = MessageRole.from_string(role)
        return self._add_message(role, text, **kwargs)

    def branch(self) -> 'ConversationBuilder':
        """Start a new branch from the last message"""
        self._current_parent_id = self._last_message_id
        return self

    def from_parent(self, parent_id: str) -> 'ConversationBuilder':
        """Continue from a specific parent message"""
        self._current_parent_id = parent_id
        return self

    def with_metadata(self, **kwargs) -> 'ConversationBuilder':
        """Set conversation metadata"""
        for key, value in kwargs.items():
            if hasattr(self.tree.metadata, key):
                setattr(self.tree.metadata, key, value)
            else:
                self.tree.metadata.custom_data[key] = value
        return self

    def with_tags(self, *tags: str) -> 'ConversationBuilder':
        """Add tags to the conversation"""
        self.tree.metadata.tags.extend(tags)
        return self

    def _add_message(self, role: MessageRole, text: str, **kwargs) -> 'ConversationBuilder':
        """Internal method to add a message"""
        content = MessageContent(text=text)

        # Handle additional content types
        if 'images' in kwargs:
            for img in kwargs['images']:
                content.add_image(**img if isinstance(img, dict) else {'url': img})

        if 'tools' in kwargs:
            for tool in kwargs['tools']:
                content.add_tool_call(**tool if isinstance(tool, dict) else {'name': tool})

        msg = Message(
            role=role,
            content=content,
            parent_id=self._current_parent_id,
            metadata=kwargs.get('metadata', {})
        )

        self.tree.add_message(msg)
        self._last_message_id = msg.id

        # Update parent for next message (linear by default)
        self._current_parent_id = msg.id

        return self

    def build(self) -> ConversationTree:
        """Build and return the conversation tree"""
        return self.tree


class ConversationLoader:
    """
    Loader for conversations from various sources.

    Example:
        CTK.load("export.json")
           .filter(lambda c: "python" in c.title.lower())
           .transform(lambda c: add_tags(c, "technical"))
           .export_as("markdown")
           .save("technical_chats.md")
    """

    def __init__(self, source: Union[str, Path, Dict, List]):
        self.source = source
        self.conversations: List[ConversationTree] = []
        self.format: Optional[str] = None
        self._load()

    def _load(self):
        """Load conversations from source"""
        if isinstance(self.source, (str, Path)):
            # File path
            self.conversations = registry.import_file(str(self.source), format=self.format)
        elif isinstance(self.source, list):
            # List of conversation trees or dicts
            if all(isinstance(c, ConversationTree) for c in self.source):
                self.conversations = self.source
            else:
                # Try to import as data
                importer = registry.get_importer(self.format or "json")
                if importer:
                    self.conversations = importer.import_data(self.source)
        elif isinstance(self.source, dict):
            # Single conversation or wrapped data
            importer = registry.get_importer(self.format or "json")
            if importer:
                self.conversations = importer.import_data(self.source)

    def with_format(self, format: str) -> 'ConversationLoader':
        """Specify the format for loading"""
        self.format = format
        self._load()  # Reload with format
        return self

    def filter(self, predicate: Callable[[ConversationTree], bool]) -> 'ConversationLoader':
        """Filter conversations"""
        self.conversations = [c for c in self.conversations if predicate(c)]
        return self

    def transform(self, transformer: Callable[[ConversationTree], ConversationTree]) -> 'ConversationLoader':
        """Transform each conversation"""
        self.conversations = [transformer(c) for c in self.conversations]
        return self

    def add_tags(self, *tags: str) -> 'ConversationLoader':
        """Add tags to all conversations"""
        for conv in self.conversations:
            conv.metadata.tags.extend(tags)
        return self

    def export_as(self, format: str) -> 'ExportBuilder':
        """Export conversations to a specific format"""
        return ExportBuilder(self.conversations, format)

    def save_to_db(self, db_path: str) -> 'ConversationLoader':
        """Save conversations to a database"""
        with ConversationDB(db_path) as db:
            for conv in self.conversations:
                db.save_conversation(conv)
        return self

    def get(self) -> List[ConversationTree]:
        """Get the loaded conversations"""
        return self.conversations

    def first(self) -> Optional[ConversationTree]:
        """Get the first conversation"""
        return self.conversations[0] if self.conversations else None

    def __iter__(self) -> Iterator[ConversationTree]:
        """Make loader iterable"""
        return iter(self.conversations)

    def __len__(self) -> int:
        """Get number of conversations"""
        return len(self.conversations)


class ExportBuilder:
    """
    Builder for exporting conversations.

    Example:
        ExportBuilder(conversations, "markdown")
            .with_paths("longest")
            .include_metadata()
            .include_timestamps()
            .save("output.md")
    """

    def __init__(self, conversations: List[ConversationTree], format: str):
        self.conversations = conversations
        self.format = format
        self.options: Dict[str, Any] = {}

    def with_paths(self, selection: str = "longest") -> 'ExportBuilder':
        """Set path selection strategy (longest, first, last, all)"""
        self.options['path_selection'] = selection
        return self

    def include_metadata(self, include: bool = True) -> 'ExportBuilder':
        """Include conversation metadata"""
        self.options['include_metadata'] = include
        return self

    def include_timestamps(self, include: bool = True) -> 'ExportBuilder':
        """Include message timestamps"""
        self.options['include_timestamps'] = include
        return self

    def include_tree_structure(self, include: bool = True) -> 'ExportBuilder':
        """Include tree structure visualization (markdown only)"""
        self.options['include_tree_structure'] = include
        return self

    def pretty_print(self, pretty: bool = True) -> 'ExportBuilder':
        """Pretty print output (JSON only)"""
        self.options['pretty_print'] = pretty
        return self

    def format_style(self, style: str) -> 'ExportBuilder':
        """Set format style (JSON only: ctk, openai, anthropic, generic)"""
        self.options['format_style'] = style
        return self

    def save(self, output_path: Union[str, Path]) -> str:
        """Save to file and return the exported content"""
        exporter = registry.get_exporter(self.format)
        if not exporter:
            raise ValueError(f"No exporter found for format: {self.format}")

        # Use export_data method (standard for all exporters)
        content = exporter.export_data(
            self.conversations,
            output_file=str(output_path),
            **self.options
        )
        return content

    def to_string(self) -> str:
        """Export to string without saving"""
        exporter = registry.get_exporter(self.format)
        if not exporter:
            raise ValueError(f"No exporter found for format: {self.format}")

        # Use export_data method (standard for all exporters)
        return exporter.export_data(
            self.conversations,
            output_file=None,
            **self.options
        )


class ImportBuilder:
    """
    Builder for importing conversations into a database.

    Example:
        ctk.import_from("chat.json")
           .with_format("openai")
           .with_tags("work", "2024")
           .with_project("CustomerSupport")
           .save()
    """

    def __init__(self, ctk_instance: CTK, source: Union[str, Path]):
        self.ctk = ctk_instance
        self.source = source
        self.format: Optional[str] = None
        self.tags: List[str] = []
        self.metadata: Dict[str, Any] = {}

    def with_format(self, format: str) -> 'ImportBuilder':
        """Specify import format"""
        self.format = format
        return self

    def with_tags(self, *tags: str) -> 'ImportBuilder':
        """Add tags to imported conversations"""
        self.tags.extend(tags)
        return self

    def with_project(self, project: str) -> 'ImportBuilder':
        """Set project for imported conversations"""
        self.metadata['project'] = project
        return self

    def with_metadata(self, **kwargs) -> 'ImportBuilder':
        """Add metadata to imported conversations"""
        self.metadata.update(kwargs)
        return self

    def save(self) -> List[ConversationTree]:
        """Execute the import"""
        # Load conversations
        conversations = registry.import_file(str(self.source), format=self.format)

        # Apply tags and metadata
        for conv in conversations:
            conv.metadata.tags.extend(self.tags)
            if 'project' in self.metadata:
                conv.metadata.project = self.metadata['project']
            for key, value in self.metadata.items():
                if key != 'project' and hasattr(conv.metadata, key):
                    setattr(conv.metadata, key, value)

        # Save to database
        if self.ctk.db:
            with self.ctk.db as db:
                for conv in conversations:
                    db.save_conversation(conv)

        return conversations


class SearchBuilder:
    """
    Builder for searching conversations.

    Example:
        results = ctk.search("python async")
                    .in_source("ChatGPT")
                    .with_model("gpt-4")
                    .limit(20)
                    .get()
    """

    def __init__(self, ctk_instance: CTK, query: str):
        self.ctk = ctk_instance
        self.query = query
        self._limit = 100
        self.filters: Dict[str, Any] = {}

    def limit(self, n: int) -> 'SearchBuilder':
        """Limit number of results"""
        self._limit = n
        return self

    def in_source(self, source: str) -> 'SearchBuilder':
        """Filter by source"""
        self.filters['source'] = source
        return self

    def with_model(self, model: str) -> 'SearchBuilder':
        """Filter by model"""
        self.filters['model'] = model
        return self

    def in_project(self, project: str) -> 'SearchBuilder':
        """Filter by project"""
        self.filters['project'] = project
        return self

    def with_tags(self, *tags: str) -> 'SearchBuilder':
        """Filter by tags"""
        self.filters['tags'] = tags
        return self

    def get(self) -> List[ConversationTree]:
        """Execute the search"""
        if not self.ctk.db:
            return []

        with self.ctk.db as db:
            # Basic search
            results = db.search_conversations(self.query, limit=self._limit)

            # Apply filters
            if self.filters:
                filtered = []
                for conv in results:
                    if 'source' in self.filters and conv.metadata.source != self.filters['source']:
                        continue
                    if 'model' in self.filters and conv.metadata.model != self.filters['model']:
                        continue
                    if 'project' in self.filters and conv.metadata.project != self.filters['project']:
                        continue
                    if 'tags' in self.filters:
                        required_tags = set(self.filters['tags'])
                        if not required_tags.issubset(set(conv.metadata.tags)):
                            continue
                    filtered.append(conv)
                results = filtered

            return results

    def first(self) -> Optional[ConversationTree]:
        """Get first search result"""
        results = self.get()
        return results[0] if results else None

    def export_as(self, format: str) -> ExportBuilder:
        """Export search results"""
        results = self.get()
        return ExportBuilder(results, format)


class QueryBuilder:
    """
    Builder for querying conversations.

    Example:
        recent_gpt4 = ctk.conversations()
                        .where(source="ChatGPT")
                        .where(model="gpt-4")
                        .order_by("updated_at", desc=True)
                        .limit(50)
                        .get()
    """

    def __init__(self, ctk_instance: CTK):
        self.ctk = ctk_instance
        self.filters: Dict[str, Any] = {}
        self._limit: Optional[int] = None
        self._offset: int = 0
        self._order_by: Optional[str] = None
        self._desc: bool = True

    def where(self, **kwargs) -> 'QueryBuilder':
        """Add filter conditions"""
        self.filters.update(kwargs)
        return self

    def limit(self, n: int) -> 'QueryBuilder':
        """Limit results"""
        self._limit = n
        return self

    def offset(self, n: int) -> 'QueryBuilder':
        """Set offset for pagination"""
        self._offset = n
        return self

    def order_by(self, field: str, desc: bool = False) -> 'QueryBuilder':
        """Order results"""
        self._order_by = field
        self._desc = desc
        return self

    def get(self) -> List[ConversationTree]:
        """Execute the query"""
        if not self.ctk.db:
            return []

        # Import the models we need
        from ctk.core.db_models import ConversationModel

        results = []
        with self.ctk.db.session_scope() as session:
            query = session.query(ConversationModel)

            # Apply filters
            for key, value in self.filters.items():
                if hasattr(ConversationModel, key):
                    query = query.filter(getattr(ConversationModel, key) == value)

            # Apply ordering
            if self._order_by and hasattr(ConversationModel, self._order_by):
                order_field = getattr(ConversationModel, self._order_by)
                query = query.order_by(order_field.desc() if self._desc else order_field)

            # Apply pagination
            if self._limit:
                query = query.limit(self._limit)
            if self._offset:
                query = query.offset(self._offset)

            # Convert to ConversationTree objects
            for conv_model in query.all():
                # We need to reload using the ID to get full tree structure
                conv_tree = self.ctk.db.load_conversation(conv_model.id)
                if conv_tree:
                    results.append(conv_tree)

        return results

    def count(self) -> int:
        """Count matching conversations"""
        if not self.ctk.db:
            return 0

        from ctk.core.db_models import ConversationModel

        with self.ctk.db.session_scope() as session:
            query = session.query(ConversationModel)

            for key, value in self.filters.items():
                if hasattr(ConversationModel, key):
                    query = query.filter(getattr(ConversationModel, key) == value)

            return query.count()

    def delete_all(self) -> int:
        """Delete all matching conversations"""
        conversations = self.get()
        count = 0

        if self.ctk.db:
            with self.ctk.db as db:
                for conv in conversations:
                    db.delete_conversation(conv.id)
                    count += 1

        return count

    def export_as(self, format: str) -> ExportBuilder:
        """Export query results"""
        results = self.get()
        return ExportBuilder(results, format)


# Convenience functions for one-liners

def load(source: Union[str, Path, Dict, List]) -> ConversationLoader:
    """Quick load conversations"""
    return CTK.load(source)

def conversation(title: Optional[str] = None) -> ConversationBuilder:
    """Quick conversation builder"""
    return CTK.conversation(title)

def from_db(db_path: str) -> CTK:
    """Quick database access"""
    return CTK(db_path)