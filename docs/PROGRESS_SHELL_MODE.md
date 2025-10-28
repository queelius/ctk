# Shell Mode Implementation Progress

## Session Summary

### Completed Tasks

#### 1. OpenAI Importer Fixes ✅
- **Fixed structural node handling**: OpenAI exports use `"client-created-root"` nodes without message content. Importer now correctly identifies these and sets `parent_id = None` for messages that reference them.
- **Fixed CLI auto-detection bug**: When `--format` wasn't specified, `source_dir` and `media_dir` weren't passed to importers. Refactored to handle both explicit and auto-detected formats uniformly.
- **Added directory import support**: CLI can now import from directories (e.g., `ctk import openai/` finds `conversations.json` automatically).
- **Image handling**:
  - Resolves `file-service://file-{ID}` URLs to local image files
  - Searches in main directory and `dalle-generations/` subdirectory
  - Copies images to `{database}/media/` with new UUIDs
  - Skips `sediment://` URLs gracefully (legacy format without files)
  - **Result**: 396 images successfully imported from test dataset

#### 2. Shell Mode Foundation ✅

**Phase 1: Command Parser** (COMPLETE)
- **Created `ShellParser` class** (`ctk/core/shell_parser.py`)
  - Parses shell command lines with quoted arguments
  - Expands environment variables (`$VAR`, `${VAR}`)
  - Splits pipelines by `|` operator
  - Distinguishes shell commands from chat input
  - Handles nested quotes correctly

- **Created `CommandDispatcher` class** (`ctk/core/command_dispatcher.py`)
  - Routes commands to appropriate handlers
  - Executes single commands and pipelines
  - Pipes stdout between commands
  - Returns structured `CommandResult` objects
  - Handles errors gracefully

**Phase 2: Unix Commands** (COMPLETE)
- **Implemented Unix command handlers** (`ctk/core/commands/unix.py`)
  - `cat <path>` - Display message or conversation content
  - `head [n]` - Show first n lines (default 10)
  - `tail [n]` - Show last n lines (default 10)
  - `echo <text>` - Print text (variables expanded by parser)
  - `grep [-i] [-n] <pattern>` - Search for pattern in input

- **Features**:
  - Full VFS path support (relative and absolute paths)
  - Stdin/stdout for piping
  - Works with message nodes and conversations
  - Options for case-insensitive search, line numbers

### Code Structure

```
ctk/
├── core/
│   ├── shell_parser.py          ✅ NEW - Parse shell commands
│   ├── command_dispatcher.py    ✅ NEW - Route and execute commands
│   └── commands/
│       ├── __init__.py          ✅ NEW - Command registry
│       └── unix.py              ✅ NEW - Unix commands (cat, head, tail, echo, grep)
├── integrations/
│   ├── importers/
│   │   └── openai.py            ✅ FIXED - Image handling, structural nodes
│   └── chat/
│       └── tui.py               ⏳ PENDING - Integration needed
└── cli.py                       ✅ FIXED - Directory import, kwargs passing
```

### Test Results

**ShellParser Tests:**
```bash
$ python -m ctk.core.shell_parser

Variable expansion:
  Input:  echo 'Current: $CWD'
  Output: echo Current: /chats
  Input:  Model: ${MODEL}, Count: $MSG_COUNT
  Output: Model: llama3.2, Count: 5

Command parsing:
  Input:  cat m1 m2 m3
  Command: cat, Args: ['m1', 'm2', 'm3']
  Input:  echo "hello world"
  Command: echo, Args: ['hello world']

Pipeline parsing:
  Input: cat m1 | grep error | head 5
  Has pipe: True
  Commands: 3
    [0] cat ['m1']
    [1] grep ['error']
    [2] head ['5']

Shell command detection:
  'cd /chats' -> COMMAND
  'cat m1' -> COMMAND
  'Hello, how are you?' -> CHAT
  'help' -> COMMAND
  'What is quantum mechanics?' -> CHAT
```

