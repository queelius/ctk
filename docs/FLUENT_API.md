# CTK Fluent API Documentation

The CTK Fluent API provides a pythonic, chainable interface for working with conversations. It's designed to be intuitive, discoverable, and powerful.

## Installation

```python
from ctk import CTK, conversation, load, from_db
```

## Quick Examples

### One-Line Operations

```python
# Load and convert between formats
CTK.load("chatgpt.json").export_as("markdown").save("output.md")

# Filter and export
load("all.json").filter(lambda c: "python" in c.title).export_as("jsonl").save("python.jsonl")
```

### Building Conversations

```python
# Create a conversation programmatically
chat = (conversation("Python Tutorial")
    .system("You are a Python expert")
    .user("What is async/await?")
    .assistant("Async/await enables concurrent code execution...")
    .user("Show me an example")
    .assistant("```python\nasync def example():...\n```")
    .with_tags("python", "tutorial")
    .build())

# Create branching conversations
branching = (conversation("Creative Writing")
    .user("Write a haiku")
    .assistant("First version...")
    .branch()  # Alternative response
    .assistant("Second version...")
    .build())
```

### Database Operations

```python
# Initialize with database
ctk = CTK("conversations.db")

# Import with metadata
ctk.import_from("export.json")
   .with_format("openai")
   .with_tags("imported", "2024")
   .with_project("Support")
   .save()

# Search with filters
results = ctk.search("python async")
    .in_source("ChatGPT")
    .with_model("gpt-4")
    .limit(20)
    .get()

# Query conversations
recent = ctk.conversations()
    .where(source="Claude")
    .order_by("updated_at", desc=True)
    .limit(10)
    .get()

# Batch operations
with ctk.batch():
    ctk.import_from("file1.json").save()
    ctk.import_from("file2.json").save()
    ctk.import_from("file3.json").save()
```

### Export Options

```python
from ctk import ExportBuilder

# Markdown with full options
ExportBuilder(conversations, "markdown")
    .with_paths("longest")
    .include_metadata(True)
    .include_timestamps(True)
    .include_tree_structure(True)
    .save("export.md")

# JSON with different formats
ExportBuilder(conversations, "json")
    .format_style("openai")  # or "anthropic", "ctk", "generic"
    .pretty_print(True)
    .save("openai.json")
```

### Complex Pipelines

```python
# Chain multiple operations
load("conversations.json")
    .filter(lambda c: len(c.message_map) > 10)  # Long conversations
    .filter(lambda c: c.metadata.source == "ChatGPT")
    .transform(lambda c: add_word_count(c))
    .add_tags("processed", "analyzed")
    .export_as("jsonl")
    .save("processed.jsonl")

def add_word_count(conv):
    """Add word count to metadata"""
    total = sum(
        len(msg.content.get_text().split())
        for msg in conv.message_map.values()
        if msg.content
    )
    conv.metadata.custom_data['word_count'] = total
    return conv
```

## API Components

### Main Classes

- **`CTK`** - Main entry point with database connection
- **`ConversationBuilder`** - Build conversations with chained messages
- **`ConversationLoader`** - Load, filter, and transform conversations
- **`SearchBuilder`** - Search with filters and limits
- **`QueryBuilder`** - Query database with SQL-like operations
- **`ImportBuilder`** - Import with tags and metadata
- **`ExportBuilder`** - Export with format-specific options

### Key Methods

#### ConversationBuilder
- `.user(text)` - Add user message
- `.assistant(text)` - Add assistant message
- `.system(text)` - Add system message
- `.branch()` - Start alternative response branch
- `.with_tags(*tags)` - Add tags
- `.with_metadata(**kwargs)` - Set metadata
- `.build()` - Create the conversation

#### ConversationLoader
- `.filter(predicate)` - Filter with lambda function
- `.transform(func)` - Transform each conversation
- `.add_tags(*tags)` - Add tags to all
- `.export_as(format)` - Export to format
- `.save_to_db(path)` - Save to database
- `.get()` - Get list of conversations

#### SearchBuilder
- `.in_source(source)` - Filter by source
- `.with_model(model)` - Filter by model
- `.with_tags(*tags)` - Filter by tags
- `.limit(n)` - Limit results
- `.get()` - Execute search

#### QueryBuilder
- `.where(**filters)` - Add filter conditions
- `.order_by(field, desc=False)` - Sort results
- `.limit(n)` - Limit results
- `.offset(n)` - Skip results
- `.count()` - Count matches
- `.delete_all()` - Delete matches
- `.get()` - Execute query

## Advanced Features

### Multimodal Content

```python
conv = (conversation("Demo")
    .user("Analyze this",
          images=[{"url": "image.png"}])
    .assistant("I can see...",
               tools=[{"name": "analyze", "arguments": {...}}])
    .build())
```

### Path Selection

When exporting from branching conversations:
- `"longest"` - Path with most messages
- `"first"` - Original path
- `"last"` - Most recent path
- `"all"` - Export all paths

### Custom Transformations

```python
def anonymize(conv):
    """Remove personal information"""
    for msg in conv.message_map.values():
        if msg.content and msg.content.text:
            msg.content.text = re.sub(r'\b[A-Z][a-z]+\b', '[NAME]', msg.content.text)
    return conv

load("chats.json")
    .transform(anonymize)
    .export_as("json")
    .save("anonymous.json")
```

## Best Practices

1. **Use context managers** for batch operations
2. **Chain methods** for cleaner code
3. **Filter early** to reduce processing
4. **Use lambdas** for custom logic
5. **Export formats** match your use case:
   - `jsonl` for training data
   - `markdown` for human reading
   - `json` for full structure preservation

## Examples

See `examples/fluent_api.py` and `examples/fluent_api_demo.ipynb` for comprehensive examples.