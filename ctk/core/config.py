"""
Configuration management for CTK

Security note: API keys should be stored in environment variables, not in
the config file. This module will warn if credentials are found in config files.
"""

import copy
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

    # Default configuration.
    #
    # ctk ships one LLM provider implementation (OpenAI-compatible) but
    # supports multiple **named profiles** under ``providers``. The
    # ``default`` field picks which profile is active at startup; the
    # TUI's ``/provider`` slash can switch live. Each profile's
    # ``base_url`` can point at any OpenAI-compatible endpoint: real
    # OpenAI, Azure, OpenRouter, vLLM, llama.cpp server, LM Studio,
    # Ollama's ``/v1`` route at localhost:11434, a remote inference
    # rig, etc.
    DEFAULTS = {
        "providers": {
            "default": "openai",
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "default_model": "gpt-3.5-turbo",
                "timeout": 30,
            },
        },
        # Database "path" is a directory; ConversationDB stores
        # ``conversations.db`` (and ``media/``) inside it.
        "database": {"default_path": "~/.ctk"},
        "tagging": {
            "auto_tag": True,
            "default_provider": "openai",
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
        # Set when an existing file could not be read; save() then refuses to
        # replace the user's file with defaults.
        self._load_error: Optional[str] = None
        self.config = self.load()

    @classmethod
    def defaults(cls) -> Dict[str, Any]:
        """A fresh deep copy of DEFAULTS (merging into it must never alias)."""
        return copy.deepcopy(cls.DEFAULTS)

    def load(self) -> Dict[str, Any]:
        """
        Load configuration from file or create default.

        Also checks for and warns about credentials in the config file.
        """
        if not self.config_path.exists():
            self.save(self.defaults())
            return self.defaults()
        try:
            with open(self.config_path, "r") as f:
                user_config = json.load(f)
        except json.JSONDecodeError as e:
            self._load_error = f"invalid JSON: {e}"
        except (IOError, OSError) as e:
            self._load_error = f"unreadable: {e}"
        else:
            if not isinstance(user_config, dict):
                self._load_error = "top-level JSON value is not an object"
        if self._load_error:
            logger.error(
                f"Config file {self.config_path} {self._load_error}; using defaults"
            )
            return self.defaults()

        # Merge with defaults (user config takes precedence)
        config = self._deep_merge(self.defaults(), user_config)
        self._warn_credentials_on_load(user_config)
        return config

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
        if self._load_error:
            raise ValueError(
                f"Config file {self.config_path} failed to load ({self._load_error});"
                " refusing to overwrite it. Fix or move it first."
            )
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
        for i, k in enumerate(keys[:-1]):
            if k not in target:
                target[k] = {}
            elif not isinstance(target[k], dict):
                prefix = ".".join(keys[: i + 1])
                raise ValueError(f"Cannot set {key}: {prefix} is not a section")
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
