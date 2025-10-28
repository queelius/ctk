# CTK Similarity API Design

## Overview

This document describes the design of CTK's similarity-based features for computing semantic similarity between conversations and generating weighted relationship graphs.

## Core Components

### 1. Embedding System

#### Providers (Already Implemented)
- **Base**: `ctk/integrations/embeddings/base.py`
  - `EmbeddingProvider` abstract class
  - `ChunkingStrategy`, `AggregationStrategy` enums
  - `EmbeddingResponse`, `EmbeddingInfo` dataclasses

- **Implementations**:
  - `OllamaEmbedding`: Local embeddings via Ollama (nomic-embed-text, etc.)
  - **TODO**: `TFIDFEmbedding`: Fast local TF-IDF vectors
  - **TODO**: `OpenAIEmbedding`: OpenAI embeddings API
  - **TODO**: `VoyageEmbedding`: Voyage AI embeddings

#### New: TF-IDF Provider
```python
class TFIDFEmbedding(EmbeddingProvider):
    """
    Fast local TF-IDF embedding provider.

    - No external dependencies (scikit-learn)
    - Fast computation (good for initial implementation)
    - Deterministic and reproducible
    - Suitable for keyword-based similarity
    """

    def __init__(self, config):
        # max_features: vocabulary size (default: 10000)
        # ngram_range: (1, 2) for unigrams + bigrams
        # min_df: minimum document frequency
        # max_df: maximum document frequency (filter common words)
        pass
```

### 2. Conversation Embedding System

#### ConversationEmbedder
Responsible for converting `ConversationTree` objects into embedding vectors.

```python
@dataclass
class ConversationEmbeddingConfig:
    """Configuration for conversation embedding"""
    provider: str = "tfidf"  # tfidf, ollama, openai, etc.
    model: Optional[str] = None  # Provider-specific model name

    # Chunking strategy
    chunking: ChunkingStrategy = ChunkingStrategy.MESSAGE

    # Aggregation strategy
    aggregation: AggregationStrategy = AggregationStrategy.WEIGHTED_MEAN

    # Role weights (for WEIGHTED_MEAN aggregation)
    role_weights: Dict[str, float] = field(default_factory=lambda: {
        "user": 2.0,      # User messages weighted 2x
        "assistant": 1.0,  # Assistant messages baseline
        "system": 0.5,     # System messages weighted 0.5x
        "tool": 0.3,       # Tool messages weighted less
    })

    # Text extraction
    include_title: bool = True
    include_tags: bool = True
    title_weight: float = 1.5  # Title weighted more heavily

    # Provider-specific config
    provider_config: Dict[str, Any] = field(default_factory=dict)


class ConversationEmbedder:
    """
    Converts conversations to embedding vectors.

    Handles:
    - Text extraction from ConversationTree
    - Role-based weighting
    - Chunking and aggregation
    - Caching embeddings
    """

    def __init__(self, config: ConversationEmbeddingConfig):
        self.config = config
        self.provider = self._load_provider()

    def embed_conversation(
        self,
        conversation: ConversationTree,
        cache: bool = True
    ) -> np.ndarray:
        """
        Generate embedding for a conversation.

        Args:
            conversation: ConversationTree to embed
            cache: Whether to cache result in database

        Returns:
            Embedding vector as numpy array
        """
        pass

    def embed_conversations(
        self,
        conversations: List[ConversationTree],
        cache: bool = True,
        show_progress: bool = False
    ) -> List[np.ndarray]:
        """
        Batch embed multiple conversations.

        Uses provider's batch API if available, falls back to sequential.
        """
        pass

    def _extract_text_chunks(
        self,
        conversation: ConversationTree
    ) -> List[Tuple[str, float]]:
        """
        Extract text chunks with weights from conversation.

        Returns:
            List of (text, weight) tuples
        """
        pass

    def _compute_message_weight(self, message: Message) -> float:
        """
        Compute weight for a message based on role.

        Returns:
            Weight multiplier for this message
        """
        pass
```

### 3. Similarity Computation

