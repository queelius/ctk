"""Auto-tagging integrations for conversations.

Two taggers ship with ctk:

* :class:`TFIDFTagger` — local, no-LLM statistical tagger.
* :class:`OpenAITagger` — LLM-driven tagger that works with any
  OpenAI-compatible chat endpoint.

Earlier versions bundled separate taggers for Ollama, OpenRouter, and
a generic "local" endpoint; they were removed in 2.10.0 because they
all spoke the same chat-completions protocol as OpenAI and thus
duplicated ``OpenAITagger``.
"""

from ctk.taggers.base import BaseLLMTagger
from ctk.taggers.openai_tagger import OpenAITagger
from ctk.taggers.tfidf_tagger import TFIDFTagger

__all__ = [
    "BaseLLMTagger",
    "OpenAITagger",
    "TFIDFTagger",
]
