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
│   ├── today/
│   ├── this-week/
│   ├── this-month/
│   └── older/
├── source/             # By source (ChatGPT, Claude, etc.)
├── model/              # By model (GPT-4, Claude-3, etc.)
└── views/              # Named views (curated collections)
    └── <view-name>/    # Conversations in view
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

## Views in Shell Mode

Navigate curated views like regular directories:

```bash
cd /views/                    # List all views
ls                            # Shows: my-favorites, research-2024, ...

cd /views/my-favorites/       # Enter a view
ls                            # Shows conversations in this view

cd abc123                     # Navigate into a conversation
cat m1/text                   # Read message content
```

Views provide the same navigation as `/chats/`, but only show the curated subset:

```bash
# List conversations in a view
cd /views/research-notes
ls -l

# Search within a view's conversations
find -content "machine learning"

# View shows title overrides from view definition
ls  # Shows custom titles if defined in view
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
cat role                # Show message role
cat timestamp           # Show message time
cat id                  # Show message ID
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

## Visualization

```bash
tree                    # Show conversation tree structure
paths                   # List all paths in branching conversation
```

## Piping

Commands support Unix-style piping:

```bash
ls | grep python | head 5
find -name "*ai*" | head 10
cat text | grep "error"
ls -l | grep starred
```

## Environment Variables

```bash
echo $CWD               # Current working directory
echo $CONV_ID           # Current conversation ID
echo $MODEL             # Current LLM model
echo $PROVIDER          # Current LLM provider
```

## Chat Mode

From shell mode, start an interactive chat:

```bash
chat                    # Start chat in current conversation
/exit                   # Return to shell mode (or Ctrl+D)
```

## Example Session

```bash
$ ctk chat --db chats.db

ctk:/$ cd /views/research-2024
ctk:/views/research-2024$ ls -l
abc123  Understanding Transformers     2024-03-15  ⭐
def456  Neural Network Optimization    2024-04-02

ctk:/views/research-2024$ cd abc123
ctk:/views/research-2024/abc123$ tree
m1 [user] What are transformers?
└── m2 [assistant] Transformers are a type of...
    └── m3 [user] How does attention work?
        └── m4 [assistant] Attention mechanisms...

ctk:/views/research-2024/abc123$ cat m2/text
Transformers are a type of neural network architecture...

ctk:/views/research-2024/abc123$ cd /starred
ctk:/starred$ find -content "python" -l
ID        Title                    Date        Source
abc789    Python Best Practices    2024-01-10  ChatGPT
```

See the [Shell Commands Reference](../reference/shell-commands.md) for complete documentation.
