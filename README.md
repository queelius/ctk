# Conversation Toolkit (CTK)

A powerful, plugin-based system for managing AI conversations from multiple providers. Import, store, search, and export your conversations in a unified tree format while preserving provider-specific details.

## 🚀 Quick Start

```bash
# Setup (one-time)
make install
source venv/bin/activate

# Import conversations
ctk import chatgpt_export.json --db my_chats.db
ctk import claude_export.json --db my_chats.db --format anthropic

# View and search with beautiful tables
ctk list --db my_chats.db --starred
ctk search "python async" --db my_chats.db --limit 10
ctk ask "show me conversations about machine learning" --db my_chats.db

# Interactive chat with LLM
ctk chat --db my_chats.db  # Start TUI with conversation management

# Export for fine-tuning
ctk export training.jsonl --db my_chats.db --format jsonl
```

## 🌟 Key Features

### Core Functionality
- **🌳 Universal Tree Format**: All conversations stored as trees - linear chats are single-path trees, branching conversations preserve all paths
- **🔌 Plugin Architecture**: Auto-discovers importers/exporters, easy to add new formats
- **💾 SQLite Backend**: Fast, searchable local database with proper indexing
- **🔒 Privacy First**: Everything local, optional secret masking for API keys/passwords
- **🤖 Coding Agent Support**: Import from GitHub Copilot, Cursor, and other coding assistants

### Search & Discovery
- **🔍 Full-Text Search**: Search across all conversations instantly with Rich table output
- **🤖 Natural Language Queries**: Use `/ask` or `ctk ask` for LLM-powered queries
- **🏷️ Smart Tagging**: Auto-tags by provider, model, language; manual tags; LLM auto-tagging
- **⭐ Organization**: Star, pin, and archive conversations for easy filtering
- **📁 Views**: Create curated, reusable collections with YAML DSL, queries, and set operations

### Interactive Features
- **💬 Chat TUI**: Beautiful terminal UI with conversation browsing, editing, and chat
- **🌐 MCP Integration**: Model Context Protocol support for tool calling
- **🔄 Live Editing**: Fork conversations, navigate paths, edit trees in real-time
- **📊 Rich Visualization**: Color-coded messages, tree views, path exploration

## 📦 Installation

### From Source

```bash
git clone https://github.com/queelius/ctk.git
cd ctk
make setup
source .venv/bin/activate
```

### Manual Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 📥 Import Examples

