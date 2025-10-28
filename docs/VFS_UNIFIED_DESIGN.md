# Unified VFS Design - Complete Specification

## Overview

CTK implements a complete POSIX-like virtual filesystem that unifies conversation management, tree navigation, and system configuration under a single, consistent interface. Everything is a file or directory. All operations use standard filesystem commands.

## Philosophy

1. **Everything is a file** - Conversations, messages, configuration, searches
2. **Uniformity above all** - One mental model for all operations
3. **POSIX compatibility** - Commands behave like Unix/Linux equivalents
4. **Composability** - Operations combine naturally without special cases
5. **Discoverability** - `ls` always shows what's available

## Directory Structure

```
/
├── chats/                    # Shared conversation storage (system-wide)
│   ├── abc123/              # Conversation (directory)
│   │   ├── .metadata        # Conversation metadata (JSON)
│   │   ├── .title           # Conversation title
│   │   ├── .tags            # Tags (one per line)
│   │   ├── .source          # Source (openai, anthropic, etc.)
│   │   ├── .model           # Model used
│   │   ├── .created         # Creation timestamp
│   │   ├── .updated         # Last update timestamp
│   │   ├── m1/              # Message node (directory)
│   │   │   ├── content.txt  # Message content
│   │   │   ├── .role        # Role (user, assistant, system)
│   │   │   ├── .timestamp   # Message timestamp
│   │   │   ├── .model       # Model used for this message
│   │   │   ├── m2/          # Child message
│   │   │   │   └── m4/      # Continued conversation
│   │   │   └── m3/          # Alternative branch (regeneration)
│   │   └── m5/              # Parallel root message
│   └── def456/
│
├── tags/                     # Hierarchical tag namespace (shared)
│   ├── physics/
│   │   ├── simulator/
│   │   │   └── abc123 -> /chats/abc123/  # Symlink
│   │   └── quantum/
│   │       └── def456 -> /chats/def456/
│   └── programming/
│       └── python/
│
├── starred/                  # Starred conversations (shared, read-only view)
│   ├── abc123 -> /chats/abc123/
│   └── xyz789 -> /chats/xyz789/
│
├── pinned/                   # Pinned conversations (shared, read-only view)
│   └── def456 -> /chats/def456/
│
├── archived/                 # Archived conversations (shared, read-only view)
│   └── old123 -> /chats/old123/
│
├── recent/                   # Time-based views (shared, read-only)
│   ├── today/
│   ├── this-week/
│   ├── this-month/
│   └── older/
│
├── source/                   # Grouped by source (shared, read-only)
│   ├── openai/
│   ├── anthropic/
│   └── gemini/
│
├── model/                    # Grouped by model (shared, read-only)
│   ├── gpt-4/
│   ├── claude-3/
│   └── llama3/
│
├── home/                     # User personal spaces
│   ├── guest/               # Default user
│   │   └── .bashrc          # User preferences
│   └── alice/               # Named user
│       ├── important/       # Personal organization
│       │   └── abc123 -> /chats/abc123/
│       ├── projects/
│       │   ├── quantum/
│       │   └── ml-research/
│       └── workspace/
│
├── system/                   # System configuration & state
│   ├── config/
│   │   ├── temperature      # LLM temperature (cat/echo to view/change)
│   │   ├── model            # Current model
│   │   ├── user             # Current user
│   │   ├── max_tokens       # Max tokens
│   │   └── system_prompt    # System prompt
│   ├── models/
│   │   ├── available/       # All available models
│   │   │   ├── ollama:llama3/
│   │   │   ├── openai:gpt-4/
│   │   │   └── anthropic:claude-3/
│   │   └── current -> available/ollama:llama3/  # Symlink to current
│   ├── mcp/
│   │   └── servers/
│   │       ├── filesystem/
│   │       │   ├── status   # "connected" or "disconnected"
│   │       │   ├── config   # Server configuration
│   │       │   └── tools/
│   │       │       ├── read_file/
│   │       │       └── write_file/
│   │       └── git/
│   │           ├── status
│   │           └── tools/
│   └── rag/
│       ├── embeddings/
│       │   └── status       # Embedding status
│       ├── similar/         # Virtual directory
│       │   └── abc123/      # Created on-demand
│       │       ├── def456 -> /chats/def456/
│       │       └── xyz789 -> /chats/xyz789/
│       └── graph/
│           └── stats        # Network statistics
│
├── search/                   # Virtual search results (created on-demand)
│   ├── quantum/             # Search query as directory name
│   │   ├── abc123 -> /chats/abc123/
│   │   └── def456 -> /chats/def456/
│   └── "machine learning"/  # Quoted for multi-word
│
├── tmp/                      # Temporary conversations (auto-deleted)
│   └── session-uuid/        # Per-session temp conversations
│
└── bin/                      # Command index (virtual, read-only)
    ├── chat                 # Not actual files, just for `ls /bin/`
    ├── search
    ├── star
    ├── find
    └── ...
```

