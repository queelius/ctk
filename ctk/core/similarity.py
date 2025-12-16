"""
Similarity computation for conversations.

This module provides:
- ConversationEmbedder: Convert conversations to embeddings
- SimilarityComputer: Compute similarity between conversations
- ConversationGraphBuilder: Build weighted graphs of conversation relationships
"""

from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import numpy as np
import hashlib
import json

from ctk.core.models import ConversationTree, MessageRole
from ctk.integrations.embeddings.base import (
    EmbeddingProvider,
    ChunkingStrategy,
    AggregationStrategy,
)


# ==================== Configuration ====================

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
        "function": 0.3,
        "tool_result": 0.3,
    })

    # Text extraction
    include_title: bool = True
    include_tags: bool = True
    title_weight: float = 1.5  # Title weighted more heavily

    # Provider-specific config
    provider_config: Dict[str, Any] = field(default_factory=dict)

    def to_hash(self) -> str:
        """Generate hash of configuration for cache invalidation"""
        # Create deterministic JSON representation
        config_dict = {
            'provider': self.provider,
            'model': self.model,
            'chunking': self.chunking.value if isinstance(self.chunking, ChunkingStrategy) else self.chunking,
            'aggregation': self.aggregation.value if isinstance(self.aggregation, AggregationStrategy) else self.aggregation,
            'role_weights': dict(sorted(self.role_weights.items())),
            'include_title': self.include_title,
            'include_tags': self.include_tags,
            'title_weight': self.title_weight,
        }
        config_json = json.dumps(config_dict, sort_keys=True)
        return hashlib.sha256(config_json.encode()).hexdigest()[:16]


# ==================== Conversation Embedder ====================

