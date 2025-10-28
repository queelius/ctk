# Network Analysis Design

## Overview

CTK's network analysis features allow users to build and analyze a graph of conversation relationships based on semantic similarity. The system uses a **single current graph** model with manual rebuild for performance.

## Command Hierarchy

### Level 0: Build Graph (Expensive)

#### `/rag embeddings [filters]`
Generate embeddings for conversations.
- Stores embedding session metadata with filters
- Marks session as "current"
- Subsequent `/rag links` uses these filters

**Example:**
```bash
/rag embeddings --starred --tags python --limit 100
# Stores: {starred: true, tags: ["python"], limit: 100}
```

#### `/rag links [--threshold T] [--max-links N] [--rebuild]`
Build conversation similarity graph.
- Uses filters from current embedding session
- Creates graph structure
- Computes all pairwise similarities (expensive!)
- Stores graph metadata + file reference
- Marks as "current graph"

**Options:**
- `--threshold`: Minimum similarity for edge (default: 0.3)
- `--max-links`: Max edges per node (default: 10)
- `--rebuild`: Force rebuild even if current graph exists

**Example:**
```bash
/rag links --threshold 0.3 --max-links 10
# Output:
Building graph from 100 conversations (from last embedding session)...
Computing pairwise similarities...
✓ Graph: 100 nodes, 487 links
✓ Cached to: graphs/graph_20250117_143022.json
```

### Level 1: Global Network Analysis (Cached)

#### `/rag network [--rebuild]`
Display global network statistics.
- Uses current cached graph
- Computes/retrieves global metrics
- Caches results in database

**Metrics shown:**
- Size: nodes, edges
- Density: edge density
- Components: number of connected components
- Giant component: size of largest component
- Diameter: longest shortest path
- Average path length
- Global clustering coefficient
- Modularity (if communities detected)

**Example:**
```bash
/rag network

Network Statistics (Graph built: 2025-01-17 14:30)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Structure:
  Nodes: 100
  Edges: 487
  Density: 0.098
  Avg degree: 9.7

Connectivity:
  Components: 2
  Giant component: 97 nodes (97%)
  Diameter: 8
  Avg path length: 3.2

Clustering:
  Global clustering: 0.34
  Avg local clustering: 0.41

Communities:
  Modularity: 0.67 (Louvain)
  Communities: 7

Source: graphs/graph_20250117_143022.json
```

### Level 2: Community Analysis (Cached)

#### `/rag communities [--algorithm louvain] [--rebuild]`
Detect and display communities.
- Uses current cached graph
- Runs community detection algorithm
- Extracts topics per community (TF-IDF on community conversations)
- Caches community assignments

**Algorithms:**
- `louvain` (default): Fast, good quality
- `label_propagation`: Very fast, lower quality
- `greedy_modularity`: Slower, high quality

**Example:**
```bash
/rag communities --algorithm louvain

Detecting communities (Louvain algorithm)...
✓ Found 7 communities

Community Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ID  Size  Density  Topics
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
0   34    0.23     asyncio, coroutines, concurrent, event-loop
1   23    0.31     fastapi, uvicorn, pydantic, routes, endpoints
2   18    0.28     pytest, fixtures, testing, mocking, coverage
3   12    0.19     sqlalchemy, orm, database, queries, models
4   8     0.35     docker, containers, deployment, images
5   3     0.67     logging, debugging, errors, traceback
6   2     0.50     performance, profiling, optimization

Modularity: 0.67 (good separation)
```

#### `/rag community <id>`
Display details about a specific community.

**Example:**
```bash
/rag community 0

Community 0: Asyncio & Concurrency
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Size: 34 conversations
Internal edges: 128
External edges: 19
Density: 0.23

Topics (TF-IDF):
  asyncio, coroutines, concurrent, event-loop, futures,
  tasks, await, async, gather, create_task

Top conversations (by degree within community):
  1. "Python asyncio comprehensive guide" (degree: 12)
  2. "Async/await patterns and best practices" (degree: 10)
  3. "Concurrency vs parallelism in Python" (degree: 9)
  ...

External connections:
  → Community 1 (FastAPI): 8 links
  → Community 2 (Testing): 6 links
  → Community 3 (Database): 5 links
```

### Level 3: Node-Level Analysis (Cached)

#### `/rag node <conversation_id>`
Display detailed metrics for a single conversation.

