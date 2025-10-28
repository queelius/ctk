# VFS Phase 3: Navigation Commands Implementation

## Overview

Implemented `/cd`, `/pwd`, and `/ls` commands for navigating the virtual filesystem in the TUI. Users can now browse conversations using POSIX-like commands with hierarchical tags, filters, and metadata views.

## Commands Implemented

### `/cd [path]` - Change Directory

Changes the current working directory in the VFS.

**Features:**
- Absolute paths: `/cd /tags/physics/simulator`
- Relative paths: `/cd ../quantum`, `/cd physics`
- Special paths: `/cd .` (current), `/cd ..` (parent)
- Error handling for non-existent or non-directory paths

**Examples:**
```bash
/cd /tags/physics           # Absolute path
/cd physics/simulator       # Relative from current dir
/cd ../quantum             # Parent then quantum
/cd /starred               # View starred conversations
/cd /                      # Back to root
```

### `/pwd` - Print Working Directory

Shows current location in the VFS.

**Example:**
```bash
/pwd
# Output: /tags/physics/simulator
```

### `/ls [-l] [path]` - List Directory

Lists contents of a directory.

**Features:**
- Simple format: Directories with `/`, files with flags
- Long format (`-l`): Rich table with metadata
- Shows: name, type, title, tags, modified date
- Flags: ⭐ (starred), 📌 (pinned), 📦 (archived)

**Examples:**
```bash
/ls                    # Current directory, simple format
/ls -l                 # Current directory, long format with metadata
/ls /tags/physics      # Specific directory
/ls -l /starred        # Starred conversations with details
```

**Simple Format Output:**
```
physics/  quantum/  simulator/
abc123 ⭐  def456 📌  xyz789
```

**Long Format Output:**
```
┏━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Name      ┃ Type ┃ Title              ┃ Tags        ┃ Modified   ┃
┡━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ physics/  │ dir  │                    │             │            │
│ quantum/  │ dir  │                    │             │            │
│ abc123 ⭐ │ file │ Quantum mechanics  │ physics, qm │ 2025-01-15 │
│ def456    │ file │ Simulator basics   │ simulation  │ 2025-01-14 │
└───────────┴──────┴────────────────────┴─────────────┴────────────┘
```

## Implementation Details

### VFS Navigator (`ctk/core/vfs_navigator.py`)

**New module** providing directory listing functionality:

**`VFSNavigator` class:**
- `list_directory(vfs_path)` - Main entry point, routes to specific handlers
- `_list_root()` - Lists root directories (chats, tags, starred, etc.)
- `_list_chats()` - Lists all conversations
- `_list_tags_root()` - Lists top-level tags
- `_list_tag_directory(tag_path)` - Lists tag subdirectories and conversations
- `_list_starred()` - Lists starred conversations
- `_list_pinned()` - Lists pinned conversations
- `_list_archived()` - Lists archived conversations
- `_list_recent(segments)` - Lists time-based views (today, this-week, etc.)
- `_list_source(segments)` - Lists conversations by source (openai, anthropic, etc.)
- `_list_model(segments)` - Lists conversations by model (gpt-4, claude-3, etc.)

**`VFSEntry` dataclass:**
Represents an entry in a directory listing:
```python
@dataclass
class VFSEntry:
    name: str
    is_directory: bool
    conversation_id: Optional[str]
    title: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    tags: Optional[List[str]]
    starred: bool
    pinned: bool
    archived: bool
    source: Optional[str]
    model: Optional[str]
```

### TUI Integration (`ctk/integrations/chat/tui.py`)

**State management:**
```python
class ChatTUI:
    vfs_cwd: str = "/"  # Current VFS directory
    vfs_navigator = None  # Lazy-initialized VFSNavigator
```

**Command handlers:**

1. **`handle_cd(args)`**
   - Parses path (absolute or relative)
   - Validates it's a directory
   - Updates `self.vfs_cwd`
   - Error handling for invalid paths

2. **`handle_pwd()`**
   - Simply prints `self.vfs_cwd`

3. **`handle_ls(args)`**
   - Parses `-l` flag and optional path
   - Defaults to current directory
   - Gets entries from `VFSNavigator`
   - Displays in simple or long format
   - Uses Rich tables for long format

**Lazy initialization:**
```python
def _ensure_vfs_navigator(self):
    if self.vfs_navigator is None:
        if not self.db:
            raise ValueError("Database required for VFS commands")
        from ctk.core.vfs_navigator import VFSNavigator
        self.vfs_navigator = VFSNavigator(self.db)
```

### Help System

Added comprehensive help for all three commands:

**COMMAND_HELP entries:**
- `cd` - Full description with examples
- `pwd` - Brief description
- `ls` - Options and usage examples

**General help section:**
```
Virtual Filesystem:
  /cd [path]         - Change directory (/tags/physics, ../quantum, /starred)
  /pwd               - Print working directory
  /ls [-l] [path]    - List directory contents (-l for long format)
  Use '/help cd', '/help pwd', or '/help ls' for details
```

## Directory Types

