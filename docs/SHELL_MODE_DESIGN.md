# Shell-First Mode Design

## Overview

**Goal**: Refactor TUI to default to a POSIX-like shell interface instead of chat mode, making it a versatile conversation management system rather than just a chat interface.

## Current State vs Target State

### Current State (Chat-First)
```bash
$ ctk chat
Starting chat session...
You: <immediately in chat mode with LLM>
```

Users must use `/commands` for VFS navigation and management.

### Target State (Shell-First)
```bash
$ ctk shell  # or just `ctk` with new default
[/] $ ls
chats/  starred/  pinned/  archived/  recent/  tags/  source/  model/  config/

[/] $ cd /recent/this-month
[/recent/this-month] $ ls
68dedd6a-cb58-832f-8443-c31c2d48995b/  MLE Performance Analysis
68df3de3-cff4-8331-9016-9b819a968690/  Philosophical reflections

[/recent/this-month] $ cd 68de
Resolved '68de' to: 68dedd6a-cb58-832f-8443-c31c2d48995b
[/recent/this-month/68dedd6a-cb58-832f-8443-c31c2d48995b] $ ls
m1/  m2/  m3/  m4/

[/recent/this-month/68dedd6a-cb58-832f-8443-c31c2d48995b] $ cat m1
User: What are the key challenges in maximum likelihood estimation?
...

[/recent/this-month/68dedd6a-cb58-832f-8443-c31c2d48995b] $ chat
Entering chat mode with model: ollama:llama3.2
(Use /exit to return to shell)

You: Let's discuss MLE...
Assistant: ...
You: /exit

[/recent/this-month/68dedd6a-cb58-832f-8443-c31c2d48995b] $ pwd
/recent/this-month/68dedd6a-cb58-832f-8443-c31c2d48995b
```

## Architecture

### Mode System

Two operational modes with seamless switching:

1. **Shell Mode** (default)
   - POSIX-like command interface
   - VFS navigation (cd, ls, pwd, etc.)
   - Unix commands (cat, head, tail, echo, grep)
   - File operations (ln, cp, mv, rm, mkdir)
   - Database operations (star, pin, archive, title)
   - Piping support for command composition
   - Enter chat mode with `chat` command

2. **Chat Mode** (entered via `chat` command)
   - Interactive LLM conversation
   - Context-aware: automatically loads conversation at current VFS path
   - `/commands` for shell operations while in chat
   - `/exit` returns to shell mode
   - State preserved when switching modes

### Command Categories

#### 1. Navigation Commands (Shell Mode)
**Already Implemented:**
- `cd [path]` - Change directory (with prefix resolution)
- `ls [options] [path]` - List directory contents
- `pwd` - Print working directory

**Enhancements Needed:**
- Remove `/` prefix requirement (currently `/cd`, `/ls`, `/pwd`)
- Make these native shell commands

#### 2. Unix-Like Commands (New)
**Read Commands:**
- `cat <path>` - Display message content
  - `cat m1` - Show first message
  - `cat m1/m2/m3` - Show message at path
  - `cat .` - Show current message (if in message node)

- `head <path> [n]` - Show first n messages (default 10)
  - `head m1 5` - First 5 lines of message
  - `head /chats/abc123` - First 10 messages of conversation

- `tail <path> [n]` - Show last n messages (default 10)
  - `tail m1 5` - Last 5 lines of message
  - `tail /chats/abc123` - Last 10 messages

- `echo <text>` - Print text or variables
  - `echo $CWD` - Print current working directory
  - `echo $MODEL` - Print current model
  - `echo "Message count: $MSG_COUNT"`

**Other Commands:**
- `grep <pattern> <path>` - Search within messages
  - `grep "quantum" m1` - Find "quantum" in message 1
  - `grep -r "error" /chats/abc123` - Recursive search

#### 3. File Operations (Already Implemented, Remove `/` Prefix)
- `ln <src> <dest>` - Link conversation to tag
- `cp <src> <dest>` - Copy conversation
- `mv <src> <dest>` - Move between tags
- `rm <path>` - Remove tag or delete conversation
- `mkdir <path>` - Create tag hierarchy

#### 4. Database Operations (Remove `/` Prefix)
**Already Implemented:**
- `star <id>` - Star conversation
- `pin <id>` - Pin conversation
- `archive <id>` - Archive conversation
- `title <id> <new_title>` - Rename conversation

