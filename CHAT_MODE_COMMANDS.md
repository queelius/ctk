# Chat Mode Commands Reference

Complete reference for all `/command` commands available in chat mode.

## Navigation Commands

### /goto-latest
Navigate to the most recently created message (leaf node) in the conversation tree.

```
/goto-latest
```

Moves `current_message` to the most recent leaf based on timestamp. Useful for resuming where you left off after exploring alternative conversation paths.

**Output:**
```
✓ Moved to most recent leaf
  ID: abc12345...
  Timestamp: 2024-01-15 10:30:00
  Role: assistant
  Content: The response text...
```

### /goto-longest
Navigate to the leaf node at the end of the longest conversation path.

```
/goto-longest
```

Useful for finding the most developed conversation branch.

### /where
Show current position in the conversation tree.

```
/where
```

Displays:
- Current message ID
- Path depth (how many messages from root)
- Message role and preview
- Number of children (alternative branches)

### /alternatives
Show alternative conversation branches at the current position.

```
/alternatives
```

Lists all sibling messages (alternative responses at the current level).

## Conversation Management

### /exit
Return to shell mode.

```
/exit
```

Exits chat mode and returns to the VFS shell interface.

### /quit
Same as `/exit` - return to shell mode.

### /clear
Clear current conversation and start fresh.

```
/clear
```

Removes all messages from memory. Does not delete from database.

### /new-chat [title]
Save current conversation and start a new one.

```
/new-chat
/new-chat My Project Discussion
```

Auto-saves the current conversation (if it has messages) before starting fresh.

### /save
Save current conversation to database.

```
/save
```

Saves the entire conversation tree to the database. Uses current conversation ID or creates a new one.

### /load <conversation_id>
Load a conversation from the database.

```
/load abc123...
/load 7c87af  # Works with prefix
```

Loads conversation and sets `current_message` to most recent leaf.

### /delete [conversation_id]
Delete a conversation from the database.

```
/delete              # Delete currently loaded conversation
/delete abc123...    # Delete specific conversation
```

## Organization Commands

### /star
Star the current conversation.

```
/star
```

Makes conversation appear in `/starred/` VFS directory.

### /unstar
Remove star from current conversation.

```
/unstar
```

### /pin
Pin the current conversation.

```
/pin
```

Makes conversation appear in `/pinned/` VFS directory.

### /unpin
Remove pin from current conversation.

```
/unpin
```

### /archive
Archive the current conversation.

```
/archive
```

Makes conversation appear in `/archived/` VFS directory and hides it from default listings.

### /unarchive
Unarchive the current conversation.

```
/unarchive
```

### /title <new_title>
Set or update the conversation title.

```
/title My Important Discussion
```

Updates the title metadata for the current conversation.

### /tag
Auto-generate tags for the conversation using LLM.

```
/tag
```

Analyzes conversation content and generates relevant tags automatically.

## Search and Browse

### /search <query>
Search conversations by content.

```
/search error handling
```

Searches all conversations in the database for the specified text.

### /list [filter]
List conversations in the database.

```
/list
/list starred
/list archived
```

Shows table of conversations with metadata.

### /ask <query>
Natural language query over conversation database.

```
/ask what did I discuss about Python last week?
```

Uses LLM with tool calling to interpret query and search database.

### /browse
Interactive browse mode with table navigation.

```
/browse
```

Opens Rich table interface for browsing all conversations.

## Message Operations

### /system <message>
Add a system message to the conversation.

```
/system You are a helpful coding assistant
```

Inserts a system message at the current position.

### /fork [conversation_id]
Fork from current position (create alternative branch).

```
/fork
```

Allows continuing from the current message with a different response.

### /fork-id <message_id>
Fork from a specific message by ID.

```
/fork-id abc12345...
```

### /regenerate
Regenerate the last assistant response.

```
/regenerate
```

Deletes the last assistant message and generates a new response to the same user message.

### /edit
Edit the last user message and regenerate response.

```
/edit
```

Opens editor to modify the last user message, then gets new response.

## Visualization

### /tree [conversation_id]
Display conversation tree structure.

```
/tree
/tree abc123...
```

Shows ASCII tree visualization of the conversation structure.

### /paths [conversation_id]
List all paths in the conversation.

```
/paths
/paths abc123...
```

Lists all possible paths from root to leaves.

### /context
Show current conversation context (messages sent to LLM).

```
/context
```

Displays all messages in the path from root to current message.

## Export

### /export <format> [conversation_id]
Export conversation to file.

```
/export markdown
/export json abc123...
/export html
```

Supported formats:
- `markdown` - Human-readable with tree visualization
- `json` - CTK native format or provider-specific (OpenAI, Anthropic)
- `jsonl` - For fine-tuning
- `html` - Interactive HTML5 with search

## LLM Configuration

### /model <model_name>
Switch to a different LLM model.

```
/model gpt-4
/model llama3.2
```

Changes the model for subsequent messages in the conversation.

### /models
List available models from the current provider.

```
/models
```

### /temp <temperature>
Set temperature for LLM responses.

```
/temp 0.7
/temp 0.2   # More deterministic
/temp 1.0   # More creative
```

## MCP Tools

### /mcp
Show MCP (Model Context Protocol) status and available tools.

```
/mcp
```

Displays connected MCP servers and their tools.

## Help

### /help [command]
Show help information.

```
/help
/help goto-latest
```

Displays available commands or detailed help for a specific command.

## Tips

1. **Resume conversations**: Use `/goto-latest` after loading a conversation to continue where you left off
2. **Explore branches**: Use `/alternatives` to see different conversation paths, then navigate with `/goto-latest` or `/goto-longest`
3. **Quick navigation**: All commands work with or without the `/` prefix in chat mode
4. **Prefix resolution**: Most commands that take conversation IDs support prefix matching (first 3+ characters)

## Examples

### Resume a conversation from shell mode
```bash
# In shell mode
$ cd /chats/abc123
$ cat m1/m1/text
What's the capital of France?

$ chat
# Now in chat mode - history loaded!

/goto-latest
✓ Moved to most recent leaf
  Role: assistant
  Content: The capital of France is Paris.

# Continue chatting with full context
> Tell me more about Paris
```

### Explore alternative conversation branches
```
/where
Current position: Message at depth 5
Role: assistant
Children: 3 alternative branches

/alternatives
1. [user] What about London?
2. [user] Tell me about Berlin
3. [user] How about Rome?

/goto-latest
✓ Moved to most recent leaf
```

### Organize and search
```
/star
✓ Starred conversation

/title Important Discussion About APIs
✓ Updated title

/search REST API design
Found 3 conversations...

/ask what did I learn about GraphQL?
# LLM searches database and summarizes findings
```

## Integration with Shell Mode

All organization commands (`/star`, `/pin`, `/archive`, `/title`) work seamlessly with the shell mode VFS:

```
# In chat mode
/star
/title Machine Learning Discussion

# Exit to shell
/exit

# In shell mode - changes are reflected
$ ls /starred
abc123.../  # Your starred conversation appears here
```