#### SimilarityComputer
```python
@dataclass
class SimilarityResult:
    """Result of similarity computation"""
    conversation1_id: str
    conversation2_id: str
    similarity: float  # 0.0 to 1.0 (cosine similarity)
    method: str  # "cosine", "euclidean", "dot"
    metadata: Dict[str, Any] = field(default_factory=dict)


class SimilarityMetric(Enum):
    """Similarity metrics"""
    COSINE = "cosine"  # Cosine similarity (default)
    EUCLIDEAN = "euclidean"  # Euclidean distance (inverted)
    DOT_PRODUCT = "dot"  # Dot product
    MANHATTAN = "manhattan"  # Manhattan distance


class SimilarityComputer:
    """
    Computes similarity between conversations.
    """

    def __init__(
        self,
        embedder: ConversationEmbedder,
        metric: SimilarityMetric = SimilarityMetric.COSINE
    ):
        self.embedder = embedder
        self.metric = metric

    def compute_similarity(
        self,
        conv1: Union[ConversationTree, str],  # ConversationTree or ID
        conv2: Union[ConversationTree, str],
        use_cache: bool = True
    ) -> SimilarityResult:
        """
        Compute similarity between two conversations.

        Args:
            conv1: First conversation (object or ID)
            conv2: Second conversation (object or ID)
            use_cache: Use cached embeddings if available

        Returns:
            SimilarityResult object
        """
        pass

    def find_similar(
        self,
        conversation: Union[ConversationTree, str],
        candidates: Optional[List[Union[ConversationTree, str]]] = None,
        top_k: int = 10,
        threshold: Optional[float] = None,
        use_cache: bool = True
    ) -> List[SimilarityResult]:
        """
        Find conversations similar to a given conversation.

        Args:
            conversation: Query conversation
            candidates: Candidate conversations (if None, search all in DB)
            top_k: Return top K most similar
            threshold: Minimum similarity threshold (0.0 to 1.0)
            use_cache: Use cached embeddings

        Returns:
            List of SimilarityResult, sorted by similarity (descending)
        """
        pass

    def compute_similarity_matrix(
        self,
        conversations: List[Union[ConversationTree, str]],
        use_cache: bool = True,
        show_progress: bool = False
    ) -> np.ndarray:
        """
        Compute pairwise similarity matrix.

        Args:
            conversations: List of conversations
            use_cache: Use cached embeddings
            show_progress: Show progress bar

        Returns:
            NxN similarity matrix (numpy array)
        """
        pass

    def _compute_metric(
        self,
        vec1: np.ndarray,
        vec2: np.ndarray
    ) -> float:
        """
        Compute similarity metric between two vectors.

        Returns:
            Similarity score (0.0 to 1.0 for most metrics)
        """
        pass
```

### 4. Link Graph Generation

#### ConversationGraphBuilder
```python
@dataclass
class ConversationLink:
    """Weighted link between conversations"""
    source_id: str
    target_id: str
    weight: float  # Similarity score
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationGraph:
    """Graph of conversation relationships"""
    nodes: List[str]  # Conversation IDs
    links: List[ConversationLink]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_networkx(self) -> Any:
        """Convert to NetworkX graph"""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (JSON-serializable)"""
        pass

    def export_gephi(self, path: str):
        """Export to Gephi format (GEXF)"""
        pass

    def export_cytoscape(self, path: str):
        """Export to Cytoscape.js format"""
        pass


class ConversationGraphBuilder:
    """
    Builds weighted graph of conversation relationships.
    """

    def __init__(self, similarity_computer: SimilarityComputer):
        self.similarity = similarity_computer

    def build_graph(
        self,
        conversations: Optional[List[str]] = None,
        threshold: float = 0.3,  # Minimum similarity for link
        max_links_per_node: Optional[int] = 10,
        use_cache: bool = True,
        show_progress: bool = False
    ) -> ConversationGraph:
        """
        Build graph of conversation relationships.

        Args:
            conversations: Conversation IDs (if None, use all in DB)
            threshold: Minimum similarity for creating link
            max_links_per_node: Maximum outgoing links per node
            use_cache: Use cached embeddings and similarities
            show_progress: Show progress bar

        Returns:
            ConversationGraph object
        """
        pass

    def detect_communities(
        self,
        graph: ConversationGraph,
        algorithm: str = "louvain"  # louvain, label_propagation, etc.
    ) -> Dict[str, int]:
        """
        Detect communities in the conversation graph.

        Args:
            graph: ConversationGraph to analyze
            algorithm: Community detection algorithm

        Returns:
            Mapping of conversation_id -> community_id
        """
        pass

    def get_cluster_topics(
        self,
        graph: ConversationGraph,
        communities: Dict[str, int],
        top_n_words: int = 10
    ) -> Dict[int, List[str]]:
        """
        Extract representative topics for each community.

        Args:
            graph: ConversationGraph
            communities: Output from detect_communities()
            top_n_words: Number of top words per community

        Returns:
            Mapping of community_id -> list of representative words
        """
        pass
```

