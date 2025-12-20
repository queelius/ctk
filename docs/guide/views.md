# Views: Curated Conversation Collections

Views provide a powerful way to create curated, reusable collections of conversations. Following SICP principles of abstraction, composition, and closure, views let you define exactly what conversations to include and how to present them.

## Overview

A **view** is a named collection that can include:

- **Explicit items**: Specific conversations by ID
- **Queries**: Dynamic selection based on filters (starred, tags, source, etc.)
- **Set operations**: Combine views using union, intersection, or subtraction
- **Metadata overrides**: Custom titles, annotations, and ordering

Views are stored as YAML files in a `views/` directory alongside your database.

## Quick Start

### Create a View

```bash
# Create an empty view
ctk view create my-favorites --db chats.db

# Create with a title
ctk view create research-notes --db chats.db --title "Research Notes 2024"
```

### Add Conversations

```bash
# Add specific conversations
ctk view add my-favorites abc123 def456 --db chats.db

# Add with custom title override
ctk view add my-favorites abc123 --db chats.db --title "Important Discussion"

# Add with annotation
ctk view add my-favorites abc123 --db chats.db --annotation "Key insights on async patterns"
```

### List and Show Views

```bash
# List all views
ctk view list --db chats.db

# Show view contents
ctk view show my-favorites --db chats.db

# Evaluate view (resolve queries, show actual conversations)
ctk view eval my-favorites --db chats.db
```

### Export with Views

```bash
# Export only conversations in a view
ctk export output.html --db chats.db --view my-favorites --format html

# Export to markdown (one file per conversation)
ctk export docs/ --db chats.db --view research-notes --format markdown
```

## View YAML Structure

Views are stored as YAML files with a declarative structure:

```yaml
name: my-curated-collection
title: "My Curated Collection"
description: "Hand-picked conversations for the blog"
created_at: "2024-12-19T10:00:00"
updated_at: "2024-12-19T15:30:00"

# Explicit items with optional overrides
items:
  - id: abc123
    title: "Understanding Async Python"  # Override original title
    annotation: "Great explanation of asyncio"
  - id: def456
  - id: ghi789
    path: m1/m3/m47  # Specific path in branching conversation

# Dynamic queries
queries:
  - starred: true
    limit: 10
  - tags:
      - machine-learning
      - tutorial
    source: ChatGPT

# Combine with other views
include_views:
  - best-of-2024
  - python-tutorials

# Set operations
operations:
  - type: subtract
    view: already-published

# Custom ordering
order:
  field: created_at
  direction: desc
```

## CLI Commands Reference

### view list

List all available views:

```bash
ctk view list --db chats.db
```

### view create

Create a new view:

```bash
ctk view create NAME --db chats.db [OPTIONS]

Options:
  --title TEXT       Human-readable title
  --description TEXT Description of the view
```

### view show

Show view definition (YAML):

```bash
ctk view show NAME --db chats.db
```

### view eval

Evaluate view and show resolved conversations:

```bash
ctk view eval NAME --db chats.db
```

### view add

Add conversations to a view:

```bash
ctk view add NAME ID [ID ...] --db chats.db [OPTIONS]

Options:
  --title TEXT       Override conversation title
  --annotation TEXT  Add annotation/notes
  --path PATH        Specific tree path (e.g., m1/m3/m47)
```

### view remove

Remove conversations from a view:

```bash
ctk view remove NAME ID [ID ...] --db chats.db
```

### view delete

Delete a view:

```bash
ctk view delete NAME --db chats.db
```

### view check

Validate view and check for missing conversations:

```bash
ctk view check NAME --db chats.db
```

## Shell Mode Integration

Views are accessible in shell mode via the `/views/` virtual directory:

```bash
# Start shell mode
ctk chat --db chats.db

# In shell mode:
cd /views/                    # List all views
cd /views/my-favorites/       # List conversations in view
cd /views/my-favorites/abc123 # Navigate into conversation
ls                            # Show message tree
cat m1/text                   # Read message content
```

## Use Cases

### Blog/Documentation Curation

Create a view of conversations to publish:

```yaml
name: blog-posts
title: "Conversations for Blog"
items:
  - id: conv1
    title: "Understanding Transformers"
    annotation: "Edit intro paragraph"
  - id: conv2
    title: "Python Best Practices"
queries:
  - tags: [tutorial, beginner-friendly]
    starred: true
```

```bash
# Export for Hugo static site
ctk export content/posts/ --db chats.db --view blog-posts --format hugo
```

### Research Collection

Gather related conversations for a research project:

```yaml
name: ml-research
title: "Machine Learning Research"
queries:
  - tags: [machine-learning, research]
  - source: Claude
    model: claude-3-opus
include_views:
  - neural-networks
  - optimization
```

### Training Data Preparation

Curate high-quality conversations for fine-tuning:

```yaml
name: training-data
title: "Fine-tuning Dataset"
queries:
  - starred: true
    tags: [high-quality]
operations:
  - type: subtract
    view: contains-pii  # Exclude sensitive conversations
```

```bash
ctk export training.jsonl --db chats.db --view training-data --format jsonl
```

## Advanced Features

### Set Operations

Combine views using set operations:

```yaml
# Union: Include all from both views
include_views:
  - view-a
  - view-b

# Intersection: Only conversations in BOTH views
operations:
  - type: intersect
    view: must-have-tags

# Subtraction: Exclude conversations from another view
operations:
  - type: subtract
    view: already-exported
```

### Tree Path Selection

For branching conversations, specify which path to use:

```yaml
items:
  - id: abc123
    path: m1/m3/m47  # Full path from root to leaf
```

### Content Hash Tracking

Views can track content hashes to detect when source conversations change:

```yaml
items:
  - id: abc123
    content_hash: "sha256:abc..."  # Auto-generated
```

Use `ctk view check` to identify conversations that have changed since being added to the view.

### Query Filters

Available query filters:

| Filter | Description |
|--------|-------------|
| `starred` | Boolean - starred conversations |
| `pinned` | Boolean - pinned conversations |
| `archived` | Boolean - archived conversations |
| `tags` | List of tags (AND logic) |
| `source` | Provider name (ChatGPT, Claude, etc.) |
| `model` | Model name (gpt-4, claude-3-opus, etc.) |
| `limit` | Maximum results |

## Best Practices

1. **Use descriptive names**: `research-ml-2024` not `view1`
2. **Add annotations**: Document why each conversation is included
3. **Combine queries and items**: Use queries for dynamic content, explicit items for must-haves
4. **Use subtraction**: Create "exclude" views for PII, drafts, or already-processed content
5. **Check regularly**: Run `ctk view check` to find missing or changed conversations
