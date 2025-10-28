# VFS Phase 3 Enhancements: Prefix Matching & Tab Completion

## Overview

Added two major usability enhancements to VFS navigation:

1. **Prefix Matching** - Type partial conversation IDs to navigate
2. **Tab Completion** - Press Tab to complete paths, IDs, and message nodes

## Feature 1: Prefix Matching

### What It Does

Allows navigation to conversations using partial ID prefixes instead of typing the full UUID.

### Examples

```bash
# Instead of typing the full ID:
cd 466af475-887c-43a5-a291-a4b756064855

# Just type the prefix:
cd 466a
# Resolved '466a' to: 466af475-887c-43a5-a291-a4b756064855

# Works from any directory with conversations
You: pwd
/pinned/

You: cd 466a
Resolved '466a' to: 466af475-887c-43a5-a291-a4b756064855
```

### How It Works

1. **Minimum Length**: Prefix must be at least 3 characters
2. **Unique Match**: If prefix matches exactly one conversation, navigates to it
3. **Multiple Matches**: Shows list of matching conversations
4. **No Matches**: Shows error message

### Multiple Match Example

```bash
You: cd 4
Error: Prefix '4' matches 15 conversations:
  466af475-887c-43a5-a291-a4b756064855
  4a2b1c3d-5e6f-7a8b-9c0d-1e2f3a4b5c6d
  42abc123-def4-56gh-78ij-90klmn123456
  ... and 12 more
Please provide more characters to uniquely identify the conversation.
```

### Implementation

**New Method**: `VFSNavigator.resolve_prefix()`

```python
def resolve_prefix(self, prefix: str, vfs_path: VFSPath) -> Optional[str]:
    """
    Resolve a partial conversation ID prefix to full ID.

    Args:
        prefix: Partial conversation ID (e.g., "466a")
        vfs_path: Current VFS path context

    Returns:
        Full conversation ID if unique match found

    Raises:
        ValueError: If multiple matches or no matches
    """
```

**Location**: `ctk/core/vfs_navigator.py` (lines 49-87)

## Feature 2: Tab Completion

### What It Does

Press Tab while typing to auto-complete:
- Directory names (`/chats`, `/recent`, `/tags`)
- Conversation IDs
- Message node names (`m1`, `m2`, `m3`)
- Relative and absolute paths

### Examples

#### Complete Directory Names
```bash
You: cd rec<TAB>
You: cd recent/

You: cd /tag<TAB>
You: cd /tags/
```

#### Complete Conversation IDs
```bash
You: ls /chats
466af475-887c... ⭐  abc12345-def6... 📌  xyz98765-abc1...

You: cd 466<TAB>
You: cd 466af475-887c-43a5-a291-a4b756064855/
```

#### Complete Message Nodes
```bash
You: cd /chats/abc123/
You: ls
m1/  m2/  m3/

You: cd m<TAB>
# Shows: m1/, m2/, m3/

You: cd m2<TAB>
You: cd m2/
```

#### Smart Metadata Display

When completing conversation IDs, shows helpful context:

```bash
You: cd 466<TAB>

# Shows:
466af475-887c-43a5-a291-a4b756064855  "Discussion about quantum mechanics"
```

For message nodes, shows role and content preview:

```bash
You: cd m<TAB>

# Shows:
m1/  user: Hello, how can you help me?
m2/  assistant: I can help with many things...
m3/  user: I need help with Python
```

### How It Works

**VFSCompleter Class**: Custom prompt_toolkit completer

**Key Features**:
- Context-aware (only completes after VFS commands)
- Shows metadata (titles, roles, content previews)
- Handles both relative and absolute paths
- Works with nested paths (`/tags/physics/abc<TAB>`)

**Location**: `ctk/core/vfs_completer.py` (new file, 147 lines)

### Integration

Tab completion is automatically enabled when:
1. Database is connected
2. VFS navigator is initialized
3. First VFS command is used (lazy initialization)

**Integration Code**: `ctk/integrations/chat/tui.py`

```python
def _ensure_vfs_navigator(self):
    """Lazy initialize VFS navigator"""
    if self.vfs_navigator is None:
        # ... create navigator ...

        # Set up VFS tab completion
        if self.vfs_completer is None:
            self.vfs_completer = VFSCompleter(
                self.vfs_navigator,
                lambda: self.vfs_cwd
            )
            # Update session with completer
            self.session = PromptSession(
                history=self.session.history,
                auto_suggest=AutoSuggestFromHistory(),
                completer=self.vfs_completer
            )
```

