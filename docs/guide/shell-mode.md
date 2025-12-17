# Shell Mode

CTK provides a Unix-like shell interface for navigating and managing conversations through a Virtual Filesystem (VFS).

## Starting Shell Mode

```bash
ctk chat --db chats.db
```

## VFS Structure

Conversations are exposed as a filesystem:

```
/
├── chats/              # All conversations by ID
│   └── <conv-id>/      # Individual conversation
│       └── m1/m2/m3    # Message tree
├── starred/            # Starred conversations
├── pinned/             # Pinned conversations
├── archived/           # Archived conversations
├── tags/               # Conversations by tag
├── recent/             # Recent conversations
├── source/             # By source (ChatGPT, Claude, etc.)
└── model/              # By model (GPT-4, Claude-3, etc.)
```

## Navigation Commands

```bash
cd /chats               # Go to conversations
cd abc123               # Navigate to conversation (prefix matching)
cd m1/m2                # Navigate message tree
cd ..                   # Go up
cd /                    # Go to root
pwd                     # Print current path
ls                      # List contents
ls -l                   # Long format with metadata
```

## Search

```bash
find -name "*python*"           # Find by title
find -content "async"           # Find by content
find -role user                 # Find user messages
find -l                         # Rich table output
find -limit 10                  # Limit results
```

## Unix Commands

```bash
cat text                # Show message content
head 5                  # First 5 lines
tail 10                 # Last 10 lines
grep "pattern"          # Search in output
```

## Organization

```bash
star                    # Star current conversation
unstar                  # Unstar
pin                     # Pin
unpin                   # Unpin
archive                 # Archive
unarchive               # Unarchive
title "New Title"       # Rename
```

## Piping

```bash
ls | grep python | head 5
find -name "*ai*" | head 10
cat text | grep "error"
```

## Chat Mode

From shell mode, start chatting:

```bash
chat                    # Start chat in current conversation
/exit                   # Return to shell mode
```

See the [Shell Commands Reference](../reference/shell-commands.md) for complete documentation.
