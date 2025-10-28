# Virtual Filesystem Design for CTK

## Overview

CTK implements a POSIX-like virtual filesystem for navigating conversations using hierarchical tags, filters, and metadata views. This enables shell-like navigation with commands like `cd`, `ls`, `cp`, `mv`, and `rm`.

## Filesystem Structure

```
/
├── chats/           # Flat list of all conversations (read-only for cp/mv)
│   ├── <hash1>
│   ├── <hash2>
│   └── ...
├── tags/            # Hierarchical tag namespace (MUTABLE)
│   ├── physics/
│   │   ├── simulator/
│   │   │   ├── molecular/
│   │   │   │   ├── <hash1>
│   │   │   │   └── <hash2>
│   │   │   └── fluid/
│   │   │       └── <hash3>
│   │   └── quantum/
│   │       └── <hash4>
│   └── programming/
│       ├── python/
│       └── cpp/
├── starred/         # Starred conversations (read-only view)
├── pinned/          # Pinned conversations (read-only view)
├── archived/        # Archived conversations (read-only view)
├── recent/          # Time-based views (read-only)
│   ├── today/
│   ├── this-week/
│   ├── this-month/
│   └── older/
├── source/          # Grouped by conversation source (read-only)
│   ├── openai/
│   ├── anthropic/
│   └── gemini/
└── model/           # Grouped by model (read-only)
    ├── gpt-4/
    ├── claude-3/
    └── ...
```

## Path Semantics

### Absolute vs Relative Paths

- **Absolute**: Start with `/` (e.g., `/tags/physics/simulator`)
- **Relative**: Don't start with `/` (e.g., `../quantum`, `./abc123`)
- **Special**: `.` (current directory), `..` (parent directory)

### Path Resolution

All paths are normalized before use:

```python
VFSPathParser.normalize_path("../../chats/", current_dir="/tags/physics/simulator/")
# Returns: "/tags/chats"

VFSPathParser.normalize_path("./abc123", current_dir="/starred/")
# Returns: "/starred/abc123"
```

### Path Types

Each parsed path has a type:

- `ROOT` - `/`
- `CHATS` - `/chats/` directory
- `TAGS` - `/tags/` directory
- `TAG_DIR` - `/tags/physics/` (tag directory)
- `CONVERSATION` - `/chats/abc123` or `/tags/physics/abc123`
- `STARRED` - `/starred/` directory
- `PINNED` - `/pinned/` directory
- `ARCHIVED` - `/archived/` directory
- `RECENT` - `/recent/*` directories
- `SOURCE` - `/source/*` directories
- `MODEL` - `/model/*` directories

## Mutable vs Read-Only Directories

### Mutable: `/tags/*`

Operations allowed:
- ✅ `cd`, `ls` - Navigate and list
- ✅ `cp <src> /tags/path/` - Add tag to conversation
- ✅ `mv /tags/old/ /tags/new/` - Change tags
- ✅ `rm /tags/path/conv` - Remove tag from conversation
- ✅ `mkdir /tags/new/hierarchy/` - Create tag structure

### Read-Only: Everything Else

Operations allowed:
- ✅ `cd`, `ls` - Navigate and list
- ✅ `cp /starred/abc123 /tags/important/` - Copy from view to tags
- ❌ `cp /chats/abc123 /starred/` - Cannot modify read-only views
- ❌ `mv /starred/abc123 ...` - Cannot move from read-only
- ❌ `rm /starred/abc123` - Cannot delete from views

**Special case for /chats/:**
- ✅ `rm /chats/abc123` - Actually deletes conversation (with confirmation)
- ❌ `cp ... /chats/` - Cannot copy into flat list

## Tag Hierarchy

Tags use `/` separator for hierarchy:

```
"physics"              # Top-level tag
"physics/simulator"    # Subtag of physics
"physics/simulator/molecular"  # Nested subtag
```

**Storage**: Tags are stored as full path strings in database:
- Simple implementation
- Flexible (any depth)
- Efficient queries

**Examples**:
```python
db.add_tag(conversation_id, "physics/simulator/molecular")
# Adds single tag with full path

db.list_tag_children("physics")
# Returns: ["simulator", "quantum", "classical"]

db.list_conversations_by_tag("physics/simulator")
# Returns all conversations with exact tag "physics/simulator"
```

## Command Semantics

### Navigation Commands

**`/cd <path>`**
- Change current working directory
- Updates shell context
- Example: `/cd /tags/physics/simulator/`

**`/pwd`**
- Print working directory
- Example: `/pwd` → `/tags/physics/simulator`

**`/ls [path]`**
- List directory contents
- Default: current directory
- `-l` flag: Show metadata (title, date, tags)
- Example: `/ls -l /tags/physics/`

### File Operation Commands

**`/cp <src> <dest>`**

Semantics depend on source and destination:

