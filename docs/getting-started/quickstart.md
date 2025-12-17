# Quick Start

## Import Your Conversations

```bash
# Import ChatGPT export
ctk import chatgpt_export.json --db my_chats.db

# Import Claude export
ctk import claude_export.json --db my_chats.db --format anthropic

# Import GitHub Copilot
ctk import ~/.vscode/workspaceStorage --db my_chats.db --format copilot
```

## Search and Browse

```bash
# List all conversations
ctk list --db my_chats.db

# Search for specific topics
ctk search "python async" --db my_chats.db

# Natural language queries
ctk ask "show me conversations about machine learning" --db my_chats.db
```

## Interactive Mode

```bash
# Launch the TUI
ctk chat --db my_chats.db
```

## Export

```bash
# Export for fine-tuning
ctk export training.jsonl --db my_chats.db --format jsonl

# Export to Hugo for your blog
ctk export content/conversations/ --format hugo --db my_chats.db --starred

# Export to interactive HTML
ctk export archive.html --format html --db my_chats.db
```
