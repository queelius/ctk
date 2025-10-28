# VFS Phase 1a: Slash-Optional Command Routing

## Overview

Implemented support for commands with or without the `/` prefix. Users can now type either `help` or `/help`, `cd /tags` or `/cd /tags`, etc. This is a transition phase toward the unified VFS design where commands are treated as programs without special prefixes.

## Changes Implemented

### 1. Known Commands Registry (`ctk/integrations/chat/tui.py`)

Added a set of all known commands at initialization (lines 97-106):

```python
# Known commands (for slash-optional command routing)
self.known_commands = {
    'help', 'exit', 'quit', 'clear', 'new-chat',
    'save', 'load', 'delete', 'search', 'list', 'ask', 'browse',
    'archive', 'star', 'pin', 'title', 'tag', 'export',
    'show', 'tree', 'paths', 'fork', 'fork-id', 'context',
    'mcp', 'cd', 'pwd', 'ls', 'ln', 'cp', 'mv', 'rm', 'mkdir',
    'rag', 'goto-longest', 'goto-latest', 'where', 'alternatives',
    'history', 'models', 'model', 'temp', 'regenerate', 'edit'
}
```

### 2. Input Handling Logic (`ctk/integrations/chat/tui.py`)

Updated main loop to recognize commands with or without `/` prefix (lines 4305-4315):

```python
# Handle commands (with or without slash prefix)
# Check if input starts with / OR if first word is a known command
first_word = user_input.split()[0].lower() if user_input.split() else ""
is_command = user_input.startswith('/') or first_word in self.known_commands

if is_command:
    # Normalize: add / if not present (for backward compatibility in handle_command)
    normalized_input = user_input if user_input.startswith('/') else '/' + user_input
    if not self.handle_command(normalized_input):
        break
    continue
```

**Logic:**
1. Extract first word from input
2. Check if input starts with `/` OR if first word is in `known_commands`
3. If command recognized, normalize by adding `/` if missing (for backward compatibility)
4. Pass normalized command to `handle_command()`

### 3. Help Text Updates

**Updated all help text to show commands without slashes:**

**General help header (line 657):**
```python
print("\nAvailable commands:")
print("  (Commands can be used with or without '/' prefix)")
```

**All command listings updated:**
```python
# Before:
print("    /help [command]    - Show this help...")

# After:
print("    help [command]    - Show this help...")
```

**Used sed for bulk updates:**
- Removed `/` from all `print("    /command...)` statements
- Updated `COMMAND_HELP` dictionary usage fields
- Updated `COMMAND_HELP` dictionary example arrays

### 4. Test Suite

Created comprehensive test suite: `tests/unit/test_slash_optional_commands.py`

**Tests:**
1. `test_known_commands_defined` - Verifies known_commands set is populated
2. `test_command_with_slash` - Tests slash commands still work
3. `test_command_without_slash` - Tests commands without slash are recognized
4. `test_non_command_not_recognized` - Ensures non-commands aren't treated as commands
5. `test_command_normalization` - Tests slash addition for backward compatibility
6. `test_first_word_extraction` - Tests parsing first word from input
7. `test_case_insensitivity` - Tests commands are case-insensitive
8. `test_multiword_command_recognition` - Tests commands with arguments
9. `test_slash_command_still_works` - Tests backward compatibility
10. `test_empty_input` - Tests empty input handling

**All tests passing ✅**

## Examples

### Before (Phase 1a)
```bash
# Only slash commands worked:
/help
/cd /tags/physics
/ls -l
```

### After (Phase 1a)
```bash
# Both syntaxes work:
help                    # NEW: works without slash
/help                   # OLD: still works

cd /tags/physics        # NEW: works without slash
/cd /tags/physics       # OLD: still works

ls -l                   # NEW: works without slash
/ls -l                  # OLD: still works
```

## Command Precedence

When user types something:

1. **Check if starts with `/`** → Command
2. **Check if first word is in `known_commands`** → Command
3. **Otherwise** → Chat input

Example:
```bash
# These are commands:
help                    # First word "help" in known_commands
cd /tags                # First word "cd" in known_commands
/quit                   # Starts with /

# These are chat:
hello there             # First word "hello" not in known_commands
explain this code       # First word "explain" not in known_commands
```

## Backward Compatibility

- All existing slash commands still work
- Help text shows new syntax but mentions slash is optional
- Internal routing normalizes by adding `/` for compatibility

## Benefits

1. **User Choice**: Users can choose which syntax they prefer
2. **Smooth Transition**: No breaking changes for existing users
3. **Future-Ready**: Prepares for unified VFS where commands are programs
4. **Familiar**: Non-slash syntax feels more like bash/shell
5. **Documented**: Help clearly states both syntaxes work

## Next Steps

**Phase 1b:** Add deprecation warnings when users use `/command` syntax
**Phase 1c:** Remove slash support entirely (after warning period)

## Files Modified

1. **`ctk/integrations/chat/tui.py`**
   - Added `known_commands` set (lines 97-106)
   - Updated input handling logic (lines 4305-4315)
   - Updated all help text (removed slashes)
   - Updated COMMAND_HELP dictionary

2. **`tests/unit/test_slash_optional_commands.py`** (NEW)
   - Comprehensive test suite for slash-optional routing
   - 10 tests covering all aspects
   - All tests passing

## Testing

To test the implementation:

```bash
# Run unit tests
pytest tests/unit/test_slash_optional_commands.py -xvs

# Manual testing in TUI:
ctk chat

# Try both syntaxes:
help                    # Should work
/help                   # Should work
cd /tags                # Should work
/cd /tags               # Should work
quit                    # Should work
/quit                   # Should work
```

## Notes

- Commands still internally use `/` prefix for backward compatibility
- The `handle_command()` method still expects `/` prefix
- Normalization layer adds `/` if missing
- Will be refactored in Phase 1c to remove slash dependency entirely