**Keep as-is:**
- `search <query>` - Full-text search
- `ask <query>` - Natural language query
- `show <id>` - Display conversation
- `tree <id>` - Visualize tree structure
- `paths <id>` - List all paths
- `export <id> <format>` - Export conversation

#### 5. LLM Commands (New/Enhanced)
- `chat [model]` - Enter interactive chat mode
  - `chat` - Use default model at current path
  - `chat ollama:llama3.2` - Specify model
  - Context: Auto-loads conversation if at conv path

- `complete <prompt>` - One-off completion
  - `complete "Summarize this conversation"` - Quick query
  - Uses context from current VFS path
  - Returns result and stays in shell mode

- `model <name>` - Set default model
  - `model ollama:llama3.2`
  - `model openai:gpt-4`

#### 6. System Commands
- `config [key] [value]` - View/set configuration
  - `config` - Show all settings
  - `config model ollama:llama3.2` - Set default model
  - `config provider openai` - Set default provider

- `help [command]` - Show help
- `exit` - Exit shell (or `/exit` in chat mode)
- `clear` - Clear screen

### Piping Support

Commands can be composed using Unix-style pipes:

```bash
# Read message and search
cat m1 | grep "quantum"

# Show conversation and filter
show abc123 | grep "error"

# List and filter
ls -l | grep "starred"

# Export and process
export abc123 json | grep "role"

# Complex pipeline
cat /chats/abc123/m1/m2 | grep "important" | head 10
```

**Implementation:**
- Parse input for `|` character
- Split into commands
- Execute left command, pipe stdout to right command
- Support multiple pipes: `cmd1 | cmd2 | cmd3`

### Configuration System

New VFS directory: `/config/` or `/system/config/`

**Structure:**
```bash
/config/
  model           # Default LLM model
  provider        # Default LLM provider
  temperature     # LLM temperature
  max_tokens      # LLM max tokens
  prompt_style    # Shell prompt format
  auto_save       # Auto-save chats
  ...
```

**Access:**
```bash
# Read config
[/] $ cd /config
[/config] $ cat model
ollama:llama3.2

# Set config (two ways)
[/config] $ echo "openai:gpt-4" > model
[/config] $ config model openai:gpt-4

# List all config
[/config] $ ls -l
model           ollama:llama3.2
provider        ollama
temperature     0.7
max_tokens      4096
```

### Environment Variables

Shell mode supports variables:

**System Variables:**
- `$CWD` - Current working directory
- `$PWD` - Same as $CWD (POSIX compatibility)
- `$MODEL` - Current LLM model
- `$PROVIDER` - Current LLM provider
- `$CONV_ID` - Current conversation ID (if in conv)
- `$MSG_PATH` - Current message path (if in message node)
- `$MSG_COUNT` - Number of messages in current conversation

**Usage:**
```bash
[/chats/abc123] $ echo "Working in: $CWD"
Working in: /chats/abc123

[/chats/abc123] $ echo "Using model: $MODEL"
Using model: ollama:llama3.2

[/chats/abc123/m1] $ echo "At message: $MSG_PATH"
At message: m1
```

## Implementation Plan

### Phase 1: Command Parser Refactor
**Goal**: Separate shell command parsing from chat input

**Tasks:**
1. Create `ShellParser` class
   - Parse command line (handle quotes, pipes, variables)
   - Distinguish between shell commands and chat input
   - Expand variables ($CWD, $MODEL, etc.)

2. Create `CommandDispatcher` class
   - Route commands to handlers
   - Execute single commands
   - Execute piped commands

3. Update TUI main loop
   - Check mode (shell vs chat)
   - Route to appropriate handler
   - Track current mode state

**Files:**
- New: `ctk/core/shell_parser.py`
- New: `ctk/core/command_dispatcher.py`
- Modify: `ctk/integrations/chat/tui.py`

### Phase 2: Unix Commands
**Goal**: Implement cat, head, tail, echo, grep

**Tasks:**
1. Implement `cat` command
   - Read message content at path
   - Format output (preserve markdown, code blocks)
   - Support multiple paths

2. Implement `head` and `tail`
   - Extract first/last n lines
   - Support message nodes and conversations

