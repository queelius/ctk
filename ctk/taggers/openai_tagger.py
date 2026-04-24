"""LLM-based auto-tagger using the openai SDK.

Works against any OpenAI-compatible endpoint. Replaces the earlier
bag of separate taggers (ollama, openrouter, local, anthropic) — they
all spoke the same chat-completions protocol so maintaining four
copies was pure duplication.
"""

from __future__ import annotations

import logging
from typing import Optional

from ctk.taggers.base import BaseLLMTagger

logger = logging.getLogger(__name__)


class OpenAITagger(BaseLLMTagger):
    """Auto-tagger that talks to any OpenAI-compatible chat endpoint."""

    name = "openai"

    def get_provider_name(self) -> str:
        return "openai"

    def _build_client(self, timeout: Optional[float] = None):
        """Construct a fresh openai SDK client.

        Local endpoints often don't enforce auth, but the SDK still
        requires a non-empty ``api_key``. A placeholder is used if
        none is configured.
        """
        from openai import OpenAI

        return OpenAI(
            api_key=self.api_key or "unused",
            base_url=(self.base_url or "https://api.openai.com/v1").rstrip("/"),
            timeout=timeout if timeout is not None else self.timeout,
        )

    def call_api(self, prompt: str) -> Optional[str]:
        """Send ``prompt`` and return the assistant reply, or None on failure."""
        try:
            client = self._build_client()
        except ImportError:
            logger.error("openai SDK not installed; install `pip install openai`")
            return None

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful assistant that generates tags "
                            "for conversations. Be concise and accurate."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=200,
            )
        except Exception as exc:
            logger.error("Tagger API call failed: %s", exc)
            return None

        try:
            return response.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            logger.error("Unexpected tagger response shape: %s", exc)
            return None

    def check_api_key(self) -> bool:
        """Cheap connectivity check using the /models endpoint."""
        try:
            self._build_client(timeout=5).models.list()
            return True
        except Exception:
            return False

    def list_models(self) -> list:
        try:
            result = self._build_client(timeout=5).models.list()
            return sorted(m.id for m in result.data)
        except Exception as exc:
            logger.debug("list_models failed: %s", exc)
            return []
