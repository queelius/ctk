"""Auto-tagging integrations for conversations"""

from ctk.taggers.anthropic_tagger import AnthropicTagger
from ctk.taggers.base import BaseLLMTagger
from ctk.taggers.local_tagger import LocalTagger
from ctk.taggers.ollama_tagger import OllamaTagger
from ctk.taggers.openai_tagger import OpenAITagger
from ctk.taggers.openrouter_tagger import OpenRouterTagger
from ctk.taggers.tfidf_tagger import TFIDFTagger

__all__ = [
    "TFIDFTagger",
    "BaseLLMTagger",
    "OllamaTagger",
    "OpenAITagger",
    "AnthropicTagger",
    "OpenRouterTagger",
    "LocalTagger",
]