3. Implement `echo` command
   - Print text
   - Expand variables
   - Support redirection (future)

4. Enhance `grep` command
   - Search within messages
   - Recursive search in conversations
   - Color highlighting (optional)

**Files:**
- New: `ctk/core/commands/unix.py`
- Modify: `ctk/core/command_dispatcher.py`

### Phase 3: Mode Switching
**Goal**: Implement chat mode as a subshell

**Tasks:**
1. Create `ChatMode` class
   - Separate state from shell mode
   - Handle LLM interactions
   - Support `/commands` within chat

2. Implement `chat` command
   - Enter chat mode
   - Load conversation context if at conv path
   - Set up model

3. Implement `complete` command
   - One-off LLM query
   - Return to shell after response

4. Add mode indicator to prompt
   - Shell: `[/path] $ `
   - Chat: `You: ` or `[/path] Chat> `

**Files:**
- New: `ctk/integrations/chat/chat_mode.py`
- Modify: `ctk/integrations/chat/tui.py`
- Modify: `ctk/core/commands.py`

### Phase 4: Piping Infrastructure
**Goal**: Support command composition

**Tasks:**
1. Extend `ShellParser`
   - Detect pipes in command line
   - Split into command segments

2. Extend `CommandDispatcher`
   - Execute pipeline of commands
   - Pipe stdout between commands
   - Handle errors in pipeline

3. Make commands pipe-aware
   - Accept stdin input
   - Write to stdout (not print directly)
   - Support both modes (interactive + piped)

**Files:**
- Modify: `ctk/core/shell_parser.py`
- Modify: `ctk/core/command_dispatcher.py`
- Modify all command handlers

### Phase 5: Configuration System
**Goal**: Implement /config/ directory

**Tasks:**
1. Create VFS config handler
   - Add `/config/` to VFS path types
   - List config keys as files
   - Read config values with `cat`

2. Implement config persistence
   - Store in database or config file
   - Load on startup
   - Save on change

3. Add `config` command
   - View all settings
   - Get/set individual values
   - Validate config values

**Files:**
- Modify: `ctk/core/vfs.py` (add CONFIG path type)
- Modify: `ctk/core/vfs_navigator.py`
- New: `ctk/core/config_manager.py`

### Phase 6: Environment Variables
**Goal**: Support $VAR expansion

**Tasks:**
1. Create `EnvironmentManager`
   - Track current state ($CWD, $MODEL, etc.)
   - Update on navigation/mode changes
   - Provide variable expansion

2. Integrate with `ShellParser`
   - Expand variables in commands
   - Support $VAR and ${VAR} syntax

3. Add `set` command (optional)
   - Set custom variables
   - List all variables

**Files:**
- New: `ctk/core/environment.py`
- Modify: `ctk/core/shell_parser.py`

## Migration Path

### Backward Compatibility

**TUI Command:**
- `ctk chat` - Starts in chat mode (legacy behavior)
- `ctk shell` - Starts in shell mode (new default)
- `ctk` - Starts in shell mode (new default)

**Within TUI:**
- `/command` syntax still works in chat mode
- Commands without `/` work in shell mode
- Both modes support all operations

### Documentation Updates

1. Update README with shell-first examples
2. Create shell mode tutorial
3. Document all new commands
4. Add piping examples
5. Migration guide for existing users

## Examples

### Example 1: Browse and Read
```bash
$ ctk shell
[/] $ cd /recent/this-week
[/recent/this-week] $ ls
5 conversations

[/recent/this-week] $ cd 68de
Resolved '68de' to: 68dedd6a-cb58-832f-8443-c31c2d48995b
[/recent/this-week/68dedd6a...] $ ls
m1/  m2/  m3/  m4/

[/recent/this-week/68dedd6a...] $ cat m1
User: What are the key challenges in maximum likelihood estimation?
Assistant: Maximum likelihood estimation (MLE) faces several key challenges...
[full message content displayed]

[/recent/this-week/68dedd6a...] $ head m2 5
Assistant: To elaborate on the first point...
[first 5 lines of m2]
```

