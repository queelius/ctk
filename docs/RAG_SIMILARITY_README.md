# CTK RAG & Similarity System

## Overview

The CTK Similarity System enables semantic search, conversation recommendation, and relationship graph generation across your conversation database. It supports multiple embedding providers (TF-IDF, Ollama, OpenAI) and provides both programmatic and CLI interfaces.

## Features

- **Multiple Embedding Providers**
  - TF-IDF (local, fast, keyword-based)
  - Ollama (local, semantic, requires server)
  - OpenAI (API, semantic) - coming soon

- **Flexible Similarity Computation**
  - Cosine similarity (default)
  - Euclidean distance
  - Dot product
  - Manhattan distance

- **Role-Based Weighting**
  - Weight user messages more heavily than assistant messages
  - Configurable weights for all roles (user, assistant, system, tool)

- **Conversation Graphs**
  - Build weighted relationship graphs
  - Community detection (Louvain, label propagation)
  - Export to Gephi (GEXF) or Cytoscape.js (JSON)

- **Efficient Caching**
  - Cache embeddings in database
  - Cache similarity scores for fast repeated queries
  - Automatic cache invalidation on config changes

## Quick Start

### Installation

Ensure you have the required dependencies:

```bash
# Install CTK with all dependencies
pip install -e .

# Or manually install similarity dependencies
pip install scikit-learn>=1.3.0 networkx>=3.0
```

### Using the Python API

```python
from ctk.core.database import ConversationDB as Database
from ctk.core.similarity import (
    ConversationEmbedder,
    ConversationEmbeddingConfig,
    SimilarityComputer,
)

# Initialize
db = Database("conversations")
config = ConversationEmbeddingConfig(provider="tfidf")
embedder = ConversationEmbedder(config)
similarity = SimilarityComputer(embedder, db=db)

# Fit TF-IDF on corpus
conversations = db.list_conversations()
texts = [extract_text(db.get_conversation(c.id)) for c in conversations]
embedder.provider.fit(texts)

# Embed conversations
for conv_summary in conversations:
    conv = db.get_conversation(conv_summary.id)
    embedding = embedder.embed_conversation(conv)
    db.save_embedding(conv.id, embedding, "tfidf", "tfidf")

# Find similar conversations
results = similarity.find_similar("conv_123", top_k=10, threshold=0.3)
for r in results:
    print(f"{r.conversation2_id}: {r.similarity:.3f}")
```

### Running the Example

```bash
# Run the quick start example
python examples/similarity_quickstart.py

# This will:
# 1. Load all conversations from default database
# 2. Fit TF-IDF embedder on corpus
# 3. Embed all conversations
# 4. Compute similarities
# 5. Build conversation graph
# 6. Export graph to JSON
```

## Configuration

### ConversationEmbeddingConfig

```python
from ctk.core.similarity import ConversationEmbeddingConfig

config = ConversationEmbeddingConfig(
    provider="tfidf",               # Provider: tfidf, ollama, openai
    model=None,                     # Model name (provider-specific)

    # Chunking strategy
    chunking=ChunkingStrategy.MESSAGE,  # message, whole, fixed_size, semantic

    # Aggregation strategy
    aggregation=AggregationStrategy.WEIGHTED_MEAN,  # weighted_mean, mean, max_pool

    # Role weights (for weighted_mean)
    role_weights={
        "user": 2.0,      # User messages weighted 2x
        "assistant": 1.0,  # Baseline
        "system": 0.5,     # System prompts less important
        "tool": 0.3,       # Tool calls less important
    },

    # Text extraction
    include_title=True,    # Include conversation title
    include_tags=True,     # Include tags
    title_weight=1.5,      # Weight title 1.5x

    # Provider-specific config
    provider_config={
        "max_features": 5000,   # TF-IDF vocabulary size
        "ngram_range": [1, 2],  # Unigrams + bigrams
    }
)
```

### TF-IDF Provider Config

