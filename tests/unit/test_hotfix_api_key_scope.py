"""Regression tests: OPENAI_API_KEY is only sent to OpenAI's own endpoint (2.20.1)."""

from unittest.mock import patch

import pytest

from ctk.core.config import Config

pytestmark = pytest.mark.unit


@pytest.fixture
def cfg(tmp_path):
    cfg = Config(config_path=tmp_path / "config.json")
    cfg.config = {
        "providers": {
            "openai": {"base_url": "https://api.openai.com/v1"},
            "ollama": {"base_url": "http://192.168.0.204:11434/v1"},
            "lookalike": {"base_url": "https://api.openai.com.evil.example/v1"},
        }
    }
    return cfg


def _key(cfg, profile, monkeypatch):
    from ctk.llm import factory

    for var in ("OLLAMA_API_KEY", "LOOKALIKE_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-openai")
    with patch.object(factory, "get_config", return_value=cfg):
        with patch("openai.OpenAI"):
            return factory.build_provider(profile=profile).api_key


@pytest.mark.parametrize("profile", ["ollama", "lookalike"])
def test_openai_key_not_sent_to_other_hosts(cfg, profile, monkeypatch):
    assert _key(cfg, profile, monkeypatch) != "sk-real-openai"


def test_openai_key_still_used_for_openai(cfg, monkeypatch):
    assert _key(cfg, "openai", monkeypatch) == "sk-real-openai"


def test_profile_specific_key_still_wins(cfg, monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-secret")
    from ctk.llm import factory

    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-openai")
    with patch.object(factory, "get_config", return_value=cfg):
        with patch("openai.OpenAI"):
            assert factory.build_provider(profile="ollama").api_key == "ollama-secret"
