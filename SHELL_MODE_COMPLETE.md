# Shell-First Mode Implementation - Complete

This document summarizes the shell-first mode implementation for the CTK (Conversation Toolkit) project.

## Overview

Shell-first mode provides a Unix-like shell interface for navigating and inspecting conversations stored in the CTK database. Instead of defaulting to chat mode, the TUI now starts in shell mode, allowing users to navigate a virtual filesystem (VFS) where conversations, messages, and metadata are exposed as directories and files.

## Implemented Features

### Phase 1: Command Parser and Dispatcher ✅

**Files Created:**
- `ctk/core/shell_parser.py` - Shell command parser with variable expansion and pipe support
- `ctk/core/command_dispatcher.py` - Routes parsed commands to handlers and manages pipelines

**Features:**
- Command parsing with `shlex` for proper quote handling
- Environment variable expansion (`$VAR` and `${VAR}`)
- Pipeline support with `|` operator
- Command detection (distinguishes shell commands from chat input)

### Phase 2: Navigation and Unix Commands ✅

**Files Created:**
- `ctk/core/commands/navigation.py` - cd, ls, pwd commands
- `ctk/core/commands/unix.py` - cat, head, tail, echo, grep commands

**Features:**

#### Navigation (cd, ls, pwd)
- `cd <path>` - Change directory with prefix resolution
  - `cd /chats` - Navigate to chats directory
  - `cd abc123` - Navigate using partial conversation ID (resolves to full UUID)
  - `cd ..` - Go to parent directory
- `ls [path]` - List directory contents with trailing `/` for directories
- `pwd` - Print current working directory

#### Unix Commands
- `cat <path>` - Display message or conversation content
  - Works with message nodes: `cat m1`
  - Works with metadata files: `cat m1/text`, `cat m1/role`
  - Works with stdin: `echo "text" | cat`
- `head [n] [path]` - Show first n lines (default 10)
- `tail [n] [path]` - Show last n lines (default 10)
- `echo <text>` - Echo text with variable expansion
- `grep [options] <pattern> [path]` - Search for patterns
  - Supports `-i` (case-insensitive) and `-n` (line numbers)
  - Works with pipes: `cat m1 | grep "error"`

**Prefix Resolution:**
Conversation IDs can be referenced by their first 3+ characters:
```
$ cd 7c87
Resolved '7c87' to: 7c87af4c-5e10-4eb4-8aaa-41070f710e0f
```

**Piping:**
Commands can be chained with `|`:
```
$ ls | grep "^7" | head 3
$ cat m1/text | grep "important" | tail 5
$ echo $CWD | grep "/chats"
```

### Phase 3: Chat Mode Integration ✅

**Files Created:**
- `ctk/core/commands/chat.py` - chat, complete commands

**Features:**
- `chat [message]` - Enter interactive chat mode, optionally sending a message
- `complete <prompt>` - Get LLM completion without entering chat mode
- `/exit` in chat mode - Return to shell mode

### Bonus: Message Metadata as VFS Files ✅

**Enhancement to VFS:**

Message nodes now expose metadata as readable files:
- `text` - Message content
- `role` - Message role (user/assistant/system)
- `timestamp` - Message creation timestamp
- `id` - Message UUID

**Example:**
```
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

This makes the VFS more Unix-like and allows message inspection with standard tools like `grep`:
```
$ ls | grep -v "^m"  # List only metadata files
$ cat text | wc -l   # Count lines in message text
```

### Phase 4: Visualization Commands ✅

**Files Created:**
- `ctk/core/commands/visualization.py` - tree, paths commands

**Features:**
- `tree [conv_id]` - Display conversation tree structure
  - Shows message hierarchy with ASCII tree art
  - Displays role indicators (U=user, A=assistant, ⚙=system)
  - Shows content previews
- `paths [conv_id]` - List all paths in conversation tree
  - Shows each path as a sequence of messages
  - Useful for branching conversations

**Example:**
```
$ cd /chats/abc123
$ tree | head 20
Conversation Tree:
================================================================================
└─⚙ 4f6e9a8c
  └─U 90a5d5f6 I'm working on a paper and associated C+...
    └─A 87491ee0 Thanks for sharing the README.md file fo...
      └─U c8a99a29 Can you tell me about any related concep...