```python
provider_config = {
    "max_features": 5000,      # Maximum vocabulary size
    "ngram_range": [1, 2],     # (min_n, max_n) for n-grams
    "min_df": 1,               # Minimum document frequency
    "max_df": 0.8,             # Maximum document frequency (filter common words)
    "sublinear_tf": True,      # Apply sublinear TF scaling
    "use_idf": True,           # Enable IDF reweighting
    "norm": "l2",              # Normalization: 'l2', 'l1', or None
}
```

### Ollama Provider Config

```python
provider_config = {
    "base_url": "http://localhost:11434",  # Ollama server URL
    "model": "nomic-embed-text",            # Model name
    "timeout": 60,                          # Request timeout (seconds)
}
```

## Similarity Metrics

### Cosine Similarity (Default)

Best for text embeddings. Range: -1 to 1 (usually 0 to 1 for text).

```python
from ctk.core.similarity import SimilarityMetric

similarity = SimilarityComputer(
    embedder,
    metric=SimilarityMetric.COSINE,  # Default
    db=db
)
```

### Other Metrics

```python
# Euclidean distance (converted to similarity: 1 / (1 + distance))
SimilarityMetric.EUCLIDEAN

# Dot product (assumes normalized vectors)
SimilarityMetric.DOT_PRODUCT

# Manhattan distance (L1 norm)
SimilarityMetric.MANHATTAN
```

## Building Conversation Graphs

### Basic Graph

```python
from ctk.core.similarity import ConversationGraphBuilder

graph_builder = ConversationGraphBuilder(similarity_computer)

graph = graph_builder.build_graph(
    conversations=None,      # None = all conversations
    threshold=0.3,           # Minimum similarity for link
    max_links_per_node=10,   # Maximum outgoing links
    use_cache=True,
    show_progress=True
)

print(f"Graph has {len(graph.nodes)} nodes and {len(graph.links)} links")
```

### Community Detection

```python
# Detect communities using Louvain algorithm
communities = graph_builder.detect_communities(graph, algorithm="louvain")

# Show community sizes
from collections import Counter
sizes = Counter(communities.values())
print(f"Found {len(sizes)} communities")
for comm_id, size in sizes.most_common(5):
    print(f"  Community {comm_id}: {size} conversations")
```

### Export Formats

```python
# Export to Gephi (for visual graph analysis)
graph.export_gephi("conversation_graph.gexf")

# Export to Cytoscape.js (for web visualization)
graph.export_cytoscape("conversation_graph.json")

# Convert to NetworkX (for programmatic analysis)
import networkx as nx
G = graph.to_networkx()
```

## Database Schema

### Embeddings Table

Stores conversation embeddings with configuration.

```sql
CREATE TABLE embeddings (
    id INTEGER PRIMARY KEY,
    conversation_id TEXT,
    model TEXT,
    provider TEXT,
    chunking_strategy TEXT,
    aggregation_strategy TEXT,
    aggregation_weights JSON,
    embedding_json JSON,    -- Embedding vector
    dimensions INTEGER,
    created_at TIMESTAMP,
    UNIQUE(conversation_id, model, provider, chunking_strategy, aggregation_strategy)
);
```

### Similarities Table

Stores precomputed similarity scores.

```sql
CREATE TABLE similarities (
    id INTEGER PRIMARY KEY,
    conversation1_id TEXT,  -- Always conv1_id < conv2_id
    conversation2_id TEXT,
    similarity REAL,
    metric TEXT,
    provider TEXT,
    model TEXT,
    created_at TIMESTAMP,
    UNIQUE(conversation1_id, conversation2_id, metric, provider)
);
```

## Database Methods

### Embedding Methods

```python
# Save embedding
db.save_embedding(
    conversation_id="conv_123",
    embedding=embedding_array,
    provider="tfidf",
    model="tfidf",
    chunking_strategy="message",
    aggregation_strategy="weighted_mean",
    aggregation_weights={"user": 2.0, "assistant": 1.0}
)

# Get cached embedding
embedding = db.get_embedding(
    conversation_id="conv_123",
    model="tfidf",
    provider="tfidf",
    chunking_strategy="message",
    aggregation_strategy="weighted_mean"
)

# Get all embeddings
embeddings = db.get_all_embeddings(provider="tfidf")

# Delete embeddings
db.delete_embeddings(provider="tfidf")
```