## Message Node Naming

### Rationale for `m1/`, `m2/`, `m3/`

- **Simple**: Easy to type and remember
- **Sequential**: Clear ordering across entire tree
- **Role-agnostic**: Works for any message sequence
- **Tab-friendly**: Easy completion
- **Global**: Numbers are unique within conversation

### Message Node Structure

Each message node is a directory containing:

```
m5/
├── content.txt      # Message content
├── .role            # "user", "assistant", or "system"
├── .timestamp       # ISO 8601 timestamp
├── .model           # Model used (if assistant message)
├── .metadata        # Additional metadata (JSON)
└── m6/              # Child message(s)
```

### Example Tree

```
/chats/abc123/
├── m1/              # "Hello, I need help with physics simulation"
│   ├── m2/          # "Sure! What specifically do you want to simulate?"
│   │   └── m4/      # "I want to simulate molecular dynamics"
│   └── m3/          # "I can help! Let's start with the basics."
└── m5/              # "Actually, let me start over..."
```

## Commands (Programs)

Commands are treated as programs, not filesystem paths. They don't require `/` prefix.

### Navigation (POSIX Standard)

**`cd [path]`** - Change directory
```bash
cd /chats/abc123/        # Absolute path
cd m5/                   # Relative path
cd ../m3/                # Parent then sibling
cd ~                     # Home directory
cd /                     # Root
```

**`pwd`** - Print working directory
```bash
pwd
# Output: /chats/abc123/m5/
```

**`ls [options] [path]`** - List directory
```bash
ls                       # Current directory
ls -l                    # Long format with metadata
ls -a                    # Include hidden files (dotfiles)
ls /chats/               # Specific directory
```

**`tree [path]`** - Show tree structure
```bash
tree                     # Tree from current position
tree /chats/abc123/      # Tree from specific conversation
tree -L 2                # Limit depth to 2 levels
```

**`find [path] [options]`** - Search filesystem
```bash
find /chats/ -name "*.txt"
find . -type d           # Find directories
find /chats/ -empty      # Find leaf nodes (conversation endpoints)
```

### File Operations (POSIX Standard)

**`cp <src> <dest>`** - Copy
```bash
cp /chats/abc123/ /tmp/backup/              # Copy conversation
cp /chats/abc123/m5/ /tmp/branch/           # Copy subtree
```

**`mv <src> <dest>`** - Move
```bash
mv /tags/draft/abc123 /tags/final/          # Move between tags
```

**`rm <path>`** - Remove
```bash
rm /tags/physics/abc123                     # Remove tag link
rm /chats/abc123/                           # Delete conversation (with confirmation)
```

**`ln -s <target> <link>`** - Create symlink
```bash
ln -s /chats/abc123/ ~/important/           # Link to home
ln -s /chats/abc123/ /tags/physics/         # Add tag
```

**`mkdir <path>`** - Create directory
```bash
mkdir ~/projects/quantum/                   # Create directory
mkdir /tags/research/ml/transformers/       # Create tag hierarchy
```

**`cat <file>`** - Display file contents
```bash
cat /chats/abc123/.title                    # Show title
cat /chats/abc123/m1/content.txt            # Show message
cat /system/config/model                    # Show current model
```

**`echo <text> > <file>`** - Write to file
```bash
echo "Physics Simulation Project" > /chats/abc123/.title
echo "quantum" >> /chats/abc123/.tags       # Append tag
echo "0.8" > /system/config/temperature     # Set temperature
```

### CTK-Specific Programs

