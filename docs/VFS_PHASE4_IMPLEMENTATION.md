# VFS Phase 4: Tag Operations Implementation

## Overview

Implemented `/ln`, `/cp`, `/mv`, `/rm`, and `/mkdir` commands for tag manipulation in the virtual filesystem. These commands provide POSIX-like file operations with semantics tailored for conversation management.

## Commands Implemented

### `/ln <src> <dest>` - Link (Add Tag)

Links a conversation to a tag directory, creating a hardlink-like relationship.

**Features:**
- Adds tag to conversation without removing existing tags
- Source must be a conversation (from any directory)
- Destination must be a `/tags/*` directory
- Same conversation appears in multiple tag directories
- Like POSIX hardlinks - editing conversation affects all views

**Examples:**
```bash
/ln /chats/abc123 /tags/physics/
# Adds "physics" tag to conversation abc123

/ln /starred/xyz789 /tags/important/
# Adds "important" tag to starred conversation xyz789

/ln abc123 /tags/research/ml/
# Adds "research/ml" tag (relative path from current dir)
```

**Semantics:**
- Creates hardlink: same conversation, multiple paths
- Non-destructive: doesn't remove existing tags
- Read-only views (starred, recent, etc.) can be source
- Only `/tags/*` can be destination

### `/cp <src> <dest>` - Copy (Deep Copy)

Creates a complete copy of a conversation with a new auto-generated UUID.

**Features:**
- Deep copy: new UUID, all messages copied
- Independent copy: editing one doesn't affect the other
- Copies all messages and tags
- Title gets " (copy)" suffix
- Doesn't copy starred/pinned/archived status
- Destination can optionally be a `/tags/*` directory

**Examples:**
```bash
/cp /chats/abc123 /tags/backup/
# Creates copy with new UUID, tagged with "backup"
# Output: Copied conversation -> <new-uuid>

/cp /tags/test/xyz789 /tags/production/
# Copies conversation from test to production tag
```

**Semantics:**
- True copy: different IDs, independent conversations
- All messages duplicated with new UUIDs
- Tags copied to new conversation
- Status flags (starred, pinned, archived) NOT copied
- Timestamps reset to current time

### `/mv <src> <dest>` - Move Between Tags

Moves a conversation from one tag to another by removing old tag and adding new tag.

**Features:**
- Changes tags while keeping same conversation ID
- Source must be from `/tags/*`
- Destination must be to `/tags/*`
- Removes old tag, adds new tag
- Atomic operation with rollback on failure

**Examples:**
```bash
/mv /tags/draft/abc123 /tags/final/
# Removes "draft" tag, adds "final" tag

/mv /tags/physics/old/xyz789 /tags/physics/new/
# Moves from physics/old to physics/new
```

**Semantics:**
- Same conversation, different tags
- NOT a copy: conversation ID unchanged
- Source tag removed, destination tag added
- Transactional: rollback if add fails

### `/rm <path>` - Remove Tag or Delete Conversation

Two modes of operation depending on path type.

**Features:**
- `/rm /tags/path/conv` - Removes tag from conversation (non-destructive)
- `/rm /chats/conv` - Permanently deletes conversation (with confirmation)
- Cannot remove from read-only directories
- Confirmation required for deletion from `/chats/`

**Examples:**
```bash
/rm /tags/physics/abc123
# Removes "physics" tag from conversation abc123

/rm /chats/xyz789
# Prompts: "WARNING: This will permanently delete conversation: <title>"
# User must type 'yes' to confirm
# Output: Deleted conversation: xyz789
```

**Semantics:**
- `/tags/*` - Remove tag only (conversation remains)
- `/chats/*` - Delete conversation entirely
- Read-only directories - Error (cannot modify)
- Directories - Error (auto-cleaned when empty)

### `/mkdir <path>` - Create Tag Hierarchy

Creates a conceptual tag hierarchy in `/tags/*`.

