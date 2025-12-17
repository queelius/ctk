# Importing Conversations

CTK supports importing conversations from multiple AI providers.

## Supported Formats

| Format | Provider | Notes |
|--------|----------|-------|
| `openai` | ChatGPT | Preserves full tree structure including regenerations |
| `anthropic` | Claude | Standard Claude export format |
| `gemini` | Google Gemini/Bard | Google AI conversations |
| `copilot` | GitHub Copilot | From VS Code workspace storage |
| `jsonl` | Various | Generic JSONL for local LLMs |

## ChatGPT/OpenAI

Export your ChatGPT conversations from [chat.openai.com/settings](https://chat.openai.com/settings) → Data Controls → Export

```bash
# Auto-detect format
ctk import conversations.json --db chats.db

# Explicit format with tags
ctk import chatgpt_export.json --db chats.db --format openai --tags "work,2024"
```

## Claude/Anthropic

Export from Claude's settings page.

```bash
ctk import claude_export.json --db chats.db --format anthropic
```

## GitHub Copilot

```bash
# Import from VS Code workspace storage
ctk import ~/.vscode/workspaceStorage --db chats.db --format copilot
```

## JSONL Format

For local LLMs and fine-tuning datasets:

```bash
ctk import training_data.jsonl --db chats.db --format jsonl

# Import multiple files
for file in *.jsonl; do
    ctk import "$file" --db chats.db --format jsonl
done
```

## Import Options

| Option | Description |
|--------|-------------|
| `--db` | Database path (required) |
| `--format` | Explicit format (auto-detected if omitted) |
| `--tags` | Comma-separated tags to add |
| `--project` | Project name for organization |