### Mutable: `/tags/*`
Directories where tags can be added/modified (Phase 4):
- `/tags/`
- `/tags/physics/`
- `/tags/physics/simulator/`
- etc.

### Read-Only Views: All Others
Dynamic views of conversations filtered by criteria:
- `/chats/` - All conversations
- `/starred/` - Starred conversations
- `/pinned/` - Pinned conversations
- `/archived/` - Archived conversations
- `/recent/` - Time-based views
  - `/recent/today/`
  - `/recent/this-week/`
  - `/recent/this-month/`
  - `/recent/older/`
- `/source/` - Grouped by source
  - `/source/openai/`
  - `/source/anthropic/`
- `/model/` - Grouped by model
  - `/model/gpt-4/`
  - `/model/claude-3/`

## Usage Examples

### Example 1: Explore Tags

```bash
/pwd
# Output: /

/ls
# Output: chats/  tags/  starred/  pinned/  archived/  recent/  source/  model/

/cd tags
/ls
# Output: physics/  programming/  research/

/cd physics
/ls
# Output: simulator/  quantum/  classical/

/cd simulator
/ls -l
# Output: Table showing conversations tagged with physics/simulator
```

### Example 2: View Starred Conversations

```bash
/cd /starred
/ls -l
# Output: Table showing all starred conversations with metadata
```

### Example 3: Navigate with Relative Paths

```bash
/cd /tags/physics/simulator
/pwd
# Output: /tags/physics/simulator

/cd ../quantum
/pwd
# Output: /tags/physics/quantum

/cd ../../programming
/pwd
# Output: /tags/programming
```

### Example 4: Time-Based Browsing

```bash
/cd /recent/today
/ls
# Output: Conversations modified today

/cd ../this-week
/ls -l
# Output: Table of conversations from this week
```

## Error Handling

### Invalid Path
```bash
/cd /nonexistent
# Output: Error: Unknown filesystem root: /nonexistent
```

### Not a Directory
```bash
/cd /chats/abc123
# Output: Error: Not a directory: /chats/abc123
```

### Database Not Available
```bash
/cd /tags
# Output: Error: Database required for VFS commands
```

### Empty Directory
```bash
/cd /tags/emptydir
/ls
# Output: (empty)
```

## Performance Considerations

### Caching
- VFS navigator is lazy-initialized once
- Directory listings query database fresh each time
- No caching of listings (ensures up-to-date data)

### Database Queries
- `/chats/`: Full table scan (cached in DB)
- `/tags/`: Queries tag table
- `/starred/`: Filtered query (indexed)
- `/recent/`: Full scan with date filtering
- `/source/`, `/model/`: Full scan with grouping

For large databases (>10K conversations), listings may be slow. Future optimization: add pagination or limits.

## Integration with Existing Features

### Works With
- `/star`, `/pin`, `/archive` - Change conversation status, visible in `/ls` flags
- `/tag` - Add tags, visible in `/tags/*` directories
- `/load` - Can load conversations found via `/ls`

### Complements
- `/list` - CLI-style flat list
- `/search` - Keyword search
- `/browse` - Interactive table browser

## Files Modified

1. **`ctk/core/vfs_navigator.py`** (NEW - 368 lines)
   - VFSNavigator class
   - VFSEntry dataclass
   - Directory listing handlers for all path types

2. **`ctk/integrations/chat/tui.py`**
   - Added VFS state: `vfs_cwd`, `vfs_navigator` (lines 93-95)
   - Added command handlers: `handle_cd`, `handle_pwd`, `handle_ls` (lines 3678-3831)
   - Added help entries for cd, pwd, ls (lines 510-557)
   - Updated general help (lines 673-677)
   - Added command routing (lines 1044-1051)

## Benefits

1. **Familiar Interface**: Unix/Linux users feel at home
2. **Hierarchical Organization**: Navigate complex tag structures
3. **Multiple Views**: Same conversations accessible multiple ways
4. **Rich Metadata**: See titles, tags, dates at a glance
5. **Stateful Navigation**: Remember current location between commands

## Next Steps

With navigation complete, the remaining work is:

- **Phase 4**: Tag operations (`/cp`, `/mv`, `/rm`, `/mkdir`)
- **Phase 5**: Tab completion for paths
- **Future**: Wildcards, find command, advanced filtering

## Testing

To test the implementation:

```bash
# Start TUI with database
ctk chat --db /path/to/db

# In TUI:
/pwd                      # Should show /
/ls                       # Should show root directories
/cd /tags                 # Navigate to tags
/ls                       # Show tag hierarchy
/ls -l                    # Show with metadata
/cd /starred              # View starred conversations
/ls -l                    # Show starred with details
/cd ../recent/today       # Relative path navigation
/pwd                      # Should show /recent/today
```

## See Also

- **Design Document**: `docs/VFS_DESIGN.md`
- **Path Parser**: `ctk/core/vfs.py`
- **Navigator**: `ctk/core/vfs_navigator.py`
- **Database Methods**: `ctk/core/database.py` (hierarchical tag methods)