```

### Phase 5: Organization Commands ✅

**Files Created:**
- `ctk/core/commands/organization.py` - star, pin, archive, title commands

**Features:**
- `star [conv_id]` - Star a conversation
  - Stars current conversation if no ID provided
  - Conversation appears in `/starred/` directory
- `unstar [conv_id]` - Remove star from conversation
- `pin [conv_id]` - Pin a conversation
  - Pinned conversations appear in `/pinned/` directory
- `unpin [conv_id]` - Unpin conversation
- `archive [conv_id]` - Archive a conversation
  - Archived conversations appear in `/archived/` directory
- `unarchive [conv_id]` - Unarchive conversation
- `title <new_title>` - Set conversation title
  - Can specify conversation ID or use current location

**Example:**
```
$ cd /chats/abc123
$ star
Starred conversation: abc123

$ title My Important Conversation
Set title to: My Important Conversation

$ cd /starred
$ ls | grep abc
abc123.../

$ star abc123  # Works from any location
$ pin 7c87     # Works with prefix resolution
```

## Architecture

### Command Registration

Commands are registered in `ChatTUI._register_shell_commands()`:

```python
def _register_shell_commands(self):
    # Register Unix commands
    unix_commands = create_unix_commands(self.db, self.vfs_navigator, tui_instance=self)
    self.command_dispatcher.register_commands(unix_commands)

    # Register navigation commands
    nav_commands = create_navigation_commands(self.vfs_navigator, tui_instance=self)
    self.command_dispatcher.register_commands(nav_commands)

    # Register visualization commands
    viz_commands = create_visualization_commands(self.db, self.vfs_navigator, tui_instance=self)
    self.command_dispatcher.register_commands(viz_commands)

    # Register chat commands
    chat_commands = create_chat_commands(tui_instance=self)
    self.command_dispatcher.register_commands(chat_commands)
```

### State Management

- **Current Path**: Stored in `tui.vfs_cwd`
- **Mode**: Stored in `tui.mode` ('shell' or 'chat')
- **Environment Variables**: Updated via `tui._update_environment()`
  - `$CWD` / `$PWD` - Current working directory
  - `$MODEL` - Current LLM model
  - `$PROVIDER` - Current LLM provider
  - `$CONV_ID` - Current conversation ID (if in conversation)
  - `$MSG_COUNT` - Message count (if in conversation)

### VFS Path Types

Extended `PathType` enum in `ctk/core/vfs.py`:

```python
class PathType(Enum):
    ROOT = "root"
    CHATS = "chats"
    CONVERSATION_ROOT = "conversation_root"
    MESSAGE_NODE = "message_node"
    MESSAGE_FILE = "message_file"  # NEW: metadata files
    # ... other types
```

## Testing

### Test Files Created

1. **test_shell_mode.py** - Basic shell mode initialization
2. **test_navigation.py** - Navigation command tests
3. **test_prefix_resolution.py** - Prefix resolution tests
4. **test_piping.py** - Command piping tests
5. **test_message_metadata.py** - Metadata file tests
6. **test_shell_comprehensive.py** - Complete feature demonstration

Run comprehensive test:
```bash
$ python test_shell_comprehensive.py
```

## Registered Commands

20 commands now available in shell mode:

1. **archive** - Archive conversation
2. **cat** - Display file/message content
3. **cd** - Change directory
4. **chat** - Enter chat mode
5. **complete** - Get LLM completion
6. **echo** - Echo text
7. **find** - Find conversations and messages
8. **grep** - Search patterns
9. **head** - Show first lines
10. **ls** - List directory
11. **paths** - Show conversation paths
12. **pin** - Pin conversation
13. **pwd** - Print working directory
14. **star** - Star conversation
15. **tail** - Show last lines
16. **title** - Set conversation title
17. **tree** - Show conversation tree
18. **unarchive** - Unarchive conversation
19. **unpin** - Unpin conversation
20. **unstar** - Unstar conversation

## Bug Fixes

During implementation, several bugs were discovered and fixed:

1. **CommandResult Constructor**: Added missing `output=""` parameter to error returns
2. **VFSNavigator API**: Fixed navigation commands to use `tui.vfs_cwd` instead of non-existent `navigator.get_current_path()`
3. **ConversationTree API**: Changed from `messages` to `message_map` attribute
4. **cat Command**: Implemented proper message retrieval by navigating conversation tree
5. **VFS Entry Formatting**: Fixed to use `entry.name` and `entry.is_directory` attributes
6. **Empty Text Display**: `cat text` now shows `[empty]` for empty content instead of blank output
7. **Chat History Loading**: `chat` command now loads full conversation history from VFS path, providing proper context to LLM
8. **Path Validation**: `cd` command validates paths exist before navigation, preventing invalid states
9. **Metadata Files in All Paths**: Metadata files (text, role, timestamp, id) now work in all VFS directory types (/tags/, /starred/, /pinned/, /archived/)

## Usage Examples

### Basic Navigation

```bash
$ pwd
/