class ConversationEmbedder:
    """
    Converts conversations to embedding vectors.

    Handles:
    - Text extraction from ConversationTree
    - Role-based weighting
    - Chunking and aggregation
    - Caching embeddings
    """

    def __init__(
        self,
        config: ConversationEmbeddingConfig,
        provider: Optional[EmbeddingProvider] = None
    ):
        """
        Initialize conversation embedder.

        Args:
            config: Embedding configuration
            provider: Pre-initialized EmbeddingProvider (if None, will be loaded)
        """
        self.config = config
        self.provider = provider or self._load_provider()

    def _load_provider(self) -> EmbeddingProvider:
        """Load embedding provider based on config"""
        provider_name = self.config.provider.lower()

        if provider_name == "tfidf":
            from ctk.integrations.embeddings.tfidf import TFIDFEmbedding
            return TFIDFEmbedding(self.config.provider_config)
        elif provider_name == "ollama":
            from ctk.integrations.embeddings.ollama import OllamaEmbedding
            return OllamaEmbedding(self.config.provider_config)
        else:
            raise ValueError(f"Unknown embedding provider: {provider_name}")

    def embed_conversation(
        self,
        conversation: ConversationTree,
    ) -> np.ndarray:
        """
        Generate embedding for a conversation.

        Args:
            conversation: ConversationTree to embed

        Returns:
            Embedding vector as numpy array
        """
        # Extract text chunks with weights
        chunks_with_weights = self._extract_text_chunks(conversation)

        if not chunks_with_weights:
            # Empty conversation - return zero vector
            dimensions = self.provider.get_dimensions()
            return np.zeros(dimensions)

        # Generate embeddings for each chunk
        texts = [text for text, _ in chunks_with_weights]
        weights = [weight for _, weight in chunks_with_weights]

        # Batch embed all texts
        embedding_responses = self.provider.embed_batch(texts)
        embeddings = [np.array(resp.embedding) for resp in embedding_responses]

        # Aggregate using specified strategy
        if self.config.aggregation == AggregationStrategy.WEIGHTED_MEAN:
            aggregated = self.provider.aggregate_embeddings(
                embeddings,
                strategy=AggregationStrategy.WEIGHTED_MEAN,
                weights=weights
            )
        else:
            aggregated = self.provider.aggregate_embeddings(
                embeddings,
                strategy=self.config.aggregation
            )

        return np.array(aggregated)

    def embed_conversations(
        self,
        conversations: List[ConversationTree],
        show_progress: bool = False
    ) -> List[np.ndarray]:
        """
        Batch embed multiple conversations.

        Args:
            conversations: List of ConversationTree objects
            show_progress: Show progress bar

        Returns:
            List of embedding vectors
        """
        embeddings = []

        if show_progress:
            try:
                from tqdm import tqdm
                conversations = tqdm(conversations, desc="Embedding conversations")
            except ImportError:
                pass

        for conv in conversations:
            embedding = self.embed_conversation(conv)
            embeddings.append(embedding)

        return embeddings

    def _extract_text_chunks(
        self,
        conversation: ConversationTree
    ) -> List[Tuple[str, float]]:
        """
        Extract text chunks with weights from conversation.

        Returns:
            List of (text, weight) tuples
        """
        chunks = []

        # Add title if configured
        if self.config.include_title and conversation.title:
            chunks.append((conversation.title, self.config.title_weight))

        # Add tags if configured
        if self.config.include_tags and conversation.metadata.tags:
            tags_text = " ".join(conversation.metadata.tags)
            chunks.append((tags_text, 1.0))

        # Extract messages based on chunking strategy
        if self.config.chunking == ChunkingStrategy.MESSAGE:
            # Each message is a separate chunk
            for message in conversation.message_map.values():
                text = self._extract_message_text(message)
                if text.strip():
                    weight = self._compute_message_weight(message)
                    chunks.append((text, weight))

        elif self.config.chunking == ChunkingStrategy.WHOLE:
            # All messages as one chunk
            all_text = []
            total_weight = 0.0
            count = 0

            for message in conversation.message_map.values():
                text = self._extract_message_text(message)
                if text.strip():
                    all_text.append(text)
                    total_weight += self._compute_message_weight(message)
                    count += 1

            if all_text:
                combined_text = " ".join(all_text)
                avg_weight = total_weight / count if count > 0 else 1.0
                chunks.append((combined_text, avg_weight))

        return chunks

    def _extract_message_text(self, message) -> str:
        """Extract text content from a message"""
        # Handle both dict and object access
        if hasattr(message, 'content'):
            content = message.content
        elif isinstance(message, dict):
            content = message.get('content', '')
        else:
            return ""

        # Content can be string or list
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # Multi-part content - extract text parts
            text_parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get('type') == 'text':
                        text_parts.append(part.get('text', ''))
                elif isinstance(part, str):
                    text_parts.append(part)
            return " ".join(text_parts)
        else:
            return str(content) if content else ""

    def _compute_message_weight(self, message) -> float:
        """
        Compute weight for a message based on role.

        Returns:
            Weight multiplier for this message
        """
        # Get role
        if hasattr(message, 'role'):
            role = message.role
        elif isinstance(message, dict):
            role = message.get('role', 'user')
        else:
            role = 'user'

        # Convert to string if enum
        if isinstance(role, MessageRole):
            role = role.value

        # Normalize role string
        role = str(role).lower()

        # Get weight from config
        return self.config.role_weights.get(role, 1.0)


# ==================== Similarity Results ====================

@dataclass
class SimilarityResult:
    """Result of similarity computation"""
    conversation1_id: str
    conversation2_id: str
    similarity: float  # 0.0 to 1.0 for cosine similarity
    method: str  # "cosine", "euclidean", "dot"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class SimilarityMetric(Enum):
    """Similarity metrics"""
    COSINE = "cosine"  # Cosine similarity (default)
    EUCLIDEAN = "euclidean"  # Euclidean distance (inverted)
    DOT_PRODUCT = "dot"  # Dot product
    MANHATTAN = "manhattan"  # Manhattan distance


# ==================== Similarity Computer ====================

