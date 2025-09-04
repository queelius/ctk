"""
Configuration management for CTK
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """Configuration manager for CTK"""
    
    DEFAULT_CONFIG_PATH = Path.home() / ".ctk" / "config.json"
    
    # Default configuration
    DEFAULTS = {
        "providers": {
            "ollama": {
                "base_url": "http://localhost:11434",
                "default_model": "llama2",
                "timeout": 30
            },
            "openai": {
                "base_url": "https://api.openai.com",
                "default_model": "gpt-3.5-turbo",
                "timeout": 30
            },
            "anthropic": {
                "base_url": "https://api.anthropic.com",
                "default_model": "claude-3-haiku-20240307",
                "timeout": 30
            },
            "openrouter": {
                "base_url": "https://openrouter.ai/api",
                "default_model": "meta-llama/llama-3-8b-instruct",
                "timeout": 30
            },
            "local": {
                "base_url": "http://localhost:8080",
                "default_model": "local-model",
                "timeout": 30
            }
        },
        "database": {
            "default_path": "~/.ctk/conversations.db"
        },
        "tagging": {
            "auto_tag": True,
            "default_provider": "ollama",
            "max_tags": 10,
            "use_tfidf": True
        },
        "export": {
            "default_format": "jsonl",
            "sanitize_secrets": False
        }
    }
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration
        
        Args:
            config_path: Optional custom config path
        """
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self.config = self.load()
    
    def load(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    user_config = json.load(f)
                # Merge with defaults (user config takes precedence)
                return self._deep_merge(self.DEFAULTS.copy(), user_config)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON in config file: {e}, using defaults")
                return self.DEFAULTS.copy()
            except (IOError, OSError) as e:
                print(f"Error reading config file: {e}, using defaults")
                return self.DEFAULTS.copy()
            except Exception as e:
                print(f"Unexpected error loading config: {e}, using defaults")
                return self.DEFAULTS.copy()
        else:
            # Create default config file
            self.save(self.DEFAULTS)
            return self.DEFAULTS.copy()
    
    def save(self, config: Optional[Dict[str, Any]] = None):
        """Save configuration to file"""
        config = config or self.config
        
        # Ensure directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key
        
        Examples:
            config.get('providers.ollama.base_url')
            config.get('tagging.max_tags', 10)
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """
        Set configuration value by dot-notation key
        
        Examples:
            config.set('providers.ollama.base_url', 'http://remote:11434')
        """
        keys = key.split('.')
        target = self.config
        
        # Navigate to parent
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        
        # Set value
        target[keys[-1]] = value
        
        # Save to file
        self.save()
    
    def get_provider_config(self, provider: str) -> Dict[str, Any]:
        """Get configuration for a specific provider"""
        return self.get(f'providers.{provider}', {})
    
    def get_api_key(self, provider: str) -> Optional[str]:
        """
        Get API key for a provider
        
        First checks environment variables, then config file
        """
        # Check environment first
        env_key = f"{provider.upper()}_API_KEY"
        if env_key in os.environ:
            return os.environ[env_key]
        
        # Check config
        return self.get(f'providers.{provider}.api_key')
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base


# Global config instance
_config = None

def get_config() -> Config:
    """Get global config instance"""
    global _config
    if _config is None:
        _config = Config()
    return _config