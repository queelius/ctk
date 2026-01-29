"""
Configuration management for CTK

Security note: API keys should be stored in environment variables, not in
the config file. This module will warn if credentials are found in config files.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Credential-related keys that should not be in config files
SENSITIVE_KEYS = {"api_key", "api_secret", "token", "password", "secret", "credential"}


class Config:
    """Configuration manager for CTK"""

    DEFAULT_CONFIG_PATH = Path.home() / ".ctk" / "config.json"

    # Default configuration
    DEFAULTS = {
        "providers": {
            "ollama": {
                "base_url": "http://localhost:11434",
                "default_model": "llama2",
                "timeout": 30,
            },
            "openai": {
                "base_url": "https://api.openai.com",
                "default_model": "gpt-3.5-turbo",
                "timeout": 30,
            },
            "anthropic": {
                "base_url": "https://api.anthropic.com",
                "default_model": "claude-3-haiku-20240307",
                "timeout": 30,
            },
            # Note: openrouter and local providers removed - use ollama for local models
        },
        "database": {"default_path": "~/.ctk/conversations.db"},
        "tagging": {
            "auto_tag": True,
            "default_provider": "ollama",
            "max_tags": 10,
            "use_tfidf": True,
        },
        "export": {"default_format": "jsonl", "sanitize_secrets": False},
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
        """
        Load configuration from file or create default.

        Also checks for and warns about credentials in the config file.
        """
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    user_config = json.load(f)
                # Merge with defaults (user config takes precedence)
                config = self._deep_merge(self.DEFAULTS.copy(), user_config)

                # Check for credentials in config and warn
                # (Done after merge so we check the final config)
                self._warn_credentials_on_load(user_config)

                return config
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in config file: {e}, using defaults")
                return self.DEFAULTS.copy()
            except (IOError, OSError) as e:
                logger.error(f"Error reading config file: {e}, using defaults")
                return self.DEFAULTS.copy()
            except Exception as e:
                logger.error(f"Unexpected error loading config: {e}, using defaults")
                return self.DEFAULTS.copy()
        else:
            # Create default config file
            self.save(self.DEFAULTS)
            return self.DEFAULTS.copy()

    def _warn_credentials_on_load(self, user_config: Dict[str, Any]) -> None:
        """Check user config for credentials and log warnings."""
        sensitive = self._find_sensitive_keys(user_config)
        if sensitive:
            logger.warning(
                f"Config file {self.config_path} contains sensitive data. "
                f"Consider using environment variables instead."
            )
            for path in sensitive:
                parts = path.split(".")
                if len(parts) >= 2 and parts[0] == "providers":
                    provider = parts[1].upper()
                    env_var = f"{provider}_API_KEY"
                    logger.warning(
                        f"  - '{path}' should be {env_var} environment variable"
                    )

    def save(self, config: Optional[Dict[str, Any]] = None):
        """Save configuration to file"""
        config = config or self.config

        # Ensure directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key

        Examples:
            config.get('providers.ollama.base_url')
            config.get('tagging.max_tags', 10)
        """
        keys = key.split(".")
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
        keys = key.split(".")
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
        return self.get(f"providers.{provider}", {})

    def get_api_key(self, provider: str) -> Optional[str]:
        """
        Get API key for a provider.

        Security note: API keys should be stored in environment variables.
        This method first checks environment variables (preferred) and only
        falls back to config file if not found. A warning is logged if
        credentials are found in the config file.

        Args:
            provider: Provider name (ollama, openai, anthropic, etc.)

        Returns:
            API key string or None if not found
        """
        # Check environment first (preferred method)
        env_key = f"{provider.upper()}_API_KEY"
        if env_key in os.environ:
            return os.environ[env_key]

        # Fall back to config file (not recommended)
        config_key = self.get(f"providers.{provider}.api_key")
        if config_key:
            logger.warning(
                f"API key for '{provider}' found in config file. "
                f"For security, use environment variable {env_key} instead."
            )
        return config_key

    def _find_sensitive_keys(self, config: Dict, path: str = "") -> List[str]:
        """
        Recursively find sensitive keys in config dictionary.

        Args:
            config: Configuration dictionary to search
            path: Current path in the config (for nested keys)

        Returns:
            List of paths to sensitive keys found
        """
        found = []
        for key, value in config.items():
            current_path = f"{path}.{key}" if path else key
            # Check if this key name indicates sensitive data
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in SENSITIVE_KEYS):
                if value:  # Only warn if key has a value
                    found.append(current_path)
            # Recurse into nested dicts
            if isinstance(value, dict):
                found.extend(self._find_sensitive_keys(value, current_path))
        return found

    def check_for_credentials(self) -> List[str]:
        """
        Check config for any credentials that should be in environment variables.

        Returns:
            List of config paths containing sensitive data
        """
        return self._find_sensitive_keys(self.config)

    def warn_about_credentials(self) -> None:
        """Log warnings about any credentials found in config file."""
        sensitive = self.check_for_credentials()
        if sensitive:
            for path in sensitive:
                # Suggest appropriate environment variable
                parts = path.split(".")
                if len(parts) >= 2 and parts[0] == "providers":
                    provider = parts[1].upper()
                    env_var = f"{provider}_API_KEY"
                else:
                    env_var = path.upper().replace(".", "_")

                logger.warning(
                    f"Sensitive data '{path}' found in config file {self.config_path}. "
                    f"Consider using environment variable {env_var} instead."
                )

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
