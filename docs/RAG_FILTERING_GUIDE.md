# RAG Embeddings Filtering Guide

## Overview

The `/rag embeddings` command now supports comprehensive filtering options, allowing you to generate embeddings for specific subsets of your conversation database. This is useful for:

- **Performance**: Embed only relevant conversations instead of all conversations
- **Focused similarity**: Create embeddings for specific topics, projects, or sources
- **Incremental updates**: Embed only new or starred conversations
- **Resource management**: Control memory and computation by limiting the number of conversations

## Available Filters

### Basic Filters

#### `--limit N`
Limit the number of conversations to embed.

**Default**: `None` (all conversations)

**Examples**:
```
/rag embeddings --limit 100        # Embed only 100 most recent conversations
/rag embeddings --limit 50 --force # Re-embed 50 conversations
```

#### `--provider PROVIDER`
Specify the embedding provider.

**Default**: `tfidf`

**Options**: `tfidf` (more providers coming: `ollama`, `openai`, etc.)

**Examples**:
```
/rag embeddings --provider tfidf
```

#### `--force`
Re-embed all conversations, ignoring cached embeddings.

**Default**: `False` (skip already-embedded conversations)

**Examples**:
```
/rag embeddings --force                    # Re-embed all
/rag embeddings --starred --force          # Re-embed starred only
```

### Search Filter

#### `--search QUERY`
Filter conversations by keyword search in titles and content.

**Examples**:
```
/rag embeddings --search python            # Only conversations about Python
/rag embeddings --search "error handling"  # Search for phrase
/rag embeddings --search API --limit 50    # First 50 API-related conversations
```

**Use cases**:
- Embed only technical conversations: `--search programming`
- Embed project-specific discussions: `--search "project alpha"`
- Focus on specific topics: `--search machine-learning`

### Organization Filters

#### `--starred`
Only embed starred conversations.

**Examples**:
```
/rag embeddings --starred              # Important conversations only
/rag embeddings --starred --limit 20   # Top 20 starred conversations
```

#### `--pinned`
Only embed pinned conversations.

**Examples**:
```
/rag embeddings --pinned               # Pinned conversations only
```

### Metadata Filters

#### `--tags TAG1,TAG2,...`
Filter by tags (comma-separated, matches ANY tag).

**Examples**:
```
/rag embeddings --tags python                    # Python-tagged conversations
/rag embeddings --tags python,machine-learning   # Python OR ML conversations
/rag embeddings --tags research --starred        # Starred research conversations
```

#### `--source SOURCE`
Filter by conversation source platform.

**Common sources**: `openai`, `anthropic`, `google`, `local`

**Examples**:
```
/rag embeddings --source openai            # OpenAI conversations only
/rag embeddings --source anthropic --limit 100
```

#### `--project PROJECT`
Filter by project name.

**Examples**:
```
/rag embeddings --project research         # Research project conversations
/rag embeddings --project ctk-dev          # CTK development conversations
```

#### `--model MODEL`
Filter by LLM model used.

**Examples**:
```
/rag embeddings --model gpt-4              # GPT-4 conversations only
/rag embeddings --model claude-3           # Claude 3 conversations only
```

## Combining Filters

Filters can be combined for powerful targeting:

### Example 1: Focused Topic Embeddings
```
/rag embeddings --search python --tags machine-learning --limit 100
```
Embeds up to 100 conversations about Python and machine learning.

### Example 2: Project-Specific Embeddings
```
/rag embeddings --project research --source openai --starred
```
Embeds starred research conversations from OpenAI.

### Example 3: Quality-Focused Embeddings
```
/rag embeddings --starred --limit 50 --force
```
Re-embeds the 50 most important conversations.

### Example 4: Incremental Updates
```
/rag embeddings --search "new feature" --limit 20
```
Embeds only recent conversations about new features.

## Filter Logic

### How Filters Work

1. **Search filter** (`--search`): Uses `search_conversations()` for full-text search
2. **Other filters**: Use `list_conversations()` for metadata filtering
3. **Combination**: All filters are AND-ed together (must satisfy all conditions)
4. **Tags**: Multiple tags are OR-ed (matches ANY tag)

### Filter Priority

