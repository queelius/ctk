"""
Ollama-based auto-tagger
"""

import requests
from typing import Optional

from ctk.integrations.taggers.base import BaseLLMTagger


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
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 200
                    }
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '')
            else:
                print(f"Ollama API error: {response.status_code} - {response.text}")
        
        except requests.exceptions.ConnectionError:
            print(f"Could not connect to Ollama at {self.base_url}")
            print("Make sure Ollama is running (ollama serve)")
        except requests.exceptions.Timeout:
            print(f"Ollama API timeout after {self.timeout} seconds")
        except Exception as e:
            print(f"Ollama API error: {e}")
        
        return None
    
    def check_connection(self) -> bool:
        """Check if Ollama is available"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def list_models(self) -> list:
        """List available models"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
        except:
            pass
        return []