### ChatGPT/OpenAI
Export your ChatGPT conversations from [chat.openai.com/settings](https://chat.openai.com/settings) → Data Controls → Export

```bash
# Auto-detect format
ctk import conversations.json --db chats.db

# Explicit format with tags
ctk import chatgpt_export.json --db chats.db --format openai --tags "work,2024"
```

### Claude/Anthropic
Export from Claude's settings

```bash
ctk import claude_export.json --db chats.db --format anthropic
```

### GitHub Copilot (from VS Code)
```bash
# Import from VS Code workspace storage
ctk import ~/.vscode/workspaceStorage --db chats.db --format copilot

# Or find Copilot data automatically
python -c "from ctk.integrations.importers.copilot import CopilotImporter; \
          paths = CopilotImporter.find_copilot_data(); \
          print('\n'.join(map(str, paths)))"
```

### Local LLM Formats (JSONL)
```bash
# Import JSONL for fine-tuning datasets
ctk import training_data.jsonl --db chats.db --format jsonl

# Import multiple files
for file in *.jsonl; do
    ctk import "$file" --db chats.db --format jsonl
done
```

## 🔍 Search and Filter

### List Conversations
```bash
# List all (newest first) with Rich tables
ctk list --db chats.db

# Filter by status
ctk list --db chats.db --starred
ctk list --db chats.db --pinned
ctk list --db chats.db --archived

# Combine filters
ctk list --db chats.db --starred --pinned --limit 10

# Output as JSON
ctk list --db chats.db --json
```

### Search
```bash
# Search with Rich table output
ctk search "machine learning" --db chats.db

# Advanced filtering
ctk search "python" --db chats.db --source ChatGPT --model GPT-4
ctk search "async" --db chats.db --tags "code,tutorial" --limit 20

# Search with date ranges
ctk search "AI" --db chats.db --date-from 2024-01-01 --date-to 2024-12-31
```

### Natural Language Queries
```bash
# Ask anything in plain English using LLM
ctk ask "show me starred conversations" --db chats.db
ctk ask "find discussions about async python" --db chats.db
ctk ask "conversations from last week about AI" --db chats.db --debug

# The LLM interprets your query and executes the right database operations
```

### View Conversations
```bash
# Show specific conversation (prefix matching)
ctk show abc123 --db chats.db

# Show with path selection
ctk show abc123 --db chats.db --path longest
ctk show abc123 --db chats.db --path latest

# View tree structure
ctk tree abc123 --db chats.db

# List all paths in branching conversation
ctk paths abc123 --db chats.db
```

### View Statistics
```bash
ctk stats --db chats.db

# Output:
# Database Statistics:
#   Total conversations: 851
#   Total messages: 25890
#   Starred: 23
#   Pinned: 5
#   Archived: 142
# Messages by role:
#     assistant: 12388
#     user: 9574
#     system: 1632
# Conversations by source:
#     ChatGPT: 423
#     Claude: 287
#     Copilot: 141
```

## 📋 Conversation Organization

### Star/Unstar Conversations
```bash
# Star a conversation for quick access
ctk star abc123 --db chats.db

# Star multiple conversations
ctk star abc123 def456 ghi789 --db chats.db

# Unstar
ctk star --unstar abc123 --db chats.db
```

### Pin/Unpin Conversations
```bash
# Pin important conversations to the top
ctk pin abc123 --db chats.db

# Unpin
ctk pin --unpin abc123 --db chats.db
```

### Archive/Unarchive
```bash
# Archive old conversations
ctk archive abc123 --db chats.db

# Unarchive
ctk archive --unarchive abc123 --db chats.db
```

### Rename Conversations
```bash
# Change conversation title
ctk title abc123 "New descriptive title" --db chats.db
```

## 📁 Views: Curated Collections

Views let you create named, reusable collections of conversations with queries, metadata overrides, and set operations.

### Create and Manage Views
```bash
# Create a view
ctk view create favorites --db chats.db --title "My Favorites"

# Add conversations to view
ctk view add favorites abc123 def456 --db chats.db

# Add with custom title override
ctk view add favorites ghi789 --db chats.db --title "Important Discussion"

# List all views
ctk view list --db chats.db

# Show view contents
ctk view eval favorites --db chats.db

# Remove from view
ctk view remove favorites abc123 --db chats.db
```

### Export with Views
```bash
# Export only conversations in a view
ctk export archive.html --db chats.db --view favorites --format html

# Export to markdown (one file per conversation)
ctk export docs/ --db chats.db --view favorites --format markdown

# Export to Hugo
ctk export content/posts/ --db chats.db --view favorites --format hugo
```

### Navigate Views in Shell Mode
```bash
ctk chat --db chats.db

# In shell mode:
cd /views/                    # List all views
cd /views/favorites/          # List conversations in view
cd abc123                     # Navigate into conversation
```

## 💬 Interactive Chat TUI

Launch the terminal UI for interactive conversation management and chat:

```bash
ctk chat --db chats.db
```

### TUI Features

**Navigation & Browsing:**
- Browse conversations with filtering (starred, pinned, archived)
- Rich table view with emoji flags (⭐📌📦)
- Quick search and natural language queries
- Tree view for branching conversations
- Path navigation in multi-branch trees

**Conversation Management:**
- Create, rename, delete conversations
- Star, pin, archive operations
- Auto-tagging with LLM
- Export to various formats

**Live Chat:**
- Chat with any LLM provider (Ollama, OpenAI, Anthropic)
- Model Context Protocol (MCP) tool support
- Fork conversations to explore alternatives
- Edit and regenerate messages
- Switch between conversation paths

### TUI Commands

```bash
# Navigation
/browse              # Browse conversations table
/show <id>           # Show conversation
/tree <id>           # View tree structure
/paths <id>          # List all paths

# Search & Query
/search <query>      # Full-text search
/ask <query>         # Natural language query (LLM-powered)

# Organization
/star <id>           # Star conversation
/pin <id>            # Pin conversation
/archive <id>        # Archive conversation
/title <id> <title>  # Rename conversation

# Chat Operations
/fork                # Fork current conversation
/regenerate          # Regenerate last message
/edit <msg_id>       # Edit a message
/model <name>        # Switch LLM model

# Export & Tools
/export <format>     # Export current conversation
/tag                 # Auto-tag with LLM
/help                # Show all commands
/quit                # Exit TUI
```

## 🗄️ Database Operations

### Merge Databases
```bash
# Combine multiple databases
ctk merge source1.db source2.db --output merged.db

# Automatically handles duplicates by conversation ID
```

### Database Diff
```bash
# Compare two databases
ctk diff db1.db db2.db

# Shows:
# - Conversations only in db1
# - Conversations only in db2
# - Conversations with different content
```

### Filter and Extract
```bash
# Create filtered database
ctk filter --db all_chats.db --output work_chats.db --tags "work"
ctk filter --db all_chats.db --output starred.db --starred
ctk filter --db all_chats.db --output recent.db --date-from 2024-01-01
```

## 📤 Export Examples

### Export for Fine-Tuning
```bash
# JSONL format for local LLMs
ctk export training.jsonl --db chats.db --format jsonl

# Include only assistant responses
ctk export responses.jsonl --db chats.db --format jsonl --path-selection longest

# Export with metadata
ctk export full_export.jsonl --db chats.db --format jsonl --include-metadata
```

### Export with Filtering
```bash
# Export specific conversations
ctk export selected.jsonl --db chats.db --ids conv1 conv2 conv3

# Filter by source
ctk export openai_only.json --db chats.db --filter-source "ChatGPT"

# Filter by model
ctk export gpt4_convs.json --db chats.db --filter-model "GPT-4"

# Filter by tags
ctk export work_chats.json --db chats.db --filter-tags "work,important"
```

### Export with Sanitization
```bash
# Remove secrets before sharing
ctk export clean_export.jsonl --db chats.db --format jsonl --sanitize

# This removes:
# - API keys (OpenAI, Anthropic, AWS, etc.)
# - Passwords and tokens
# - SSH keys
# - Database URLs
# - Credit card numbers (if any)
```

### Export to Markdown
```bash
# Single file with all conversations
ctk export all_chats.md --db chats.db --format markdown

# Per-file export (one markdown file per conversation)
ctk export docs/ --db chats.db --format markdown
# Creates: docs/2024-01-15_title_abc123.md, docs/2024-01-16_title_def456.md, ...
```

### Export to Hugo (Static Site)
```bash
# Export all conversations as Hugo page bundles
ctk export content/conversations/ --format hugo --db chats.db

# Export only starred conversations (curated for blog)
ctk export content/conversations/ --format hugo --db chats.db --starred

# Export specific conversations
ctk export content/conversations/ --format hugo --db chats.db --ids conv1 conv2

# Mark as drafts for review
ctk export content/conversations/ --format hugo --db chats.db --draft
```

Each conversation becomes a Hugo page bundle:
```
content/conversations/
  2024-01-15-debugging-rust-abc123/
    index.md        # Frontmatter + markdown content
    images/         # Copied media files
```

### Export to HTML5 (Interactive App)
```bash
# Single self-contained HTML file (default, recommended)
ctk export archive.html --format html --db chats.db

# Separate media files for smaller HTML
ctk export archive.html --format html --db chats.db --media-dir media
# Creates: archive.html + media/ folder

# Multi-file export (requires web server)
ctk export archive/ --format html --db chats.db --no-embed
```

## 🌳 Understanding the Tree Structure

CTK stores all conversations as trees, which provides several benefits:

### Linear Conversations → Single-Path Trees
```
User: "What is Python?"
  └── Assistant: "Python is a programming language..."
      └── User: "How do I install it?"
          └── Assistant: "You can install Python by..."
```

### Branching Conversations (e.g., ChatGPT regenerations)
```
User: "Write a poem"
  ├── Assistant (v1): "Roses are red..."
  └── Assistant (v2): "In fields of gold..."  [regenerated]
      └── User: "Make it longer"
          └── Assistant: "In fields of gold, where sunshine..."
```

### Path Selection for Export
```bash
# Export longest path (default)
ctk export out.jsonl --db chats.db --path-selection longest

# Export first path (original)
ctk export out.jsonl --db chats.db --path-selection first

# Export most recent path
ctk export out.jsonl --db chats.db --path-selection last
```

## 🔧 Advanced Usage

### Python API
```python
from ctk import ConversationDB, registry

# Load conversations
with ConversationDB("chats.db") as db:
    # Search
    results = db.search_conversations("python async")
    
    # Load specific conversation
    conv = db.load_conversation("conv_id_123")
    
    # Get all paths in a branching conversation
    paths = conv.get_all_paths()
    
    # Get longest path
    longest = conv.get_longest_path()
    
    # Add new message to existing conversation
    from ctk import Message, MessageContent, MessageRole
    
    msg = Message(
        role=MessageRole.USER,
        content=MessageContent(text="New question")
    )
    conv.add_message(msg, parent_id="previous_msg_id")
    db.save_conversation(conv)
```

### Batch Operations
```python
import glob
from ctk import ConversationDB, registry

# Import all exports from a directory
with ConversationDB("all_chats.db") as db:
    for file in glob.glob("exports/*.json"):
        format = "openai" if "chatgpt" in file.lower() else None
        convs = registry.import_file(file, format=format)
        
        for conv in convs:
            # Add file source as tag
            conv.metadata.tags.append(f"file:{file}")
            db.save_conversation(conv)
    
    # Get statistics
    stats = db.get_statistics()
    print(f"Imported {stats['total_conversations']} conversations")
```

### Custom Sanitization Rules
```python
from ctk.core.sanitizer import Sanitizer, SanitizationRule
import re

# Create custom sanitizer
sanitizer = Sanitizer(enabled=True)

# Add company-specific patterns
sanitizer.add_rule(SanitizationRule(
    name="internal_urls",
    pattern=re.compile(r'https://internal\.company\.com/[^\s]+'),
    replacement="[INTERNAL_URL]"
))

sanitizer.add_rule(SanitizationRule(
    name="employee_ids",
    pattern=re.compile(r'EMP\d{6}'),
    replacement="[EMPLOYEE_ID]"
))
```

## 🔌 Available Plugins

### Importers
- **openai** - ChatGPT exports (preserves full tree structure)
- **anthropic** - Claude exports
- **gemini** - Google Gemini/Bard
- **copilot** - GitHub Copilot from VS Code
- **jsonl** - Generic JSONL format for local LLMs
- **filesystem_coding** - Auto-detect coding agent data
- **coding_agent** - Generic coding assistant format

### Exporters
- **jsonl** - JSONL for fine-tuning (multiple formats)
- **json** - Native CTK format, OpenAI, Anthropic, or generic JSON
- **markdown** - Human-readable with tree visualization
- **html** - Interactive HTML5 app with browsing, search, and media gallery
- **hugo** - Hugo page bundles for static site generation

### List Available Plugins
```bash
ctk plugins
```

## 🛠️ Creating Custom Plugins

### Custom Importer
```python
# File: ctk/integrations/importers/my_format.py
from ctk.core.plugin import ImporterPlugin
from ctk.core.models import ConversationTree, Message, MessageContent, MessageRole

class MyFormatImporter(ImporterPlugin):
    name = "my_format"
    description = "Import from My Custom Format"
    version = "1.0.0"
    
    def validate(self, data):
        """Check if data is your format"""
        return "my_format_marker" in str(data)
    
    def import_data(self, data, **kwargs):
        """Convert data to ConversationTree objects"""
        conversations = []
        
        # Parse your format
        tree = ConversationTree(
            id="conv_1",
            title="Imported Conversation"
        )
        
        # Add messages
        msg = Message(
            role=MessageRole.USER,
            content=MessageContent(text="Hello")
        )
        tree.add_message(msg)
        
        conversations.append(tree)
        return conversations
```

The plugin is automatically discovered when placed in the integrations folder!

## 🗄️ Database Schema

CTK uses SQLite with the following structure:

- **conversations** - Metadata, title, timestamps, source, model
- **messages** - Content, role, parent/child relationships
- **tags** - Searchable tags per conversation
- **paths** - Cached conversation paths for fast retrieval

## 🔐 Privacy & Security

- **100% Local** - No data leaves your machine
- **No Analytics** - No telemetry or tracking
- **Optional Sanitization** - Remove sensitive data before sharing
- **Configurable Rules** - Add custom patterns to mask

## 🗺️ Roadmap

### Completed ✅
- [x] Terminal UI with conversation management
- [x] Rich console output with tables
- [x] Natural language queries (ask command)
- [x] Star/pin/archive organization
- [x] Multiple export formats (JSONL, JSON, Markdown, HTML5, Hugo)
- [x] MCP tool integration
- [x] Auto-tagging with LLM
- [x] Database merge/diff operations
- [x] Shell-first mode with VFS navigation
- [x] Hugo static site export
- [x] Views system for curated collections (YAML DSL, queries, set operations)
- [x] Per-file markdown export (directory output)
- [x] VFS integration for views (`/views/` directory)

### In Progress 🔨
- [ ] Embeddings and similarity search
- [ ] Improved test coverage
- [ ] Performance optimization for large databases

### Planned 📋
- [ ] Web-based UI (complement to TUI)
- [ ] Conversation deduplication utilities
- [ ] LangChain/LlamaIndex integration
- [ ] Advanced analytics dashboard

## 🧪 Development

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run integration tests only
make test-integration

# Run with coverage report
make coverage

# Format code (black + isort)
make format

# Lint code (flake8 + mypy)
make lint

# Clean build artifacts
make clean

# View all Makefile targets
make help
```

## 📝 License

MIT

## 🤝 Contributing

Contributions welcome! To add support for a new provider:

1. Create importer in `ctk/integrations/importers/provider_name.py`
2. Implement `validate()` and `import_data()` methods
3. Add tests in `tests/`
4. Submit PR

## 🙏 Acknowledgments

Built to solve the fragmentation of AI conversations across platforms. Special thanks to all contributors!