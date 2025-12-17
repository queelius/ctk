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

## JSONL (Fine-tuning)

```bash
# Basic export
ctk export training.jsonl --db chats.db --format jsonl

# With metadata
ctk export full.jsonl --db chats.db --format jsonl --include-metadata
```

## Hugo (Static Sites)

Export conversations as Hugo page bundles:

```bash
# Export all conversations
ctk export content/conversations/ --format hugo --db chats.db

# Export only starred (curated for blog)
ctk export content/conversations/ --format hugo --db chats.db --starred

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

```bash
# Single self-contained file (recommended)
ctk export archive.html --format html --db chats.db

# With separate media folder (smaller HTML)
ctk export archive.html --format html --db chats.db --media-dir media

# Multi-file (requires web server)
ctk export archive/ --format html --db chats.db --no-embed
```

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
```

## Sanitization

Remove sensitive data before sharing:

```bash
ctk export clean.jsonl --db chats.db --format jsonl --sanitize
```

This removes:
- API keys
- Passwords and tokens
- SSH keys
- Database URLs
