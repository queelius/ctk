"""
OpenAI-based auto-tagger
"""

import requests
from typing import Optional

from ctk.integrations.taggers.base import BaseLLMTagger


class OpenAITagger(BaseLLMTagger):
    """OpenAI-based automatic tagging"""
    
    name = "openai"
    
    def get_provider_name(self) -> str:
        """Return the provider name"""
        return "openai"
    
    def call_api(self, prompt: str) -> Optional[str]:
        """Call OpenAI API"""
        if not self.api_key:
            print("OpenAI API key not set. Set OPENAI_API_KEY environment variable or add to ~/.ctk/config.json")
            return None
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
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
                print(f"OpenAI API error: {error_msg}")
        
        except requests.exceptions.Timeout:
            print(f"OpenAI API timeout after {self.timeout} seconds")
        except Exception as e:
            print(f"OpenAI API error: {e}")
        
        return None
    
    def check_api_key(self) -> bool:
        """Check if API key is valid"""
        if not self.api_key:
            return False
        
        try:
            response = requests.get(
                f"{self.base_url}/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    def list_models(self) -> list:
        """List available models"""
        if not self.api_key:
            return []
        
        try:
            response = requests.get(
                f"{self.base_url}/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                return [model['id'] for model in data.get('data', [])]
        except:
            pass
        return []