### Example 2: Search and Filter
```bash
[/] $ cd /chats
[/chats] $ ls | grep "quantum"
466af475-887c-43a5-a291-a4b756064855  Discussion about quantum mechanics
abc12345-def6-7890-abcd-ef1234567890  Quantum computing basics

[/chats] $ grep -r "Schrödinger" /chats/466af475-887c-43a5-a291-a4b756064855
m3: The Schrödinger equation is fundamental...
m7: When considering Schrödinger's cat...
```

### Example 3: Chat Mode
```bash
[/chats/466af475...] $ chat ollama:llama3.2
Entering chat mode with model: ollama:llama3.2
Context: Loaded conversation "Discussion about quantum mechanics" (4 messages)
(Use /exit to return to shell)

You: Can you summarize our discussion so far?
Assistant: We've been discussing quantum mechanics fundamentals, covering...

You: What about quantum entanglement?
Assistant: Quantum entanglement is...

You: /exit
Exited chat mode (conversation saved)

[/chats/466af475...] $ ls
m1/  m2/  m3/  m4/  m5/  m6/
# New messages m5 and m6 added during chat!
```

### Example 4: One-Off Completion
```bash
[/chats/abc123] $ complete "Summarize this conversation in 3 bullet points"
• Discussed Python best practices for error handling
• Reviewed exception hierarchy and custom exceptions
• Explored context managers and try-finally patterns

[/chats/abc123] $ # Still in shell mode!
```

### Example 5: Piping and Composition
```bash
[/] $ cd /starred
[/starred] $ ls -l | head 10
# Shows first 10 starred conversations

[/starred] $ cat /chats/abc123/m1 | grep "error" | tail 3
# Find "error" in message, show last 3 matches

[/] $ search "quantum" | grep "starred" | export - jsonl
# Search, filter starred results, export to JSONL
```

### Example 6: Configuration
```bash
[/] $ cd /config
[/config] $ ls
model  provider  temperature  max_tokens  prompt_style  auto_save

[/config] $ cat model
ollama:llama3.2

[/config] $ echo "openai:gpt-4" > model
Updated: model = openai:gpt-4

[/config] $ config temperature 0.9
Updated: temperature = 0.9

[/config] $ config
Configuration:
  model: openai:gpt-4
  provider: openai
  temperature: 0.9
  max_tokens: 4096
  prompt_style: [%p] $
  auto_save: true
```

### Example 7: Environment Variables
```bash
[/chats/abc123] $ echo "Current directory: $CWD"
Current directory: /chats/abc123

[/chats/abc123] $ echo "Model: $MODEL, Messages: $MSG_COUNT"
Model: ollama:llama3.2, Messages: 5

[/chats/abc123/m1] $ echo "Reading message at: $MSG_PATH"
Reading message at: m1
```

## Benefits

### 1. Unix Philosophy
- Small, composable commands
- Piping for complex operations
- Standard interface patterns
- Familiar to developers

### 2. Flexibility
- Shell mode for management tasks
- Chat mode for conversations
- Seamless switching between modes
- Context preservation

### 3. Automation
- Scriptable commands
- Pipe outputs between tools
- Environment variables
- Configuration management

### 4. Discoverability
- `help` command for guidance
- Tab completion (prefix matching)
- Clear command structure
- Consistent patterns

### 5. Power Users
- Fast navigation with prefix resolution
- Quick inspection with cat/head/tail
- Complex queries with piping
- Advanced filtering with grep

## Technical Considerations

### 1. Prompt Rendering
**Current**: Uses `prompt_toolkit.PromptSession` for input
**Change**: Need to handle two prompt styles
- Shell: `[/path] $ `
- Chat: `You: ` (or custom user name)

### 2. Command History
**Current**: Shared history for all inputs
**Change**: Separate histories for shell vs chat
- Shell history: Commands only
- Chat history: Chat messages only
- Switching modes preserves both histories

### 3. Output Formatting
**Current**: Print statements and Rich tables
**Enhancement**: Commands should return data, formatters handle display
- Use `OutputFormatter` abstraction (already started in `formatters.py`)
- Support both human-readable and machine-readable output
- Piping requires text output

### 4. Error Handling
**Current**: Print error messages directly
**Enhancement**: Consistent error reporting
- Error codes (0 = success, non-zero = error)
- Structured error messages
- Pipeline error propagation

### 5. State Management
Need to track:
- Current mode (shell vs chat)
- Current VFS path
- Current conversation context
- Current model/provider
- Environment variables
- Configuration