**Features:**
- Conceptual operation: doesn't create actual entities
- Directories appear when conversations are tagged
- No need to create before tagging
- Mainly for documentation/organization

**Examples:**
```bash
/mkdir /tags/research/ml/transformers/
# Output: Created tag hierarchy: research/ml/transformers
#         Note: This is conceptual - the directory will appear when conversations are tagged

/mkdir /tags/projects/new-feature/
# Creates conceptual hierarchy
```

**Semantics:**
- Purely conceptual: no database changes
- Directories auto-appear when tags used
- Informational command for organization
- Cannot create outside `/tags/*`

## Implementation Details

### Database Methods (`ctk/core/database.py`)

**`remove_tag(conversation_id: str, tag_name: str) -> bool`** (lines 818-846)

Removes a specific tag from a conversation.

```python
def remove_tag(self, conversation_id: str, tag_name: str) -> bool:
    """
    Remove a tag from a conversation.

    Args:
        conversation_id: ID of conversation
        tag_name: Tag name to remove

    Returns:
        True if successful, False if conversation or tag not found
    """
    with self.session_scope() as session:
        conv_model = session.get(ConversationModel, conversation_id)
        if not conv_model:
            return False

        tag = session.query(TagModel).filter_by(name=tag_name).first()
        if not tag:
            return False

        if tag in conv_model.tags:
            conv_model.tags.remove(tag)
            conv_model.updated_at = datetime.now()
            session.commit()
            return True

        return False
```

**Key aspects:**
- Validates conversation and tag exist
- Only removes if tag is actually attached
- Updates conversation timestamp
- Returns False if tag wasn't attached

**`duplicate_conversation(conversation_id: str) -> Optional[str]`** (lines 848-906)

Deep copies a conversation with a new auto-generated UUID.

```python
def duplicate_conversation(self, conversation_id: str) -> Optional[str]:
    """
    Deep copy a conversation with a new auto-generated UUID.

    Args:
        conversation_id: ID of conversation to duplicate

    Returns:
        New conversation ID if successful, None otherwise
    """
    with self.session_scope() as session:
        original = session.get(ConversationModel, conversation_id)
        if not original:
            return None

        # Generate new UUID
        import uuid
        new_id = str(uuid.uuid4())

        # Create new conversation model
        new_conv = ConversationModel(
            id=new_id,
            title=f"{original.title} (copy)" if original.title else None,
            source=original.source,
            model=original.model,
            project=original.project,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            starred=False,  # Don't copy starred status
            pinned=False,   # Don't copy pinned status
            archived=False, # Don't copy archived status
            starred_at=None,
            pinned_at=None,
            archived_at=None
        )

        # Copy all messages
        for msg in original.messages:
            new_msg = MessageModel(
                id=str(uuid.uuid4()),
                conversation_id=new_id,
                role=msg.role,
                content=msg.content,
                parent_id=msg.parent_id,
                timestamp=msg.timestamp,
                model=msg.model,
                metadata_=msg.metadata_
            )
            new_conv.messages.append(new_msg)

        # Copy all tags
        for tag in original.tags:
            new_conv.tags.append(tag)

        session.add(new_conv)
        session.commit()

        return new_id
```

**Key aspects:**
- Generates fresh UUIDs for conversation and all messages
- Appends " (copy)" to title
- Resets timestamps to current time
- Does NOT copy starred/pinned/archived status
- Copies all tags
- Returns new conversation ID

### TUI Command Handlers (`ctk/integrations/chat/tui.py`)

**`handle_ln(args)`** (lines 3888-3942)

Links conversation to tag directory.

**Process:**
1. Parse source and destination paths
2. Validate source is a conversation (not directory)
3. Validate destination is a `/tags/*` directory
4. Extract tag name from destination path
5. Call `db.add_tags()` to add tag
6. Print confirmation

**Error handling:**
- Source is directory → Error
- Destination not directory → Error
- Destination not `/tags/*` → Error (read-only)
- Destination is `/tags/` (no specific tag) → Error

**`handle_cp(args)`** (lines 3944-3998)

