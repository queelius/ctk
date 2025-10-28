"""
Base embedding provider abstraction for CTK.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
import numpy as np


class ChunkingStrategy(Enum):
    """Strategy for splitting text into embeddable chunks"""
    WHOLE = "whole"  # Embed entire text as-is
    MESSAGE = "message"  # Embed each message separately
    FIXED_SIZE = "fixed_size"  # Fixed token/char chunks with overlap
    SEMANTIC = "semantic"  # Split on semantic boundaries (paragraphs, sentences)


class AggregationStrategy(Enum):
    """Strategy for aggregating multiple embeddings into one"""
    MEAN = "mean"  # Simple average
    WEIGHTED_MEAN = "weighted_mean"  # Weighted by role (user:assistant)
    MAX_POOL = "max_pool"  # Element-wise maximum
    CONCATENATE = "concatenate"  # Concatenate (increases dimensionality)
    FIRST = "first"  # Use only first chunk
    LAST = "last"  # Use only last chunk


@dataclass
class EmbeddingInfo:
    """Information about an embedding model"""
    id: str
    name: str
    dimensions: int
    max_tokens: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class EmbeddingResponse:
    """Response from embedding generation"""
    embedding: List[float]
    model: str
    dimensions: int
    metadata: Optional[Dict[str, Any]] = None


class EmbeddingProvider(ABC):
    """
    Base class for all embedding providers.

    Implements a standard interface for generating embeddings across
    different providers (Ollama, OpenAI, Anthropic, etc.)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize provider with configuration.

        Args:
            config: Provider-specific configuration (API keys, endpoints, model, etc.)
        """
        self.config = config
        self.model = config.get('model')

    @abstractmethod
    def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            **kwargs: Provider-specific parameters

        Returns:
            EmbeddingResponse object

        Raises:
            EmbeddingProviderError: On API errors, network issues, etc.
        """
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str], **kwargs) -> List[EmbeddingResponse]:
        """
        Generate embeddings for multiple texts (batch processing).

        Args:
            texts: List of texts to embed
            **kwargs: Provider-specific parameters

        Returns:
            List of EmbeddingResponse objects

        Raises:
            EmbeddingProviderError: On API errors, network issues, etc.
        """
        pass

    @abstractmethod
    def get_models(self) -> List[EmbeddingInfo]:
        """
        List available embedding models for this provider.

        Returns:
            List of EmbeddingInfo objects

        Raises:
            EmbeddingProviderError: On API errors
        """
        pass

    def get_dimensions(self) -> int:
        """
        Get dimensionality of embeddings from current model.

        Returns:
            Number of dimensions (e.g., 768, 1024, 1536)

        Raises:
            EmbeddingProviderError: If dimensions cannot be determined
        """
        # Default implementation - providers should override if they can determine this
        raise NotImplementedError("Provider must implement get_dimensions()")

    def truncate_text(self, text: str, max_tokens: Optional[int] = None) -> str:
        """
        Truncate text to fit within token limit.

        Args:
            text: Input text
            max_tokens: Maximum tokens (uses model's limit if not specified)

        Returns:
            Truncated text
        """
        # Simple implementation - providers can override with proper tokenization
        if max_tokens is None:
            return text

        # Rough estimate: ~4 chars per token
        max_chars = max_tokens * 4
        if len(text) > max_chars:
            return text[:max_chars]
        return text

    def aggregate_embeddings(
        self,
        embeddings: List[List[float]],
        strategy: AggregationStrategy = AggregationStrategy.MEAN,
        weights: Optional[List[float]] = None
    ) -> List[float]:
        """
        Aggregate multiple embeddings into a single embedding.

        Args:
            embeddings: List of embedding vectors
            strategy: Aggregation strategy to use
            weights: Optional weights for weighted aggregation (must match len(embeddings))

        Returns:
            Aggregated embedding vector

        Raises:
            ValueError: If weights don't match embeddings length
        """
        if not embeddings:
            raise ValueError("Cannot aggregate empty embedding list")

        embeddings_array = np.array(embeddings)

        if strategy == AggregationStrategy.MEAN:
            return embeddings_array.mean(axis=0).tolist()

        elif strategy == AggregationStrategy.WEIGHTED_MEAN:
            if weights is None:
                raise ValueError("WEIGHTED_MEAN requires weights parameter")
            if len(weights) != len(embeddings):
                raise ValueError(f"Weights length {len(weights)} must match embeddings length {len(embeddings)}")
            weights_array = np.array(weights).reshape(-1, 1)
            weights_array = weights_array / weights_array.sum()  # Normalize
            return (embeddings_array * weights_array).sum(axis=0).tolist()

        elif strategy == AggregationStrategy.MAX_POOL:
            return embeddings_array.max(axis=0).tolist()

        elif strategy == AggregationStrategy.CONCATENATE:
            return embeddings_array.flatten().tolist()

        elif strategy == AggregationStrategy.FIRST:
            return embeddings[0]

        elif strategy == AggregationStrategy.LAST:
            return embeddings[-1]

        else:
            raise ValueError(f"Unknown aggregation strategy: {strategy}")

    @property
    def name(self) -> str:
        """Provider name (e.g., 'ollama', 'openai')"""
        return self.__class__.__name__.replace('Provider', '').replace('Embedding', '').lower()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model})"


# ==================== Exceptions ====================

class EmbeddingProviderError(Exception):
    """Base exception for embedding provider errors"""
    pass


class AuthenticationError(EmbeddingProviderError):
    """API authentication failed"""
    pass


class RateLimitError(EmbeddingProviderError):
    """Rate limit exceeded"""
    pass


class ModelNotFoundError(EmbeddingProviderError):
    """Requested model not available"""
    pass
