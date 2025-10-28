"""
TF-IDF embedding provider implementation.

Fast local embedding using scikit-learn's TfidfVectorizer.
Good for keyword-based similarity without requiring external services.
"""

from typing import List, Dict, Optional, Any
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
import pickle

from ctk.integrations.embeddings.base import (
    EmbeddingProvider,
    EmbeddingInfo,
    EmbeddingResponse,
    EmbeddingProviderError,
)


class TFIDFEmbedding(EmbeddingProvider):
    """
    TF-IDF embedding provider using scikit-learn.

    Features:
    - Fast local computation
    - No external dependencies (beyond scikit-learn)
    - Deterministic and reproducible
    - Sparse vectors (memory efficient)
    - Good for keyword-based similarity

    Limitations:
    - Requires fitting on corpus (all documents must be available)
    - No semantic understanding (purely lexical)
    - Vocabulary size affects memory usage
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize TF-IDF embedding provider.

        Args:
            config: Configuration dict with keys:
                - max_features: Maximum vocabulary size (default: 10000)
                - ngram_range: Tuple (min_n, max_n) for n-grams (default: (1, 2))
                - min_df: Minimum document frequency (default: 1)
                - max_df: Maximum document frequency (default: 0.8)
                - sublinear_tf: Apply sublinear TF scaling (default: True)
                - use_idf: Enable IDF reweighting (default: True)
                - norm: Normalization ('l2', 'l1', or None) (default: 'l2')
        """
        super().__init__(config)

        # TF-IDF parameters
        max_features = config.get('max_features', 10000)
        ngram_range = tuple(config.get('ngram_range', [1, 2]))
        min_df = config.get('min_df', 1)
        max_df = config.get('max_df', 0.8)
        sublinear_tf = config.get('sublinear_tf', True)
        use_idf = config.get('use_idf', True)
        norm = config.get('norm', 'l2')

        # Initialize vectorizer
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            ngram_range=ngram_range,
            min_df=min_df,
            max_df=max_df,
            sublinear_tf=sublinear_tf,
            use_idf=use_idf,
            norm=norm,
            lowercase=True,
            stop_words='english',
            token_pattern=r'(?u)\b\w+\b',  # Include single-character words
        )

        # Fitted flag
        self._is_fitted = False
        self._dimensions: Optional[int] = None

    def fit(self, texts: List[str]):
        """
        Fit the TF-IDF vectorizer on a corpus.

        This must be called before embed() or embed_batch().

        Args:
            texts: List of documents to fit on

        Raises:
            EmbeddingProviderError: If fitting fails
        """
        try:
            self.vectorizer.fit(texts)
            self._is_fitted = True
            self._dimensions = len(self.vectorizer.get_feature_names_out())
        except Exception as e:
            raise EmbeddingProviderError(f"Failed to fit TF-IDF vectorizer: {e}")

    def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        """
        Generate TF-IDF embedding for a single text.

        Args:
            text: Text to embed
            **kwargs: Ignored (for compatibility)

        Returns:
            EmbeddingResponse object

        Raises:
            EmbeddingProviderError: If not fitted or embedding fails
        """
        if not self._is_fitted:
            raise EmbeddingProviderError(
                "TF-IDF vectorizer not fitted. Call fit() first with a corpus."
            )

        try:
            # Transform returns sparse matrix, convert to dense
            sparse_vec = self.vectorizer.transform([text])
            dense_vec = sparse_vec.toarray()[0]

            return EmbeddingResponse(
                embedding=dense_vec.tolist(),
                model="tfidf",
                dimensions=len(dense_vec),
                metadata={
                    'vocabulary_size': len(self.vectorizer.vocabulary_),
                    'sparsity': 1.0 - (np.count_nonzero(dense_vec) / len(dense_vec))
                }
            )

        except Exception as e:
            raise EmbeddingProviderError(f"Failed to generate TF-IDF embedding: {e}")

    def embed_batch(self, texts: List[str], **kwargs) -> List[EmbeddingResponse]:
        """
        Generate TF-IDF embeddings for multiple texts (batch processing).

        Args:
            texts: List of texts to embed
            **kwargs: Ignored (for compatibility)

        Returns:
            List of EmbeddingResponse objects

        Raises:
            EmbeddingProviderError: If not fitted or embedding fails
        """
        if not self._is_fitted:
            raise EmbeddingProviderError(
                "TF-IDF vectorizer not fitted. Call fit() first with a corpus."
            )

        try:
            # Transform returns sparse matrix, convert to dense
            sparse_matrix = self.vectorizer.transform(texts)
            dense_matrix = sparse_matrix.toarray()

            responses = []
            vocab_size = len(self.vectorizer.vocabulary_)

            for vec in dense_matrix:
                responses.append(EmbeddingResponse(
                    embedding=vec.tolist(),
                    model="tfidf",
                    dimensions=len(vec),
                    metadata={
                        'vocabulary_size': vocab_size,
                        'sparsity': 1.0 - (np.count_nonzero(vec) / len(vec))
                    }
                ))

            return responses

        except Exception as e:
            raise EmbeddingProviderError(f"Failed to generate TF-IDF embeddings: {e}")

    def get_models(self) -> List[EmbeddingInfo]:
        """
        List available models.

        For TF-IDF, there's only one "model" (the fitted vectorizer).

        Returns:
            List with single EmbeddingInfo
        """
        return [EmbeddingInfo(
            id="tfidf",
            name="TF-IDF Vectorizer",
            dimensions=self._dimensions or 0,
            metadata={
                'fitted': self._is_fitted,
                'max_features': self.vectorizer.max_features,
                'ngram_range': self.vectorizer.ngram_range,
            }
        )]

    def get_dimensions(self) -> int:
        """
        Get dimensionality of TF-IDF embeddings.

        Returns:
            Number of dimensions (vocabulary size after fitting)

        Raises:
            EmbeddingProviderError: If not fitted
        """
        if not self._is_fitted:
            raise EmbeddingProviderError(
                "Cannot determine dimensions: vectorizer not fitted"
            )
        return self._dimensions or 0

    def save(self, path: str):
        """
        Save fitted vectorizer to disk.

        Args:
            path: File path to save to

        Raises:
            EmbeddingProviderError: If save fails
        """
        if not self._is_fitted:
            raise EmbeddingProviderError("Cannot save: vectorizer not fitted")

        try:
            with open(path, 'wb') as f:
                pickle.dump({
                    'vectorizer': self.vectorizer,
                    'dimensions': self._dimensions,
                    'config': self.config,
                }, f)
        except Exception as e:
            raise EmbeddingProviderError(f"Failed to save vectorizer: {e}")

    def load(self, path: str):
        """
        Load fitted vectorizer from disk.

        Args:
            path: File path to load from

        Raises:
            EmbeddingProviderError: If load fails
        """
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
                self.vectorizer = data['vectorizer']
                self._dimensions = data['dimensions']
                self.config = data.get('config', self.config)
                self._is_fitted = True
        except Exception as e:
            raise EmbeddingProviderError(f"Failed to load vectorizer: {e}")

    def get_feature_names(self) -> List[str]:
        """
        Get vocabulary feature names.

        Returns:
            List of feature names (words/n-grams)

        Raises:
            EmbeddingProviderError: If not fitted
        """
        if not self._is_fitted:
            raise EmbeddingProviderError("Vectorizer not fitted")

        return self.vectorizer.get_feature_names_out().tolist()

    def get_top_features(self, embedding: List[float], top_k: int = 10) -> List[tuple]:
        """
        Get top K features (words) for an embedding.

        Useful for understanding what words contribute most to the vector.

        Args:
            embedding: Embedding vector
            top_k: Number of top features to return

        Returns:
            List of (feature_name, weight) tuples, sorted by weight descending

        Raises:
            EmbeddingProviderError: If not fitted
        """
        if not self._is_fitted:
            raise EmbeddingProviderError("Vectorizer not fitted")

        feature_names = self.get_feature_names()
        embedding_array = np.array(embedding)

        # Get indices of top K values
        top_indices = np.argsort(embedding_array)[-top_k:][::-1]

        return [
            (feature_names[idx], float(embedding_array[idx]))
            for idx in top_indices
        ]

    @property
    def is_fitted(self) -> bool:
        """Check if vectorizer is fitted"""
        return self._is_fitted