### 5. Database Integration

#### Schema Changes
```sql
-- New table for storing conversation embeddings
CREATE TABLE conversation_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,  -- "tfidf", "ollama", "openai", etc.
    model TEXT,              -- Provider-specific model name
    embedding BLOB NOT NULL, -- Serialized numpy array
    dimensions INTEGER NOT NULL,
    config_hash TEXT,        -- Hash of embedding config (for cache invalidation)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- Index for faster lookups
CREATE INDEX idx_embeddings_conv_id ON conversation_embeddings(conversation_id);
CREATE INDEX idx_embeddings_provider ON conversation_embeddings(provider, model);

-- Table for storing precomputed similarities
CREATE TABLE conversation_similarities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation1_id TEXT NOT NULL,
    conversation2_id TEXT NOT NULL,
    similarity REAL NOT NULL,
    metric TEXT NOT NULL,     -- "cosine", "euclidean", etc.
    embedding_provider TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation1_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (conversation2_id) REFERENCES conversations(id) ON DELETE CASCADE,
    -- Ensure we don't duplicate (A,B) and (B,A)
    CHECK (conversation1_id < conversation2_id)
);

CREATE INDEX idx_similarities_conv1 ON conversation_similarities(conversation1_id);
CREATE INDEX idx_similarities_conv2 ON conversation_similarities(conversation2_id);
CREATE UNIQUE INDEX idx_similarities_pair ON conversation_similarities(
    conversation1_id, conversation2_id, metric, embedding_provider
);
```

#### Database Methods
Add to `Database` class:
```python
class Database:
    # ... existing methods ...

    def save_embedding(
        self,
        conversation_id: str,
        embedding: np.ndarray,
        provider: str,
        model: Optional[str] = None,
        config_hash: Optional[str] = None
    ):
        """Save conversation embedding to database"""
        pass

    def get_embedding(
        self,
        conversation_id: str,
        provider: str,
        model: Optional[str] = None
    ) -> Optional[np.ndarray]:
        """Retrieve cached embedding"""
        pass

    def save_similarity(
        self,
        conv1_id: str,
        conv2_id: str,
        similarity: float,
        metric: str,
        provider: str
    ):
        """Save similarity score"""
        pass

    def get_similarity(
        self,
        conv1_id: str,
        conv2_id: str,
        metric: str,
        provider: str
    ) -> Optional[float]:
        """Retrieve cached similarity"""
        pass

    def get_all_embeddings(
        self,
        provider: str,
        model: Optional[str] = None
    ) -> Dict[str, np.ndarray]:
        """Get all embeddings for a provider/model"""
        pass
```

## CLI Interface

### Commands

#### 1. Generate Embeddings
```bash
# Embed all conversations using TF-IDF (fast)
ctk rag embeddings --provider tfidf

# Embed using Ollama with specific model
ctk rag embeddings --provider ollama --model nomic-embed-text

# Embed specific conversations
ctk rag embeddings --provider tfidf --ids conv1,conv2,conv3

# Embed with custom role weights
ctk rag embeddings --provider tfidf --user-weight 3.0 --assistant-weight 1.0

# Show progress for large databases
ctk rag embeddings --provider tfidf --progress

# Force re-embed (ignore cache)
ctk rag embeddings --provider tfidf --force
```

