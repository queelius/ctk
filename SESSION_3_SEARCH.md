# Shell Mode Session 3 - Search Functionality

This document summarizes the search feature implementation added in session 3.

## Summary

This session added comprehensive search functionality to shell mode:

1. ✅ **find command** - Search conversations and messages across the VFS
2. ✅ **Enhanced grep** - Already working, tested and documented
3. ✅ **Chat mode commands documented** - Complete reference for all `/command` options

## New Feature: find Command

### Implementation

Created `ctk/core/commands/search.py` (360 lines) implementing the `find` command with comprehensive search capabilities:

**Key features:**
- Search by conversation title pattern (`-name`)
- Search by message content (`-content`)
- Filter by message role (`-role`)
- Filter by type: directories/conversations (`-type d`) or files/messages (`-type f`)
- Case-insensitive search (`-i`)
- Limit results (`-limit`)
- Search in specific VFS paths

### Command Syntax

```bash
find                        # Find all conversations
find <path>                 # Find in specific path
find -name <pattern>        # Find by title pattern (supports * and ?)
find -content <pattern>     # Find messages by content
find -role <role>           # Find by role (user/assistant/system)
find -type d                # Find directories (conversations)
find -type f                # Find files (messages)
find -i                     # Case-insensitive search
find -limit <n>             # Limit results to n items
```

### Examples

```bash
# Find first 5 conversations
$ find /chats -type d -limit 5
/chats/7c87af4c-5e10-4eb4-8aaa-41070f710e0f/
/chats/5dce9708-0f2d-4c73-a634-b1db3517e7c1/
/chats/33e5a339-e4a5-4015-a9b5-d9fce3676933/

# Find conversations with "test" in title
$ find -name '*test*'
/chats/abc123.../

# Find messages containing "conservatism" (limit 2)
$ find -content 'conservatism' -limit 2
/chats/67a03a2a-c990-8003-b7ca-86a0d5e01940/m1/m1/m1/m1/m1/m1/m1
/chats/67a03a2a-c990-8003-b7ca-86a0d5e01940/m1/m1/m1/m1/m1/m1/m1/m1/m1

# Find user messages (limit 3)
$ find -role user -limit 3
/chats/7c87af4c-5e10-4eb4-8aaa-41070f710e0f/m1/m1
/chats/7c87af4c-5e10-4eb4-8aaa-41070f710e0f/m1/m1/m1/m1
/chats/7c87af4c-5e10-4eb4-8aaa-41070f710e0f/m1/m1/m1/m1/m1/m1

# Search in starred conversations
$ find /starred -content 'important'
```

### Integration with Existing Features

The `find` command works seamlessly with:
- **Piping**: `find -role user | head 10`
- **VFS paths**: Search in `/starred`, `/tags`, `/archived`, etc.
- **Prefix resolution**: Works with partial conversation IDs
- **grep**: Combine with grep for advanced filtering

## grep Command (Already Exists)

The `grep` command was already implemented and working. This session verified it works correctly:

```bash
# Search within a specific file
$ grep -i 'pattern' text

# Case-insensitive search
$ grep -i 'conservative' text

# With line numbers
$ grep -n 'TODO' text

# Piping
$ cat text | grep 'law'
what's that quote again about conservatism consisting of in-groups whom the law protects...
```

## Chat Mode Navigation Commands

Discovered and documented existing chat mode navigation commands:

### /goto-latest
Navigate to the most recently created message (leaf node).

```
/goto-latest
✓ Moved to most recent leaf
  ID: abc12345...
  Timestamp: 2024-01-15 10:30:00
  Role: assistant
  Content: The response text...
```

**Use case**: Resume conversation where you left off after exploring branches.

### /goto-longest
Navigate to the leaf node at the end of the longest path.

### /where
Show current position in the conversation tree.

### /alternatives
Show alternative conversation branches at current position.

## Files Modified/Created

