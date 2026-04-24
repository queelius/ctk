"""
Anthropic Claude-based auto-tagger
"""

import logging
from typing import Optional

import requests

from ctk.taggers.base import BaseLLMTagger

logger = logging.getLogger(__name__)


class AnthropicTagger(BaseLLMTagger):
    """Anthropic Claude-based automatic tagging"""

    name = "anthropic"

    def get_provider_name(self) -> str:
        """Return the provider name"""
        return "anthropic"

    def call_api(self, prompt: str) -> Optional[str]:
        """Call Anthropic API"""
        if not self.api_key:
            logger.error(
                "Anthropic API key not set. Set ANTHROPIC_API_KEY environment variable or add to ~/.ctk/config.json"
            )
            return None

        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.3,
                },
                timeout=self.timeout,
            )

            if response.status_code == 200:
                result = response.json()
                return result["content"][0]["text"]
            else:
                error_msg = (
                    response.json().get("error", {}).get("message", response.text)
                )
                logger.error("Anthropic API error: %s", error_msg)

        except requests.exceptions.Timeout:
            logger.error("Anthropic API timeout after %s seconds", self.timeout)
        except Exception as e:
            logger.error("Anthropic API error: %s", e)

        return None

    def check_api_key(self) -> bool:
        """Check if API key is valid"""
        if not self.api_key:
            return False

        # Anthropic doesn't have a simple endpoint to check API key validity
        # We could make a minimal request but that would cost tokens
        # For now, just check if key exists
        return True