**Example:**
```bash
/rag node test_abc123

Conversation: "Python asyncio comprehensive guide"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Community: 0 (Asyncio & Concurrency)

Connectivity:
  Degree: 23 (highly connected)
  Neighbors: 23 conversations

Centrality:
  Degree centrality: 0.23 (top 5%)
  Betweenness: 0.045 (bridge between topics)
  Closeness: 0.67
  PageRank: 0.034
  Eigenvector: 0.12

Local structure:
  Clustering coefficient: 0.41
  Ego network: 23 nodes, 87 edges

Top neighbors (by similarity):
  0.87  "Async/await patterns" (same community)
  0.82  "Concurrency in Python" (same community)
  0.76  "FastAPI async endpoints" (community 1)
  ...
```

#### `/rag neighbors <conversation_id> [--limit N]`
List neighboring conversations.

**Example:**
```bash
/rag neighbors test_abc123 --limit 5

Neighbors of "Python asyncio comprehensive guide":
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Similarity  Title                           Community
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
0.87        Async/await patterns            0 (Asyncio)
0.82        Concurrency in Python           0 (Asyncio)
0.76        FastAPI async endpoints         1 (FastAPI)
0.71        Background tasks with asyncio   0 (Asyncio)
0.68        Error handling in async code    0 (Asyncio)
```

#### `/rag hubs [--top N]`
List most connected conversations (highest degree).

**Example:**
```bash
/rag hubs --top 5

Most Connected Conversations (Hubs):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rank  Degree  Title                           Community
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1     34      Python best practices           Multi-topic
2     28      FastAPI comprehensive tutorial  1 (FastAPI)
3     23      Asyncio guide                   0 (Asyncio)
4     21      Testing strategies in Python    2 (Testing)
5     19      Database design patterns        3 (Database)
```

#### `/rag bridges [--top N]`
List bridge conversations (highest betweenness centrality).

**Example:**
```bash
/rag bridges --top 5

Bridge Conversations (High Betweenness):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rank  Betweenness  Title                           Connects
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1     0.123        Python async vs threading       0 ↔ 2
2     0.089        FastAPI + async background      0 ↔ 1
3     0.076        Testing async code              0 ↔ 2
4     0.064        SQLAlchemy async sessions       0 ↔ 3
5     0.058        Logging in production           Multi
```

#### `/rag central [--metric pagerank] [--top N]`
List most central conversations by various metrics.

**Metrics:**
- `pagerank` (default): Google's algorithm
- `betweenness`: Bridge nodes
- `closeness`: Close to all others
- `eigenvector`: Connected to important nodes
- `degree`: Simple connection count

**Example:**
```bash
/rag central --metric pagerank --top 5

Most Central Conversations (PageRank):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Rank  PageRank  Title                           Community
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1     0.034     Python best practices           Multi-topic
2     0.028     FastAPI tutorial                1 (FastAPI)
3     0.025     Asyncio comprehensive guide     0 (Asyncio)
4     0.021     Testing patterns                2 (Testing)
5     0.019     Database optimization           3 (Database)
```

## Database Schema

### Current Graph Metadata
```sql
CREATE TABLE current_graph (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- Only one row
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Embedding session reference
    embedding_session_id INTEGER REFERENCES embedding_sessions(id),

    -- Graph build parameters
    threshold REAL NOT NULL,
    max_links_per_node INTEGER,

    -- File references
    graph_file_path TEXT NOT NULL,  -- e.g., "graphs/graph_20250117_143022.json"

    -- Global metrics (cached)
    num_nodes INTEGER,
    num_edges INTEGER,
    density REAL,
    num_components INTEGER,
    giant_component_size INTEGER,
    avg_path_length REAL,
    diameter INTEGER,
    global_clustering REAL,
    avg_local_clustering REAL,

    -- Community detection (if run)
    communities_algorithm TEXT,  -- louvain, label_propagation, etc.
    num_communities INTEGER,
    modularity REAL
);
```

### Embedding Sessions
```sql
CREATE TABLE embedding_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Embedding config
    provider TEXT NOT NULL,
    model TEXT,
    chunking_strategy TEXT,
    aggregation_strategy TEXT,
    role_weights_json TEXT,  -- {"user": 2.0, "assistant": 1.0}

    -- Filters used (JSON)
    filters_json TEXT,  -- {"starred": true, "tags": ["python"], "limit": 100}

    -- Results
    num_conversations INTEGER,

    -- Status
    is_current BOOLEAN DEFAULT FALSE
);
```

