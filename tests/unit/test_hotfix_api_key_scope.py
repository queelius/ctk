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


# 2.20.2: the ``openai`` profile's own variable *is* OPENAI_API_KEY, so it
# must get the same host check as the fallback (found by an external review).


def _openai_key_for(cfg, monkeypatch, **build_kwargs):
    from ctk.llm import factory

    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-openai")
    with patch.object(factory, "get_config", return_value=cfg):
        with patch("openai.OpenAI"):
            return factory.build_provider(profile="openai", **build_kwargs).api_key


def test_base_url_override_withholds_openai_key(cfg, monkeypatch):
    key = _openai_key_for(cfg, monkeypatch, base_url="http://third-party.example/v1")
    assert key != "sk-real-openai"


def test_openai_base_url_env_redirect_withholds_openai_key(cfg, monkeypatch):
    from ctk.llm import factory

    cfg.config["providers"]["openai"] = {}
    monkeypatch.setenv("OPENAI_BASE_URL", "http://third-party.example/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-openai")
    with patch.object(factory, "get_config", return_value=cfg):
        with patch("openai.OpenAI"):
            assert factory.build_provider(profile="openai").api_key != "sk-real-openai"


def test_legacy_openai_profile_on_local_server_withholds_openai_key(cfg, monkeypatch):
    cfg.config["providers"]["openai"] = {"base_url": "http://localhost:11434/v1"}
    assert _openai_key_for(cfg, monkeypatch) != "sk-real-openai"


def test_config_file_key_is_used_for_its_profile(cfg, monkeypatch):
    cfg.config["providers"]["openai"] = {
        "base_url": "http://localhost:8000/v1",
        "api_key": "local-key",
    }
    assert _openai_key_for(cfg, monkeypatch) == "local-key"


def test_tagger_base_url_override_withholds_openai_key(cfg, monkeypatch):
    from ctk.taggers import base
    from ctk.taggers.openai_tagger import OpenAITagger

    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-openai")
    with patch.object(base, "get_config", return_value=cfg):
        remote = OpenAITagger(base_url="http://third-party.example/v1")
        default = OpenAITagger()
    assert remote.api_key != "sk-real-openai"
    assert default.api_key == "sk-real-openai"