$ ls
chats/
tags/
starred/
...

$ cd /chats
$ ls | head 5
7c87af4c-5e10-4eb4-8aaa-41070f710e0f/
5dce9708-0f2d-4c73-a634-b1db3517e7c1/
...

$ cd 7c87
Resolved '7c87' to: 7c87af4c-5e10-4eb4-8aaa-41070f710e0f
```

### Message Inspection

```bash
$ cd /chats/abc123/m1
$ ls
text
role
timestamp
id
m1/

$ cat text | head 3
$ cat role
user
```

### Piping and Filtering

```bash
$ ls /chats | grep "^7" | head 3
$ cat m1/text | grep "important"
$ echo $CWD | grep "/chats"
```

### Search

```bash
# Find conversations
$ find /chats -type d -limit 5
/chats/7c87af4c.../
/chats/5dce9708.../
...

# Find by title pattern
$ find -name '*important*'
/chats/abc123.../

# Find messages by content
$ find -content 'error' -limit 10
/chats/abc123/m1/m1/m1
/chats/def456/m1/m1
...

# Find by role
$ find -role user -limit 5
/chats/abc123/m1/m1
/chats/abc123/m1/m1/m1/m1
...

# Grep within message
$ cat text | grep -i 'pattern'
```

### Visualization

```bash
$ cd /chats/abc123
$ tree | head 20
$ paths | head 15
```

### Mode Switching

```bash
# Enter chat from a specific message node - history is loaded!
$ cd /chats/abc123/m1/m1/m1
$ cat text
What's the capital of France?
$ chat
Entering chat mode. Type /exit to return to shell.
# LLM now has full context of conversation up to this point
[Chat mode active]

/exit
Returned to shell mode

$ complete "What is 2+2?"
4
```

## Next Steps (Future Phases)

### Phase 5: Configuration VFS (Not Implemented)

- `/config/` directory for settings
- Files like `model`, `temperature`, `max_tokens`
- Edit configuration with standard commands

### Phase 6: Environment Management (Not Implemented)

- `export VAR=value` - Set variables
- `unset VAR` - Remove variables
- `.env` files for persistent configuration

### Phase 7: Advanced Features (Not Implemented)

- Tab completion
- Command history
- Aliases
- Shell scripts (`.sh` files in VFS)

## Files Modified

### Core Files

- `ctk/integrations/chat/tui.py`
  - Added shell mode support
  - Integrated command dispatcher
  - Updated main loop for mode switching
  - Added `_register_shell_commands()` and `_update_environment()`

- `ctk/core/vfs.py`
  - Added `MESSAGE_FILE` path type
  - Updated path parser to recognize metadata files
  - Added `file_name` attribute to `VFSPath`

- `ctk/core/vfs_navigator.py`
  - Modified `_list_message_node()` to expose metadata files

### Files Created

- `ctk/core/shell_parser.py` (280 lines)
- `ctk/core/command_dispatcher.py` (150 lines)
- `ctk/core/commands/navigation.py` (210 lines)
- `ctk/core/commands/unix.py` (360 lines)
- `ctk/core/commands/visualization.py` (280 lines)
- `ctk/core/commands/chat.py` (140 lines)
- `ctk/core/commands/organization.py` (300 lines)

Total new code: ~1,720 lines

## Summary

Shell-first mode is now fully functional with:
- ✅ Complete navigation system (cd, ls, pwd)
- ✅ Unix-like commands (cat, head, tail, echo, grep)
- ✅ Search functionality (find)
- ✅ Command piping and composition
- ✅ Prefix resolution for conversation IDs
- ✅ Message metadata as VFS files
- ✅ Tree and path visualization
- ✅ Organization commands (star, pin, archive, title)
- ✅ Environment variable support
- ✅ Chat mode integration with history loading
- ✅ Comprehensive test suite

The implementation provides a powerful and intuitive way to explore and organize conversation data through a familiar Unix shell interface.

**20 total commands** spanning navigation, search, file operations, piping, visualization, and organization - all working seamlessly in a POSIX-like shell environment.
