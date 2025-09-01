"""
Local LLM auto-tagger (OpenAI-compatible endpoints)
"""

import requests
from typing import Optional

from ctk.integrations.taggers.base import BaseLLMTagger


class LocalTagger(BaseLLMTagger):
    """Local LLM automatic tagging (OpenAI-compatible API)"""
    
    name = "local"
    
    def get_provider_name(self) -> str:
        """Return the provider name"""
        return "local"
    
    def call_api(self, prompt: str) -> Optional[str]:
        """Call local LLM API (OpenAI-compatible)"""
        try:
            # Try OpenAI-compatible endpoint first
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful assistant that generates tags for conversations."
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
            
        except:
            # Try simpler completion endpoint
            try:
                response = requests.post(
                    f"{self.base_url}/completions",
                    json={
                        "prompt": prompt,
                        "max_tokens": 200,
                        "temperature": 0.3
                    },
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get('text', result.get('response', ''))
            except:
                pass
        
        print(f"Could not connect to local LLM at {self.base_url}")
        return None
    
    def check_connection(self) -> bool:
        """Check if local LLM is available"""
        try:
            # Try health endpoint
            response = requests.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                return True
            
            # Try models endpoint
            response = requests.get(f"{self.base_url}/v1/models", timeout=5)
            return response.status_code == 200
        except:
            return False