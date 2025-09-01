"""Auto-tagging integrations for conversations"""

from ctk.integrations.taggers.tfidf_tagger import TFIDFTagger
from ctk.integrations.taggers.base import BaseLLMTagger
from ctk.integrations.taggers.ollama_tagger import OllamaTagger
from ctk.integrations.taggers.openai_tagger import OpenAITagger
from ctk.integrations.taggers.anthropic_tagger import AnthropicTagger
from ctk.integrations.taggers.openrouter_tagger import OpenRouterTagger
from ctk.integrations.taggers.local_tagger import LocalTagger

__all__ = [
    'TFIDFTagger',
    'BaseLLMTagger',
    'OllamaTagger',
    'OpenAITagger',
    'AnthropicTagger',
    'OpenRouterTagger',
    'LocalTagger'
]