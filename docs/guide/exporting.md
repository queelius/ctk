# Exporting Conversations

CTK supports multiple export formats for different use cases.

## Export Formats

| Format | Use Case |
|--------|----------|
| `jsonl` | Fine-tuning, data pipelines |
| `json` | Data interchange, backup |
| `markdown` | Human-readable documentation |
| `html` | Interactive browsing, archiving |
| `hugo` | Static site generation, blogging |

## Using Views for Curated Exports

Views let you define reusable collections for export. See [Views Guide](views.md) for details.

```bash
# Export only conversations in a view
ctk export output.html --db chats.db --view my-favorites --format html

# Export curated research to markdown
ctk export research/ --db chats.db --view research-2024 --format markdown
```

## JSONL (Fine-tuning)

```bash
# Basic export
ctk export training.jsonl --db chats.db --format jsonl

# With metadata
ctk export full.jsonl --db chats.db --format jsonl --include-metadata

# Using a curated view
ctk export training.jsonl --db chats.db --view high-quality --format jsonl
```

## Markdown

Export conversations as readable markdown files.

### Single File

```bash
# All conversations in one file
ctk export conversations.md --db chats.db --format markdown
```

### Per-Conversation Files

When the output path is a directory, each conversation becomes a separate file:

```bash
# Create one markdown file per conversation
ctk export docs/ --db chats.db --format markdown

# Output structure:
# docs/
#   2024-01-15_debugging-rust_abc123.md
#   2024-01-16_python-async_def456.md
#   ...
```

Files are named: `{date}_{title-slug}_{id-prefix}.md`

### Markdown with Views

```bash
# Export curated collection to separate files
ctk export blog-posts/ --db chats.db --view for-publication --format markdown
```

## Hugo (Static Sites)

Export conversations as Hugo page bundles:

```bash
# Export all conversations
ctk export content/conversations/ --format hugo --db chats.db

# Export only starred (curated for blog)
ctk export content/conversations/ --format hugo --db chats.db --starred

# Export a curated view
ctk export content/conversations/ --format hugo --db chats.db --view blog-posts

# Export as drafts for review
ctk export content/conversations/ --format hugo --db chats.db --draft
```

Output structure:
```
content/conversations/
  2024-01-15-debugging-rust-abc123/
    index.md        # Frontmatter + markdown
    images/         # Media files
```

## HTML (Interactive Archive)

Create an interactive, searchable HTML archive:

```bash
# Single self-contained file (recommended)
ctk export archive.html --format html --db chats.db

# With separate media folder (smaller HTML file)
ctk export archive.html --format html --db chats.db --media-dir media

# Multi-file export (requires web server)
ctk export archive/ --format html --db chats.db --no-embed
```

### HTML Features

- **Browse**: Paginated conversation list with search
- **Tree Navigation**: Explore branching conversations
- **Media Gallery**: View all images across conversations
- **Dark/Light Mode**: Toggle with theme switcher
- **Responsive**: Works on desktop and mobile

## Filtering Exports

```bash
# Specific conversations
ctk export out.jsonl --db chats.db --ids conv1 conv2 conv3

# By source
ctk export chatgpt.json --db chats.db --filter-source "ChatGPT"

# By model
ctk export gpt4.json --db chats.db --filter-model "GPT-4"

# By tags
ctk export work.json --db chats.db --filter-tags "work,important"

# Starred/pinned only
ctk export favorites.json --db chats.db --starred
ctk export important.json --db chats.db --pinned
```

## Path Selection

For branching conversations, choose which path to export:

```bash
# Longest path (default)
ctk export out.jsonl --db chats.db --path-selection longest

# First path (original)
ctk export out.jsonl --db chats.db --path-selection first

# Most recent path
ctk export out.jsonl --db chats.db --path-selection last
```

## Sanitization

Remove sensitive data before sharing:

```bash
ctk export clean.jsonl --db chats.db --format jsonl --sanitize
```

This removes:

- API keys (OpenAI, Anthropic, AWS, etc.)
- Passwords and tokens
- SSH keys
- Database URLs
- Credit card patterns

## Export Workflow Example

A typical workflow for publishing conversations:

```bash
# 1. Create a view for curation
ctk view create blog-ready --db chats.db --title "Ready for Blog"

# 2. Add conversations to the view
ctk view add blog-ready abc123 def456 --db chats.db

# 3. Add annotations for editing notes
ctk view add blog-ready ghi789 --db chats.db \
  --title "Custom Title" \
  --annotation "Edit intro, add code examples"

# 4. Check view is valid
ctk view check blog-ready --db chats.db

# 5. Export to Hugo
ctk export content/posts/ --db chats.db --view blog-ready --format hugo

# 6. Or export to standalone HTML
ctk export blog-archive.html --db chats.db --view blog-ready --format html
```