### Similarity Methods

```python
# Save similarity
db.save_similarity(
    conversation1_id="conv_1",
    conversation2_id="conv_2",
    similarity=0.85,
    metric="cosine",
    provider="tfidf"
)

# Get cached similarity
sim = db.get_similarity(
    conversation1_id="conv_1",
    conversation2_id="conv_2",
    metric="cosine",
    provider="tfidf"
)

# Get similar conversations
similar = db.get_similar_conversations(
    conversation_id="conv_1",
    metric="cosine",
    top_k=10,
    threshold=0.3
)

# Delete similarities
db.delete_similarities(provider="tfidf")
```

## Advanced Usage

### Custom Role Weights

Weight different message roles based on your use case:

```python
# For technical Q&A: weight user questions heavily
config = ConversationEmbeddingConfig(
    role_weights={
        "user": 3.0,       # Questions are most important
        "assistant": 1.0,
        "system": 0.1,     # System prompts not important
    }
)

# For conversation analysis: weight all equally
config = ConversationEmbeddingConfig(
    role_weights={
        "user": 1.0,
        "assistant": 1.0,
        "system": 1.0,
    }
)
```

### Different Aggregation Strategies

```python
from ctk.core.similarity import AggregationStrategy

# Use first message only (for intent-based similarity)
config = ConversationEmbeddingConfig(
    aggregation=AggregationStrategy.FIRST
)

# Use max pooling (capture peak features)
config = ConversationEmbeddingConfig(
    aggregation=AggregationStrategy.MAX_POOL
)

# Use simple mean (no weighting)
config = ConversationEmbeddingConfig(
    aggregation=AggregationStrategy.MEAN
)
```

### Batch Processing with Progress

```python
# Embed many conversations with progress bar
embeddings = embedder.embed_conversations(
    conversations,
    show_progress=True  # Requires tqdm: pip install tqdm
)

# Compute similarity matrix with progress
matrix = similarity_computer.compute_similarity_matrix(
    conversations,
    use_cache=True,
    show_progress=True
)
```

### Finding Conversations Above Threshold

```python
# Find all conversations above similarity threshold
results = similarity_computer.find_similar(
    conversation="conv_123",
    threshold=0.5,    # Only return similarities >= 0.5
    top_k=None,       # Return all above threshold
)
```

### Using Cached Results

```python
# First time: compute and cache
result = similarity_computer.compute_similarity(
    "conv_1", "conv_2", use_cache=True
)
print(result.metadata["cached"])  # False

# Second time: use cache
result = similarity_computer.compute_similarity(
    "conv_1", "conv_2", use_cache=True
)
print(result.metadata["cached"])  # True
```

## Performance Considerations

### TF-IDF Performance

- **Fitting**: O(N * M) where N = documents, M = avg length
- **Embedding**: O(M) per document after fitting
- **Similarity**: O(D) where D = dimensions (~5k-10k)
- **Memory**: ~1-10KB per embedding (sparse)

Expected throughput:
- Embedding: ~100-500 conversations/sec
- Similarity: ~10k pairs/sec with cached embeddings

### Scalability

- **<10K conversations**: TF-IDF handles easily, full matrix feasible
- **10K-100K**: Need efficient search (FAISS/Annoy) - coming in Phase 5
- **>100K**: Require distributed processing or approximate methods

### Optimization Tips

1. **Cache everything**: Use `use_cache=True` to avoid recomputation
2. **Batch processing**: Use `embed_conversations()` and `embed_batch()` for better performance
3. **Threshold filtering**: Set reasonable threshold to reduce graph size
4. **Max links**: Limit `max_links_per_node` to keep graphs manageable
5. **Vocabulary size**: Reduce `max_features` if memory is constrained

## CLI Commands (Coming Soon)

### Generate Embeddings

