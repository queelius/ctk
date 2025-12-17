# Searching & Filtering

CTK provides powerful search capabilities across all your conversations.

## Basic Search

```bash
# Full-text search
ctk search "machine learning" --db chats.db

# Search with limit
ctk search "python" --db chats.db --limit 20
```

## Filtering

```bash
# Filter by source
ctk search "python" --db chats.db --source ChatGPT

# Filter by model
ctk search "code" --db chats.db --model GPT-4

# Filter by tags
ctk search "tutorial" --db chats.db --tags "code,learning"

# Date range
ctk search "AI" --db chats.db --date-from 2024-01-01 --date-to 2024-12-31
```

## Natural Language Queries

Use the `ask` command for LLM-powered queries:

```bash
ctk ask "show me starred conversations" --db chats.db
ctk ask "find discussions about async python" --db chats.db
ctk ask "conversations from last week about AI" --db chats.db
```

## Organization

### Star Conversations

```bash
ctk star abc123 --db chats.db
ctk star abc123 def456 --db chats.db  # Multiple
ctk star --unstar abc123 --db chats.db
```

### Pin Conversations

```bash
ctk pin abc123 --db chats.db
ctk pin --unpin abc123 --db chats.db
```

### Archive Conversations

```bash
ctk archive abc123 --db chats.db
ctk archive --unarchive abc123 --db chats.db
```

## List with Filters

```bash
ctk list --db chats.db --starred
ctk list --db chats.db --pinned
ctk list --db chats.db --archived
ctk list --db chats.db --json  # JSON output
```
