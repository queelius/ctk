# CLI Reference

## Commands Overview

| Command | Description |
|---------|-------------|
| `import` | Import conversations from various formats |
| `export` | Export conversations to various formats |
| `list` | List conversations |
| `search` | Search conversations |
| `ask` | Natural language queries |
| `show` | Show specific conversation |
| `tree` | View conversation tree structure |
| `paths` | List all paths in conversation |
| `star` | Star/unstar conversations |
| `pin` | Pin/unpin conversations |
| `archive` | Archive/unarchive conversations |
| `title` | Rename conversation |
| `tag` | Auto-tag with LLM |
| `stats` | Database statistics |
| `merge` | Merge databases |
| `diff` | Compare databases |
| `filter` | Create filtered database |
| `chat` | Launch interactive TUI |
| `plugins` | List available plugins |
| `view` | Manage named views |

## Global Options

```bash
--db, -d PATH    # Database path (required for most commands)
--help, -h       # Show help
```

## import

```bash
ctk import FILE --db DB [OPTIONS]

Options:
  --format FORMAT    # Explicit format (auto-detected if omitted)
  --tags TAGS        # Comma-separated tags to add
  --project NAME     # Project name
```

## export

```bash
ctk export OUTPUT --db DB [OPTIONS]

Options:
  --format FORMAT      # json, jsonl, markdown, html, hugo
  --ids ID [ID ...]    # Specific conversation IDs
  --limit N            # Maximum conversations (0 = all)
  --filter-source S    # Filter by source
  --filter-model M     # Filter by model
  --filter-tags T      # Filter by tags
  --starred            # Export only starred
  --pinned             # Export only pinned
  --sanitize           # Remove sensitive data
  --path-selection     # longest, first, last
  --view NAME          # Export only conversations in named view

HTML options:
  --theme              # light, dark, auto
  --media-dir DIR      # Output media separately
  --no-embed           # Multi-file export

Hugo options:
  --draft              # Mark as drafts
  --no-date-prefix     # Skip date in directory names

Markdown options:
  # Output to directory for per-file export:
  ctk export docs/ --db chats.db --format markdown
```

## list

```bash
ctk list --db DB [OPTIONS]

Options:
  --limit N            # Maximum results
  --starred            # Show only starred
  --pinned             # Show only pinned
  --archived           # Show only archived
  --source SOURCE      # Filter by source
  --model MODEL        # Filter by model
  --tags TAGS          # Filter by tags
  --json               # Output as JSON
```

## search

```bash
ctk search QUERY --db DB [OPTIONS]

Options:
  --limit N            # Maximum results
  --title-only         # Search titles only
  --content-only       # Search content only
  --date-from DATE     # Filter by date
  --date-to DATE       # Filter by date
  --source SOURCE      # Filter by source
  --model MODEL        # Filter by model
  --tags TAGS          # Filter by tags
```

## Organization Commands

```bash
ctk star ID [ID ...] --db DB [--unstar]
ctk pin ID [ID ...] --db DB [--unpin]
ctk archive ID [ID ...] --db DB [--unarchive]
ctk title ID "New Title" --db DB
```

## Database Operations

```bash
ctk merge DB1 DB2 --output OUTPUT
ctk diff DB1 DB2
ctk filter --db DB --output OUTPUT [--starred] [--tags T]
```

## view

Manage named views for curated conversation collections.

### view list

List all available views:

```bash
ctk view list --db DB
```

### view create

Create a new view:

```bash
ctk view create NAME --db DB [OPTIONS]

Options:
  --title TEXT         # Human-readable title
  --description TEXT   # Description
```

### view show

Show view definition (YAML):

```bash
ctk view show NAME --db DB
```

### view eval

Evaluate view and show resolved conversations:

```bash
ctk view eval NAME --db DB
```

### view add

Add conversations to a view:

```bash
ctk view add NAME ID [ID ...] --db DB [OPTIONS]

Options:
  --title TEXT         # Override conversation title in view
  --annotation TEXT    # Add notes/annotation
  --path PATH          # Specific tree path (e.g., m1/m3/m47)
```

### view remove

Remove conversations from a view:

```bash
ctk view remove NAME ID [ID ...] --db DB
```

### view delete

Delete a view:

```bash
ctk view delete NAME --db DB
```

### view check

Validate view and check for missing/changed conversations:

```bash
ctk view check NAME --db DB
```

## Examples

### Create and populate a view

```bash
# Create view
ctk view create favorites --db chats.db --title "My Favorites"

# Add conversations
ctk view add favorites abc123 def456 --db chats.db

# Add with custom title
ctk view add favorites ghi789 --db chats.db --title "Important Discussion"

# Show contents
ctk view eval favorites --db chats.db
```

### Export using a view

```bash
# Export view to HTML
ctk export archive.html --db chats.db --view favorites --format html

# Export view to markdown (one file per conversation)
ctk export docs/ --db chats.db --view favorites --format markdown

# Export view to Hugo
ctk export content/posts/ --db chats.db --view favorites --format hugo
```