**`chat <message>`** - Continue/fork conversation
```bash
cd /chats/abc123/m5/
chat "what about edge cases?"               # Creates m5/m12/
```

Context-aware:
- At conversation root: starts new conversation
- At message node: creates child message (fork if multiple children)
- In `/tmp/`: creates temporary conversation

**`regenerate`** - Regenerate current message
```bash
cd /chats/abc123/m2/
regenerate                                  # Creates m2's sibling (m3)
```

**`edit <content>`** - Edit current message
```bash
cd /chats/abc123/m1/
edit "Hello, I need help with quantum mechanics"
```

**`fork [message]`** - Explicitly fork at current position
```bash
cd /chats/abc123/m5/
fork "let me try a different approach"      # Creates m5/m12/ even if m5/m11/ exists
```

**`star`** - Star current conversation
```bash
cd /chats/abc123/
star                                        # Creates /starred/abc123 -> /chats/abc123/
```

**`unstar`** - Remove from starred
```bash
cd /starred/abc123/
unstar                                      # Removes symlink
```

**`pin`** - Pin conversation
**`unpin`** - Unpin conversation
**`archive`** - Archive conversation
**`unarchive`** - Unarchive conversation

**`tag add <tags>`** - Add tags to conversation
```bash
cd /chats/abc123/
tag add physics quantum simulation
# Creates /tags/physics/abc123, /tags/quantum/abc123, etc.
```

**`tag remove <tags>`** - Remove tags
```bash
tag remove physics
```

**`tag list`** - List tags for current conversation
```bash
cd /chats/abc123/
tag list
# physics
# quantum
# simulation
```

**`search <query>`** - Search conversations
```bash
search quantum                              # Creates /search/quantum/
cd /search/quantum/
ls -l                                       # Shows results
```

**`ask <query>`** - Natural language query (LLM-powered)
```bash
ask "show me starred conversations about physics"
```

**`import <format> <file> [dest]`** - Import conversations
```bash
import openai conversations.json /chats/
import markdown discussion.md /tmp/
```

**`export <format> <src> <file>`** - Export conversations
```bash
export markdown /chats/abc123/ output.md
export json /chats/abc123/m5/ branch.json   # Export subtree
```

**`models`** - List available models
```bash
models
# ollama:llama3 (current)
# openai:gpt-4
# anthropic:claude-3
```

**`model <name>`** - Switch model
```bash
model openai:gpt-4
# Or: echo "openai:gpt-4" > /system/config/model
```

**`mcp <subcommand>`** - MCP server management
```bash
mcp add filesystem
mcp connect filesystem
mcp list
mcp tools
mcp call read_file /etc/hosts
```

**`rag <subcommand>`** - RAG operations
```bash
rag embeddings                              # Generate embeddings
rag similar abc123                          # Find similar conversations
# Or: ls /system/rag/similar/abc123/
```

### Shell Builtins

**`help [command]`** - Show help
```bash
help                                        # General help
help cd                                     # Help for specific command
```

**`quit`** / **`exit`** - Exit TUI

**`clear`** - Clear screen

**`history`** - Show command history

**`login <user>`** - Login as user
```bash
login alice
pwd                                         # /home/alice/
```

**`logout`** - Logout (returns to guest)

## Path Resolution Rules

### Absolute vs Relative Paths

- **Absolute**: Start with `/` (e.g., `/chats/abc123/m5/`)
- **Relative**: Don't start with `/` (e.g., `m5/`, `../m3/`)
- **Home**: `~` expands to current user's home (e.g., `/home/alice/`)
- **Special**: `.` (current), `..` (parent)

### Resolution Algorithm

1. If path starts with `/`, it's absolute
2. If path starts with `~`, expand to home directory
3. Otherwise, resolve relative to `pwd`
4. Normalize by resolving `.` and `..`

### Examples

```bash
pwd                                         # /chats/abc123/m5/

cd m6/                                      # /chats/abc123/m5/m6/
cd ../m3/                                   # /chats/abc123/m3/
cd ../../def456/                            # /chats/def456/
cd /tags/physics/                           # /tags/physics/
cd ~/important/                             # /home/alice/important/
```

## Command vs Filesystem Disambiguation

When user types something like `cd abc123`:

