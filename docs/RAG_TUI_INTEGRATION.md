# CTK RAG Commands - TUI Integration

## Overview

The RAG/Similarity system is now fully integrated into the CTK TUI (Terminal User Interface). Users can generate embeddings and find similar conversations directly from the chat interface.

Use `/help rag` in the TUI for detailed command help and examples.

## Available Commands

### 1. `/rag embeddings [options]`

Generate embeddings for conversations in the database.

**Options:**
- `--provider`: Embedding provider to use (default: tfidf)
- `--force`: Re-embed all conversations, ignoring cache
- `--limit N`: Limit number of conversations (default: all)
- `--search QUERY`: Filter by keyword search in title/content
- `--starred`: Only starred conversations
- `--pinned`: Only pinned conversations
- `--tags TAG1,TAG2`: Filter by tags (comma-separated)
- `--source SOURCE`: Filter by source (e.g., openai, anthropic)
- `--project PROJECT`: Filter by project name
- `--model MODEL`: Filter by model (e.g., gpt-4, claude-3)

See `docs/RAG_FILTERING_GUIDE.md` for detailed filtering documentation.

**Examples:**

Basic usage:
```
You: /rag embeddings
Generating embeddings using tfidf...
Found 851 conversations
Fitting TF-IDF on corpus...
✓ Fitted with 5234 features
Embedding conversations...
✓ Embedded 851 conversations
```

With filtering:
```
You: /rag embeddings --search python --limit 50
Generating embeddings using tfidf (search='python')...
Found 50 conversations
Fitting TF-IDF on corpus...
✓ Fitted with 2341 features
Embedding conversations...
✓ Embedded 50 conversations
```

Multiple filters:
```
You: /rag embeddings --starred --tags machine-learning
Generating embeddings using tfidf (starred, tags=machine-learning)...
Found 23 conversations
Fitting TF-IDF on corpus...
✓ Fitted with 1876 features
Embedding conversations...
✓ Embedded 23 conversations
```

**How it works:**
1. Loads all conversations from database
2. Fits TF-IDF vectorizer on the entire corpus
3. Generates embeddings for each conversation
4. Caches embeddings in database (skips already-embedded unless `--force`)
5. Uses role-based weighting (user messages: 2x, assistant: 1x)

### 2. `/rag similar [conv_id] [--top-k N] [--threshold T] [--provider tfidf]`

Find conversations similar to a given conversation.

**Options:**
- `conv_id`: Conversation ID to find similar conversations for (optional, uses current conversation if not specified)
- `--top-k`: Number of results to return (default: 10)
- `--threshold`: Minimum similarity score (default: 0.0)
- `--provider`: Embedding provider (default: tfidf)

**Example:**
```
You: /rag similar --top-k 5
Finding conversations similar to: 'Python asyncio tutorial'

                        Similar Conversations (top 5)
┏━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Rank ┃ Similarity ┃ Title                    ┃ Tags           ┃ ID            ┃
┡━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ 1    │ 0.372      │ Python type hints        │ python, typing │ test_4f2a9... │
│ 2    │ 0.285      │ Python async practices   │ python, async  │ test_7d3c1... │
│ 3    │ 0.192      │ FastAPI tutorial         │ python, web    │ test_2b8e4... │
│ 4    │ 0.173      │ SQLAlchemy ORM guide     │ python, db     │ test_9a1f6... │
│ 5    │ 0.133      │ React hooks tutorial     │ react, js      │ test_5c7d2... │
└──────┴────────────┴──────────────────────────┴────────────────┴───────────────┘
```

**How it works:**
1. Loads the query conversation (current or specified)
2. Fits TF-IDF if not already fitted
3. Computes similarity with all other conversations
4. Returns top-K results sorted by similarity
5. Displays results in a Rich table

**Using current conversation:**
```
You: /load test_abc123
You: /rag similar --top-k 3
Finding conversations similar to: 'Current conversation title'
...
```

### 3. `/rag links [--threshold T]`

**Status:** Not yet implemented

Build a graph of conversation relationships based on similarity.

**Placeholder message:**
```
You: /rag links
Error: /rag links not yet implemented
Use the Python API: ConversationGraphBuilder
```

## Configuration

Embeddings are configured with:
- **Provider**: tfidf (local, fast)
- **Chunking**: MESSAGE (each message is a chunk)
- **Aggregation**: WEIGHTED_MEAN (role-weighted averaging)
- **Role weights**:
  - User: 2.0 (questions weighted heavily)
  - Assistant: 1.0 (baseline)
  - System: 0.5 (system prompts less important)
  - Tool: 0.3 (tool calls less important)