**CommandDispatcher Tests:**
```bash
$ python -m ctk.core.command_dispatcher

=== Test 1: Single command ===
Output: 'Hello World\n'

=== Test 2: Simple pipe ===
Output: ''

=== Test 3: Command not found ===
Success: False
Error: Command not found: nonexistent
```

**Import Tests:**
```bash
$ ctk import openai/ --db test-images-final
Imported 2218 conversation(s)
  [396 images copied to media directory]
```

## Next Steps

### Phase 1 (Remaining): TUI Integration
- Update TUI main loop to use `ShellParser` and `CommandDispatcher`
- Add mode tracking (shell vs chat)
- Update prompt rendering for shell mode
- Implement command history separation

### Phase 3: Mode Switching
- Create `ChatMode` class for LLM interactions
- Implement `chat` command to enter chat mode
- Implement `complete` command for one-off queries
- Add `/exit` to return to shell mode
- Context loading (auto-load conversation at current path)

### Phase 4: Piping (Mostly Done)
- Pipeline infrastructure already works in `CommandDispatcher`
- Need to make existing TUI commands pipe-aware:
  - Accept stdin
  - Return structured output
  - Support both interactive and piped modes

### Phase 5: Configuration System
- Add `/config/` VFS directory
- Implement config persistence
- Add `config` command for get/set operations
- Store settings: model, provider, temperature, etc.

### Phase 6: Environment Variables
- Create `EnvironmentManager` class
- Track dynamic variables: `$CWD`, `$MODEL`, `$CONV_ID`, etc.
- Variable expansion already works in `ShellParser`
- Need to update variables on navigation/mode changes

## Architecture Overview

### Current Flow (Chat-First)
```
User Input → TUI → Check for /command → Execute command or chat
```

### Target Flow (Shell-First)
```
User Input → ShellParser → is_shell_command?
                                ├─ Yes → CommandDispatcher → Handler → Output
                                └─ No  → ChatMode → LLM → Save → Output
```

### Command Execution Pipeline
```
"cat m1 | grep error | head 5"
    ↓
ShellParser.parse()
    ↓
ParsedPipeline(commands=[
    ParsedCommand("cat", ["m1"]),
    ParsedCommand("grep", ["error"]),
    ParsedCommand("head", ["5"])
])
    ↓
CommandDispatcher.execute_pipeline()
    ↓
1. cat m1          → "User: What is X?\nAssistant: X is..."
2. grep error      → filter for "error" (no matches)
3. head 5          → first 5 lines (empty input)
    ↓
CommandResult(success=True, output="")
```

## Design Benefits

### Unix Philosophy ✅
- Small, composable commands
- Piping for complex operations
- Standard interface patterns
- Text streams as universal interface

### Implementation Benefits ✅
- Clean separation of concerns
- Parser handles syntax → Dispatcher handles execution
- Commands are stateless functions
- Easy to add new commands
- Test-friendly architecture

### User Benefits 🎯
- Familiar Unix commands (cat, grep, head, tail)
- Fast navigation with prefix resolution
- Powerful piping for filtering
- Shell mode for management, chat mode for conversations
- Seamless mode switching with context preservation

## Timeline

- ✅ **Day 1**: OpenAI importer fixes, ShellParser, CommandDispatcher, Unix commands
- ⏳ **Day 2-3**: TUI integration, mode switching
- ⏳ **Day 4-5**: Chat/complete commands, configuration system
- ⏳ **Day 6-7**: Testing, documentation, polish

## Success Metrics

- [x] ShellParser correctly parses commands with quotes and pipes
- [x] CommandDispatcher routes commands to handlers
- [x] Pipeline execution works (stdin → cmd1 → cmd2 → stdout)
- [x] Unix commands (cat, head, tail, echo, grep) implemented
- [ ] TUI uses shell mode by default
- [ ] Mode switching works (shell ↔ chat)
- [ ] Configuration system functional
- [ ] Test coverage >70% for new components
- [ ] Documentation complete

## Notes

- **Variable expansion** is already implemented and working
- **Piping infrastructure** is complete and tested
- **Command registration** system is modular and extensible
- **Error handling** is consistent across all components
- **VFS integration** works with existing navigation system

The foundation is solid and ready for TUI integration!