Filters are applied in this order:
1. Search/list conversations based on criteria
2. Apply limit (if specified)
3. Check cache (unless `--force`)
4. Embed matching conversations

## Performance Considerations

### TF-IDF Fitting

When using TF-IDF, the vectorizer must be fitted on the **filtered corpus**, not the entire database.

**Good practice**:
```
/rag embeddings --search python          # Fits on Python conversations only
```

**Result**: TF-IDF learns vocabulary specific to Python discussions.

### Memory Usage

- **TF-IDF**: ~1-10KB per embedding (sparse)
- **1000 conversations**: ~5-10 seconds to fit + embed
- **10,000 conversations**: ~30-60 seconds

**Recommendation**: Use `--limit` for large databases during experimentation.

### Caching Strategy

Embeddings are cached by:
- Conversation ID
- Provider
- Model
- Chunking strategy
- Aggregation strategy

**Important**: Changing filters doesn't invalidate cache. Use `--force` to re-embed.

## Use Cases

### Use Case 1: Topic-Specific Similarity

**Goal**: Find similar conversations within a specific domain.

```bash
# Step 1: Embed domain-specific conversations
/rag embeddings --tags database --search SQL

# Step 2: Find similar within that domain
/load <conversation_id>
/rag similar --top-k 5
```

### Use Case 2: Quality-Focused RAG

**Goal**: Create embeddings only for high-quality conversations.

```bash
# Embed only starred, well-tagged conversations
/rag embeddings --starred --tags python,machine-learning,best-practices

# Use for similarity
/rag similar --top-k 10 --threshold 0.5
```

### Use Case 3: Project-Specific Knowledge Base

**Goal**: Build a project-specific embedding set.

```bash
# Embed project conversations
/rag embeddings --project myproject --source openai

# Find related project discussions
/rag similar --top-k 5
```

### Use Case 4: Incremental Embedding Updates

**Goal**: Embed new conversations without re-processing old ones.

```bash
# Initial embedding (all conversations)
/rag embeddings

# Later: embed only new conversations
/rag embeddings --limit 50  # 50 most recent

# Re-embed starred conversations that were updated
/rag embeddings --starred --force
```

## Troubleshooting

### "No conversations found matching filters"

**Cause**: Filters are too restrictive.

**Solution**:
1. Check filter values: `/list --tags python` to verify tags exist
2. Remove filters one by one to find the issue
3. Use `--search` with broader terms

### "Fitted with 0 features" (TF-IDF)

**Cause**: No text content in filtered conversations.

**Solution**:
1. Verify conversations have messages: `/show <id>`
2. Check filter isn't excluding all conversations
3. Try without filters: `/rag embeddings`

### Embeddings not updating

**Cause**: Cache is being used.

**Solution**: Use `--force` to re-embed:
```
/rag embeddings --starred --force
```

## Best Practices

1. **Start small**: Test with `--limit 10` before embedding thousands of conversations
2. **Use filters strategically**: Embed subsets for specific use cases
3. **Combine starred + tags**: `--starred --tags important-topic` for quality + relevance
4. **Monitor performance**: Note how long embeddings take for your database size
5. **Cache wisely**: Don't use `--force` unless you've changed configuration
6. **Document your filters**: Keep track of which filter combinations you use

## Command Reference

### Full Syntax
```
/rag embeddings [--provider PROVIDER] [--force] [--limit N] [--search QUERY]
                [--starred] [--pinned] [--tags TAG1,TAG2] [--source SOURCE]
                [--project PROJECT] [--model MODEL]
```

### Quick Examples
```bash
# Minimal
/rag embeddings

# With search
/rag embeddings --search python

# Multiple filters
/rag embeddings --starred --tags research --limit 100

# Force re-embedding
/rag embeddings --force

# Project-specific
/rag embeddings --project myproject --source openai --limit 50

# Quality subset
/rag embeddings --starred --pinned --tags important
```

## See Also

- **Main guide**: `docs/RAG_SIMILARITY_README.md`
- **TUI integration**: `docs/RAG_TUI_INTEGRATION.md`
- **API design**: `docs/SIMILARITY_API_DESIGN.md`
- **Help command**: `/help rag` in TUI
