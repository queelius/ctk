"""
OpenRouter-based auto-tagger (supports many models)
"""

import requests
from typing import Optional

from ctk.integrations.taggers.base import BaseLLMTagger


class OpenRouterTagger(BaseLLMTagger):
    """OpenRouter-based automatic tagging (access to many models)"""
    
    name = "openrouter"
    
    def get_provider_name(self) -> str:
        """Return the provider name"""
        return "openrouter"
    
    def call_api(self, prompt: str) -> Optional[str]:
        """Call OpenRouter API"""
        if not self.api_key:
            print("OpenRouter API key not set. Set OPENROUTER_API_KEY environment variable or add to ~/.ctk/config.json")
            return None
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/ctk",  # Optional but recommended
                    "X-Title": "CTK Auto-Tagger"  # Optional
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful assistant that generates tags for conversations. Be concise and accurate."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.3,
                    "max_tokens": 200
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                error_msg = response.json().get('error', {}).get('message', response.text)
                print(f"OpenRouter API error: {error_msg}")
        
        except requests.exceptions.Timeout:
            print(f"OpenRouter API timeout after {self.timeout} seconds")
        except Exception as e:
            print(f"OpenRouter API error: {e}")
        
        return None
    
    def list_models(self) -> list:
        """List available models from OpenRouter"""
        try:
            response = requests.get(
                f"{self.base_url}/v1/models",
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                return [model['id'] for model in data.get('data', [])]
        except:
            pass
        return []