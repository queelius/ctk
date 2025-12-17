# Shell Mode Commands Reference

Quick reference for all 19 shell commands in CTK.

## Navigation (3 commands)

### cd - Change Directory
```bash
cd <path>       # Change to path
cd /chats       # Go to chats directory
cd abc123       # Navigate using conversation prefix
cd m1           # Navigate to message node
cd ..           # Go to parent directory
cd /            # Go to root
```

### ls - List Directory
```bash
ls              # List current directory
ls <path>       # List specific path
ls -l           # Long format (shows metadata)
ls | head 5     # List first 5 entries (with pipe)
```

### pwd - Print Working Directory
```bash
pwd             # Show current VFS path
```

## Search (1 command)

### find - Find Conversations and Messages
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
find -l                     # Long format: rich table with title, model, date, tags

# Examples - Default Format (paths for piping)
find /chats -type d -limit 5
# Output:
# /chats/7c87af4c-5e10-4eb4-8aaa-41070f710e0f/
# /chats/5dce9708-0f2d-4c73-a634-b1db3517e7c1/

# Long Format (-l flag shows metadata table)
find /chats -type d -limit 5 -l
# Shows rich table with: #, ID (short), Title, Model, Updated, Tags
# Includes visual flags: ⭐ (starred), 📌 (pinned), 📦 (archived)

# Search and navigate workflow
find -name '*API*'                     # Find by title
find -content 'error' -limit 10        # Find in content
cd $(find -name '*bug*' | head -1)     # Navigate to first match
find /starred -content 'important' -l  # Search starred with metadata
```

## File Operations (5 commands)

### cat - Display Content
```bash
cat <path>      # Display file/message content
cat m1          # Display message at m1
cat m1/text     # Display message text metadata
cat .           # Display current message
echo "text" | cat  # Display from stdin
```

### head - Show First Lines
```bash
head [n]        # Show first 10 lines from stdin
head 5          # Show first 5 lines
head <path> [n] # Show first n lines from path
cat m1 | head 3 # Pipe example
```

### tail - Show Last Lines
```bash
tail [n]        # Show last 10 lines from stdin
tail 5          # Show last 5 lines
tail <path> [n] # Show last n lines from path
cat m1 | tail 3 # Pipe example
```

### echo - Echo Text
```bash
echo <text>     # Print text
echo $VAR       # Print environment variable
echo "hello"    # Print with quotes
```

### grep - Search Patterns
```bash
grep <pattern>          # Search stdin
grep <pattern> <path>   # Search file
grep -i <pattern>       # Case-insensitive
grep -n <pattern>       # Show line numbers
cat m1 | grep "error"   # Pipe example
```

## Visualization (2 commands)

### tree - Show Conversation Tree
```bash
tree            # Show tree for current conversation
tree <conv_id>  # Show tree for specific conversation
tree | head 20  # Show first 20 lines
```

### paths - List Conversation Paths
```bash
paths           # Show all paths in current conversation
paths <conv_id> # Show paths for specific conversation
paths | head 15 # Show first 15 lines
```

## Organization (7 commands)

### star - Star Conversation
```bash
star            # Star current conversation
star <conv_id>  # Star specific conversation
star 7c87       # Works with prefix resolution
```

### unstar - Unstar Conversation
```bash
unstar          # Unstar current conversation
unstar <conv_id># Unstar specific conversation
```

### pin - Pin Conversation
```bash
pin             # Pin current conversation
pin <conv_id>   # Pin specific conversation
```

### unpin - Unpin Conversation
```bash
unpin           # Unpin current conversation
unpin <conv_id> # Unpin specific conversation
```

### archive - Archive Conversation
```bash
archive         # Archive current conversation
archive <conv_id> # Archive specific conversation
```

### unarchive - Unarchive Conversation
```bash
unarchive       # Unarchive current conversation
unarchive <conv_id> # Unarchive specific conversation
```

### title - Set Conversation Title
```bash
title <text>    # Set title for current conversation
title My Title  # Example
title <conv_id> <text> # Set title for specific conversation
```

## Chat & LLM (2 commands)

### chat - Enter Chat Mode
```bash
chat            # Enter interactive chat mode
chat <message>  # Send message and enter chat mode
echo "text" | chat  # Send piped text as message
```

**Important:** When you enter `chat` from a conversation or message node, the full conversation history up to that point is automatically loaded as context for the LLM.

Example:
```bash
$ cd /chats/abc123/m1/m1/m1  # Navigate to specific message
$ chat                        # Conversation history loaded!
Entering chat mode. Type /exit to return to shell.
# LLM now has context of all messages from root to m1/m1/m1
```

### complete - Get LLM Completion
```bash
complete <prompt>       # Get completion without entering chat
echo "prompt" | complete  # Get completion from stdin
```

## VFS Structure

```
/
├── chats/                  # All conversations
│   └── <conv_id>/         # Specific conversation
│       └── m1/            # Message nodes
│           ├── text       # Message content (file)
│           ├── role       # Message role (file)
│           ├── timestamp  # Creation time (file)
│           ├── id         # Message UUID (file)
│           └── m1/        # Child messages
├── starred/               # Starred conversations
├── pinned/                # Pinned conversations
├── archived/              # Archived conversations
├── tags/                  # Tag hierarchy
├── recent/                # Recent conversations
├── source/                # Grouped by source
└── model/                 # Grouped by model
```

## Environment Variables

Available variables:
- `$CWD` / `$PWD` - Current working directory
- `$MODEL` - Current LLM model
- `$PROVIDER` - Current LLM provider
- `$CONV_ID` - Current conversation ID (if in conversation)
- `$MSG_COUNT` - Message count (if in conversation)

Usage:
```bash
echo $CWD
cd /chats && echo $PWD
grep $MODEL model.txt
```

## Piping Examples

```bash
# List and filter
ls | grep "^7" | head 3

