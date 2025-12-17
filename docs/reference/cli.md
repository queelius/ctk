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

HTML options:
  --theme              # light, dark, auto
  --media-dir DIR      # Output media separately
  --no-embed           # Multi-file export

Hugo options:
  --draft              # Mark as drafts
  --no-date-prefix     # Skip date in directory names
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
