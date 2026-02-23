"""Tests for EmbeddingProvider base class and aggregation strategies."""

import numpy as np
import pytest

from ctk.integrations.embeddings.base import (
    AggregationStrategy,
    ChunkingStrategy,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingResponse,
)


class ConcreteProvider(EmbeddingProvider):
    """Minimal concrete provider for testing base class methods."""

    def __init__(self, dimensions=4):
        super().__init__({"model": "test"})
        self._dimensions = dimensions

    def embed(self, text, **kwargs):
        vec = [float(ord(c) % 10) / 10 for c in text[:self._dimensions]]
        vec += [0.0] * (self._dimensions - len(vec))
        return EmbeddingResponse(embedding=vec, model="test", dimensions=self._dimensions)

    def embed_batch(self, texts, **kwargs):
        return [self.embed(t) for t in texts]

    def get_models(self):
        return []

    def get_dimensions(self):
        return self._dimensions


class TestAggregationStrategies:
    @pytest.fixture
    def provider(self):
        return ConcreteProvider(dimensions=3)

    @pytest.fixture
    def embeddings(self):
        return [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]

    def test_mean(self, provider, embeddings):
        result = provider.aggregate_embeddings(embeddings, AggregationStrategy.MEAN)
        np.testing.assert_allclose(result, [2.5, 3.5, 4.5])

    def test_weighted_mean(self, provider, embeddings):
        result = provider.aggregate_embeddings(
            embeddings, AggregationStrategy.WEIGHTED_MEAN, weights=[1.0, 3.0]
        )
        # weights normalized: [0.25, 0.75]
        # [1*0.25 + 4*0.75, 2*0.25 + 5*0.75, 3*0.25 + 6*0.75] = [3.25, 4.25, 5.25]
        np.testing.assert_allclose(result, [3.25, 4.25, 5.25])

    def test_weighted_mean_requires_weights(self, provider, embeddings):
        with pytest.raises(ValueError, match="requires weights"):
            provider.aggregate_embeddings(embeddings, AggregationStrategy.WEIGHTED_MEAN)

    def test_weighted_mean_length_mismatch(self, provider, embeddings):
        with pytest.raises(ValueError, match="must match"):
            provider.aggregate_embeddings(
                embeddings, AggregationStrategy.WEIGHTED_MEAN, weights=[1.0]
            )

    def test_max_pool(self, provider, embeddings):
        result = provider.aggregate_embeddings(embeddings, AggregationStrategy.MAX_POOL)
        np.testing.assert_allclose(result, [4.0, 5.0, 6.0])

    def test_concatenate(self, provider, embeddings):
        result = provider.aggregate_embeddings(embeddings, AggregationStrategy.CONCATENATE)
        np.testing.assert_allclose(result, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

    def test_first(self, provider, embeddings):
        result = provider.aggregate_embeddings(embeddings, AggregationStrategy.FIRST)
        assert result == [1.0, 2.0, 3.0]

    def test_last(self, provider, embeddings):
        result = provider.aggregate_embeddings(embeddings, AggregationStrategy.LAST)
        assert result == [4.0, 5.0, 6.0]

    def test_empty_raises(self, provider):
        with pytest.raises(ValueError, match="empty"):
            provider.aggregate_embeddings([], AggregationStrategy.MEAN)


class TestTruncateText:
    def test_no_truncation_when_short(self):
        p = ConcreteProvider()
        assert p.truncate_text("hello", max_tokens=100) == "hello"

    def test_truncates_long_text(self):
        p = ConcreteProvider()
        result = p.truncate_text("a" * 1000, max_tokens=10)
        assert len(result) == 40  # 10 tokens * 4 chars/token

    def test_no_truncation_when_no_limit(self):
        p = ConcreteProvider()
        text = "a" * 1000
        assert p.truncate_text(text) == text


class TestChunkingStrategyEnum:
    def test_values(self):
        assert ChunkingStrategy.WHOLE.value == "whole"
        assert ChunkingStrategy.MESSAGE.value == "message"
        assert ChunkingStrategy.FIXED_SIZE.value == "fixed_size"
        assert ChunkingStrategy.SEMANTIC.value == "semantic"


class TestProviderName:
    def test_name_property(self):
        p = ConcreteProvider()
        assert p.name == "concrete"