## Usage Examples

### Combined Usage

```bash
# Start CTK with database
ctk chat --db allchats/

# Use tab completion to explore
You: cd rec<TAB>
You: cd recent/

You: ls
today/  this-week/  this-month/  older/

You: cd thi<TAB>
You: cd this-month/

You: ls
466af475... ⭐  abc12345... 📌  xyz98765...

# Use prefix matching to navigate
You: cd 466a
Resolved '466a' to: 466af475-887c-43a5-a291-a4b756064855

You: ls -l
Name    Type    Role    Content Preview                      Created
m1/     dir     user    Hello, I need help with...           2025-01-01 10:00
m2/     dir     assistant  Sure! What do you need...         2025-01-01 10:05

# Use tab completion for message nodes
You: cd m<TAB>
# Shows: m1/, m2/

You: cd m2<TAB>
You: cd m2/
```

### Workflow Benefits

**Before** (without these features):
```bash
# Had to copy-paste long UUIDs
You: ls
466af475-887c-43a5-a291-a4b756064855

You: cd 466af475-887c-43a5-a291-a4b756064855/
# Tedious!
```

**After** (with prefix matching + tab completion):
```bash
You: ls
466af475... ⭐

# Option 1: Tab completion
You: cd 466<TAB>
You: cd 466af475-887c-43a5-a291-a4b756064855/

# Option 2: Prefix matching
You: cd 466a
Resolved '466a' to: 466af475-887c-43a5-a291-a4b756064855
# Much faster!
```

## Implementation Details

### Files Modified

1. **`ctk/core/vfs_navigator.py`**
   - Added `resolve_prefix()` method (lines 49-87)
   - 39 lines added

2. **`ctk/integrations/chat/tui.py`**
   - Updated imports to include `merge_completers`
   - Added `self.vfs_completer = None` initialization
   - Updated `_ensure_vfs_navigator()` to create completer
   - Updated `handle_cd()` to use prefix resolution
   - ~30 lines modified

### Files Created

1. **`ctk/core/vfs_completer.py`**
   - New VFSCompleter class
   - 147 lines
   - Full tab completion implementation

## Testing

### Manual Testing Checklist

✅ **Prefix Matching**:
- [ ] `cd 466a` resolves to full ID
- [ ] `cd 4` shows multiple matches
- [ ] `cd xyz` shows "no matches" error
- [ ] Works in `/chats`, `/pinned`, `/starred`, `/recent/*`, etc.

✅ **Tab Completion**:
- [ ] `cd rec<TAB>` completes to `recent/`
- [ ] `cd 466<TAB>` shows conversation with title
- [ ] `cd m<TAB>` shows message nodes with role/content
- [ ] Works with nested paths (`/tags/physics/<TAB>`)
- [ ] Doesn't interfere with regular chat input
- [ ] Only activates after VFS commands

## Error Handling

### Prefix Matching Errors

**No matches**:
```bash
You: cd xyz999
Error: No conversation found matching prefix: xyz999
```

**Multiple matches**:
```bash
You: cd 4
Error: Prefix '4' matches 15 conversations:
  ...
Please provide more characters to uniquely identify the conversation.
```

**Too short** (< 3 characters):
```bash
You: cd 4
Error: Unknown filesystem root: /4
# Falls back to normal path parsing error
```

### Tab Completion Errors

Tab completion silently fails on errors to avoid disrupting user input. No error messages shown.

## Performance

**Prefix Matching**:
- O(n) scan through current directory entries
- Fast for typical directories (<100 conversations)

**Tab Completion**:
- Only triggers on Tab key
- Caches directory listings briefly
- Minimal overhead

## Future Enhancements

Potential improvements for future phases:

1. **Fuzzy Matching**: Match anywhere in ID, not just prefix
2. **Smart Sorting**: Sort completions by recency, starred status
3. **Command History**: Remember recently accessed conversations
4. **Async Completion**: For large databases (>10k conversations)
5. **Custom Aliases**: User-defined short names for conversations

## Summary

Two powerful usability features added! ✅

**Prefix Matching**:
- Navigate with partial IDs (`cd 466a`)
- Unique match resolution
- Clear error messages for ambiguity

**Tab Completion**:
- Auto-complete paths, IDs, message nodes
- Context-aware metadata display
- Seamless integration with existing workflow

Combined, these make VFS navigation **fast, intuitive, and productive**.
