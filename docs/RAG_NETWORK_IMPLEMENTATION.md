# `/rag network` Command - Implementation Summary

## Overview

Implemented the `/rag network` command to compute and display global network statistics for conversation similarity graphs. The command computes expensive metrics (diameter, clustering, etc.) once and caches them in the database for instant repeated access.

## Key Features

1. **Comprehensive Metrics**: Density, connectivity, diameter, clustering, components
2. **Intelligent Caching**: Computes once, reuses forever (unless `--rebuild`)
3. **Fast Display**: Cached metrics load instantly from database
4. **NetworkX Integration**: Leverages NetworkX for robust graph analysis
5. **Readable Output**: Formatted statistics with clear sections

## Command Usage

### Basic Usage

```bash
You: /rag network
```

First run computes metrics, subsequent runs load from cache.

### Force Recompute

```bash
You: /rag network --rebuild
```

Recomputes all metrics even if cached (useful after graph changes).

## Example Output

```
Network Statistics (Graph built: 2025-01-18 14:30)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Structure:
  Nodes: 42
  Edges: 187
  Density: 0.214
  Avg degree: 8.9

Connectivity:
  Components: 2
  Giant component: 40 nodes (95%)
  Diameter: 6
  Avg path length: 2.8

Clustering:
  Global clustering: 0.412
  Avg local clustering: 0.489

Parameters:
  Similarity threshold: 0.3
  Max links per node: 10

Source: /path/to/db/graphs/graph_20250118_143022.json
```

## Metrics Explained

### Structure Section

- **Nodes**: Number of conversations in graph
- **Edges**: Number of similarity links between conversations
- **Density**: Proportion of possible edges that exist (0 to 1)
  - 0.0 = No connections
  - 1.0 = Fully connected (every node connected to every other)
  - Typical: 0.1-0.3 for similarity graphs
- **Avg degree**: Average number of connections per conversation
  - Related to max_links parameter
  - Higher = more interconnected topics

### Connectivity Section

- **Components**: Number of disconnected subgraphs
  - 1 = All conversations reachable from each other
  - >1 = Multiple isolated topic clusters
- **Giant component**: Largest connected subgraph
  - Size and percentage of total nodes
  - Usually contains most of the graph
- **Diameter**: Longest shortest path between any two nodes
  - Measures graph "width"
  - Lower = more tightly connected
- **Avg path length**: Average shortest path between all node pairs
  - Measures typical separation
  - Related to "six degrees of separation"

### Clustering Section

- **Global clustering** (Transitivity): Fraction of triangles in graph
  - If A→B and B→C, how often does A→C exist?
  - Measures "friend of friend is my friend"
  - Higher = more cohesive topic communities
- **Avg local clustering**: Average clustering per node
  - How interconnected are each node's neighbors?
  - Higher = conversations tend to form tight groups

### Parameters Section

Shows settings used to build the graph:
- **Similarity threshold**: Minimum similarity for edge creation
- **Max links per node**: Maximum edges per conversation

## Implementation Details

### Network Analysis Module (`ctk/core/network_analysis.py`)

**New Module** with utilities for graph analysis:

1. **`load_graph_from_file(graph_path)`**
   - Loads graph JSON and converts to NetworkX format
   - Returns NetworkX Graph object

2. **`compute_global_metrics(G)`**
   - Computes all network statistics
   - Returns dictionary with metrics
   - Handles disconnected graphs gracefully

3. **`format_network_stats(graph_metadata, G)`**
   - Formats metrics for display
   - Sections: Structure, Connectivity, Clustering, Parameters
   - Returns formatted string

4. **`save_network_metrics_to_db(db, metrics)`**
   - Saves computed metrics to database
   - Updates `current_graph` table

### Database Schema Updates

Added `avg_degree` field to `CurrentGraphModel`:

```python
class CurrentGraphModel(Base):
    # ... existing fields ...

    avg_degree: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
```

Updated `to_dict()` method to include avg_degree.

### TUI Integration (`ctk/integrations/chat/tui.py`)

**Command Flow:**

1. **Parse Options**: Extract `--rebuild` flag

2. **Get Graph Metadata**:
   - Loads current graph from database
   - Checks if metrics already cached

3. **Cache Check**:
   - If `density` is not None and `--rebuild` not set → use cache
   - Otherwise → compute metrics

4. **Compute Metrics** (if needed):
   - Load graph from JSON file
   - Use NetworkX to compute metrics
   - Save to database for caching

5. **Display Results**:
   - Format statistics with sections
   - Show all computed metrics

## Workflow Example

### Complete Workflow from Scratch