1. **First**: Try as command (e.g., `cd` is a command with argument `abc123`)
2. **If command exists**: Execute command with arguments
3. **If command doesn't exist**: Error (unknown command)

When command is `cd`, `ls`, etc., the argument is always a path:
- Check if path exists in filesystem
- If not, error

### Precedence Rules

1. **Builtins** (`help`, `quit`, `exit`, `clear`, `history`) - Always commands
2. **Known commands** (in `/bin/` index) - Always commands
3. **Filesystem paths** - If command not found, check if it's a file/directory
4. **Error** - Unknown command or path

### Example

```bash
# "chat" is a known command
chat "hello"                                # Executes chat command

# Even if ~/chat/ exists:
cd ~/
mkdir chat/
chat "hello"                                # Still executes chat command, not cd to chat/

# To access the directory:
cd chat/                                    # Explicit path with /
cd ./chat/                                  # Explicit relative path
```

## User Management

### Default User

When no user is logged in, user is `guest`:
- `~` → `/home/guest/`
- Auto-created on first use
- Temporary (may be cleared on exit)

### Login/Logout

```bash
login alice                                 # Create or switch to alice
pwd                                         # /home/alice/

logout                                      # Back to guest
```

### User Home Directory

Each user has a home directory in `/home/<username>/`:
- Personal organization (directories, links)
- User preferences (`.bashrc`, `.vimrc`, etc.)
- Custom workspaces

### Shared vs Personal

- **Shared**: `/chats/`, `/tags/`, `/starred/`, etc. - System-wide
- **Personal**: `/home/<user>/` - User-specific organization
- **Linking**: Users `ln -s` shared conversations into `~/` for personal views

### Example Workflow

```bash
# Alice's personal organization
login alice
cd ~
mkdir important/
mkdir projects/quantum/
mkdir projects/ml/

# Link important conversations
ln -s /chats/abc123/ important/
ln -s /chats/def456/ projects/quantum/

# Alice's view
ls ~/important/
# abc123/

# Bob's separate organization
login bob
cd ~
mkdir favorites/
ln -s /chats/abc123/ favorites/            # Same conversation, different organization

# Both see the same conversation data
cd ~/favorites/abc123/
cat .title                                  # Same title Alice sees
```

## Metadata Files

### Conversation Metadata

Dotfiles in conversation directory:

- **`.metadata`**: Complete metadata (JSON)
- **`.title`**: Conversation title (text)
- **`.tags`**: Tags (one per line)
- **`.source`**: Source (openai, anthropic, etc.)
- **`.model`**: Model used
- **`.created`**: Creation timestamp (ISO 8601)
- **`.updated`**: Last update timestamp
- **`.starred`**: "true" or "false"
- **`.pinned`**: "true" or "false"
- **`.archived`**: "true" or "false"

### Message Metadata

Dotfiles in message node directory:

- **`.role`**: Role (user, assistant, system)
- **`.timestamp`**: Message timestamp (ISO 8601)
- **`.model`**: Model used (if assistant)
- **`.metadata`**: Additional metadata (JSON)

### Reading/Writing Metadata

```bash
# Read
cat /chats/abc123/.title
# "Physics Simulation Discussion"

cat /chats/abc123/m1/.role
# "user"

# Write
echo "Quantum Mechanics Q&A" > /chats/abc123/.title
echo "0.9" > /system/config/temperature
```

## Virtual Directories

### `/search/` - Search Results

Created on-demand when `search` command is used:

```bash
search quantum
# Creates /search/quantum/

cd /search/quantum/
ls -l
# abc123 -> /chats/abc123/
# def456 -> /chats/def456/
```

Multiple searches coexist:
```bash
search "machine learning"
cd /search/
ls
# quantum/
# "machine learning"/
```

### `/system/rag/similar/` - Similar Conversations

Created on-demand for similarity queries:

```bash
rag similar abc123
# Or:
cd /system/rag/similar/abc123/
ls -l
# def456 -> /chats/def456/   (similarity: 0.95)
# xyz789 -> /chats/xyz789/   (similarity: 0.87)
```

### `/bin/` - Command Index

Virtual directory listing all available commands:

```bash
ls /bin/
# chat, search, star, pin, tag, import, export, models, mcp, rag, ...

cat /bin/chat
# Error: /bin/ files are not readable (just for listing)
```