## File Structure

```
ctk/
├── core/
│   ├── commands/          # Command handlers
│   │   ├── __init__.py
│   │   ├── navigation.py  # cd, ls, pwd
│   │   ├── unix.py        # cat, head, tail, echo, grep
│   │   ├── file_ops.py    # ln, cp, mv, rm, mkdir
│   │   ├── database.py    # star, pin, archive, title
│   │   ├── llm.py         # chat, complete, model
│   │   └── system.py      # config, help, exit
│   ├── shell_parser.py    # Parse shell commands
│   ├── command_dispatcher.py  # Route and execute commands
│   ├── environment.py     # Environment variables
│   ├── config_manager.py  # Configuration persistence
│   └── formatters.py      # Output formatting (exists)
├── integrations/
│   └── chat/
│       ├── tui.py         # Main TUI loop (refactor)
│       ├── chat_mode.py   # Chat mode handler (new)
│       └── shell_mode.py  # Shell mode handler (new)
└── cli.py                 # Entry point

docs/
└── SHELL_MODE_DESIGN.md   # This document
```

## Testing Strategy

### Unit Tests
- `test_shell_parser.py` - Command parsing, variable expansion
- `test_command_dispatcher.py` - Command routing, piping
- `test_commands_unix.py` - cat, head, tail, echo, grep
- `test_environment.py` - Variable management
- `test_config_manager.py` - Configuration persistence

### Integration Tests
- `test_shell_mode.py` - Shell mode workflows
- `test_chat_mode.py` - Chat mode workflows
- `test_mode_switching.py` - Switch between modes
- `test_piping.py` - Command composition

### Manual Testing Checklist
- [ ] Shell mode starts by default
- [ ] All commands work without `/` prefix
- [ ] Prefix resolution works for conversation IDs
- [ ] cat/head/tail display message content correctly
- [ ] grep searches within messages
- [ ] Piping works for simple cases
- [ ] Piping works for complex cases
- [ ] chat command enters chat mode
- [ ] Chat mode loads conversation context
- [ ] /exit returns to shell mode
- [ ] complete command works without entering chat
- [ ] Configuration can be read/written
- [ ] Environment variables expand correctly
- [ ] Backward compatibility with `ctk chat`

## Open Questions

1. **Should `ctk` default to shell mode or chat mode?**
   - Proposal: Shell mode (more versatile)
   - `ctk chat` for legacy behavior

2. **How to handle conversation creation in shell mode?**
   - Option 1: `chat` command always creates new conversation
   - Option 2: `chat --new` creates new, `chat` resumes at current path
   - Proposal: `chat` resumes if at conversation path, else creates new

3. **Should piping support binary data (images, attachments)?**
   - Proposal: Phase 1 = text only, Phase 2 = binary support

4. **How to handle multi-line input in shell mode?**
   - Option 1: Trailing backslash `\` for continuation
   - Option 2: Special command like `multiline` to enter multi-line mode
   - Proposal: Backslash continuation for simple cases

5. **Should environment variables be persistent across sessions?**
   - Proposal: System variables ($CWD, $MODEL) are dynamic, user-defined variables ($MYVAR) are session-only

## Timeline Estimate

- **Phase 1** (Command Parser): 2-3 days
- **Phase 2** (Unix Commands): 3-4 days
- **Phase 3** (Mode Switching): 2-3 days
- **Phase 4** (Piping): 3-4 days
- **Phase 5** (Configuration): 2-3 days
- **Phase 6** (Environment Variables): 1-2 days

**Total**: 13-19 days (approximately 3-4 weeks)

## Success Metrics

- [ ] Users can perform all VFS operations without `/` prefix
- [ ] cat/head/tail commands work for reading messages
- [ ] Piping works for at least 3 common use cases
- [ ] chat and complete commands work as expected
- [ ] Mode switching is seamless
- [ ] Configuration system is functional
- [ ] Test coverage >70% for new components
- [ ] Documentation is complete and clear

## References

- **VFS Design**: `docs/VFS_DESIGN.md`
- **Command Handlers**: `ctk/core/commands.py`
- **Formatters**: `ctk/core/formatters.py`
- **Current TUI**: `ctk/integrations/chat/tui.py`
- **Testing Plan**: `TESTING_PLAN.md`