```bash
# Step 1: Generate embeddings
You: /rag embeddings --starred --limit 50
Generating embeddings using tfidf (starred)...
Found 50 conversations
Fitting TF-IDF on corpus...
✓ Fitted with 2341 features
Embedding conversations...
✓ Embedded 50 conversations
✓ Saved embedding session (ID: 1)

# Step 2: Build graph
You: /rag links --threshold 0.3
Building graph from embedding session 1...
Using filters: {'starred': True, 'limit': 50}
Found 50 conversations
Computing pairwise similarities (threshold=0.3)...
✓ Graph: 50 nodes, 234 edges
✓ Saved to: /path/to/db/graphs/graph_20250118_143022.json
✓ Graph metadata saved to database

Use /rag network to view global statistics

# Step 3: View network statistics (first time - computes)
You: /rag network
Computing network statistics...

Network Statistics (Graph built: 2025-01-18 14:30)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Structure:
  Nodes: 50
  Edges: 234
  Density: 0.191
  Avg degree: 9.4

Connectivity:
  Components: 1
  Giant component: 50 nodes (100%)
  Diameter: 5
  Avg path length: 2.3

Clustering:
  Global clustering: 0.467
  Avg local clustering: 0.521

Parameters:
  Similarity threshold: 0.3
  Max links per node: 10

Source: /path/to/db/graphs/graph_20250118_143022.json

# Step 4: View again (instant - cached)
You: /rag network

Network Statistics (Graph built: 2025-01-18 14:30)
[... same output, instant ...]
```

## Performance

### First Run (Computing Metrics)

| Nodes | Time Estimate |
|-------|---------------|
| 10    | < 0.1 seconds |
| 100   | < 1 second    |
| 1,000 | 2-5 seconds   |
| 10,000| 20-60 seconds |

**Note**: Diameter and path length are most expensive (O(N²) to O(N³)).

### Cached Runs

Instant (< 0.01 seconds) - just database lookup.

## Caching Strategy

Metrics are cached in the `current_graph` table:

```python
# First run
density = None  # Not yet computed
→ Load graph from file
→ Compute all metrics with NetworkX
→ Save to database

# Subsequent runs
density = 0.191  # Already cached
→ Skip computation
→ Display from database
```

**Cache invalidation**: Only when `--rebuild` flag used or new graph built.

## Error Handling

### Error 1: No Graph Exists

```bash
You: /rag network
Error: No graph found. Run '/rag links' first to build a graph.
```

**Solution**: Run `/rag links` to build graph.

### Error 2: Graph File Missing

```bash
You: /rag network
Computing network statistics...
Error: Graph file not found: /path/to/graph.json
Run '/rag links --rebuild' to regenerate the graph
```

**Solution**:
- Graph metadata exists but file was deleted
- Run `/rag links --rebuild` to regenerate

### Error 3: NetworkX Not Installed

```bash
You: /rag network
Computing network statistics...
Error: NetworkX required: pip install networkx
```

**Solution**: Install NetworkX (`pip install networkx`)

## Integration with Other Commands

### After `/rag links`

```bash
You: /rag links
[builds graph]
✓ Graph metadata saved to database

Use /rag network to view global statistics

You: /rag network
[displays statistics]
```

### Before `/rag communities` (Future)

```bash
You: /rag network
[shows 2 components, modularity would help]

You: /rag communities
[runs community detection to understand structure]
```

## Testing

Created comprehensive test suite (`/tmp/test_network_command.py`):

✅ **Test 1**: Save graph metadata to database
✅ **Test 2**: Load graph from file
✅ **Test 3**: Compute global metrics
✅ **Test 4**: Save metrics to database
✅ **Test 5**: Retrieve cached metrics
✅ **Test 6**: Format network statistics

All tests pass successfully.

## Files Modified

1. **`ctk/core/network_analysis.py`** (NEW - 256 lines)
   - Graph loading and metric computation
   - Formatting utilities
   - Database integration

2. **`ctk/core/db_models.py`**
   - Added `avg_degree` field to `CurrentGraphModel` (line 459)
   - Updated `to_dict()` method (line 494)

3. **`ctk/core/database.py`**
   - Updated `get_current_graph()` to include avg_degree (line 1569)

4. **`ctk/integrations/chat/tui.py`**
   - Implemented `/rag network` command (lines 3595-3650)
   - Updated help text (lines 483-503)
   - Added examples

## Benefits

1. **Fast Access**: Cached metrics load instantly
2. **Comprehensive**: All major network statistics in one view
3. **Readable**: Formatted output with clear sections
4. **Efficient**: Expensive computations only done once
5. **Flexible**: Can recompute with `--rebuild` if needed

## Interpreting Results

### High Density (> 0.5)

- Conversations are highly interconnected
- Most topics relate to most other topics
- Might indicate: broad thematic similarity or high threshold

### Low Density (< 0.1)

- Sparse connections
- Conversations form distinct clusters
- Might indicate: diverse topics or low threshold

### Multiple Components

- Disconnected topic clusters
- Some conversations unreachable from others
- Consider: lowering threshold or examining isolated groups

### High Clustering (> 0.4)

- Strong community structure
- Conversations form cohesive groups
- Good candidate for community detection

### Low Diameter (< 5)

- "Small world" network
- Quick paths between any two conversations
- Information/ideas spread quickly

## Next Steps

With network statistics complete, the remaining implementations are:

1. **`/rag communities`** - Community detection and topic extraction
2. **Node-level commands** - `/rag node`, `/rag hubs`, `/rag bridges`, etc.
3. **`/rag export`** - Export graph to various formats

## See Also

- **Design Document**: `docs/NETWORK_ANALYSIS_DESIGN.md`
- **Links Implementation**: `docs/RAG_LINKS_IMPLEMENTATION.md`
- **Embedding Sessions**: `docs/EMBEDDING_SESSION_TRACKING.md`
- **NetworkX Documentation**: https://networkx.org/