### Communities (for current graph)
```sql
CREATE TABLE current_communities (
    community_id INTEGER PRIMARY KEY,
    algorithm TEXT NOT NULL,  -- louvain, etc.

    -- Community properties
    size INTEGER,
    internal_edges INTEGER,
    external_edges INTEGER,
    density REAL,

    -- Topics (TF-IDF extracted)
    topics_json TEXT,  -- ["asyncio", "coroutines", "concurrent"]

    -- Members
    conversation_ids_json TEXT  -- ["conv1", "conv2", ...]
);
```

### Node Metrics (for current graph)
```sql
CREATE TABLE current_node_metrics (
    conversation_id TEXT PRIMARY KEY,

    -- Basic metrics
    degree INTEGER,
    clustering_coefficient REAL,

    -- Centrality (computed lazily)
    degree_centrality REAL,
    betweenness_centrality REAL,
    closeness_centrality REAL,
    eigenvector_centrality REAL,
    pagerank REAL,

    -- Community membership
    community_id INTEGER
);
```

## File Storage

```
<db_dir>/
├── conversations.db
├── media/
└── graphs/
    └── graph_20250117_143022.json  -- Current graph (Cytoscape format)
```

**Note:** We only keep one graph file at a time. When rebuilding, we overwrite.

## Export Options

For visualization, we should support:

```bash
/rag export [--format cytoscape|gephi|graphml|json] [--output path]
```

**Formats:**
- `cytoscape` (default): Cytoscape.js JSON for web visualization
- `gephi`: GEXF format for Gephi
- `graphml`: GraphML for general tools
- `json`: Simple nodes/edges JSON

**Example:**
```bash
/rag export --format cytoscape --output my_network.json
# Creates file that can be visualized in browser with Cytoscape.js
```

**Future:** Could generate HTML file with embedded Cytoscape.js visualization:
```bash
/rag export --format html --output network.html
# Opens in browser, interactive visualization
```

## Implementation Priority

### Phase 1: Core (Week 1)
1. ✅ Graph building (`ConversationGraphBuilder`) - Already done
2. Database schema for current graph
3. Embedding session tracking with filters
4. `/rag links` implementation with caching
5. `/rag network` global metrics

### Phase 2: Communities (Week 2)
1. ✅ Community detection algorithms - Already done
2. Community topic extraction (TF-IDF on community conversations)
3. `/rag communities` implementation
4. `/rag community <id>` implementation

### Phase 3: Node-Level (Week 3)
1. Centrality computation (lazy)
2. `/rag node <id>` implementation
3. `/rag neighbors <id>` implementation
4. `/rag hubs`, `/rag bridges`, `/rag central` implementation

### Phase 4: Export & Visualization (Week 4)
1. `/rag export` command
2. HTML export with Cytoscape.js
3. Integration with existing `/export` command

## Performance Considerations

### Expensive Operations (Always Cached)
1. **Pairwise similarities**: O(N²) - Done in `/rag links`
2. **Community detection**: O(N log N) to O(N²) - Cache results
3. **Betweenness centrality**: O(N³) - Lazy compute, cache
4. **PageRank**: O(N × E × iterations) - Lazy compute, cache

### Fast Operations (Computed on demand)
1. **Degree**: O(1) lookup
2. **Neighbors**: O(1) lookup
3. **Global metrics**: O(N + E), cached anyway

### Cache Invalidation
Only rebuild when user explicitly runs:
- `/rag embeddings --rebuild`
- `/rag links --rebuild`
- `/rag communities --rebuild`

## Error Handling

```bash
# If no graph exists
You: /rag network
Error: No graph found. Run '/rag links' first to build a graph.

# If embeddings changed
You: /rag embeddings --starred
You: /rag network
Warning: Graph was built with different filters.
Current graph: All conversations
New embeddings: Starred only
Run '/rag links --rebuild' to rebuild graph with new embeddings.

# If graph is stale
You: /rag links
Building graph...
Note: Using embeddings from 2025-01-15 (2 days old)
Use '/rag embeddings --rebuild' to refresh embeddings first.
```

## See Also
- `docs/SIMILARITY_API_DESIGN.md` - Original API design
- `docs/RAG_SIMILARITY_README.md` - User guide for similarity
- `docs/RAG_FILTERING_GUIDE.md` - Filtering options for embeddings
