# Chat TUI

The Terminal User Interface provides interactive conversation management and live chat.

## Starting the TUI

```bash
ctk chat --db chats.db
```

## Features

- **Shell Mode**: Unix-like navigation with VFS
- **Chat Mode**: Live conversation with LLM providers
- **Rich Output**: Color-coded messages, tables, tree views
- **MCP Support**: Model Context Protocol tool integration

## Slash Commands

### Navigation
```
/browse              # Browse conversations table
/show <id>           # Show conversation
/tree <id>           # View tree structure
/paths <id>          # List all paths
```

### Search
```
/search <query>      # Full-text search
/ask <query>         # Natural language query
```

### Organization
```
/star <id>           # Star conversation
/pin <id>            # Pin conversation
/archive <id>        # Archive conversation
/title <id> <title>  # Rename
```

### Chat Operations
```
/fork                # Fork current conversation
/regenerate          # Regenerate last message
/edit <msg_id>       # Edit a message
/model <name>        # Switch LLM model
```

### Export
```
/export <format>     # Export current conversation
/tag                 # Auto-tag with LLM
```

### System
```
/help                # Show all commands
/quit                # Exit TUI
```

## LLM Providers

The TUI supports multiple providers:

- **Ollama** (local)
- **OpenAI**
- **Anthropic**

Configure via environment variables or config file.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+D` | Exit chat mode / Exit TUI |
| `Tab` | Auto-complete |
| `Up/Down` | Command history |