#### 2. Compute Similarity
```bash
# Compute similarity between two conversations
ctk rag similar conv1 conv2

# Compute similarity using currently loaded conversation (in TUI context)
ctk rag similar conv1

# Find top 10 conversations similar to conv1
ctk rag similar conv1 --top-k 10

# Find similar with minimum threshold
ctk rag similar conv1 --threshold 0.5

# Use specific embedding provider
ctk rag similar conv1 --provider ollama --model nomic-embed-text

# Output as JSON
ctk rag similar conv1 --top-k 10 --json
```

#### 3. Generate Link Graph
```bash
# Generate graph for all conversations
ctk rag links

# Generate with custom threshold
ctk rag links --threshold 0.4

# Limit links per node
ctk rag links --max-links 5

# Export to file formats
ctk rag links --export graph.gexf  # Gephi format
ctk rag links --export graph.json  # Cytoscape.js format

# Detect communities
ctk rag links --communities --algorithm louvain

# Show cluster topics
ctk rag links --communities --topics
```

## TUI Interface

### New Commands

#### `/rag embeddings [options]`
Generate embeddings for conversations in current database.

```
/rag embeddings                    # Embed all with TF-IDF
/rag embeddings --provider ollama  # Use Ollama
/rag embeddings --force            # Re-embed all
```

#### `/rag similar <conv_id> [options]`
Find conversations similar to a given conversation.

```
/rag similar conv1                 # Find similar to conv1
/rag similar                       # Find similar to current conversation
/rag similar conv1 --top-k 20      # Top 20 most similar
/rag similar conv1 --threshold 0.6 # Minimum similarity 0.6
```

#### `/rag links [options]`
Generate and visualize conversation graph.

```
/rag links                         # Generate link graph
/rag links --threshold 0.5         # Custom threshold
/rag links --communities           # Show communities
/rag links --export graph.json     # Export to file
```

### TUI Display

**Similarity Results Table:**
```
Similar Conversations
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Rank     ┃ Title                          ┃ Similarity  ┃ Tags      ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ 1        │ Python async programming       │ 0.87        │ python    │
│ 2        │ FastAPI best practices         │ 0.82        │ python    │
│ 3        │ SQLAlchemy ORM tutorial        │ 0.75        │ database  │
└──────────┴────────────────────────────────┴─────────────┴───────────┘
```

## Python API

### Basic Usage

```python
from ctk.core.database import Database
from ctk.integrations.embeddings.tfidf import TFIDFEmbedding
from ctk.core.similarity import (
    ConversationEmbedder,
    ConversationEmbeddingConfig,
    SimilarityComputer,
    ConversationGraphBuilder
)

# Initialize
db = Database("conversations.db")
config = ConversationEmbeddingConfig(
    provider="tfidf",
    role_weights={"user": 2.0, "assistant": 1.0}
)
embedder = ConversationEmbedder(config)
similarity = SimilarityComputer(embedder)

# Embed conversations
conversations = db.list_conversations()
for conv in conversations:
    tree = db.get_conversation(conv.id)
    embedder.embed_conversation(tree, cache=True)

# Find similar conversations
results = similarity.find_similar("conv_123", top_k=10)
for result in results:
    print(f"{result.conversation2_id}: {result.similarity:.2f}")

# Build conversation graph
graph_builder = ConversationGraphBuilder(similarity)
graph = graph_builder.build_graph(threshold=0.4)
graph.export_gephi("conversation_graph.gexf")

# Detect communities
communities = graph_builder.detect_communities(graph)
topics = graph_builder.get_cluster_topics(graph, communities)
```

## Implementation Phases

### Phase 1: TF-IDF Foundation (Current)
- [ ] Implement `TFIDFEmbedding` provider
- [ ] Implement `ConversationEmbedder` with role weighting
- [ ] Implement `SimilarityComputer` with cosine similarity
- [ ] Add database schema for embeddings
- [ ] Add database methods for embedding storage/retrieval
- [ ] Implement CLI: `ctk rag embeddings`
- [ ] Implement CLI: `ctk rag similar`
- [ ] Add basic tests

