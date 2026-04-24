"""
OpenAI-based auto-tagger
"""

import logging
from typing import Optional

import requests

from ctk.taggers.base import BaseLLMTagger

logger = logging.getLogger(__name__)


class OpenAITagger(BaseLLMTagger):
    """OpenAI-based automatic tagging"""

    name = "openai"

    def get_provider_name(self) -> str:
        """Return the provider name"""
        return "openai"

    def call_api(self, prompt: str) -> Optional[str]:
        """Call OpenAI API"""
        if not self.api_key:
            logger.error(
                "OpenAI API key not set. Set OPENAI_API_KEY environment variable or add to ~/.ctk/config.json"
            )
            return None

        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful assistant that generates tags for conversations. Be concise and accurate.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 200,
                },
                timeout=self.timeout,
            )

            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                error_msg = (
                    response.json().get("error", {}).get("message", response.text)
                )
                logger.error("OpenAI API error: %s", error_msg)

        except requests.exceptions.Timeout:
            logger.error("OpenAI API timeout after %s seconds", self.timeout)
        except Exception as e:
            logger.error("OpenAI API error: %s", e)

        return None

    def check_api_key(self) -> bool:
        """Check if API key is valid"""
        if not self.api_key:
            return False

        try:
            response = requests.get(
                f"{self.base_url}/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5,
            )
            return response.status_code == 200
        except (requests.exceptions.RequestException, ConnectionError):
            return False

    def list_models(self) -> list:
        """List available models"""
        if not self.api_key:
            return []

        try:
            response = requests.get(
                f"{self.base_url}/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                return [model["id"] for model in data.get("data", [])]
        except (requests.exceptions.RequestException, ValueError):
            pass
        return []