- **TF-IDF config**:
  - Max features: 5000
  - N-gram range: [1, 2] (unigrams + bigrams)

## Workflow Examples

### Example 1: Find Similar Conversations

```bash
# Start TUI with your database
ctk chat

# Generate embeddings (one-time setup)
You: /rag embeddings

# List conversations to get IDs
You: /list

# Find similar to a specific conversation
You: /rag similar test_abc123 --top-k 10

# Or use currently loaded conversation
You: /load test_abc123
You: /rag similar
```

### Example 2: Explore Related Topics

```bash
You: /search "python async"
# Shows list of conversations about Python async

You: /load <first_result_id>
# Loads the conversation

You: /rag similar --top-k 5 --threshold 0.3
# Shows only highly similar conversations (>0.3 similarity)
```

### Example 3: Re-generate Embeddings

```bash
# If you've changed the embedding configuration or want fresh embeddings
You: /rag embeddings --force
```

## Testing the Commands

A test script is available to create a sample database:

```bash
python examples/test_rag_tui_commands.py
```

This creates a test database at `/tmp/ctk_test_rag_tui` with 3 sample conversations.

Then test the commands:

```bash
ctk chat --db /tmp/ctk_test_rag_tui

# In the TUI:
You: /rag embeddings
You: /list
You: /rag similar test_<id_from_list>
```

## Implementation Details

### File: `ctk/integrations/chat/tui.py`

**Added command handler:**
```python
elif cmd == '/rag':
    if not args:
        print("Error: /rag requires a subcommand (embeddings, similar, links)")
        # ... usage help
    else:
        self.handle_rag_command(args)
```

**Added method: `handle_rag_command()`**
- ~250 lines
- Handles all three subcommands
- Uses the similarity API (`ConversationEmbedder`, `SimilarityComputer`)
- Displays results using Rich tables

### Dependencies

- `ctk.core.similarity`: Core similarity computation
- `ctk.integrations.embeddings.tfidf`: TF-IDF provider
- `rich`: Table formatting

## Performance

### TF-IDF Embedding Speed
- **Fitting**: O(N × M) where N = documents, M = avg length
- **Embedding**: ~100-500 conversations/sec
- **Memory**: ~1-10KB per embedding (sparse)

### Expected Times
- **1000 conversations**: ~5-10 seconds to fit + embed
- **10,000 conversations**: ~30-60 seconds
- **Finding similar**: <1 second (with cached embeddings)

## Caching

Embeddings are cached in the database:
- First run: Fits TF-IDF and embeds all conversations
- Subsequent runs: Skips already-embedded conversations
- Use `--force` to re-embed all

Similarities are also cached:
- Computed once, stored in database
- Reused for faster queries

## Limitations

1. **TF-IDF only**: Currently only supports TF-IDF embeddings
   - Future: Ollama, OpenAI, Voyage AI providers

2. **No graph visualization**: `/rag links` not yet implemented
   - Workaround: Use Python API (`ConversationGraphBuilder`)

3. **No incremental updates**: Adding new conversations requires re-fitting
   - Workaround: Use `--force` to re-embed all

## Future Enhancements

1. **Provider selection**: Support Ollama, OpenAI embeddings
2. **Graph visualization**: Implement `/rag links` with ASCII/Rich display
3. **Semantic search**: Natural language queries over embeddings
4. **Clustering**: Automatic topic detection and grouping
5. **Recommendations**: "You might be interested in..." suggestions

## Troubleshooting

### "No conversations found in database"
- Check you're using the correct database
- Import some conversations first

### "TF-IDF vectorizer not fitted"
- Run `/rag embeddings` first before `/rag similar`

### "Conversation not found"
- Use `/list` to see available conversation IDs
- Check you're using the full conversation ID

### Empty similarity results
- Lower the `--threshold` value
- Check embeddings were generated: `/rag embeddings`
- Verify conversations have content (not empty)

## See Also

- **Design Document**: `docs/SIMILARITY_API_DESIGN.md`
- **Implementation Summary**: `docs/SIMILARITY_IMPLEMENTATION_SUMMARY.md`
- **User Guide**: `docs/RAG_SIMILARITY_README.md`
- **Example Script**: `examples/similarity_quickstart.py`
- **Test Script**: `examples/test_similarity_system.py`