```bash
# Embed all conversations using TF-IDF
ctk rag embeddings --provider tfidf

# Use Ollama
ctk rag embeddings --provider ollama --model nomic-embed-text

# Embed specific conversations
ctk rag embeddings --ids conv1,conv2,conv3

# Force re-embedding
ctk rag embeddings --force
```

### Compute Similarity

```bash
# Pairwise similarity
ctk rag similar conv1 conv2

# Find top 10 similar
ctk rag similar conv1 --top-k 10

# With threshold
ctk rag similar conv1 --threshold 0.5

# JSON output
ctk rag similar conv1 --json
```

### Build Conversation Graph

```bash
# Generate graph
ctk rag links

# With custom threshold
ctk rag links --threshold 0.4

# Detect communities
ctk rag links --communities

# Export to file
ctk rag links --export graph.gexf
```

## TUI Commands (Coming Soon)

### Embeddings

```
/rag embeddings              # Embed all with default provider
/rag embeddings --provider ollama
/rag embeddings --force      # Re-embed all
```

### Similarity Search

```
/rag similar conv1           # Find similar to conv1
/rag similar                 # Find similar to current conversation
/rag similar conv1 --top-k 20
```

### Graph Visualization

```
/rag links                   # Generate and show graph
/rag links --threshold 0.5
/rag links --communities     # Show community detection
```

## Troubleshooting

### TF-IDF Not Fitted Error

**Error**: `TF-IDF vectorizer not fitted. Call fit() first with a corpus.`

**Solution**: You must fit the TF-IDF vectorizer on your corpus before embedding:

```python
# Extract all text from conversations
corpus_texts = [extract_text(conv) for conv in conversations]

# Fit TF-IDF
embedder.provider.fit(corpus_texts)

# Now you can embed
embedding = embedder.embed_conversation(conv)
```

### Empty Embeddings

**Issue**: Embeddings are all zeros.

**Possible causes**:
1. Conversation has no text content
2. All text was filtered out by TF-IDF (too common or too rare)
3. Vocabulary doesn't match corpus

**Solution**:
- Check conversation content
- Adjust `min_df` and `max_df` in TF-IDF config
- Ensure TF-IDF is fitted on representative corpus

### Low Similarity Scores

**Issue**: All similarity scores are very low (<0.1).

**Possible causes**:
1. Conversations are genuinely dissimilar
2. Vocabulary mismatch (TF-IDF fitted on wrong corpus)
3. Wrong aggregation strategy

**Solution**:
- Check if conversations share common terms
- Re-fit TF-IDF on correct corpus
- Try different aggregation strategy (MEAN vs WEIGHTED_MEAN)
- Use semantic embeddings (Ollama) instead of TF-IDF

### Graph Has Too Many/Too Few Links

**Solution**: Adjust threshold and max_links:

```python
# More selective (fewer links)
graph = graph_builder.build_graph(threshold=0.5, max_links_per_node=5)

# More permissive (more links)
graph = graph_builder.build_graph(threshold=0.2, max_links_per_node=20)
```

## Next Steps

1. **Try the example**: Run `python examples/similarity_quickstart.py`
2. **Experiment with config**: Adjust role weights, aggregation strategy
3. **Build a graph**: Visualize relationships between conversations
4. **Integrate into workflow**: Use similarity for recommendations, clustering

## References

- **Design Document**: `docs/SIMILARITY_API_DESIGN.md`
- **Implementation Summary**: `docs/SIMILARITY_IMPLEMENTATION_SUMMARY.md`
- **Example Code**: `examples/similarity_quickstart.py`
- **Source Code**:
  - Core: `ctk/core/similarity.py`
  - TF-IDF Provider: `ctk/integrations/embeddings/tfidf.py`
  - Database: `ctk/core/database.py`, `ctk/core/db_models.py`

## Contributing

To add a new embedding provider:

1. Create provider class inheriting from `EmbeddingProvider`
2. Implement required methods: `embed()`, `embed_batch()`, `get_models()`, `get_dimensions()`
3. Add provider to `ConversationEmbedder._load_provider()`
4. Add tests in `tests/unit/test_<provider>_embedding.py`

See `ctk/integrations/embeddings/tfidf.py` for a complete example.
