"""LLM provider abstractions for CTK chat integration.

ctk ships a single provider (``OpenAIProvider``) that talks to any
OpenAI-compatible endpoint — the real OpenAI API, Azure, OpenRouter,
vLLM, llama.cpp server, LM Studio, and Ollama's OpenAI-compat mode.

Earlier versions maintained hand-rolled clients for Ollama and
Anthropic; those were removed in 2.10.0 in favor of the single wrapper.
"""

from ctk.llm.base import (AuthenticationError, ChatResponse,
                          ContextLengthError, LLMProvider, LLMProviderError,
                          Message, MessageRole, ModelInfo, ModelNotFoundError,
                          RateLimitError)
from ctk.llm.factory import build_provider
from ctk.llm.openai import OpenAIProvider

__all__ = [
    # Base classes and types
    "LLMProvider",
    "Message",
    "MessageRole",
    "ChatResponse",
    "ModelInfo",
    # Exceptions
    "LLMProviderError",
    "AuthenticationError",
    "RateLimitError",
    "ModelNotFoundError",
    "ContextLengthError",
    # Providers
    "OpenAIProvider",
    # Factory
    "build_provider",
]