Copies conversation with new UUID.

**Process:**
1. Parse source and destination paths
2. Validate source is a conversation
3. Validate destination is directory
4. Call `db.duplicate_conversation()` to create copy
5. If destination is specific tag directory, add tag
6. Print new conversation ID

**Error handling:**
- Source is directory → Error
- Destination not directory → Error
- Destination not `/tags/*` → Error (read-only)
- Duplication fails → Error

**`handle_mv(args)`** (lines 4000-4065)

Moves conversation between tags.

**Process:**
1. Parse source and destination paths
2. Validate source is conversation from `/tags/*`
3. Validate destination is `/tags/*` directory
4. Extract old and new tag names
5. Remove old tag
6. Add new tag
7. Rollback if add fails

**Error handling:**
- Source not from `/tags/*` → Error
- Source is directory → Error
- Destination not `/tags/*` → Error
- Remove fails → Error
- Add fails → Rollback (re-add old tag)

**`handle_rm(args)`** (lines 4067-4135)

Removes tag or deletes conversation.

**Process:**
1. Parse path
2. If `/chats/conv_id`:
   - Prompt for confirmation
   - Delete conversation if confirmed
3. If `/tags/path/conv_id`:
   - Remove tag from conversation
4. Otherwise:
   - Error (read-only or invalid path)

**Error handling:**
- Path is directory → Error
- Path is conversation in read-only view → Error
- Deletion not confirmed → Cancelled
- Remove/delete fails → Error

**`handle_mkdir(args)`** (lines 4137-4173)

Creates conceptual tag hierarchy.

**Process:**
1. Parse path
2. Validate path is in `/tags/*`
3. Print confirmation message
4. Note that directory is conceptual

**Error handling:**
- Path not in `/tags/*` → Error
- Path is just `/tags/` → Note (already exists)

### Command Routing (`ctk/integrations/chat/tui.py`)

Added routing for all commands (lines 1108-1121):

```python
elif cmd == '/ln':
    self.handle_ln(args)

elif cmd == '/cp':
    self.handle_cp(args)

elif cmd == '/mv':
    self.handle_mv(args)

elif cmd == '/rm':
    self.handle_rm(args)

elif cmd == '/mkdir':
    self.handle_mkdir(args)
```

### Help System

**COMMAND_HELP entries** (lines 558-617):

Added detailed help for all five commands:
- `ln` - Usage, description, details, examples
- `cp` - Deep copy semantics explained
- `mv` - Move between tags
- `rm` - Two modes (remove tag vs delete)
- `mkdir` - Conceptual hierarchy creation

**General help** (lines 733-742):

Updated VFS section:
```
Virtual Filesystem:
  /cd [path]           - Change directory (/tags/physics, ../quantum, /starred)
  /pwd                 - Print working directory
  /ls [-l] [path]      - List directory contents (-l for long format)
  /ln <src> <dest>     - Link conversation to tag (add tag)
  /cp <src> <dest>     - Copy conversation (deep copy with new UUID)
  /mv <src> <dest>     - Move conversation between tags
  /rm <path>           - Remove tag or delete conversation
  /mkdir <path>        - Create tag hierarchy (conceptual)
  Use '/help <command>' for details on any VFS command
```

## Command Semantics Summary

### Hardlink vs Copy Semantics

**Hardlink (`/ln`):**
- Same conversation, multiple tag paths
- Editing affects all views
- Like POSIX hardlinks

**Copy (`/cp`):**
- Different conversation IDs
- Independent editing
- Like POSIX copy

**Move (`/mv`):**
- Same conversation, different tag
- Like renaming tag
- Source tag removed

### Read-Only vs Mutable Directories

**Mutable: `/tags/*`**
- ✅ `/ln <any> /tags/path/` - Add tag
- ✅ `/cp <any> /tags/path/` - Copy and tag
- ✅ `/mv /tags/old/ /tags/new/` - Move tags
- ✅ `/rm /tags/path/conv` - Remove tag
- ✅ `/mkdir /tags/path/` - Create hierarchy

