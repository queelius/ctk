"""Convenience factory for constructing the default LLM provider.

Most ctk callers want "give me whatever provider the user has
configured, overridden by any CLI flags they passed". This module
centralises that construction so every call site doesn't need to know
about config loading, environment variables, and provider selection.

Since ctk only ships one provider (``OpenAIProvider`` against any
OpenAI-compatible endpoint), the factory is a thin helper. It stays a
factory rather than direct construction so the abstraction is preserved
for future providers and so tests can patch a single entry point.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ctk.core.config import get_config
from ctk.llm.base import LLMProvider
from ctk.llm.openai import OpenAIProvider


def build_provider(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    organization: Optional[str] = None,
) -> LLMProvider:
    """Build an ``LLMProvider`` from config, overridden by keyword args.

    Resolution order for each field, highest precedence first:

    1. Explicit argument passed to this function (usually from a CLI flag).
    2. ``providers.openai`` section of ``~/.ctk/config.json``.
    3. Environment variables (``OPENAI_API_KEY``, ``OPENAI_BASE_URL``).
    4. Hard-coded defaults.
    """
    cfg = get_config()
    provider_config = cfg.get_provider_config("openai") or {}

    resolved: Dict[str, Any] = {
        "model": model
        or provider_config.get("default_model")
        or "gpt-3.5-turbo",
        "base_url": base_url
        or provider_config.get("base_url")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1",
        "api_key": api_key
        or cfg.get_api_key("openai")
        or os.environ.get("OPENAI_API_KEY"),
        "timeout": timeout or provider_config.get("timeout") or 120,
    }
    if organization or provider_config.get("organization"):
        resolved["organization"] = organization or provider_config.get("organization")

    return OpenAIProvider(resolved)