### Phase 2: Graph & Visualization
- [ ] Implement `ConversationGraphBuilder`
- [ ] Implement graph export formats (GEXF, Cytoscape.js)
- [ ] Implement community detection
- [ ] Implement cluster topic extraction
- [ ] Implement CLI: `ctk rag links`
- [ ] Add TUI commands: `/rag embeddings`, `/rag similar`, `/rag links`
- [ ] Add visualization to TUI

### Phase 3: Advanced Providers
- [ ] Implement `OllamaEmbedding` (verify nomic-embed-text is 2k context)
- [ ] Implement `OpenAIEmbedding` (text-embedding-3-small/large)
- [ ] Implement `VoyageEmbedding` (voyage-2, voyage-code-2)
- [ ] Add provider auto-selection based on availability
- [ ] Add benchmarking for different providers

### Phase 4: Optimization
- [ ] Add batch processing for large databases
- [ ] Implement efficient similarity search (FAISS/Annoy)
- [ ] Add incremental embedding updates
- [ ] Cache similarity matrix for fast lookups
- [ ] Add progress bars and performance metrics

## Configuration

### Global Config (`~/.ctk/config.yaml`)
```yaml
rag:
  default_provider: tfidf

  providers:
    tfidf:
      max_features: 10000
      ngram_range: [1, 2]
      min_df: 1
      max_df: 0.8

    ollama:
      base_url: http://localhost:11434
      model: nomic-embed-text
      timeout: 60

    openai:
      api_key: ${OPENAI_API_KEY}
      model: text-embedding-3-small

  embedding:
    role_weights:
      user: 2.0
      assistant: 1.0
      system: 0.5
      tool: 0.3
    include_title: true
    include_tags: true
    title_weight: 1.5

  similarity:
    metric: cosine
    default_threshold: 0.3
    default_top_k: 10

  graph:
    max_links_per_node: 10
    community_algorithm: louvain
```

## Testing Strategy

### Unit Tests
- `tests/unit/test_tfidf_embedding.py`
- `tests/unit/test_conversation_embedder.py`
- `tests/unit/test_similarity_computer.py`
- `tests/unit/test_graph_builder.py`
- `tests/unit/test_database_embeddings.py`

### Integration Tests
- `tests/integration/test_rag_workflow.py`
- `tests/integration/test_rag_cli.py`
- `tests/integration/test_rag_tui.py`

### Test Coverage Goals
- Core similarity logic: >90%
- TF-IDF provider: >80%
- Database integration: >80%
- CLI commands: >70%

## Performance Considerations

### TF-IDF Performance
- **Embedding**: ~100-500 conversations/sec (single-threaded)
- **Similarity**: O(1) with cached embeddings (cosine similarity)
- **Memory**: ~1-10KB per embedding (depends on vocabulary size)
- **Disk**: SQLite BLOB storage is efficient

### Scaling to Large Databases
- **10K conversations**: TF-IDF handles easily, full similarity matrix feasible
- **100K conversations**: Need efficient similarity search (FAISS), incremental updates
- **1M+ conversations**: Require distributed processing, approximate methods

### Optimization Strategies
1. **Batch processing**: Vectorize operations with NumPy
2. **Caching**: Store embeddings and similarities in DB
3. **Incremental updates**: Only re-embed modified conversations
4. **Approximate search**: Use FAISS/Annoy for large-scale similarity search
5. **Sparse representations**: TF-IDF produces sparse vectors (efficient storage)

## Future Enhancements

### Advanced Features
- **Semantic search**: Natural language queries over conversation content
- **Hybrid search**: Combine keyword (TF-IDF) + semantic (neural) embeddings
- **Temporal similarity**: Weight recent conversations higher
- **Multi-modal**: Include images, code snippets in similarity
- **Cross-lingual**: Multilingual embeddings for conversations in different languages

### Visualization
- **Interactive graph**: Web-based graph visualization (D3.js, Cytoscape.js)
- **3D embedding plots**: t-SNE/UMAP visualization of conversation space
- **Heatmaps**: Similarity matrices with interactive exploration
- **Timeline view**: Temporal evolution of conversation topics

### Integration
- **Recommendation engine**: "You might be interested in..."
- **Auto-tagging enhancement**: Use similar conversations to suggest tags
- **Duplicate detection**: Find near-duplicate conversations
- **Conversation merging**: Merge similar conversations based on content