class SimilarityComputer:
    """
    Computes similarity between conversations.
    """

    def __init__(
        self,
        embedder: ConversationEmbedder,
        metric: SimilarityMetric = SimilarityMetric.COSINE,
        db=None  # Database instance for caching
    ):
        """
        Initialize similarity computer.

        Args:
            embedder: ConversationEmbedder instance
            metric: Similarity metric to use
            db: Optional Database instance for caching
        """
        self.embedder = embedder
        self.metric = metric
        self.db = db

    def compute_similarity(
        self,
        vec1: Union[ConversationTree, np.ndarray, str],
        vec2: Union[ConversationTree, np.ndarray, str],
        use_cache: bool = True
    ) -> SimilarityResult:
        """
        Compute similarity between two conversations or vectors.

        Args:
            vec1: First conversation (ConversationTree, embedding array, or ID)
            vec2: Second conversation (ConversationTree, embedding array, or ID)
            use_cache: Use cached embeddings/similarities if available

        Returns:
            SimilarityResult object
        """
        # Get embeddings
        emb1, id1 = self._get_embedding(vec1, use_cache)
        emb2, id2 = self._get_embedding(vec2, use_cache)

        # Check cache for similarity
        if use_cache and self.db and id1 and id2:
            cached = self.db.get_similarity(
                id1, id2,
                metric=self.metric.value,
                provider=self.embedder.config.provider
            )
            if cached is not None:
                return SimilarityResult(
                    conversation1_id=id1,
                    conversation2_id=id2,
                    similarity=cached,
                    method=self.metric.value,
                    metadata={'cached': True}
                )

        # Compute similarity
        similarity = self._compute_metric(emb1, emb2)

        # Cache result
        if self.db and id1 and id2:
            self.db.save_similarity(
                id1, id2,
                similarity=similarity,
                metric=self.metric.value,
                provider=self.embedder.config.provider
            )

        return SimilarityResult(
            conversation1_id=id1 or "unknown",
            conversation2_id=id2 or "unknown",
            similarity=similarity,
            method=self.metric.value,
            metadata={'cached': False}
        )

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
            conversation: Query conversation (object or ID)
            candidates: Candidate conversations (if None, search all in DB)
            top_k: Return top K most similar
            threshold: Minimum similarity threshold (0.0 to 1.0)
            use_cache: Use cached embeddings

        Returns:
            List of SimilarityResult, sorted by similarity (descending)
        """
        # Get query embedding
        query_emb, query_id = self._get_embedding(conversation, use_cache)

        # Get candidates
        if candidates is None:
            if not self.db:
                raise ValueError("Database required when candidates not specified")
            candidates = [c.id for c in self.db.list_conversations()]

        # Compute similarities
        results = []
        for candidate in candidates:
            # Skip self-similarity
            cand_id = candidate if isinstance(candidate, str) else candidate.id
            if cand_id == query_id:
                continue

            # Pass conversation (not embedding) to compute_similarity so IDs are tracked
            result = self.compute_similarity(conversation, candidate, use_cache)

            # Ensure query conversation is always conversation1_id
            if result.conversation1_id != query_id:
                # Swap if needed
                result.conversation1_id, result.conversation2_id = result.conversation2_id, result.conversation1_id

            # Apply threshold
            if threshold is not None and result.similarity < threshold:
                continue

            results.append(result)

        # Sort by similarity descending
        results.sort(key=lambda r: r.similarity, reverse=True)

        # Return top K
        return results[:top_k]

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
        n = len(conversations)
        matrix = np.zeros((n, n))

        # Get all embeddings first
        embeddings = []
        for conv in conversations:
            emb, _ = self._get_embedding(conv, use_cache)
            embeddings.append(emb)

        # Compute pairwise similarities
        iterator = range(n)
        if show_progress:
            try:
                from tqdm import tqdm
                iterator = tqdm(iterator, desc="Computing similarity matrix")
            except ImportError:
                pass

        for i in iterator:
            for j in range(i, n):
                if i == j:
                    matrix[i, j] = 1.0  # Self-similarity
                else:
                    sim = self._compute_metric(embeddings[i], embeddings[j])
                    matrix[i, j] = sim
                    matrix[j, i] = sim  # Symmetric

        return matrix

    def _get_embedding(
        self,
        source: Union[ConversationTree, np.ndarray, str],
        use_cache: bool
    ) -> Tuple[np.ndarray, Optional[str]]:
        """
        Get embedding from various sources.

        Returns:
            (embedding_array, conversation_id)
        """
        # Already an array
        if isinstance(source, np.ndarray):
            return source, None

        # Conversation ID - load from DB
        if isinstance(source, str):
            if not self.db:
                raise ValueError("Database required to load conversation by ID")

            # Try to get cached embedding
            # Use provider as model fallback (same logic as when saving)
            model_name = self.embedder.config.model or self.embedder.config.provider
            if use_cache:
                cached_emb = self.db.get_embedding(
                    source,
                    provider=self.embedder.config.provider,
                    model=model_name
                )
                if cached_emb is not None:
                    return cached_emb, source

            # Load conversation and embed
            conv = self.db.load_conversation(source)
            if not conv:
                raise ValueError(f"Conversation not found: {source}")

            emb = self.embedder.embed_conversation(conv)

            # Cache it
            if self.db:
                self.db.save_embedding(
                    conversation_id=source,
                    embedding=emb,
                    provider=self.embedder.config.provider,
                    model=self.embedder.config.model or self.embedder.config.provider,
                    chunking_strategy=self.embedder.config.chunking.value,
                    aggregation_strategy=self.embedder.config.aggregation.value,
                    aggregation_weights=self.embedder.config.role_weights
                )

            return emb, source

        # ConversationTree object
        if isinstance(source, ConversationTree):
            conv_id = source.id

            # Try cache (use provider as model fallback, same as when saving)
            model_name = self.embedder.config.model or self.embedder.config.provider
            if use_cache and self.db and conv_id:
                cached_emb = self.db.get_embedding(
                    conv_id,
                    provider=self.embedder.config.provider,
                    model=model_name
                )
                if cached_emb is not None:
                    return cached_emb, conv_id

            # Compute embedding
            emb = self.embedder.embed_conversation(source)

            # Cache it
            if self.db and conv_id:
                self.db.save_embedding(
                    conversation_id=conv_id,
                    embedding=emb,
                    provider=self.embedder.config.provider,
                    model=self.embedder.config.model or self.embedder.config.provider,
                    chunking_strategy=self.embedder.config.chunking.value,
                    aggregation_strategy=self.embedder.config.aggregation.value,
                    aggregation_weights=self.embedder.config.role_weights
                )

            return emb, conv_id

        raise TypeError(f"Unsupported source type: {type(source)}")

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
        if self.metric == SimilarityMetric.COSINE:
            # Cosine similarity
            dot = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return float(dot / (norm1 * norm2))

        elif self.metric == SimilarityMetric.DOT_PRODUCT:
            # Dot product (assumes normalized vectors)
            return float(np.dot(vec1, vec2))

        elif self.metric == SimilarityMetric.EUCLIDEAN:
            # Euclidean distance, converted to similarity
            dist = np.linalg.norm(vec1 - vec2)
            # Convert distance to similarity (1 / (1 + distance))
            return float(1.0 / (1.0 + dist))

        elif self.metric == SimilarityMetric.MANHATTAN:
            # Manhattan distance, converted to similarity
            dist = np.sum(np.abs(vec1 - vec2))
            return float(1.0 / (1.0 + dist))

        else:
            raise ValueError(f"Unknown similarity metric: {self.metric}")


# ==================== Graph Builder ====================

@dataclass
class ConversationLink:
    """Weighted link between conversations"""
    source_id: str
    target_id: str
    weight: float  # Similarity score
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class ConversationGraph:
    """Graph of conversation relationships"""
    nodes: List[str]  # Conversation IDs
    links: List[ConversationLink]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (JSON-serializable)"""
        return {
            'nodes': self.nodes,
            'links': [link.to_dict() for link in self.links],
            'metadata': self.metadata,
        }

    def to_networkx(self):
        """Convert to NetworkX graph"""
        try:
            import networkx as nx
        except ImportError:
            raise ImportError("NetworkX required for graph operations: pip install networkx")

        G = nx.Graph()
        G.add_nodes_from(self.nodes)

        for link in self.links:
            G.add_edge(link.source_id, link.target_id, weight=link.weight)

        return G

    def export_gephi(self, path: str):
        """Export to Gephi format (GEXF)"""
        G = self.to_networkx()
        try:
            import networkx as nx
            nx.write_gexf(G, path)
        except Exception as e:
            raise Exception(f"Failed to export to GEXF: {e}")

    def export_cytoscape(self, path: str):
        """Export to Cytoscape.js format"""
        import json

        cytoscape_data = {
            'elements': {
                'nodes': [{'data': {'id': node}} for node in self.nodes],
                'edges': [
                    {
                        'data': {
                            'id': f"{link.source_id}-{link.target_id}",
                            'source': link.source_id,
                            'target': link.target_id,
                            'weight': link.weight,
                        }
                    }
                    for link in self.links
                ]
            }
        }

        with open(path, 'w') as f:
            json.dump(cytoscape_data, f, indent=2)


