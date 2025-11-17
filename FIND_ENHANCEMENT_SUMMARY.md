# Find Command Enhancement - Long Format Support

## Summary

Enhanced the `find` command with `-l` (long format) flag to display rich metadata tables, making search results more actionable and user-friendly.

## Problem

The original `find` command showed bare conversation IDs or paths:
```bash
$ find -content 'API'
7c87af4c-5e10-4eb4-8aaa-41070f710e0f
5dce9708-0f2d-4c73-a634-b1db3517e7c1
```

**Issues:**
- Hard to know what these IDs represent
- No context about conversation titles, models, dates
- Cumbersome to navigate (`cd /chats/<id>`)
- Not user-friendly

## Solution

Added `-l` flag for **long format** with rich metadata table:

```bash
$ find -content 'API' -l

┏━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━┓
┃ # ┃ ID       ┃ Title                 ┃ Model    ┃ Updated     ┃ Tags  ┃
┡━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━┩
│ 1 │ 7c87af4c │ ⭐ API Design Doc     │ gpt-4    │ 2024-11-15  │ api   │
│ 2 │ 5dce9708 │ 📌 REST API Review    │ llama3.2 │ 2024-11-14  │ code  │
└───┴──────────┴───────────────────────┴──────────┴─────────────┴───────┘
```

**Benefits:**
- ✅ See conversation titles at a glance
- ✅ Visual flags (⭐ starred, 📌 pinned, 📦 archived)
- ✅ Model and date information
- ✅ Tags for context
- ✅ Easy to identify which conversation to navigate to

## Implementation

### Files Modified

1. **`ctk/core/commands/search.py`**
   - Added `-l` flag parsing
   - Extract conversation IDs from result paths
   - Load conversation summaries from database
   - Use `format_conversations_table()` helper for rich output
   - Capture table to string buffer for CommandResult

2. **`ctk/core/helpers.py`**
   - Modified `format_conversations_table()` to accept optional `console` parameter
   - Allows capturing output to string buffer

3. **`SHELL_COMMANDS_REFERENCE.md`**
   - Updated find command documentation
   - Added `-l` flag description
   - Added examples showing both formats

### Key Code Changes

**Added long_format flag** (search.py:71):
```python
long_format = False
```

**Parse -l option** (search.py:93-95):
```python
elif arg == '-l':
    long_format = True
    i += 1
```

**Format output with metadata** (search.py:164-193):
```python
if long_format and type_filter != 'f':
    # Extract conversation IDs from paths
    conv_ids = set()
    for result_path in results:
        parts = result_path.strip('/').split('/')
        if len(parts) >= 2 and parts[0] == 'chats':
            conv_ids.add(parts[1])

    # Load conversation summaries
    all_summaries = self.db.list_conversations()
    conversations = [s for s in all_summaries if s.id in conv_ids]

    # Display rich table
    import io
    buffer = io.StringIO()
    temp_console = Console(file=buffer, force_terminal=True)

    format_conversations_table(conversations, show_message_count=False, console=temp_console)
    return CommandResult(success=True, output=buffer.getvalue())
```

## Usage Examples

### Default Format (Good for Piping)
```bash
# Get paths only
$ find -name '*test*'
/chats/abc123.../
/chats/def456.../

# Pipe to other commands
$ find -role user | head 10
$ cd $(find -name '*bug*' | head -1)
```

### Long Format (Human-Friendly)
```bash
# See metadata with titles
$ find -content 'error' -l

# Search starred conversations with context
$ find /starred -content 'important' -l

# Find by title pattern with details
$ find -name '*API*' -type d -l
```

### Combined with Other Options
```bash
# Case-insensitive search with metadata
$ find -content 'python' -i -limit 5 -l

# Search specific directory
$ find /starred -name '*machine learning*' -l

# Find user messages in archived conversations
$ find /archived -role user -limit 20 -l
```

## Workflow Improvements

### Before (Cumbersome)
```bash
$ find -content 'API'
7c87af4c-5e10-4eb4-8aaa-41070f710e0f
5dce9708-0f2d-4c73-a634-b1db3517e7c1

# No idea what these are!
# Have to manually check each one:
$ cd /chats/7c87af4c-5e10-4eb4-8aaa-41070f710e0f
$ cat ../../title  # Doesn't exist!
$ tree | head       # Too much output
```

### After (Streamlined)
```bash
$ find -content 'API' -l

# Instantly see:
# - "API Design Doc" (starred, gpt-4, recent)
# - "REST API Review" (pinned, llama3.2, yesterday)

# Navigate to the one you want:
$ cd /chats/7c87af4c  # Tab completion from prefix!
```

## Technical Details

### Path Extraction Logic
Extracts conversation IDs from paths like:
- `/chats/abc123/` → `abc123`
- `/chats/abc123/m1/m2` → `abc123`

Works with all VFS path types that contain conversation IDs.

### Metadata Loading
- Calls `db.list_conversations()` to get all summaries
- Filters to only matching IDs
- Reuses existing `format_conversations_table()` helper
- Maintains consistent table format with other commands

### Console Capture
Uses StringIO buffer to capture Rich table output:
```python
buffer = io.StringIO()
temp_console = Console(file=buffer, force_terminal=True)
format_conversations_table(conversations, console=temp_console)
table_output = buffer.getvalue()
```

## Future Enhancements

Potential improvements:
1. **Clickable paths**: Make table rows clickable in supported terminals
2. **Custom columns**: Allow `-l` to accept column specifications (e.g., `-l id,title,model`)
3. **Sorting**: Add `-sort` flag to sort by date, title, etc.
4. **Preview**: Add `-p` flag to show content preview in table
5. **Export**: Add option to export results to JSON/CSV

## Backward Compatibility

✅ **Fully backward compatible**:
- Default behavior unchanged (paths only)
- `-l` is opt-in
- All existing scripts/pipelines continue to work
- No breaking changes

## Testing

Manual testing recommended:
```bash
# Test default format
find /chats -type d -limit 3

# Test long format
find /chats -type d -limit 3 -l

# Test with search
find -content 'error' -i -limit 5 -l

# Test piping (should use default format)
find -name '*test*' | head 5
```

## Summary

The `-l` flag transforms `find` from a purely scriptable tool into a **user-friendly search interface** while maintaining its pipeable default behavior. This addresses the user's concern about search results being "not obvious how to use."

**Key Improvements:**
- ✅ Actionable output with context
- ✅ Visual metadata (flags, colors)
- ✅ Maintains pipe-friendly default
- ✅ Consistent with Unix philosophy (ls -l pattern)
- ✅ Leverages existing helper functions
