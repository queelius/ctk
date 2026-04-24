"""OpenAI-compatible embedding provider.

Uses the official ``openai`` SDK against any endpoint exposing the
``/v1/embeddings`` protocol. Replaces the earlier Ollama-specific client
now that ctk standardises on OpenAI-compat endpoints.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ctk.embeddings.base import (EmbeddingInfo, EmbeddingProvider,
                                 EmbeddingResponse)

logger = logging.getLogger(__name__)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embeddings backed by the openai SDK against an OpenAI-compat API.

    Config keys:

    * ``api_key`` — bearer token. Local servers that don't enforce auth
      accept any non-empty string; a placeholder is used if unset.
    * ``base_url`` — endpoint root (must include ``/v1`` if needed).
    * ``model`` — embedding model id (e.g. ``text-embedding-3-small``
      for real OpenAI, ``nomic-embed-text`` for Ollama-compat).
    * ``timeout`` — per-request timeout in seconds.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.base_url = (
            config.get("base_url") or "https://api.openai.com/v1"
        ).rstrip("/")
        self.model = config.get("model") or "text-embedding-3-small"
        self.timeout = config.get("timeout", 30)

        from openai import OpenAI

        self._client = OpenAI(
            api_key=self.api_key or "unused",
            base_url=self.base_url,
            timeout=self.timeout,
        )
        # Cached once we see a response; some local servers don't
        # advertise dimensions up front so we back into it.
        self._dimensions: Optional[int] = None

    def embed(self, text: str, **kwargs: Any) -> EmbeddingResponse:
        response = self._client.embeddings.create(
            model=self.model, input=text, **kwargs
        )
        data = response.data[0]
        vector = list(data.embedding)
        self._dimensions = len(vector)
        return EmbeddingResponse(
            embedding=vector,
            model=response.model,
            dimensions=len(vector),
            metadata={"provider": "openai"},
        )

    def embed_batch(
        self, texts: List[str], **kwargs: Any
    ) -> List[EmbeddingResponse]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self.model, input=texts, **kwargs
        )
        out: List[EmbeddingResponse] = []
        for item in response.data:
            vector = list(item.embedding)
            self._dimensions = len(vector)
            out.append(
                EmbeddingResponse(
                    embedding=vector,
                    model=response.model,
                    dimensions=len(vector),
                    metadata={"provider": "openai"},
                )
            )
        return out

    def get_models(self) -> List[EmbeddingInfo]:
        """List models advertised by the endpoint.

        Real OpenAI returns many non-embedding models in ``/v1/models``;
        we return everything that looks embedding-shaped and let the
        caller filter further. Local servers typically only expose
        embedding models at their embedding port.
        """
        result = self._client.models.list()
        models: List[EmbeddingInfo] = []
        for m in result.data:
            mid = m.id
            # Heuristic — OpenAI's embedding models start with
            # "text-embedding"; most local servers use names that
            # include "embed".
            if "embed" in mid.lower() or mid.startswith("text-embedding"):
                models.append(
                    EmbeddingInfo(
                        id=mid,
                        name=mid,
                        dimensions=self._dimensions or 0,
                        metadata={
                            "created": getattr(m, "created", None),
                            "owned_by": getattr(m, "owned_by", None),
                        },
                    )
                )
        models.sort(key=lambda e: e.id)
        return models

    def get_dimensions(self) -> int:
        if self._dimensions is None:
            # Do a one-shot embed to learn the dimensionality; this is
            # lazy so constructor doesn't do network work.
            self.embed("dimension probe")
        assert self._dimensions is not None
        return self._dimensions
