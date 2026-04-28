"""Convenience factory for constructing the active LLM provider.

Ctk uses one provider implementation (``OpenAIProvider``) against any
OpenAI-compatible endpoint, but supports multiple **named profiles**
in ``~/.ctk/config.json`` so the user can switch between (e.g.) the
real OpenAI API, a local Ollama, and a remote inference server
without editing config every time.

Profile resolution (highest precedence first):

1. Explicit ``profile=`` argument to ``build_provider``.
2. ``providers.default`` field in the config.
3. ``"openai"`` (the implicit default profile, always present).

Within the chosen profile, individual fields (``base_url``, ``model``,
``api_key``, ``timeout``) follow the same precedence: explicit kwarg,
then the profile dict, then env vars, then hard-coded defaults.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ctk.core.config import get_config
from ctk.llm.base import LLMProvider
from ctk.llm.openai import OpenAIProvider


def list_profiles() -> List[str]:
    """Return all defined profile names from ``providers.*``.

    Excludes the ``default`` key (it's a pointer, not a profile).
    """
    cfg = get_config()
    providers = cfg.get("providers", {}) or {}
    return sorted(name for name, value in providers.items()
                  if name != "default" and isinstance(value, dict))


def active_profile_name(explicit: Optional[str] = None) -> str:
    """Resolve which profile name should be active right now."""
    if explicit:
        return explicit
    cfg = get_config()
    return cfg.get("providers.default") or "openai"


def build_provider(
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
    organization: Optional[str] = None,
    profile: Optional[str] = None,
) -> LLMProvider:
    """Build an ``LLMProvider`` from the active profile, overridden by kwargs.

    Args:
        profile: Named profile to use (key under ``providers`` in config).
            If omitted, falls back to ``providers.default`` and then to
            ``"openai"``.
        model / base_url / api_key / timeout / organization: Per-field
            overrides, taking precedence over the profile's values.
    """
    cfg = get_config()
    name = active_profile_name(profile)
    provider_config = cfg.get_provider_config(name) or {}

    resolved: Dict[str, Any] = {
        "model": model
        or provider_config.get("default_model")
        or "gpt-3.5-turbo",
        "base_url": base_url
        or provider_config.get("base_url")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1",
        # Env-var lookup keys off the profile name so e.g. profile
        # ``muse`` reads MUSE_API_KEY. Falls back to the canonical
        # OPENAI_API_KEY so users who only set that don't have to mirror
        # it across profiles.
        "api_key": api_key
        or cfg.get_api_key(name)
        or os.environ.get("OPENAI_API_KEY"),
        "timeout": timeout or provider_config.get("timeout") or 120,
    }
    if organization or provider_config.get("organization"):
        resolved["organization"] = organization or provider_config.get("organization")

    provider = OpenAIProvider(resolved)
    # Stamp the profile name on the instance so the TUI can display it
    # without having to re-read config.
    provider.profile_name = name
    return provider