### New Files
- `ctk/core/commands/search.py` (360 lines) - find command implementation
- `CHAT_MODE_COMMANDS.md` (450 lines) - Complete chat mode commands reference

### Modified Files
- `ctk/integrations/chat/tui.py` - Added search command registration (4 lines)
- `SHELL_COMMANDS_REFERENCE.md` - Added find command documentation, updated count to 20 commands
- `SHELL_MODE_COMPLETE.md` - Added search examples and usage, updated summary

## Documentation Updates

### SHELL_COMMANDS_REFERENCE.md
- Added new "Search" section with find command documentation
- Added search examples to "Piping Examples"
- Added search tips to "Tips & Tricks"
- Updated command count: **19 → 20 commands**

### SHELL_MODE_COMPLETE.md
- Added search section with practical examples
- Updated summary to include search functionality
- Updated registered commands list

### CHAT_MODE_COMMANDS.md (NEW)
Complete reference guide for all chat mode commands:
- Navigation: `/goto-latest`, `/goto-longest`, `/where`, `/alternatives`
- Conversation management: `/exit`, `/clear`, `/new-chat`, `/save`, `/load`, `/delete`
- Organization: `/star`, `/pin`, `/archive`, `/title`, `/tag`
- Search: `/search`, `/list`, `/ask`, `/browse`
- Message operations: `/system`, `/fork`, `/regenerate`, `/edit`
- Visualization: `/tree`, `/paths`, `/context`
- Export: `/export`
- LLM config: `/model`, `/models`, `/temp`
- MCP tools: `/mcp`

## Testing

### Test Results

**Basic find tests:**
```
$ find /chats -type d -limit 3
/chats/7c87af4c-5e10-4eb4-8aaa-41070f710e0f/
/chats/5dce9708-0f2d-4c73-a634-b1db3517e7c1/
/chats/33e5a339-e4a5-4015-a9b5-d9fce3676933/
```

**Content search:**
```
$ find -content 'conservatism' -limit 2
  ✓ Found 2 messages containing the pattern
```

**Role filter:**
```
$ find -role user -limit 3
  ✓ Found 3 user messages
```

**grep integration:**
```
$ cat text | grep 'law'
what's that quote again about conservatism consisting of in-groups whom the law protects...
  ✓ grep correctly filters message content
```

## Impact

The search functionality dramatically improves shell mode usability:

1. **Fast discovery**: Quickly find conversations by title, content, or metadata
2. **Flexible filtering**: Combine multiple search criteria
3. **Scalability**: `-limit` flag prevents overwhelming output on large databases
4. **Unix philosophy**: Works seamlessly with pipes and other commands
5. **Context-aware**: Search within specific VFS directories (tags, starred, etc.)

## Use Cases

### Find conversations about a topic
```bash
$ find -content 'machine learning' -limit 10
```

### Find recent user questions
```bash
$ find -role user -limit 20
```

### Search starred conversations
```bash
$ find /starred -content 'API design'
```

### Combine find and grep
```bash
$ find -role assistant | head 5  # First 5 assistant messages
$ cd /chats/abc123
$ find -content 'error'          # Find errors in specific conversation
```

### Navigate and chat
```bash
$ find -content 'Python tutorial' -limit 1
/chats/abc123/m1/m1/m1

$ cd /chats/abc123/m1/m1/m1
$ cat text
# Read the message

$ chat
# Resume conversation with full history loaded!
```

## Summary

Shell-first mode now has **20 commands** with comprehensive search capabilities:

- ✅ **Navigation** (3): cd, ls, pwd
- ✅ **Search** (1): find
- ✅ **File Operations** (5): cat, head, tail, echo, grep
- ✅ **Visualization** (2): tree, paths
- ✅ **Organization** (7): star, unstar, pin, unpin, archive, unarchive, title
- ✅ **Chat/LLM** (2): chat, complete

Plus **30+ chat mode commands** (with `/` prefix) for in-conversation navigation and management.

The search functionality completes the core shell experience, making CTK's VFS a powerful tool for conversation exploration and management.
