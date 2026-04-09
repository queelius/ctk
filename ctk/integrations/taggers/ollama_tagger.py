"""
Ollama-based auto-tagger
"""

import logging
from typing import Optional

import requests

from ctk.integrations.taggers.base import BaseLLMTagger

logger = logging.getLogger(__name__)


class OllamaTagger(BaseLLMTagger):
    """Ollama-based automatic tagging"""

    name = "ollama"

    def get_provider_name(self) -> str:
        """Return the provider name"""
        return "ollama"

    def call_api(self, prompt: str) -> Optional[str]:
        """Call Ollama API"""
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3,
                    "max_tokens": 200,
                    "options": {"temperature": 0.3, "num_predict": 200},
                },
                timeout=self.timeout,
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            else:
                logger.error("Ollama API error: %s - %s", response.status_code, response.text)

        except requests.exceptions.ConnectionError:
            logger.error(
                "Could not connect to Ollama at %s. Make sure Ollama is running (ollama serve)",
                self.base_url,
            )
        except requests.exceptions.Timeout:
            logger.error("Ollama API timeout after %s seconds", self.timeout)
        except Exception as e:
            logger.error("Ollama API error: %s", e)

        return None

    def check_connection(self) -> bool:
        """Check if Ollama is available"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except (requests.exceptions.RequestException, ConnectionError):
            return False

    def list_models(self) -> list:
        """List available models"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [model["name"] for model in data.get("models", [])]
        except (requests.exceptions.RequestException, ValueError):
            pass
        return []
