# Conversation Toolkit (CTK)

A powerful, plugin-based system for managing AI conversations from multiple providers. Import, store, search, and export your conversations in a unified tree format while preserving provider-specific details.

## 🚀 Quick Start

```bash
# Setup (one-time)
make setup
source .venv/bin/activate

# Import conversations
ctk import chatgpt_export.json --db my_chats.db
ctk import claude_export.json --db my_chats.db --format anthropic

# View and search
ctk list --db my_chats.db
ctk search "python async" --db my_chats.db
ctk stats --db my_chats.db

# Export for fine-tuning
ctk export training.jsonl --db my_chats.db --format jsonl
```

## 🌟 Key Features

- **🌳 Universal Tree Format**: All conversations stored as trees - linear chats are single-path trees, branching conversations preserve all paths
- **🔌 Plugin Architecture**: Auto-discovers importers/exporters, easy to add new formats
- **💾 SQLite Backend**: Fast, searchable local database with proper indexing
- **🏷️ Rich Metadata**: Auto-tags by provider (OpenAI, Anthropic), model (GPT-4, Claude), language, etc.
- **🔒 Privacy First**: Everything local, optional secret masking for API keys/passwords
- **🔍 Full-Text Search**: Search across all conversations instantly
- **🤖 Coding Agent Support**: Import from GitHub Copilot, Cursor, and other coding assistants

## 📦 Installation

### From Source

```bash
git clone https://github.com/yourusername/ctk.git
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
# List all (newest first)
ctk list --db chats.db

# List with limit
ctk list --db chats.db --limit 50

# Output as JSON
ctk list --db chats.db --json
```

### Search
```bash
# Search in content and titles
ctk search "machine learning" --db chats.db

# Search with limit
ctk search "async python" --db chats.db --limit 20
```

### View Statistics
```bash
ctk stats --db chats.db

# Output:
# Database Statistics:
#   Total conversations: 851
#   Total messages: 25890
# Messages by role:
#     assistant: 12388
#     user: 9574
#     system: 1632
# Conversations by source:
#     ChatGPT: 423
#     Claude: 287
#     Copilot: 141
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
- More coming soon!

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

- [ ] Web UI for browsing conversations
- [ ] More export formats (Markdown, PDF, HTML)
- [ ] Conversation merging and deduplication
- [ ] LangChain/LlamaIndex integration
- [ ] Embeddings and semantic search
- [ ] Conversation analytics dashboard

## 🧪 Development

```bash
# Run tests
make dev

# Format code
make dev  # includes black, flake8, pytest

# Clean everything
make clean

# View Makefile options
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