**Read-Only: Everything Else**
- ✅ Can be SOURCE for `/ln`, `/cp`
- ❌ Cannot be DESTINATION for modifications
- ❌ Cannot `/rm` from these directories
- ✅ `/rm /chats/conv` - Special case (delete)

### Special Cases

**Deleting from `/chats/`:**
- `/rm /chats/conv_id` - Permanently deletes
- Requires typing "yes" to confirm
- Destructive operation

**Directory removal:**
- Cannot directly remove directories
- Directories auto-removed when empty
- Tags removed when no conversations have them

**Conceptual directories:**
- `/mkdir` creates conceptual hierarchy
- Directories appear when tagged
- No database changes for `/mkdir`

## Usage Examples

### Example 1: Organize with Tags

```bash
# Start in root
/pwd
# Output: /

# Navigate to tags
/cd /tags/
/ls
# Output: (empty or existing tags)

# Link conversations to tags
/ln /chats/abc123 /tags/physics/
/ln /chats/def456 /tags/physics/
/ln /chats/abc123 /tags/quantum/
# Now abc123 has both tags: physics and quantum

# View physics conversations
/cd physics/
/ls -l
# Shows abc123, def456 with metadata
```

### Example 2: Backup and Experiment

```bash
# Create backup copy before experimenting
/cp /chats/important-123 /tags/backup/
# Output: Copied conversation -> xyz789-new
#         Tagged with: backup

# Now we have:
# - Original: /chats/important-123
# - Backup: /chats/xyz789-new (also in /tags/backup/)

# Edit original without affecting backup
# If it works, delete backup
/rm /tags/backup/xyz789-new
# Removes backup tag

# If you want to delete the backup completely
/rm /chats/xyz789-new
# Prompts for confirmation, then deletes
```

### Example 3: Workflow Management

```bash
# Create tag hierarchy
/mkdir /tags/workflow/draft/
/mkdir /tags/workflow/review/
/mkdir /tags/workflow/approved/

# Tag new conversation as draft
/ln /chats/new-idea-123 /tags/workflow/draft/

# Move to review when ready
/mv /tags/workflow/draft/new-idea-123 /tags/workflow/review/

# Move to approved when done
/mv /tags/workflow/review/new-idea-123 /tags/workflow/approved/

# View approved conversations
/cd /tags/workflow/approved/
/ls -l
```

### Example 4: Tag Cleanup

```bash
# Remove obsolete tags
/cd /tags/old-project/
/ls
# Shows conversations with old-project tag

# Remove tag from each
/rm /tags/old-project/abc123
/rm /tags/old-project/def456

# Directory auto-removed when empty
/cd /tags/
/ls
# old-project no longer appears
```

## Error Handling

### Invalid Paths

```bash
/ln /nonexistent /tags/physics/
# Error: Unknown filesystem root: /nonexistent

/cp /chats/ /tags/backup/
# Error: Source must be a conversation, not a directory
```

### Permission Errors

```bash
/ln /chats/abc123 /starred/
# Error: Can only link to /tags/* directories (destination is read-only)

/rm /starred/abc123
# Error: Cannot remove from read-only directory: /starred/abc123
```

### Missing Entities

```bash
/rm /tags/physics/nonexistent-123
# Error: Failed to remove tag

/cp /chats/nonexistent /tags/backup/
# Error: Failed to duplicate conversation
```

### Confirmation Required

```bash
/rm /chats/abc123
# Output: WARNING: This will permanently delete conversation: Important Chat
#         Type 'yes' to confirm: no
#         Deletion cancelled

/rm /chats/abc123
# Output: WARNING: This will permanently delete conversation: Important Chat
#         Type 'yes' to confirm: yes
#         Deleted conversation: abc123
```

## Files Modified

1. **`ctk/core/database.py`**
   - Added `remove_tag()` method (lines 818-846)
   - Added `duplicate_conversation()` method (lines 848-906)

