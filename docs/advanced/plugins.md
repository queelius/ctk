# Creating Plugins

CTK uses a plugin architecture for importers and exporters. Plugins are auto-discovered when placed in the integrations folder.

## Plugin Types

- **Importers**: Convert external formats to ConversationTree
- **Exporters**: Convert ConversationTree to external formats

## Creating an Importer

```python
# File: ctk/integrations/importers/my_format.py
from ctk.core.plugin import ImporterPlugin
from ctk.core.models import (
    ConversationTree, Message, MessageContent, MessageRole
)

class MyFormatImporter(ImporterPlugin):
    name = "my_format"
    description = "Import from My Custom Format"
    version = "1.0.0"

    def validate(self, data):
        """Check if data matches this format"""
        return "my_format_marker" in str(data)

    def import_data(self, data, **kwargs):
        """Convert data to ConversationTree objects"""
        conversations = []

        tree = ConversationTree(
            id="conv_1",
            title="Imported Conversation"
        )

        msg = Message(
            role=MessageRole.USER,
            content=MessageContent(text="Hello")
        )
        tree.add_message(msg)

        conversations.append(tree)
        return conversations

# Plugin is auto-discovered!
```

## Creating an Exporter

```python
# File: ctk/integrations/exporters/my_format.py
from ctk.core.plugin import ExporterPlugin
from ctk.core.models import ConversationTree

class MyFormatExporter(ExporterPlugin):
    name = "my_format"
    description = "Export to My Custom Format"
    version = "1.0.0"

    def validate(self, data):
        """Exporters typically return False"""
        return False

    def export_data(self, conversations, **kwargs):
        """Convert conversations to your format"""
        output = []
        for conv in conversations:
            # Process conversation
            output.append({"title": conv.title})
        return output

    def export_to_file(self, conversations, file_path, **kwargs):
        """Export to file"""
        data = self.export_data(conversations, **kwargs)
        with open(file_path, 'w') as f:
            json.dump(data, f)
```

## Core Models

### ConversationTree

```python
tree = ConversationTree(
    id="unique_id",
    title="Conversation Title"
)

# Add messages
tree.add_message(msg, parent_id=None)  # Root message
tree.add_message(msg2, parent_id=msg.id)  # Child message

# Navigate tree
paths = tree.get_all_paths()
longest = tree.get_longest_path()
```

### Message

```python
msg = Message(
    id="msg_id",  # Auto-generated if not provided
    role=MessageRole.USER,  # USER, ASSISTANT, SYSTEM, TOOL
    content=MessageContent(text="Hello"),
    timestamp=datetime.now(),
    metadata={"custom": "data"}
)
```

### MessageContent

```python
content = MessageContent(
    text="Message text",
    parts=["Part 1", "Part 2"],
    images=[MediaContent(url="path/to/image.png")],
    metadata={}
)
```

## Listing Plugins

```bash
ctk plugins
```

## Plugin Discovery

Plugins are discovered in:
- `ctk/integrations/importers/`
- `ctk/integrations/exporters/`

Any Python file with a class inheriting from `ImporterPlugin` or `ExporterPlugin` is automatically registered.
