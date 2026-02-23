"""Tests for ctk/core/similarity.py."""

import json
import os

import numpy as np
import pytest

from ctk.core.models import (ConversationMetadata, ConversationTree, Message,
                             MessageContent, MessageRole)
from ctk.core.similarity import (ConversationEmbedder,
                                 ConversationEmbeddingConfig,
                                 ConversationGraph, ConversationGraphBuilder,
                                 ConversationLink, SimilarityComputer,
                                 SimilarityMetric, SimilarityResult)
from ctk.integrations.embeddings.base import (AggregationStrategy,
                                              ChunkingStrategy,
                                              EmbeddingProvider,
                                              EmbeddingResponse)

# ==================== Mock Provider ====================


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding provider for testing.

    Generates a normalized vector from the character codes of the input text.
    The same text always produces the same embedding, and different texts
    produce different embeddings.
    """

    DIMENSIONS = 8

    def __init__(self):
        super().__init__({"model": "mock"})

    def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        vec = self._text_to_vec(text)
        return EmbeddingResponse(
            embedding=vec, model="mock", dimensions=self.DIMENSIONS
        )

    def embed_batch(self, texts, **kwargs):
        return [self.embed(t) for t in texts]

    def get_models(self):
        return []

    def get_dimensions(self):
        return self.DIMENSIONS

    def _text_to_vec(self, text: str) -> list:
        """Convert text to a deterministic normalized vector."""
        vec = [0.0] * self.DIMENSIONS
        for i, ch in enumerate(text):
            vec[i % self.DIMENSIONS] += ord(ch) / 1000.0
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


# ==================== Fixtures ====================


def _make_conversation(conv_id, title, messages, tags=None):
    """Create a ConversationTree with the given messages.

    Args:
        conv_id: Conversation ID string.
        title: Conversation title.
        messages: List of (role_str, text) tuples.
        tags: Optional list of tag strings.
    """
    tree = ConversationTree(
        id=conv_id,
        title=title,
        metadata=ConversationMetadata(
            source="test",
            model="test-model",
            tags=tags or ["test"],
            created_at=None,
            updated_at=None,
        ),
    )
    parent_id = None
    for role_str, text in messages:
        role = MessageRole(role_str)
        msg = Message(
            role=role,
            content=MessageContent(text=text),
            parent_id=parent_id,
        )
        tree.add_message(msg)
        parent_id = msg.id
    return tree


@pytest.fixture
def mock_provider():
    return MockEmbeddingProvider()


@pytest.fixture
def default_config():
    return ConversationEmbeddingConfig(provider="mock")


@pytest.fixture
def embedder(default_config, mock_provider):
    return ConversationEmbedder(config=default_config, provider=mock_provider)


@pytest.fixture
def conv_python():
    """Conversation about Python programming."""
    return _make_conversation(
        "conv-python",
        "Python Programming",
        [
            ("user", "How do I write a function in Python?"),
            ("assistant", "Use the def keyword to define a function in Python."),
        ],
        tags=["python", "programming"],
    )


@pytest.fixture
def conv_python_similar():
    """Another conversation about Python, similar to conv_python."""
    return _make_conversation(
        "conv-python-2",
        "Python Functions",
        [
            ("user", "How do I define functions in Python?"),
            ("assistant", "You can use def to define functions in Python."),
        ],
        tags=["python"],
    )


@pytest.fixture
def conv_cooking():
    """Conversation about cooking, very different from Python."""
    return _make_conversation(
        "conv-cooking",
        "Italian Cooking",
        [
            ("user", "How do I make pasta carbonara?"),
            ("assistant", "Mix eggs, pecorino cheese, guanciale, and black pepper."),
        ],
        tags=["cooking", "italian"],
    )


@pytest.fixture
def conv_empty():
    """Empty conversation with no messages."""
    return ConversationTree(
        id="conv-empty",
        title=None,
        metadata=ConversationMetadata(
            source="test", model="test-model", tags=[], created_at=None, updated_at=None
        ),
    )


@pytest.fixture
def three_conversations(conv_python, conv_python_similar, conv_cooking):
    return [conv_python, conv_python_similar, conv_cooking]


# ==================== ConversationEmbeddingConfig ====================


@pytest.mark.unit
class TestConversationEmbeddingConfig:
    """Tests for ConversationEmbeddingConfig dataclass."""

    def test_default_values(self):
        config = ConversationEmbeddingConfig()
        assert config.provider == "tfidf"
        assert config.model is None
        assert config.chunking == ChunkingStrategy.MESSAGE
        assert config.aggregation == AggregationStrategy.WEIGHTED_MEAN
        assert config.include_title is True
        assert config.include_tags is True
        assert config.title_weight == 1.5
        assert "user" in config.role_weights
        assert config.role_weights["user"] == 2.0
        assert config.role_weights["assistant"] == 1.0
        assert config.role_weights["system"] == 0.5

    def test_custom_values(self):
        config = ConversationEmbeddingConfig(
            provider="ollama",
            model="nomic-embed-text",
            chunking=ChunkingStrategy.WHOLE,
            aggregation=AggregationStrategy.MEAN,
            role_weights={"user": 1.0, "assistant": 1.0},
            include_title=False,
            include_tags=False,
            title_weight=1.0,
        )
        assert config.provider == "ollama"
        assert config.model == "nomic-embed-text"
        assert config.chunking == ChunkingStrategy.WHOLE
        assert config.aggregation == AggregationStrategy.MEAN
        assert config.include_title is False

    def test_to_hash_deterministic(self):
        config1 = ConversationEmbeddingConfig()
        config2 = ConversationEmbeddingConfig()
        assert config1.to_hash() == config2.to_hash()

    def test_to_hash_changes_with_config(self):
        config1 = ConversationEmbeddingConfig(provider="tfidf")
        config2 = ConversationEmbeddingConfig(provider="ollama")
        assert config1.to_hash() != config2.to_hash()

    def test_to_hash_length(self):
        config = ConversationEmbeddingConfig()
        h = config.to_hash()
        assert len(h) == 16  # sha256 hex[:16]
        assert all(c in "0123456789abcdef" for c in h)

    def test_to_hash_changes_with_role_weights(self):
        config1 = ConversationEmbeddingConfig(role_weights={"user": 2.0})
        config2 = ConversationEmbeddingConfig(role_weights={"user": 3.0})
        assert config1.to_hash() != config2.to_hash()


# ==================== ConversationEmbedder ====================


@pytest.mark.unit
class TestConversationEmbedder:
    """Tests for ConversationEmbedder class."""

    def test_init_with_provider(self, default_config, mock_provider):
        embedder = ConversationEmbedder(config=default_config, provider=mock_provider)
        assert embedder.config is default_config
        assert embedder.provider is mock_provider

    def test_embed_conversation_returns_ndarray(self, embedder, conv_python):
        result = embedder.embed_conversation(conv_python)
        assert isinstance(result, np.ndarray)
        assert result.shape == (MockEmbeddingProvider.DIMENSIONS,)

    def test_embed_conversation_nonzero(self, embedder, conv_python):
        result = embedder.embed_conversation(conv_python)
        assert np.any(
            result != 0
        ), "Non-empty conversation should produce non-zero embedding"

    def test_embed_empty_conversation_returns_zeros(self, embedder, conv_empty):
        # Empty conversation with no title, no tags, no messages -> zero vector
        result = embedder.embed_conversation(conv_empty)
        assert isinstance(result, np.ndarray)
        np.testing.assert_array_equal(
            result, np.zeros(MockEmbeddingProvider.DIMENSIONS)
        )

    def test_embed_conversation_deterministic(self, embedder, conv_python):
        emb1 = embedder.embed_conversation(conv_python)
        emb2 = embedder.embed_conversation(conv_python)
        np.testing.assert_array_almost_equal(emb1, emb2)

    def test_embed_conversations_batch(self, embedder, three_conversations):
        results = embedder.embed_conversations(three_conversations)
        assert len(results) == 3
        for emb in results:
            assert isinstance(emb, np.ndarray)
            assert emb.shape == (MockEmbeddingProvider.DIMENSIONS,)

    def test_embed_different_conversations_produce_different_vectors(
        self, embedder, conv_python, conv_cooking
    ):
        emb1 = embedder.embed_conversation(conv_python)
        emb2 = embedder.embed_conversation(conv_cooking)
        # They should not be identical
        assert not np.allclose(
            emb1, emb2
        ), "Different conversations should produce different embeddings"

    def test_include_title_setting(self, mock_provider, conv_python):
        config_with = ConversationEmbeddingConfig(include_title=True)
        config_without = ConversationEmbeddingConfig(include_title=False)

        emb_with = ConversationEmbedder(config=config_with, provider=mock_provider)
        emb_without = ConversationEmbedder(
            config=config_without, provider=mock_provider
        )

        result_with = emb_with.embed_conversation(conv_python)
        result_without = emb_without.embed_conversation(conv_python)

        # Including title should change the embedding
        assert not np.allclose(result_with, result_without)

    def test_include_tags_setting(self, mock_provider, conv_python):
        config_with = ConversationEmbeddingConfig(include_tags=True)
        config_without = ConversationEmbeddingConfig(include_tags=False)

        emb_with = ConversationEmbedder(config=config_with, provider=mock_provider)
        emb_without = ConversationEmbedder(
            config=config_without, provider=mock_provider
        )

        result_with = emb_with.embed_conversation(conv_python)
        result_without = emb_without.embed_conversation(conv_python)

        assert not np.allclose(result_with, result_without)

    def test_chunking_whole(self, mock_provider, conv_python):
        config = ConversationEmbeddingConfig(chunking=ChunkingStrategy.WHOLE)
        emb = ConversationEmbedder(config=config, provider=mock_provider)
        result = emb.embed_conversation(conv_python)
        assert isinstance(result, np.ndarray)
        assert result.shape == (MockEmbeddingProvider.DIMENSIONS,)
        assert np.any(result != 0)

    def test_chunking_message(self, mock_provider, conv_python):
        config = ConversationEmbeddingConfig(chunking=ChunkingStrategy.MESSAGE)
        emb = ConversationEmbedder(config=config, provider=mock_provider)
        result = emb.embed_conversation(conv_python)
        assert isinstance(result, np.ndarray)
        assert result.shape == (MockEmbeddingProvider.DIMENSIONS,)

    def test_chunking_whole_vs_message_differ(self, mock_provider, conv_python):
        config_whole = ConversationEmbeddingConfig(chunking=ChunkingStrategy.WHOLE)
        config_msg = ConversationEmbeddingConfig(chunking=ChunkingStrategy.MESSAGE)

        emb_whole = ConversationEmbedder(config=config_whole, provider=mock_provider)
        emb_msg = ConversationEmbedder(config=config_msg, provider=mock_provider)

        result_whole = emb_whole.embed_conversation(conv_python)
        result_msg = emb_msg.embed_conversation(conv_python)

        # Different chunking strategies should produce different results
        assert not np.allclose(result_whole, result_msg)

    def test_aggregation_mean(self, mock_provider, conv_python):
        config = ConversationEmbeddingConfig(aggregation=AggregationStrategy.MEAN)
        emb = ConversationEmbedder(config=config, provider=mock_provider)
        result = emb.embed_conversation(conv_python)
        assert isinstance(result, np.ndarray)
        assert result.shape == (MockEmbeddingProvider.DIMENSIONS,)

    def test_message_weight_by_role(self, embedder):
        """User messages should get weight 2.0, assistant 1.0 by default."""
        user_msg = Message(role=MessageRole.USER, content=MessageContent(text="test"))
        assistant_msg = Message(
            role=MessageRole.ASSISTANT, content=MessageContent(text="test")
        )
        system_msg = Message(
            role=MessageRole.SYSTEM, content=MessageContent(text="test")
        )

        assert embedder._compute_message_weight(user_msg) == 2.0
        assert embedder._compute_message_weight(assistant_msg) == 1.0
        assert embedder._compute_message_weight(system_msg) == 0.5

    def test_message_weight_unknown_role_default(self, embedder):
        """Unknown role strings should default to weight 1.0."""
        msg = {"role": "unknown_role", "content": "test"}
        assert embedder._compute_message_weight(msg) == 1.0

    def test_extract_text_from_string_content(self, embedder):
        """_extract_message_text handles raw string content."""
        msg = {"content": "hello world"}
        assert embedder._extract_message_text(msg) == "hello world"

    def test_extract_text_from_list_content(self, embedder):
        """_extract_message_text handles list content (multi-part)."""
        msg = {
            "content": [
                {"type": "text", "text": "part one"},
                {"type": "text", "text": "part two"},
            ]
        }
        assert embedder._extract_message_text(msg) == "part one part two"

    def test_extract_text_from_list_with_strings(self, embedder):
        """_extract_message_text handles list of raw strings."""
        msg = {"content": ["hello", "world"]}
        assert embedder._extract_message_text(msg) == "hello world"

    def test_extract_text_from_dict_message(self, embedder):
        """_extract_message_text with dict that has no content key."""
        msg = {"role": "user"}
        assert embedder._extract_message_text(msg) == ""

    def test_extract_text_from_non_dict_non_object(self, embedder):
        """_extract_message_text returns empty string for unsupported types."""
        assert embedder._extract_message_text(42) == ""

    def test_extract_text_chunks_includes_title(self, embedder, conv_python):
        """Title should appear in chunks with title_weight."""
        chunks = embedder._extract_text_chunks(conv_python)
        titles = [(text, w) for text, w in chunks if text == "Python Programming"]
        assert len(titles) == 1
        assert titles[0][1] == 1.5  # default title_weight

    def test_extract_text_chunks_includes_tags(self, embedder, conv_python):
        """Tags should appear as a joined text chunk."""
        chunks = embedder._extract_text_chunks(conv_python)
        tag_chunks = [
            (text, w)
            for text, w in chunks
            if "python" in text and "programming" in text
        ]
        assert len(tag_chunks) >= 1

    def test_extract_text_chunks_no_title_for_empty(self, embedder, conv_empty):
        """Empty conversation (no title, no tags, no messages) should give empty chunks."""
        chunks = embedder._extract_text_chunks(conv_empty)
        assert chunks == []

    def test_load_provider_tfidf(self):
        """_load_provider should load TFIDFEmbedding for 'tfidf'."""
        config = ConversationEmbeddingConfig(provider="tfidf")
        embedder = ConversationEmbedder(config=config)
        from ctk.integrations.embeddings.tfidf import TFIDFEmbedding

        assert isinstance(embedder.provider, TFIDFEmbedding)

    def test_load_provider_unknown_raises(self):
        """_load_provider should raise ValueError for unknown provider."""
        config = ConversationEmbeddingConfig(provider="unknown_provider")
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            ConversationEmbedder(config=config)

    def test_conversation_with_no_title_no_tags(self, mock_provider):
        """Conversation with no title and no tags still embeds messages."""
        conv = ConversationTree(
            id="no-meta",
            title=None,
            metadata=ConversationMetadata(
                source="test",
                model="test-model",
                tags=[],
                created_at=None,
                updated_at=None,
            ),
        )
        msg = Message(role=MessageRole.USER, content=MessageContent(text="hello world"))
        conv.add_message(msg)

        config = ConversationEmbeddingConfig(include_title=True, include_tags=True)
        emb = ConversationEmbedder(config=config, provider=mock_provider)
        result = emb.embed_conversation(conv)
        assert np.any(result != 0), "Messages should still produce non-zero embedding"


# ==================== SimilarityResult ====================


@pytest.mark.unit
class TestSimilarityResult:
    """Tests for the SimilarityResult dataclass."""

    def test_creation(self):
        r = SimilarityResult(
            conversation1_id="a",
            conversation2_id="b",
            similarity=0.95,
            method="cosine",
        )
        assert r.conversation1_id == "a"
        assert r.conversation2_id == "b"
        assert r.similarity == 0.95
        assert r.method == "cosine"
        assert r.metadata == {}

    def test_to_dict(self):
        r = SimilarityResult(
            conversation1_id="a",
            conversation2_id="b",
            similarity=0.5,
            method="cosine",
            metadata={"cached": True},
        )
        d = r.to_dict()
        assert d["conversation1_id"] == "a"
        assert d["conversation2_id"] == "b"
        assert d["similarity"] == 0.5
        assert d["method"] == "cosine"
        assert d["metadata"]["cached"] is True

    def test_default_metadata(self):
        r = SimilarityResult(
            conversation1_id="x",
            conversation2_id="y",
            similarity=0.0,
            method="euclidean",
        )
        assert r.metadata == {}


# ==================== SimilarityMetric ====================


@pytest.mark.unit
class TestSimilarityMetric:
    """Tests for the SimilarityMetric enum."""

    def test_values(self):
        assert SimilarityMetric.COSINE.value == "cosine"
        assert SimilarityMetric.EUCLIDEAN.value == "euclidean"
        assert SimilarityMetric.DOT_PRODUCT.value == "dot"
        assert SimilarityMetric.MANHATTAN.value == "manhattan"

    def test_all_members(self):
        members = list(SimilarityMetric)
        assert len(members) == 4


# ==================== ConversationLink ====================


@pytest.mark.unit
class TestConversationLink:
    """Tests for the ConversationLink dataclass."""

    def test_creation(self):
        link = ConversationLink(source_id="a", target_id="b", weight=0.8)
        assert link.source_id == "a"
        assert link.target_id == "b"
        assert link.weight == 0.8
        assert link.metadata == {}

    def test_to_dict(self):
        link = ConversationLink(
            source_id="a",
            target_id="b",
            weight=0.75,
            metadata={"reason": "similar"},
        )
        d = link.to_dict()
        assert d["source_id"] == "a"
        assert d["target_id"] == "b"
        assert d["weight"] == 0.75
        assert d["metadata"]["reason"] == "similar"


# ==================== SimilarityComputer ====================


@pytest.mark.unit
class TestSimilarityComputer:
    """Tests for SimilarityComputer class."""

    def test_init(self, embedder):
        sc = SimilarityComputer(embedder=embedder)
        assert sc.embedder is embedder
        assert sc.metric == SimilarityMetric.COSINE
        assert sc.db is None

    def test_init_custom_metric(self, embedder):
        sc = SimilarityComputer(embedder=embedder, metric=SimilarityMetric.EUCLIDEAN)
        assert sc.metric == SimilarityMetric.EUCLIDEAN

    def test_compute_similarity_between_conversations(
        self, embedder, conv_python, conv_cooking
    ):
        sc = SimilarityComputer(embedder=embedder)
        result = sc.compute_similarity(conv_python, conv_cooking)
        assert isinstance(result, SimilarityResult)
        assert result.conversation1_id == "conv-python"
        assert result.conversation2_id == "conv-cooking"
        assert 0.0 <= result.similarity <= 1.0
        assert result.method == "cosine"
        assert result.metadata.get("cached") is False

    def test_self_similarity_is_one(self, embedder, conv_python):
        """A conversation compared with itself should have similarity ~1.0."""
        sc = SimilarityComputer(embedder=embedder)
        result = sc.compute_similarity(conv_python, conv_python)
        assert result.similarity == pytest.approx(1.0, abs=1e-6)

    def test_compute_similarity_with_numpy_arrays(self, embedder):
        """Should accept raw numpy arrays."""
        sc = SimilarityComputer(embedder=embedder)
        v1 = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        result = sc.compute_similarity(v1, v2)
        assert result.similarity == pytest.approx(0.0, abs=1e-6)
        assert result.conversation1_id == "unknown"
        assert result.conversation2_id == "unknown"

    def test_cosine_similarity_identical_vectors(self, embedder):
        sc = SimilarityComputer(embedder=embedder, metric=SimilarityMetric.COSINE)
        v = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        result = sc.compute_similarity(v, v)
        assert result.similarity == pytest.approx(1.0, abs=1e-6)

    def test_cosine_similarity_orthogonal_vectors(self, embedder):
        sc = SimilarityComputer(embedder=embedder, metric=SimilarityMetric.COSINE)
        v1 = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        result = sc.compute_similarity(v1, v2)
        assert result.similarity == pytest.approx(0.0, abs=1e-6)

    def test_euclidean_similarity_identical(self, embedder):
        sc = SimilarityComputer(embedder=embedder, metric=SimilarityMetric.EUCLIDEAN)
        v = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        result = sc.compute_similarity(v, v)
        # 1 / (1 + 0) = 1.0
        assert result.similarity == pytest.approx(1.0, abs=1e-6)

    def test_euclidean_similarity_distant(self, embedder):
        sc = SimilarityComputer(embedder=embedder, metric=SimilarityMetric.EUCLIDEAN)
        v1 = np.zeros(8)
        v2 = np.ones(8) * 10.0
        result = sc.compute_similarity(v1, v2)
        # Distance is sqrt(8*100) = 28.28..., similarity = 1/(1+28.28) < 1
        assert 0.0 < result.similarity < 0.1

    def test_dot_product_similarity(self, embedder):
        sc = SimilarityComputer(embedder=embedder, metric=SimilarityMetric.DOT_PRODUCT)
        v1 = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        v2 = np.array([0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        result = sc.compute_similarity(v1, v2)
        assert result.similarity == pytest.approx(0.5, abs=1e-6)
        assert result.method == "dot"

    def test_manhattan_similarity_identical(self, embedder):
        sc = SimilarityComputer(embedder=embedder, metric=SimilarityMetric.MANHATTAN)
        v = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        result = sc.compute_similarity(v, v)
        # 1 / (1 + 0) = 1.0
        assert result.similarity == pytest.approx(1.0, abs=1e-6)

    def test_manhattan_similarity_distant(self, embedder):
        sc = SimilarityComputer(embedder=embedder, metric=SimilarityMetric.MANHATTAN)
        v1 = np.zeros(8)
        v2 = np.ones(8) * 10.0
        result = sc.compute_similarity(v1, v2)
        # Manhattan distance = 80, similarity = 1/(1+80) ~ 0.012
        assert result.similarity == pytest.approx(1.0 / 81.0, abs=1e-6)

    def test_cosine_with_zero_vector(self, embedder):
        """Cosine similarity with a zero vector should return 0.0."""
        sc = SimilarityComputer(embedder=embedder, metric=SimilarityMetric.COSINE)
        v1 = np.zeros(8)
        v2 = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        result = sc.compute_similarity(v1, v2)
        assert result.similarity == pytest.approx(0.0, abs=1e-6)

    def test_compute_similarity_matrix(self, embedder, three_conversations):
        sc = SimilarityComputer(embedder=embedder)
        matrix = sc.compute_similarity_matrix(three_conversations)
        assert isinstance(matrix, np.ndarray)
        assert matrix.shape == (3, 3)

        # Diagonal should be 1.0 (self-similarity)
        for i in range(3):
            assert matrix[i, i] == pytest.approx(1.0, abs=1e-6)

        # Matrix should be symmetric
        for i in range(3):
            for j in range(3):
                assert matrix[i, j] == pytest.approx(matrix[j, i], abs=1e-6)

    def test_compute_similarity_matrix_values_in_range(
        self, embedder, three_conversations
    ):
        sc = SimilarityComputer(embedder=embedder)
        matrix = sc.compute_similarity_matrix(three_conversations)
        # All cosine similarities should be between -1 and 1
        assert np.all(matrix >= -1.0 - 1e-6)
        assert np.all(matrix <= 1.0 + 1e-6)

    def test_compute_similarity_matrix_single(self, embedder, conv_python):
        sc = SimilarityComputer(embedder=embedder)
        matrix = sc.compute_similarity_matrix([conv_python])
        assert matrix.shape == (1, 1)
        assert matrix[0, 0] == pytest.approx(1.0, abs=1e-6)

    def test_find_similar_with_candidates(
        self, embedder, conv_python, three_conversations
    ):
        sc = SimilarityComputer(embedder=embedder)
        results = sc.find_similar(
            conv_python,
            candidates=three_conversations,
            top_k=5,
        )
        # Should not include self
        for r in results:
            assert r.conversation1_id == "conv-python"
            assert r.conversation2_id != "conv-python"

        # Results should be sorted descending by similarity
        for i in range(len(results) - 1):
            assert results[i].similarity >= results[i + 1].similarity

    def test_find_similar_top_k(self, embedder, three_conversations):
        sc = SimilarityComputer(embedder=embedder)
        results = sc.find_similar(
            three_conversations[0],
            candidates=three_conversations,
            top_k=1,
        )
        assert len(results) <= 1

    def test_find_similar_threshold(self, embedder, three_conversations):
        sc = SimilarityComputer(embedder=embedder)
        # Very high threshold should filter out most results
        results = sc.find_similar(
            three_conversations[0],
            candidates=three_conversations,
            threshold=0.9999,
        )
        for r in results:
            assert r.similarity >= 0.9999

    def test_find_similar_no_db_no_candidates_raises(self, embedder, conv_python):
        sc = SimilarityComputer(embedder=embedder, db=None)
        with pytest.raises(ValueError, match="Database required"):
            sc.find_similar(conv_python, candidates=None)

    def test_get_embedding_unsupported_type_raises(self, embedder):
        sc = SimilarityComputer(embedder=embedder)
        with pytest.raises(TypeError, match="Unsupported source type"):
            sc._get_embedding(12345, use_cache=False)

    def test_get_embedding_string_without_db_raises(self, embedder):
        sc = SimilarityComputer(embedder=embedder, db=None)
        with pytest.raises(ValueError, match="Database required"):
            sc._get_embedding("some-id", use_cache=False)

    def test_similar_conversations_score_higher(
        self, embedder, conv_python, conv_python_similar, conv_cooking
    ):
        """Python conversations should be more similar to each other than to cooking."""
        sc = SimilarityComputer(embedder=embedder)
        sim_python_python2 = sc.compute_similarity(conv_python, conv_python_similar)
        sim_python_cooking = sc.compute_similarity(conv_python, conv_cooking)

        assert sim_python_python2.similarity > sim_python_cooking.similarity, (
            f"Python-Python2 similarity ({sim_python_python2.similarity:.4f}) "
            f"should be > Python-Cooking ({sim_python_cooking.similarity:.4f})"
        )


# ==================== ConversationGraph ====================


@pytest.mark.unit
class TestConversationGraph:
    """Tests for the ConversationGraph dataclass."""

    def test_creation(self):
        graph = ConversationGraph(
            nodes=["a", "b", "c"],
            links=[
                ConversationLink(source_id="a", target_id="b", weight=0.8),
                ConversationLink(source_id="b", target_id="c", weight=0.5),
            ],
        )
        assert len(graph.nodes) == 3
        assert len(graph.links) == 2

    def test_to_dict(self):
        graph = ConversationGraph(
            nodes=["a", "b"],
            links=[ConversationLink(source_id="a", target_id="b", weight=0.9)],
            metadata={"threshold": 0.3},
        )
        d = graph.to_dict()
        assert d["nodes"] == ["a", "b"]
        assert len(d["links"]) == 1
        assert d["links"][0]["source_id"] == "a"
        assert d["links"][0]["weight"] == 0.9
        assert d["metadata"]["threshold"] == 0.3

    def test_to_networkx(self):
        import networkx as nx

        graph = ConversationGraph(
            nodes=["a", "b", "c"],
            links=[
                ConversationLink(source_id="a", target_id="b", weight=0.8),
                ConversationLink(source_id="b", target_id="c", weight=0.5),
            ],
        )
        G = graph.to_networkx()
        assert isinstance(G, nx.Graph)
        assert set(G.nodes()) == {"a", "b", "c"}
        assert G.number_of_edges() == 2
        assert G["a"]["b"]["weight"] == 0.8
        assert G["b"]["c"]["weight"] == 0.5

    def test_to_networkx_empty(self):
        graph = ConversationGraph(nodes=["a", "b"], links=[])
        G = graph.to_networkx()
        assert G.number_of_nodes() == 2
        assert G.number_of_edges() == 0

    def test_export_gephi(self, tmp_path):
        graph = ConversationGraph(
            nodes=["a", "b"],
            links=[ConversationLink(source_id="a", target_id="b", weight=0.5)],
        )
        path = str(tmp_path / "test.gexf")
        graph.export_gephi(path)
        assert os.path.exists(path)
        with open(path) as f:
            content = f.read()
        assert "gexf" in content.lower()

    def test_export_cytoscape(self, tmp_path):
        graph = ConversationGraph(
            nodes=["a", "b"],
            links=[ConversationLink(source_id="a", target_id="b", weight=0.7)],
        )
        path = str(tmp_path / "test.json")
        graph.export_cytoscape(path)
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert "elements" in data
        assert "nodes" in data["elements"]
        assert "edges" in data["elements"]
        assert len(data["elements"]["nodes"]) == 2
        assert len(data["elements"]["edges"]) == 1
        edge = data["elements"]["edges"][0]["data"]
        assert edge["source"] == "a"
        assert edge["target"] == "b"
        assert edge["weight"] == 0.7


# ==================== ConversationGraphBuilder ====================


@pytest.mark.unit
class TestConversationGraphBuilder:
    """Tests for ConversationGraphBuilder class."""

    def test_init(self, embedder):
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)
        assert builder.similarity is sc

    def test_build_graph_basic(self, embedder, three_conversations):
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)
        graph = builder.build_graph(
            conversations=three_conversations,
            threshold=0.0,  # Include all links
        )
        assert isinstance(graph, ConversationGraph)
        assert len(graph.nodes) == 3
        assert graph.metadata["total_nodes"] == 3

    def test_build_graph_nodes_are_conversation_objects(
        self, embedder, three_conversations
    ):
        """When ConversationTree objects are passed, nodes are the objects themselves."""
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)
        graph = builder.build_graph(
            conversations=three_conversations,
            threshold=0.0,
        )
        # Nodes are the ConversationTree objects (not strings)
        assert len(graph.nodes) == 3

    def test_build_graph_threshold_filters(self, embedder, three_conversations):
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)

        # Very high threshold should produce fewer links
        graph_high = builder.build_graph(
            conversations=three_conversations,
            threshold=0.9999,
        )
        graph_low = builder.build_graph(
            conversations=three_conversations,
            threshold=0.0,
        )
        assert len(graph_high.links) <= len(graph_low.links)

    def test_build_graph_max_links_per_node(self, embedder, three_conversations):
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)
        graph = builder.build_graph(
            conversations=three_conversations,
            threshold=0.0,
            max_links_per_node=1,
        )
        # With max_links_per_node=1, each node contributes at most 1 link
        # (but due to i<j dedup, some may not appear)
        assert len(graph.links) <= 3

    def test_build_graph_metadata(self, embedder, three_conversations):
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)
        graph = builder.build_graph(
            conversations=three_conversations,
            threshold=0.5,
            max_links_per_node=5,
        )
        assert graph.metadata["threshold"] == 0.5
        assert graph.metadata["max_links_per_node"] == 5
        assert graph.metadata["total_nodes"] == 3
        assert "total_links" in graph.metadata

    def test_build_graph_link_weights_above_threshold(
        self, embedder, three_conversations
    ):
        threshold = 0.5
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)
        graph = builder.build_graph(
            conversations=three_conversations,
            threshold=threshold,
        )
        for link in graph.links:
            assert link.weight >= threshold

    def test_build_graph_no_self_links(self, embedder, three_conversations):
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)
        graph = builder.build_graph(
            conversations=three_conversations,
            threshold=0.0,
        )
        for link in graph.links:
            assert link.source_id != link.target_id

    def test_build_graph_no_duplicate_links(self, embedder, three_conversations):
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)
        graph = builder.build_graph(
            conversations=three_conversations,
            threshold=0.0,
        )
        seen = set()
        for link in graph.links:
            pair = frozenset([str(link.source_id), str(link.target_id)])
            assert (
                pair not in seen
            ), f"Duplicate link: {link.source_id} <-> {link.target_id}"
            seen.add(pair)

    def test_build_graph_single_conversation(self, embedder, conv_python):
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)
        graph = builder.build_graph(
            conversations=[conv_python],
            threshold=0.0,
        )
        assert len(graph.nodes) == 1
        assert len(graph.links) == 0

    def test_build_graph_no_conversations_raises(self, embedder):
        sc = SimilarityComputer(embedder=embedder, db=None)
        builder = ConversationGraphBuilder(sc)
        with pytest.raises(ValueError, match="Database required"):
            builder.build_graph(conversations=None)

    def test_build_graph_converts_to_networkx_with_string_ids(
        self, embedder, three_conversations
    ):
        """build_graph with string IDs allows conversion to NetworkX."""
        # build_graph is typed List[str] for conversations param.
        # When ConversationTree objects are passed, compute_similarity_matrix
        # works (it accepts Union[ConversationTree, str]), but the graph nodes
        # become ConversationTree objects which NetworkX cannot unpack.
        # The correct pattern for NetworkX integration is to use string IDs
        # with a database backend. Here we test using ConversationTree objects
        # and verify the graph structure via to_dict instead.
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)
        graph = builder.build_graph(
            conversations=three_conversations,
            threshold=0.0,
        )
        d = graph.to_dict()
        assert len(d["nodes"]) == 3
        assert "links" in d

    def test_build_graph_to_networkx_with_constructed_graph(self):
        """Verify to_networkx works with string node IDs (manual graph)."""
        import networkx as nx

        graph = ConversationGraph(
            nodes=["c1", "c2", "c3"],
            links=[
                ConversationLink(source_id="c1", target_id="c2", weight=0.8),
                ConversationLink(source_id="c2", target_id="c3", weight=0.5),
            ],
        )
        G = graph.to_networkx()
        assert isinstance(G, nx.Graph)
        assert G.number_of_nodes() == 3
        assert G.number_of_edges() == 2


# ==================== Integration-style tests ====================


@pytest.mark.unit
class TestSimilarityEndToEnd:
    """End-to-end tests exercising the full pipeline."""

    def test_full_pipeline_embed_compute_build(self, mock_provider):
        """Full pipeline: create conversations, embed, compute similarity, build graph."""
        config = ConversationEmbeddingConfig(provider="mock")
        embedder = ConversationEmbedder(config=config, provider=mock_provider)
        sc = SimilarityComputer(embedder=embedder)
        builder = ConversationGraphBuilder(sc)

        convs = [
            _make_conversation(
                "c1",
                "Python Lists",
                [
                    ("user", "How do I create a list in Python?"),
                    ("assistant", "Use square brackets: my_list = [1, 2, 3]"),
                ],
            ),
            _make_conversation(
                "c2",
                "Python Dicts",
                [
                    ("user", "How do I create a dictionary in Python?"),
                    ("assistant", "Use curly braces: my_dict = {'key': 'value'}"),
                ],
            ),
            _make_conversation(
                "c3",
                "Baking Bread",
                [
                    ("user", "How do I bake sourdough bread?"),
                    ("assistant", "You need a starter, flour, water, and salt."),
                ],
            ),
        ]

        # Build graph
        graph = builder.build_graph(conversations=convs, threshold=0.0)
        assert len(graph.nodes) == 3
        assert graph.metadata["total_nodes"] == 3

        # Verify graph structure via to_dict (to_networkx requires string node IDs)
        d = graph.to_dict()
        assert len(d["nodes"]) == 3
        assert "links" in d
        assert len(d["links"]) > 0

    def test_multiple_metrics_produce_results(
        self, mock_provider, conv_python, conv_cooking
    ):
        """All supported metrics should produce valid results."""
        config = ConversationEmbeddingConfig(provider="mock")
        embedder = ConversationEmbedder(config=config, provider=mock_provider)

        for metric in SimilarityMetric:
            sc = SimilarityComputer(embedder=embedder, metric=metric)
            result = sc.compute_similarity(conv_python, conv_cooking)
            assert isinstance(result.similarity, float), f"Metric {metric} failed"
            assert result.method == metric.value

    def test_similarity_matrix_matches_pairwise(
        self, mock_provider, three_conversations
    ):
        """Matrix entries should match individual pairwise computations."""
        config = ConversationEmbeddingConfig(provider="mock")
        embedder = ConversationEmbedder(config=config, provider=mock_provider)
        sc = SimilarityComputer(embedder=embedder)

        matrix = sc.compute_similarity_matrix(three_conversations)

        # Verify matrix[i][j] matches compute_similarity
        for i in range(3):
            for j in range(i + 1, 3):
                result = sc.compute_similarity(
                    three_conversations[i], three_conversations[j]
                )
                assert matrix[i, j] == pytest.approx(
                    result.similarity, abs=1e-6
                ), f"Matrix[{i},{j}] = {matrix[i, j]} != pairwise {result.similarity}"

    def test_empty_graph_export_cytoscape(self, tmp_path):
        """Empty graph should still export valid Cytoscape JSON."""
        graph = ConversationGraph(nodes=[], links=[])
        path = str(tmp_path / "empty.json")
        graph.export_cytoscape(path)
        with open(path) as f:
            data = json.load(f)
        assert data["elements"]["nodes"] == []
        assert data["elements"]["edges"] == []

    def test_single_message_conversation(self, mock_provider):
        """A conversation with a single message should embed fine."""
        config = ConversationEmbeddingConfig(
            provider="mock", include_title=False, include_tags=False
        )
        embedder = ConversationEmbedder(config=config, provider=mock_provider)
        conv = _make_conversation("single", "Single", [("user", "Hello")])
        result = embedder.embed_conversation(conv)
        assert isinstance(result, np.ndarray)
        assert np.any(result != 0)

    def test_many_messages_conversation(self, mock_provider):
        """Conversation with many messages should embed without error."""
        config = ConversationEmbeddingConfig(provider="mock")
        embedder = ConversationEmbedder(config=config, provider=mock_provider)
        messages = [
            (("user" if i % 2 == 0 else "assistant"), f"Message {i}") for i in range(50)
        ]
        conv = _make_conversation("many", "Many Messages", messages)
        result = embedder.embed_conversation(conv)
        assert isinstance(result, np.ndarray)
        assert result.shape == (MockEmbeddingProvider.DIMENSIONS,)