| Source | Destination | Effect |
|--------|-------------|--------|
| `/chats/abc123` | `/tags/physics/` | Adds tag "physics" to abc123 |
| `/tags/old/abc123` | `/tags/new/` | Adds tag "new" (keeps "old") |
| `/starred/abc123` | `/tags/important/` | Adds tag "important" |

**`/mv <src> <dest>`**

Move conversation between tags:

```bash
/mv /tags/physics/abc123 /tags/quantum/
# Removes tag "physics", adds tag "quantum"
```

**`/rm <path>`**

Remove tag or delete conversation:

```bash
/rm /tags/physics/abc123
# Removes tag "physics" from abc123

/rm /chats/abc123
# Actually DELETES conversation (with confirmation!)
```

**`/mkdir <path>`**

Create tag hierarchy (doesn't actually create anything, just allows cd):

```bash
/mkdir /tags/research/ml/transformers/
# Creates conceptual hierarchy
# Tags are created when conversations are added
```

## Conversation References

Conversations appear in multiple locations simultaneously (like hardlinks):

```
/chats/abc123              # Original location
/tags/physics/abc123       # Also appears here (has tag "physics")
/tags/quantum/abc123       # And here (has tag "quantum")
/starred/abc123            # And here (is starred)
```

All references point to the same conversation. Modifying metadata in one location affects all views.

## Implementation

### Core Modules

**`ctk/core/vfs.py`**: Virtual filesystem
- `VFSPath` - Parsed path dataclass
- `VFSPathParser` - Path parsing and normalization
- `PathType` - Enum of path types
- Helper methods: `is_read_only()`, `can_delete()`

**`ctk/core/database.py`**: Hierarchical tag support
- `list_tag_children(parent_tag)` - List immediate children
- `list_conversations_by_tag(tag_path)` - Get conversations
- `get_all_hierarchical_tags()` - List all tag paths

### TUI Integration (Upcoming)

**State management**:
```python
class ChatTUI:
    current_dir: str = "/"  # Current working directory

    def handle_cd(self, path: str):
        vfs_path = VFSPathParser.parse(path, self.current_dir)
        if vfs_path.is_directory:
            self.current_dir = vfs_path.normalized_path
```

**Command handlers**:
- `/cd` - Change directory
- `/pwd` - Print working directory
- `/ls` - List contents
- `/cp` - Copy/add tags
- `/mv` - Move/change tags
- `/rm` - Remove tag or delete
- `/mkdir` - Create tag hierarchy

## Examples

### Example Workflow

```bash
# Start at root
/pwd
# Output: /

# Navigate to tags
/cd /tags/
/ls
# Output: physics  programming  research

# Go into physics
/cd physics/
/ls
# Output: simulator  quantum  classical

# List conversations in simulator
/cd simulator/
/ls -l
# Output:
# abc123  "Molecular dynamics simulation"  2025-01-15
# def456  "Fluid simulation basics"        2025-01-14

# Copy conversation to different tag
/cp abc123 ../../quantum/
# Now abc123 has both tags: physics/simulator AND physics/quantum

# Move conversation between tags
/mv abc123 /tags/archived/
# Removes physics/simulator tag, adds archived tag

# View starred conversations
/cd /starred/
/ls
# Output: All starred conversation IDs

# Copy starred to important tag
/cp xyz789 /tags/important/
# Adds "important" tag to starred conversation

# Return to root
/cd /
```

### Tab Completion (Future)

```bash
/cd /tags/ph<TAB>
# Completes to: /cd /tags/physics/

/cd physics/si<TAB>
# Completes to: /cd physics/simulator/

/cp /chats/ab<TAB>
# Shows all conversation IDs starting with "ab"
```

## Design Principles

1. **POSIX-like**: Familiar to Unix/Linux users
2. **Consistent**: Same semantics across commands
3. **Safe**: Read-only views prevent accidents
4. **Flexible**: Hierarchical tags allow organization
5. **Intuitive**: Natural mental model (file = conversation, directory = category)

## Benefits

1. **Powerful Navigation**: Navigate conversations like files
2. **Tag Organization**: Hierarchical structure for complex taxonomies
3. **Multiple Views**: Same conversation accessible multiple ways
4. **Batch Operations**: Unix tools semantics enable powerful workflows
5. **Mental Model**: Familiar to developers (POSIX filesystem)

## Future Enhancements

1. **Wildcards**: `/cp /tags/physics/* /tags/archived/`
2. **Find Command**: `/find "quantum" --type conversation`
3. **Symlinks**: `/ln -s /chats/abc123 /tags/physics/important`
4. **Permissions**: Role-based access control
5. **Mount Points**: External conversation sources

## See Also

- `ctk/core/vfs.py` - Virtual filesystem implementation
- `ctk/core/database.py` - Hierarchical tag database methods
- `ctk/integrations/chat/tui.py` - TUI command handlers (upcoming)