2. **`ctk/integrations/chat/tui.py`**
   - Added `handle_ln()` (lines 3888-3942)
   - Added `handle_cp()` (lines 3944-3998)
   - Added `handle_mv()` (lines 4000-4065)
   - Added `handle_rm()` (lines 4067-4135)
   - Added `handle_mkdir()` (lines 4137-4173)
   - Added command routing (lines 1108-1121)
   - Added COMMAND_HELP entries (lines 558-617)
   - Updated general help (lines 733-742)

## Benefits

1. **POSIX-like Operations**: Familiar file operations for conversations
2. **Flexible Organization**: Multiple tags per conversation
3. **Safe Copying**: Deep copy with independent editing
4. **Workflow Support**: Move conversations through stages
5. **Tag Management**: Add, remove, reorganize tags easily
6. **Safety**: Confirmation required for destructive operations
7. **Clear Semantics**: Hardlink vs copy clearly distinguished

## Design Decisions

### Why `/ln` instead of `/cp` for adding tags?

User feedback noted that using `/cp` to add tags was confusing because editing the "copy" would modify the original. Separated semantics:
- `/ln` - Hardlink (add tag, same conversation)
- `/cp` - True copy (new UUID, independent)

### Why auto-generate UUIDs for copies?

To avoid conflicts and user confusion. UUIDs are auto-generated:
- Prevents ID collisions
- Users don't need to track IDs
- System handles uniqueness

### Why not copy starred/pinned/archived status?

These are user-specific organization flags. Copies should start fresh:
- Starred: User's current favorites
- Pinned: User's current priorities
- Archived: Explicitly hidden conversations

Copying these would clutter organization.

### Why require confirmation for `/rm /chats/*`?

Deleting from `/chats/` is the ONLY destructive operation. Everything else is reversible:
- Remove tag → Can re-add tag
- Move tags → Can move back
- Delete conversation → PERMANENT

Confirmation prevents accidental data loss.

## Integration with Existing Features

### Works With

- `/cd`, `/pwd`, `/ls` - Navigate and view tagged conversations
- `/star`, `/pin`, `/archive` - Organize conversations (orthogonal to tags)
- `/load` - Load conversations found via `/ls`
- `/search` - Find conversations, then tag them
- `/browse` - Browse conversations, then tag them

### Complements

- `/tag` - Auto-tag with LLM (different from manual tagging)
- `/list` - CLI-style flat list
- Network analysis - Tags as graph nodes

## Next Steps

With tag operations complete, the remaining work is:

- **Phase 5**: Tab completion for paths (optional)
- **Future**: Wildcards (`/ln /starred/* /tags/important/`)
- **Future**: Find command (`/find "quantum" --type conversation`)
- **Future**: Batch operations (`/ln --batch <file>`)

## Testing

To test tag operations:

```bash
# Start TUI with database
ctk chat --db /path/to/db

# In TUI - test linking
/ln /chats/<some-id> /tags/test/
/ls /tags/test/
# Should show linked conversation

# Test copying
/cp /chats/<some-id> /tags/backup/
/ls /tags/backup/
# Should show new conversation with different ID

# Test moving
/mv /tags/test/<some-id> /tags/final/
/ls /tags/test/
# Should not show moved conversation
/ls /tags/final/
# Should show moved conversation

# Test removing tag
/rm /tags/final/<some-id>
/ls /tags/final/
# Should not show conversation

# Test deletion (be careful!)
/cp /chats/<some-id> /tags/temp/
/rm /chats/<temp-id>
# Should prompt for confirmation
# Type 'yes' to confirm deletion
```

## See Also

- **Design Document**: `docs/VFS_DESIGN.md`
- **Phase 3**: `docs/VFS_PHASE3_IMPLEMENTATION.md` (Navigation commands)
- **Path Parser**: `ctk/core/vfs.py`
- **Navigator**: `ctk/core/vfs_navigator.py`
- **Database**: `ctk/core/database.py`
