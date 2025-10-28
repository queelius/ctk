# `/rag links` Command - Implementation Summary

## Overview

Implemented the `/rag links` command to build a conversation similarity graph based on embeddings. The graph is cached in both the database (metadata) and filesystem (graph structure) for fast reuse in subsequent network analysis commands.

## Key Features

1. **Automatic Filter Recall**: Reuses filters from most recent embedding session
2. **Graph Caching**: Stores graph metadata in database, structure in JSON file
3. **Manual Rebuild**: Expensive operation requires `--rebuild` flag if graph exists
4. **Configurable Parameters**: Adjustable similarity threshold and max links per node
5. **Progress Tracking**: Shows progress during pairwise similarity computation

## Command Usage

### Basic Usage

```bash
You: /rag links
```

Builds graph using default parameters (threshold=0.3, max_links=10).

### With Options

```bash
You: /rag links --threshold 0.5 --max-links 5
```

Custom threshold (higher = stricter) and max links per node (lower = sparser graph).

### Force Rebuild

```bash
You: /rag links --rebuild
```

Rebuilds graph even if one already exists (overwrites previous graph).

## Options

- `--threshold T`: Minimum similarity for creating edge (default: 0.3)
  - Range: 0.0 to 1.0
  - Higher values = fewer, stronger connections
  - Lower values = more, weaker connections

- `--max-links N`: Maximum outgoing links per node (default: 10)
  - Prevents over-connected graphs
  - Keeps only top-N most similar neighbors

- `--rebuild`: Force rebuild even if current graph exists
  - Warning: Expensive operation (O(N²) similarity computations)
  - Use when embeddings have changed or parameters need adjustment

## Workflow

### Step 1: Generate Embeddings (if not done)

```bash
You: /rag embeddings --starred --tags python
Generating embeddings using tfidf (starred, tags=python)...
Found 42 conversations
Fitting TF-IDF on corpus...
✓ Fitted with 2341 features
Embedding conversations...
✓ Embedded 42 conversations
✓ Saved embedding session (ID: 1)
```

### Step 2: Build Graph

```bash
You: /rag links --threshold 0.3
Building graph from embedding session 1...
Using filters: {'starred': True, 'tags': ['python']}
Found 42 conversations
Computing pairwise similarities (threshold=0.3)...
[Progress bar...]
✓ Graph: 42 nodes, 187 edges
✓ Saved to: /path/to/db/graphs/graph_20250118_143022.json
✓ Graph metadata saved to database

Use /rag network to view global statistics
```

### Step 3: Prevent Accidental Rebuild

```bash
You: /rag links
Graph already exists:
  Created: 2025-01-18 14:30:22
  Nodes: 42
  Edges: 187
  Threshold: 0.3
  File: /path/to/db/graphs/graph_20250118_143022.json

Use --rebuild to force rebuild
```

## Implementation Details

### Database Layer (`ctk/core/database.py`)

**New Methods:**

1. **`save_current_graph()`**
   - Saves/updates graph metadata in `current_graph` table
   - Only one graph exists at a time (id=1)
   - Stores file path, parameters, and cached metrics

2. **`get_current_graph()`**
   - Retrieves current graph metadata
   - Returns all cached metrics (nodes, edges, density, etc.)

3. **`delete_current_graph()`**
   - Deletes graph and all associated data
   - Cascades to communities and node metrics

### TUI Integration (`ctk/integrations/chat/tui.py`)

**Command Flow:**

1. **Parse Options**: Extract threshold, max_links, rebuild flag

2. **Check Existing Graph**:
   - If graph exists and `--rebuild` not set, show info and exit
   - Prevents accidental expensive recomputation

3. **Get Embedding Session**:
   - Retrieves current embedding session
   - Extracts filters used during embedding

4. **Filter Recall**:
   - Reapplies same filters to get conversation list
   - Ensures graph built on same set as embeddings
   - Example: If embeddings used `--starred --tags python`, links uses same

5. **Build Graph**:
   - Uses `ConversationGraphBuilder` from similarity module
   - Computes pairwise similarities (cached when possible)
   - Applies threshold and max_links constraints
   - Shows progress bar during computation

6. **Save Graph**:
   - Creates `graphs/` directory in database folder
   - Saves graph structure as JSON with timestamp
   - Example: `graphs/graph_20250118_143022.json`

7. **Save Metadata**:
   - Stores graph metadata in database
   - Links to embedding session
   - Caches basic stats (nodes, edges)

## File Structure

After running `/rag links`, the database directory contains:

```
<db_dir>/
├── conversations.db          # SQLite database
├── media/                    # Uploaded media files
└── graphs/
    └── graph_20250118_143022.json  # Current graph (Cytoscape format)
```

### Graph JSON Format

```json
{
  "nodes": [
    "conv_id_1",
    "conv_id_2",
    "conv_id_3"
  ],
  "links": [
    {
      "source_id": "conv_id_1",
      "target_id": "conv_id_2",
      "weight": 0.857,
      "metric": "cosine"
    },
    {
      "source_id": "conv_id_1",
      "target_id": "conv_id_3",
      "weight": 0.732,
      "metric": "cosine"
    }
  ],
  "metadata": {
    "threshold": 0.3,
    "max_links_per_node": 10
  }
}
```

