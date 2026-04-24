"""Built-in importer plugins.

Importing this package loads every first-party importer so the plugin
registry can discover them via ``ImporterPlugin.__subclasses__()``.

Add new importers here to register them automatically.
"""

from ctk.importers.anthropic import AnthropicImporter
from ctk.importers.copilot import CopilotImporter
from ctk.importers.filesystem_coding import FilesystemCodingImporter
from ctk.importers.gemini import GeminiImporter
from ctk.importers.jsonl import JSONLImporter
from ctk.importers.openai import OpenAIImporter

__all__ = [
    "AnthropicImporter",
    "CopilotImporter",
    "FilesystemCodingImporter",
    "GeminiImporter",
    "JSONLImporter",
    "OpenAIImporter",
]
