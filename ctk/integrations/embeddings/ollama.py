"""
Ollama embedding provider implementation.
"""

import requests
from typing import List, Dict, Optional, Any

from ctk.integrations.embeddings.base import (
    EmbeddingProvider,
    EmbeddingInfo,
    EmbeddingResponse,
    EmbeddingProviderError,
    ModelNotFoundError,
)


class OllamaEmbedding(EmbeddingProvider):
    """
    Ollama provider for local embedding generation.

    Requires Ollama to be running locally (default: http://localhost:11434)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Ollama embedding provider.

        Args:
            config: Configuration dict with keys:
                - base_url: Ollama API URL (default: http://localhost:11434)
                - model: Model name (e.g., 'nomic-embed-text', 'mxbai-embed-large')
                - timeout: Request timeout in seconds (default: 60)
        """
        super().__init__(config)
        self.base_url = config.get('base_url', 'http://localhost:11434').rstrip('/')
        self.timeout = config.get('timeout', 60)

        if not self.model:
            raise ValueError("Model name is required for Ollama embedding provider")

        # Cache dimensions after first embedding
        self._dimensions: Optional[int] = None

    def embed(self, text: str, **kwargs) -> EmbeddingResponse:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            **kwargs: Additional Ollama parameters

        Returns:
            EmbeddingResponse object

        Raises:
            EmbeddingProviderError: On API errors
        """
        try:
            response = requests.post(
                f'{self.base_url}/api/embeddings',
                json={
                    'model': self.model,
                    'prompt': text,
                    **kwargs
                },
                timeout=self.timeout
            )
            response.raise_for_status()

            result = response.json()
            embedding = result['embedding']

            # Cache dimensions
            if self._dimensions is None:
                self._dimensions = len(embedding)

            return EmbeddingResponse(
                embedding=embedding,
                model=self.model,
                dimensions=len(embedding),
                metadata=result
            )

        except requests.exceptions.ConnectionError:
            raise EmbeddingProviderError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Is Ollama running? Try: ollama serve"
            )
        except requests.exceptions.Timeout:
            raise EmbeddingProviderError(f"Request timed out after {self.timeout}s")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ModelNotFoundError(
                    f"Model '{self.model}' not found. "
                    f"Pull it with: ollama pull {self.model}"
                )
            raise EmbeddingProviderError(f"Ollama API error: {e}")
        except KeyError as e:
            raise EmbeddingProviderError(f"Unexpected API response format: missing {e}")
        except Exception as e:
            raise EmbeddingProviderError(f"Unexpected error: {e}")

    def embed_batch(self, texts: List[str], **kwargs) -> List[EmbeddingResponse]:
        """
        Generate embeddings for multiple texts.

        Note: Ollama doesn't have native batch API, so this calls embed() sequentially.
        For better performance, consider using a provider with batch support.

        Args:
            texts: List of texts to embed
            **kwargs: Additional Ollama parameters

        Returns:
            List of EmbeddingResponse objects

        Raises:
            EmbeddingProviderError: On API errors
        """
        return [self.embed(text, **kwargs) for text in texts]

    def get_models(self) -> List[EmbeddingInfo]:
        """
        List available embedding models from Ollama.

        Note: Ollama doesn't distinguish between chat and embedding models in /api/tags.
        This returns all models - you need to know which are embedding models.
        Common embedding models: nomic-embed-text, mxbai-embed-large, all-minilm

        Returns:
            List of EmbeddingInfo objects

        Raises:
            EmbeddingProviderError: On API errors
        """
        try:
            response = requests.get(
                f'{self.base_url}/api/tags',
                timeout=10
            )
            response.raise_for_status()

            result = response.json()
            models = []

            for model_data in result.get('models', []):
                # We can't easily determine dimensions without calling the model
                # So we set it to None and let it be determined on first use
                models.append(EmbeddingInfo(
                    id=model_data['name'],
                    name=model_data['name'],
                    dimensions=0,  # Unknown until first embedding
                    metadata={
                        'size': model_data.get('size'),
                        'modified': model_data.get('modified_at'),
                        'digest': model_data.get('digest'),
                    }
                ))

            return models

        except requests.exceptions.ConnectionError:
            raise EmbeddingProviderError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Is Ollama running?"
            )
        except Exception as e:
            raise EmbeddingProviderError(f"Failed to list models: {e}")

    def get_dimensions(self) -> int:
        """
        Get dimensionality of embeddings from current model.

        If not yet cached, generates a test embedding to determine dimensions.

        Returns:
            Number of dimensions

        Raises:
            EmbeddingProviderError: On API errors
        """
        if self._dimensions is None:
            # Generate test embedding to determine dimensions
            test_response = self.embed("test")
            self._dimensions = test_response.dimensions

        return self._dimensions

    def is_available(self) -> bool:
        """
        Check if Ollama is running and accessible.

        Returns:
            True if Ollama is available, False otherwise
        """
        try:
            response = requests.get(f'{self.base_url}/api/tags', timeout=2)
            return response.ok
        except:
            return False
