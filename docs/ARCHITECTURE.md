# CTK Architecture

## Overview

CTK (Conversation Toolkit) is designed with a modular, plugin-based architecture that allows for multiple interfaces and extensible import/export capabilities. At its core, CTK treats all conversations as tree structures, providing a unified model that can represent both linear and branching conversations.

## Core Principles

1. **Tree-First Design**: All conversations are trees. Linear conversations are simply trees with a single path.
2. **Plugin Architecture**: Import/export formats are discovered and loaded dynamically.
3. **Multiple Interfaces**: The same core functionality is exposed through CLI, REST API, MCP, and other interfaces.
4. **Provider Agnostic**: Unified data model works across all AI providers (OpenAI, Anthropic, etc.).

## Directory Structure

```
ctk/
├── core/                   # Core data models and database
│   ├── models.py          # Tree-based conversation model
│   ├── database.py        # SQLAlchemy database layer
│   ├── db_models.py       # Database schema
│   ├── plugin.py          # Plugin system
│   └── config.py          # Configuration management
│
├── integrations/          # Import/Export plugins
│   ├── importers/         # Provider-specific importers
│   │   ├── openai.py
│   │   ├── anthropic.py
│   │   └── ...
│   └── exporters/         # Format-specific exporters
│       ├── jsonl.py
│       ├── markdown.py
│       └── json.py
│
├── interfaces/            # Multiple interface implementations
│   ├── base.py           # Base interface class
│   ├── rest/             # RESTful API
│   │   └── api.py
│   ├── mcp/              # Model Context Protocol
│   ├── web/              # Web frontend
│   └── cli_v2/           # Enhanced CLI
│
└── cli.py                # Main CLI entry point
```

## Data Model

### ConversationTree

The central data structure that represents all conversations:

```python
@dataclass
class ConversationTree:
    id: str                              # Unique identifier
    title: Optional[str]                 # Conversation title
    metadata: ConversationMetadata       # Source, model, tags, etc.
    message_map: Dict[str, Message]      # All messages by ID
    root_message_ids: List[str]          # Entry points to the tree
```

### Message

Individual messages in the tree:

```python
@dataclass
class Message:
    id: str                              # Unique identifier
    role: MessageRole                    # User, assistant, system, etc.
    content: MessageContent              # Text, media, tool calls
    timestamp: Optional[datetime]
    parent_id: Optional[str]            # Tree structure
    metadata: Dict[str, Any]
```

### Tree Structure

Messages form a directed acyclic graph (DAG):
- Each message can have one parent (except roots)
- Each message can have multiple children (branching)
- Paths through the tree represent conversation flows

## Database Schema

SQLAlchemy-based schema with proper relationships:

1. **conversations** - Metadata and root information
2. **messages** - All messages with parent-child relationships
3. **tags** - Categorization system
4. **paths** - Cached conversation paths for performance

## Plugin System

### Auto-Discovery

Plugins are automatically discovered when placed in the appropriate directory:

```python
class ImporterPlugin(ABC):
    name: str
    description: str

    @abstractmethod
    def validate(self, data) -> bool:
        """Check if this importer can handle the data"""

    @abstractmethod
    def import_data(self, data) -> List[ConversationTree]:
        """Import and return conversation trees"""
```

### Registry

The plugin registry maintains all available importers/exporters:

```python
registry.import_file("data.json")  # Auto-detects format
registry.get_exporter("markdown")  # Get specific exporter
```

## Interfaces

### Fluent Python API

Pythonic, chainable API for programmatic use:

```python
from ctk import CTK, conversation, load

# Quick operations
CTK.load("chat.json").export_as("markdown").save("chat.md")

# Build conversations
conv = (conversation("Python Help")
    .user("How does async work?")
    .assistant("Async allows concurrent execution...")
    .with_tags("python", "async")
    .build())

# Database operations
ctk = CTK("conversations.db")
results = ctk.search("machine learning")
    .in_source("ChatGPT")
    .with_model("gpt-4")
    .limit(20)
    .get()

# Complex pipelines
load("all_chats.json")
    .filter(lambda c: "python" in c.title.lower())
    .add_tags("technical")
    .export_as("jsonl")
    .save("training.jsonl")
```

### Base Interface

All interfaces implement a common base class:

```python
class BaseInterface(ABC):
    @abstractmethod
    def import_conversations(...)

    @abstractmethod
    def export_conversations(...)

    @abstractmethod
    def search_conversations(...)

    @abstractmethod
    def list_conversations(...)
```

### REST API

Flask-based REST API for web integration:

```
GET    /api/conversations        # List all
GET    /api/conversations/<id>   # Get specific
POST   /api/conversations/search # Search
POST   /api/import              # Import data
POST   /api/export              # Export data
```

### CLI

Command-line interface for terminal usage:

```bash
ctk import data.json
ctk export output.md --format markdown
ctk search "python async"
```

### MCP (Model Context Protocol)

Integration with AI assistants and tools (coming soon).

### Web Frontend

Browser-based interface for non-technical users.

## Export Formats

### JSON (Native CTK Format)

Preserves full tree structure:

```json
{
  "format": "ctk",
  "version": "2.0.0",
  "conversations": [{
    "id": "...",
    "messages": {},
    "root_message_ids": []
  }]
}
```

### Markdown

Human-readable format with optional tree visualization:

```markdown
# Conversation Title

## Metadata
| Field | Value |
|-------|-------|
| Source | ChatGPT |

## Conversation
### 👤 User
Question...

### 🤖 Assistant
Response...
```

### JSONL

For fine-tuning and data pipelines:

```jsonl
{"messages": [{"role": "user", "content": "..."}, ...]}
{"messages": [{"role": "user", "content": "..."}, ...]}
```

## Path Selection Strategies

When exporting linear formats from branching conversations:

1. **longest** - Select the path with most messages
2. **first** - Select the first (original) path
3. **last** - Select the most recent path
4. **all** - Export all paths separately

## Future Extensions

### Planned Features

1. **Embeddings & Semantic Search**: Vector database integration
2. **Conversation Merging**: Combine related conversations
3. **Real-time Sync**: Live updates from provider APIs
4. **Analytics Dashboard**: Usage patterns and insights
5. **LangChain Integration**: Use as a memory store

### Extension Points

1. **Custom Importers**: Add support for new providers
2. **Custom Exporters**: Create specialized output formats
3. **Interface Plugins**: Build new ways to interact with CTK
4. **Processing Pipelines**: Transform conversations in bulk

## Development

### Adding a New Importer

1. Create file in `ctk/integrations/importers/`
2. Inherit from `ImporterPlugin`
3. Implement `validate()` and `import_data()`
4. Plugin is auto-discovered

### Adding a New Interface

1. Create directory in `ctk/interfaces/`
2. Inherit from `BaseInterface`
3. Implement required methods
4. Add entry point or server script

### Testing

```bash
make test           # Run all tests
make test-unit      # Unit tests only
make coverage       # Coverage report
```

## Performance Considerations

1. **Lazy Loading**: Messages loaded on-demand
2. **Path Caching**: Common paths pre-computed
3. **Indexed Search**: Full-text search via SQLite FTS
4. **Batch Operations**: Bulk import/export support
5. **Connection Pooling**: Reuse database connections