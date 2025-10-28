# RAG Help Command Fix

## Issue

The `/rag` commands were integrated into the TUI but `/help rag` was showing "Unknown command: rag".

## Root Cause

While the `/rag` command handler was implemented and the general help text showed the RAG commands, the `COMMAND_HELP` dictionary did not include an entry for 'rag'. This meant that `/help rag` couldn't find detailed help for the command.

## Fix

Added comprehensive help entry to `ChatTUI.COMMAND_HELP` dictionary in `ctk/integrations/chat/tui.py` (lines 449-477):

```python
'rag': {
    'usage': '/rag <subcommand> [options]',
    'desc': 'RAG and similarity commands for finding related conversations',
    'details': '''Subcommands:
  embeddings [--provider tfidf] [--force]
    Generate embeddings for all conversations in the database.
    Options:
      --provider PROVIDER   Embedding provider (default: tfidf)
      --force              Re-embed all conversations, ignoring cache

  similar [conv_id] [--top-k N] [--threshold T]
    Find conversations similar to a given conversation.
    Options:
      conv_id              Conversation ID (uses current if not specified)
      --top-k N           Number of results (default: 10)
      --threshold T       Minimum similarity score (default: 0.0)
      --provider PROVIDER  Embedding provider (default: tfidf)

  links [--threshold T]
    Build a graph of conversation relationships (not yet implemented).

Note: Run '/rag embeddings' once before using '/rag similar'.''',
    'examples': [
        '/rag embeddings',
        '/rag embeddings --force',
        '/rag similar --top-k 5',
        '/rag similar test_abc123 --top-k 10 --threshold 0.3',
    ]
},
```

## Verification

Tested with `/tmp/test_rag_help.py`:
- ✅ 'rag' command found in COMMAND_HELP
- ✅ Usage, description, details, and examples all display correctly
- ✅ TUI module loads without errors

## Usage

Users can now get detailed help for RAG commands in the TUI:

```
You: /help rag

rag
Usage: /rag <subcommand> [options]

RAG and similarity commands for finding related conversations

Details: [comprehensive subcommand documentation]

Examples:
  /rag embeddings
  /rag embeddings --force
  /rag similar --top-k 5
  /rag similar test_abc123 --top-k 10 --threshold 0.3
```

## Files Modified

- `ctk/integrations/chat/tui.py` (lines 449-477): Added 'rag' entry to COMMAND_HELP
- `docs/RAG_TUI_INTEGRATION.md` (line 7): Added note about `/help rag`

## Related

- Original implementation: `docs/SIMILARITY_IMPLEMENTATION_SUMMARY.md`
- User guide: `docs/RAG_SIMILARITY_README.md`
- TUI integration: `docs/RAG_TUI_INTEGRATION.md`