class ConversationGraphBuilder:
    """
    Builds weighted graph of conversation relationships.
    """

    def __init__(self, similarity_computer: SimilarityComputer):
        """
        Initialize graph builder.

        Args:
            similarity_computer: SimilarityComputer instance
        """
        self.similarity = similarity_computer

    def build_graph(
        self,
        conversations: Optional[List[str]] = None,
        threshold: float = 0.3,
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
        # Get all conversation IDs
        if conversations is None:
            if not self.similarity.db:
                raise ValueError("Database required when conversations not specified")
            conversations = [c.id for c in self.similarity.db.list_conversations()]

        # Compute similarity matrix
        matrix = self.similarity.compute_similarity_matrix(
            conversations,
            use_cache=use_cache,
            show_progress=show_progress
        )

        # Build links
        links = []
        n = len(conversations)

        for i in range(n):
            # Get similarities for this node
            similarities = [(j, matrix[i, j]) for j in range(n) if i != j]

            # Sort by similarity descending
            similarities.sort(key=lambda x: x[1], reverse=True)

            # Apply threshold and max_links
            count = 0
            for j, sim in similarities:
                if sim < threshold:
                    break

                if max_links_per_node and count >= max_links_per_node:
                    break

                # Only add if not already added (avoid duplicates)
                if i < j:  # Only add edge once
                    links.append(ConversationLink(
                        source_id=conversations[i],
                        target_id=conversations[j],
                        weight=sim
                    ))

                count += 1

        return ConversationGraph(
            nodes=conversations,
            links=links,
            metadata={
                'threshold': threshold,
                'max_links_per_node': max_links_per_node,
                'total_nodes': len(conversations),
                'total_links': len(links),
            }
        )

    def detect_communities(
        self,
        graph: ConversationGraph,
        algorithm: str = "louvain"
    ) -> Dict[str, int]:
        """
        Detect communities in the conversation graph.

        Args:
            graph: ConversationGraph to analyze
            algorithm: Community detection algorithm (louvain, label_propagation, etc.)

        Returns:
            Mapping of conversation_id -> community_id
        """
        try:
            import networkx as nx
            import networkx.algorithms.community as nx_comm
        except ImportError:
            raise ImportError("NetworkX required for community detection: pip install networkx")

        G = graph.to_networkx()

        if algorithm == "louvain":
            try:
                import community as community_louvain
                communities = community_louvain.best_partition(G)
            except ImportError:
                raise ImportError(
                    "python-louvain required: pip install python-louvain"
                )

        elif algorithm == "label_propagation":
            communities_iter = nx_comm.label_propagation_communities(G)
            # Convert to dict
            communities = {}
            for idx, comm in enumerate(communities_iter):
                for node in comm:
                    communities[node] = idx

        elif algorithm == "greedy_modularity":
            communities_iter = nx_comm.greedy_modularity_communities(G)
            communities = {}
            for idx, comm in enumerate(communities_iter):
                for node in comm:
                    communities[node] = idx

        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")

        return communities
