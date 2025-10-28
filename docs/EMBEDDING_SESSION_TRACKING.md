# Embedding Session Tracking - Implementation Summary

## Overview

Implemented tracking of embedding generation sessions to enable filter recall for network analysis commands. When users run `/rag embeddings` with filters, the system now stores:
- Which filters were applied (starred, tags, search, etc.)
- Embedding configuration used (provider, model, role weights)
- Number of conversations processed
- Timestamp and current status

This metadata enables `/rag links` to automatically recall and reuse the same filters when building conversation graphs.

## Implementation Details

### Database Layer (`ctk/core/database.py`)

**New Methods:**

1. **`save_embedding_session()`**
   - Saves embedding session metadata to database
   - Automatically unmarks previous "current" sessions
   - Returns session ID

2. **`get_current_embedding_session()`**
   - Retrieves the most recent embedding session marked as "current"
   - Falls back to most recent session if none marked current
   - Returns dictionary with all session metadata

3. **`get_embedding_session(session_id)`**
   - Retrieves specific session by ID
   - Used for historical session lookup

4. **`list_embedding_sessions(limit)`**
   - Lists recent embedding sessions, newest first
   - Useful for debugging and session history

### TUI Integration (`ctk/integrations/chat/tui.py`)

**Modified `/rag embeddings` command:**

After successfully embedding conversations, the command now:

1. Collects all filter parameters used:
   ```python
   filters_dict = {}
   if starred is not None:
       filters_dict['starred'] = starred
   if pinned is not None:
       filters_dict['pinned'] = pinned
   # ... other filters
   ```

2. Saves session metadata:
   ```python
   session_id = self.db.save_embedding_session(
       provider=provider,
       model=provider,
       chunking_strategy="message",
       aggregation_strategy="weighted_mean",
       num_conversations=len(conversations),
       role_weights=config.role_weights,
       filters=filters_dict if filters_dict else None,
       mark_current=True
   )
   ```

3. Displays confirmation:
   ```
   ✓ Saved embedding session (ID: 1)
   ```

## Database Schema

The `EmbeddingSessionModel` table stores:

```python
class EmbeddingSessionModel(Base):
    __tablename__ = 'embedding_sessions'

    id: Mapped[int]                                    # Auto-increment primary key
    created_at: Mapped[datetime]                       # Timestamp

    # Embedding configuration
    provider: Mapped[str]                              # e.g., "tfidf"
    model: Mapped[Optional[str]]                       # Model name (if applicable)
    chunking_strategy: Mapped[str]                     # "message", "conversation"
    aggregation_strategy: Mapped[str]                  # "weighted_mean", "max", etc.
    role_weights_json: Mapped[Optional[dict]]          # {"user": 2.0, "assistant": 1.0}

    # Filters used (JSON serialized)
    filters_json: Mapped[Optional[dict]]               # All filters applied

    # Results
    num_conversations: Mapped[int]                     # Number embedded

    # Status
    is_current: Mapped[bool]                           # Currently active session
```

### Filter Storage Format

Filters are stored as JSON dictionary:

```json
{
    "starred": true,
    "tags": ["python", "machine-learning"],
    "search": "async await",
    "limit": 100,
    "source": "openai",
    "project": "research",
    "model": "gpt-4"
}
```

**Important:** Only filters that were explicitly used are stored. If no filters applied, `filters_json` is `null`.

## Usage Examples

### Example 1: Basic Embedding with Filters

```bash
You: /rag embeddings --starred --tags python --limit 100
Generating embeddings using tfidf (starred, tags=python)...
Found 42 conversations
Fitting TF-IDF on corpus...
✓ Fitted with 2341 features
Embedding conversations...
✓ Embedded 42 conversations
✓ Saved embedding session (ID: 1)
```

**Session stored:**
```python
{
    'id': 1,
    'provider': 'tfidf',
    'filters': {
        'starred': True,
        'tags': ['python'],
        'limit': 100
    },
    'num_conversations': 42,
    'is_current': True
}
```

### Example 2: Embedding Without Filters

```bash
You: /rag embeddings
Generating embeddings using tfidf...
Found 851 conversations
Fitting TF-IDF on corpus...
✓ Fitted with 5234 features
Embedding conversations...
✓ Embedded 851 conversations
✓ Saved embedding session (ID: 2)
```

**Session stored:**
```python
{
    'id': 2,
    'provider': 'tfidf',
    'filters': None,  # No filters applied
    'num_conversations': 851,
    'is_current': True
}
```

### Example 3: Filter Recall for Graph Building

Future implementation of `/rag links`:

```python
# Get current embedding session
session = db.get_current_embedding_session()

if session and session['filters']:
    # Reuse same filters to get conversations
    filters = session['filters']
    conversations = db.list_conversations(
        starred=filters.get('starred'),
        tags=filters.get('tags'),
        limit=filters.get('limit'),
        # ... other filters
    )
    print(f"Using filters from embedding session {session['id']}")
else:
    # No filters, use all conversations
    conversations = db.list_conversations()
```

## Testing

Created comprehensive test suite (`/tmp/test_embedding_sessions.py`):

✅ **Test 1:** Save embedding session with filters
✅ **Test 2:** Retrieve current embedding session
✅ **Test 3:** Save second session (unmarks previous as current)
✅ **Test 4:** List embedding sessions (ordered by date)
✅ **Test 5:** Session with no filters

All tests pass successfully.

## Benefits

1. **Automatic Filter Recall**: `/rag links` can reuse exact filters from embedding generation
2. **Session History**: Track which embeddings were generated with which parameters
3. **Debugging**: See which filters produced which results
4. **Consistency**: Ensures graph is built on same conversation set as embeddings
5. **Audit Trail**: Full history of embedding operations

## Future Enhancements

Potential additions:

1. **Session Comparison**: Compare filters between sessions
2. **Session Diff**: Show what changed between embedding runs
3. **Session Naming**: Allow users to name important sessions
4. **Session Reuse**: Re-run embedding with filters from previous session
5. **Session Export**: Export session metadata for documentation

## Files Modified

1. **`ctk/core/database.py`**
   - Added imports for new models (line 18-22)
   - Added 4 new methods (lines 1333-1476):
     - `save_embedding_session()`
     - `get_current_embedding_session()`
     - `get_embedding_session()`
     - `list_embedding_sessions()`

2. **`ctk/integrations/chat/tui.py`**
   - Modified `/rag embeddings` command (lines 3272-3301)
   - Added session metadata saving after embedding
   - Added confirmation message with session ID

3. **`ctk/core/db_models.py`**
   - Added `EmbeddingSessionModel` (lines 385-431)
   - Previous work in Phase 1

## See Also

- **Design Document**: `docs/NETWORK_ANALYSIS_DESIGN.md`
- **Database Models**: `ctk/core/db_models.py`
- **Filtering Guide**: `docs/RAG_FILTERING_GUIDE.md`
- **RAG TUI Integration**: `docs/RAG_TUI_INTEGRATION.md`