This format is compatible with:
- Cytoscape.js for web visualization
- NetworkX for Python analysis
- Gephi for standalone visualization (after conversion)

## Database Schema

The `current_graph` table stores:

```python
class CurrentGraphModel(Base):
    __tablename__ = 'current_graph'

    id: Mapped[int]                                 # Always 1 (single row constraint)
    created_at: Mapped[datetime]                    # Build timestamp

    # Embedding session reference
    embedding_session_id: Mapped[Optional[int]]     # Links to embedding session

    # Build parameters
    threshold: Mapped[float]                        # Similarity threshold used
    max_links_per_node: Mapped[Optional[int]]       # Max edges per node

    # File reference
    graph_file_path: Mapped[str]                    # Path to graph JSON

    # Cached metrics (filled by /rag network)
    num_nodes: Mapped[Optional[int]]
    num_edges: Mapped[Optional[int]]
    density: Mapped[Optional[float]]
    num_components: Mapped[Optional[int]]
    # ... other metrics
```

## Error Handling

### Error 1: No Embedding Session

```bash
You: /rag links
Error: No embedding session found. Run /rag embeddings first.
```

**Solution**: Run `/rag embeddings` to generate embeddings.

### Error 2: No Conversations Match Filters

```bash
You: /rag links
Building graph from embedding session 1...
Using filters: {'starred': True, 'tags': ['python']}
Error: No conversations found with current filters
```

**Solution**:
- Check if conversations still match filters
- Conversations may have been deleted or unstarred
- Run `/rag embeddings --rebuild` with new filters

### Error 3: Graph Already Exists

```bash
You: /rag links
Graph already exists:
  ...
Use --rebuild to force rebuild
```

**Solution**:
- Use existing graph (efficient)
- Or use `--rebuild` to overwrite (expensive)

## Performance Considerations

### Time Complexity

- **O(N²)** for pairwise similarity computation
- **O(N log N)** for top-K selection per node

### Expected Times

| Conversations | Embeddings Cached | Time Estimate |
|--------------|------------------|---------------|
| 10           | Yes              | < 1 second    |
| 100          | Yes              | 5-10 seconds  |
| 1,000        | Yes              | 2-5 minutes   |
| 10,000       | Yes              | 30-60 minutes |

**Note**: Times assume embeddings are cached. If embeddings need generation, multiply by ~2-3x.

### Optimization Strategies

1. **Use Caching**: Always cache embeddings and similarities
2. **Filter First**: Use `--starred` or `--tags` to reduce N
3. **Higher Threshold**: Fewer edges = faster graph operations
4. **Lower Max Links**: Reduces graph density

## Integration with Other Commands

### `/rag network` (Future)

```bash
You: /rag links
[builds graph]

You: /rag network
Network Statistics (Graph built: 2025-01-18 14:30)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Structure:
  Nodes: 42
  Edges: 187
  Density: 0.21
  ...
```

Reads graph from file, computes global metrics, caches results.

### `/rag communities` (Future)

```bash
You: /rag communities --algorithm louvain
[runs community detection on current graph]
```

### `/rag export` (Future)

```bash
You: /rag export --format cytoscape --output network.json
[exports current graph to specified format]
```

## Benefits

1. **Single Source of Truth**: One current graph, no confusion
2. **Filter Consistency**: Graph uses exact same conversation set as embeddings
3. **Fast Reuse**: Cached graph avoids expensive recomputation
4. **Manual Control**: User explicitly rebuilds when needed
5. **Full Traceability**: Graph linked to embedding session with all parameters

## Testing

To test the implementation:

```bash
# Create test database
ctk chat --db /tmp/test_rag_links

# In TUI:
You: /rag embeddings --limit 10
You: /rag links
You: /rag links          # Should show "Graph already exists"
You: /rag links --rebuild  # Should rebuild
```

Expected output shows:
- Filter recall working
- Graph saved to filesystem
- Metadata saved to database
- Rebuild protection working

## Files Modified

1. **`ctk/core/database.py`**
   - Added 3 graph management methods (lines 1477-1598):
     - `save_current_graph()`
     - `get_current_graph()`
     - `delete_current_graph()`

2. **`ctk/integrations/chat/tui.py`**
   - Implemented `/rag links` command (lines 3431-3586)
   - Updated help text (lines 475-494)
   - Added usage examples

## Next Steps

With graph building complete, the next implementation phase is:

1. **`/rag network`** - Global network statistics
2. **`/rag communities`** - Community detection and analysis
3. **Node-level commands** - `/rag node`, `/rag hubs`, `/rag bridges`, etc.
4. **`/rag export`** - Export to various formats

## See Also

- **Design Document**: `docs/NETWORK_ANALYSIS_DESIGN.md`
- **Embedding Sessions**: `docs/EMBEDDING_SESSION_TRACKING.md`
- **Database Models**: `ctk/core/db_models.py`
- **Similarity Module**: `ctk/core/similarity.py`