## Advanced Features (Future)

### Piping

```bash
# Find conversations and tag them
ls /search/quantum/ | xargs tag add quantum-physics

# Export multiple conversations
find /tags/physics/ -type l | xargs export markdown output/
```

### Redirection

```bash
# Save search results
ls /search/quantum/ > results.txt

# Append to tag list
echo "new-tag" >> /chats/abc123/.tags
```

### Process Substitution

```bash
# Compare two conversation branches
diff <(cat /chats/abc123/m1/m2/content.txt) <(cat /chats/abc123/m1/m3/content.txt)
```

### Wildcards

```bash
# Tag all conversations in a directory
ln -s /starred/* /tags/important/

# Export all physics conversations
export markdown /tags/physics/* output/
```

## Implementation Phases

### Phase 1: Remove Slash Prefixes (1-2 days)
- 1a: Support both `/command` and `command`
- 1b: Add deprecation warnings for `/command`
- 1c: Remove slash support entirely

**Deliverable:** All commands work without slashes

### Phase 2: Unified Path Parser (2-3 days)
- Merge VFS path parsing with message tree paths
- Support `/chats/abc123/m5/` syntax
- Handle message node directories

**Deliverable:** Can parse full paths to message nodes

### Phase 3: Conversations as Directories (3-4 days)
- Implement `ls /chats/abc123/` to show messages
- Implement `cd /chats/abc123/m5/` navigation
- Update `tree` to work from current position
- Implement dotfiles (`.title`, `.tags`, etc.)

**Deliverable:** Can browse conversation trees via filesystem

### Phase 4: Chat Action from Message Nodes (2 days)
- Implement `chat <message>` to fork from current node
- Update chat logic to use `pwd` for context

**Deliverable:** Can chat from any point in tree

### Phase 5: System Directories (2-3 days)
- Implement `/system/config/`, `/system/models/`
- Make config files readable/writable
- Update model/config commands to use filesystem

**Deliverable:** Can configure via filesystem

### Phase 6: Advanced VFS Features (3-4 days)
- Implement `/search/` virtual directory
- Implement `/system/mcp/`, `/system/rag/`
- Implement `/tmp/` for temporary conversations
- Implement `/bin/` command index
- Implement `/home/` user directories

**Deliverable:** Full VFS ecosystem

### Phase 7: Cleanup & Documentation (2 days)
- Remove deprecated code
- Update all documentation
- Create migration guide
- Full integration test suite

**Deliverable:** Production-ready unified VFS

## Benefits

1. **Conceptual Unity**: One mental model for everything
2. **POSIX Compatibility**: Familiar to Unix/Linux users
3. **Composability**: Commands combine naturally
4. **Discoverability**: `ls` always shows options
5. **Power**: Standard tools work (find, grep, etc.)
6. **Extensibility**: Easy to add new virtual directories
7. **Scriptability**: Shell-like automation possible
8. **Natural**: Conversations as files feels intuitive
9. **Flexible**: Personal organization via user homes
10. **Future-proof**: Piping, redirection, wildcards possible

## Design Principles

1. **Uniformity above all**: If a feature breaks expectations, drop it
2. **Commands take precedence**: `chat` is always a command, even if `~/chat/` exists
3. **Filesystem second**: If not a command, check filesystem
4. **Shared by default**: `/chats/` is system-wide storage
5. **Personal organization**: Users link into `~/` for views
6. **Virtual is real**: `/search/`, `/system/` navigate like real directories
7. **Dotfiles for metadata**: Hidden files for conversation/message properties
8. **Symlinks for organization**: Tags, starred, etc. are symlinks
9. **Read-only views**: `/starred/`, `/recent/`, etc. are computed views
10. **Mutable only in `/tags/`** and `/home/`: Write operations restricted

## See Also

- **VFS Core**: `docs/VFS_DESIGN.md`
- **Phase 3 Navigation**: `docs/VFS_PHASE3_IMPLEMENTATION.md`
- **Phase 4 Tag Operations**: `docs/VFS_PHASE4_IMPLEMENTATION.md`
- **Path Parser**: `ctk/core/vfs.py`
- **Navigator**: `ctk/core/vfs_navigator.py`
- **Database**: `ctk/core/database.py`