# Read and search
cat m1/text | grep "important"

# Count lines
cat m1 | wc -l

# Environment variable inspection
echo $CWD | grep "/chats"

# Complex pipeline
ls /starred | grep -i "test" | head 5

# Find and pipe to head
find -role user | head 10

# Search message content
cat text | grep -i "error"
```

## Prefix Resolution

Conversation IDs can be referenced by their first 3+ characters:

```bash
$ cd 7c87
Resolved '7c87' to: 7c87af4c-5e10-4eb4-8aaa-41070f710e0f

$ star abc1
Starred conversation: abc123...

$ tree 68e
# Shows tree for 68e133a0-f23c-832b-b3d9-a3a748b39b06
```

## Relative Path Navigation

```bash
cd ..           # Parent directory
cd m1           # Relative to current path
cd ./m1/m2      # Explicit relative path
cd /chats/abc/m1  # Absolute path
```

## Message Metadata Files

Each message node exposes metadata as readable files:

```bash
$ cd /chats/abc123/m1
$ ls
text
role
timestamp
id
m1/

$ cat text
Hello, world!

$ cat role
user

$ cat timestamp
2024-01-15 10:30:00
```

## Tips & Tricks

1. **Quick navigation**: Use prefix resolution for faster navigation
   ```bash
   cd /chats/7c8  # Instead of full UUID
   ```

2. **Organize on the fly**: Star/pin/archive from anywhere
   ```bash
   star 7c87      # Star without navigating to it
   ```

3. **Pipe for powerful queries**:
   ```bash
   ls /chats | grep "^a" | head 10  # First 10 conversations starting with 'a'
   ```

4. **Inspect metadata**: Use cat on metadata files
   ```bash
   cat m1/role    # Quick role check
   cat m1/id      # Get message UUID
   ```

5. **Combine commands**:
   ```bash
   cd /starred && ls | head 5  # Show first 5 starred conversations
   ```

6. **Search efficiently**:
   ```bash
   find -content 'error' -limit 20        # Limit results for faster search
   find /starred -role user               # Search specific VFS directories
   find -name '*important*' -type d       # Find conversations by title
   ```

7. **Grep within messages**:
   ```bash
   cat text | grep -i 'pattern'           # Case-insensitive search in message
   grep -n 'TODO' text                    # Show line numbers
   ```

## Command Summary

| Category | Commands | Count |
|----------|----------|-------|
| Navigation | cd, ls, pwd | 3 |
| Search | find | 1 |
| File Operations | cat, head, tail, echo, grep | 5 |
| Visualization | tree, paths | 2 |
| Organization | star, unstar, pin, unpin, archive, unarchive, title | 7 |
| Chat/LLM | chat, complete | 2 |
| **Total** | | **20** |
