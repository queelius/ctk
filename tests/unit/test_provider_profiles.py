"""Tests for named LLM provider profiles (since 2.14.x).

The factory supports multiple named profiles under ``providers.{name}``
in ``~/.ctk/config.json``, with ``providers.default`` choosing the
active one. Backward compat: configs that only define ``providers.openai``
keep working unchanged.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ctk.core.config import Config


@pytest.fixture
def config_with_profiles(tmp_path):
    """Build a Config pointing at a temp file with two profiles."""
    cfg_path = tmp_path / "config.json"
    cfg = Config(config_path=cfg_path)
    cfg.config = {
        "providers": {
            "default": "muse",
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "default_model": "gpt-4o",
                "timeout": 60,
            },
            "muse": {
                "base_url": "http://muse.lan:8000/v1",
                "default_model": "qwen3-omni",
                "timeout": 120,
            },
            "ollama": {
                "base_url": "http://localhost:11434/v1",
                "default_model": "llama3.1:70b",
            },
        },
    }
    return cfg


class TestListProfiles:
    @pytest.mark.unit
    def test_list_profiles_excludes_default_pointer(self, config_with_profiles):
        from ctk.llm import factory

        with patch.object(factory, "get_config", return_value=config_with_profiles):
            profiles = factory.list_profiles()
        # 'default' is a pointer string, not a profile dict, so it's filtered out.
        assert profiles == ["muse", "ollama", "openai"]
        assert "default" not in profiles

    @pytest.mark.unit
    def test_list_profiles_handles_empty_config(self, tmp_path):
        from ctk.llm import factory

        cfg = Config(config_path=tmp_path / "empty.json")
        cfg.config = {}
        with patch.object(factory, "get_config", return_value=cfg):
            assert factory.list_profiles() == []


class TestActiveProfileName:
    @pytest.mark.unit
    def test_explicit_argument_wins(self, config_with_profiles):
        from ctk.llm import factory

        with patch.object(factory, "get_config", return_value=config_with_profiles):
            assert factory.active_profile_name("openai") == "openai"
            # config.default is "muse" but explicit overrides
            assert factory.active_profile_name("ollama") == "ollama"

    @pytest.mark.unit
    def test_falls_back_to_providers_default(self, config_with_profiles):
        from ctk.llm import factory

        with patch.object(factory, "get_config", return_value=config_with_profiles):
            assert factory.active_profile_name() == "muse"

    @pytest.mark.unit
    def test_falls_back_to_openai_when_no_default_set(self, tmp_path):
        from ctk.llm import factory

        cfg = Config(config_path=tmp_path / "no-default.json")
        cfg.config = {"providers": {"openai": {}}}
        with patch.object(factory, "get_config", return_value=cfg):
            assert factory.active_profile_name() == "openai"


class TestBuildProvider:
    @pytest.mark.unit
    def test_uses_profile_default_model_and_base_url(self, config_with_profiles):
        from ctk.llm import factory

        with patch.object(factory, "get_config", return_value=config_with_profiles):
            with patch("openai.OpenAI"):  # avoid real openai client
                provider = factory.build_provider(profile="muse")
        assert provider.model == "qwen3-omni"
        assert provider.base_url == "http://muse.lan:8000/v1"
        assert provider.profile_name == "muse"

    @pytest.mark.unit
    def test_no_profile_uses_default_pointer(self, config_with_profiles):
        from ctk.llm import factory

        with patch.object(factory, "get_config", return_value=config_with_profiles):
            with patch("openai.OpenAI"):
                provider = factory.build_provider()
        # config.default is "muse"
        assert provider.profile_name == "muse"
        assert provider.base_url == "http://muse.lan:8000/v1"

    @pytest.mark.unit
    def test_explicit_kwargs_override_profile(self, config_with_profiles):
        from ctk.llm import factory

        with patch.object(factory, "get_config", return_value=config_with_profiles):
            with patch("openai.OpenAI"):
                provider = factory.build_provider(
                    profile="muse",
                    model="custom-model",
                    base_url="http://override:9000/v1",
                )
        assert provider.model == "custom-model"
        assert provider.base_url == "http://override:9000/v1"
        # Profile name is still muse — kwargs override values, not which
        # profile we recorded as the source.
        assert provider.profile_name == "muse"

    @pytest.mark.unit
    def test_backward_compat_with_only_openai_profile(self, tmp_path):
        """Existing configs with only providers.openai keep working."""
        from ctk.llm import factory

        cfg = Config(config_path=tmp_path / "legacy.json")
        cfg.config = {
            "providers": {
                "openai": {
                    "base_url": "https://api.openai.com/v1",
                    "default_model": "gpt-3.5-turbo",
                },
            },
        }
        with patch.object(factory, "get_config", return_value=cfg):
            with patch("openai.OpenAI"):
                provider = factory.build_provider()
        assert provider.profile_name == "openai"
        assert provider.model == "gpt-3.5-turbo"

    @pytest.mark.unit
    def test_api_key_uses_profile_specific_env_var(
        self, config_with_profiles, monkeypatch
    ):
        """MUSE_API_KEY beats OPENAI_API_KEY when profile is muse."""
        from ctk.llm import factory

        monkeypatch.setenv("MUSE_API_KEY", "muse-secret")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
        with patch.object(factory, "get_config", return_value=config_with_profiles):
            with patch("openai.OpenAI"):
                provider = factory.build_provider(profile="muse")
        assert provider.api_key == "muse-secret"


class TestProviderProfileSlash:
    """Exercise the /provider slash command end-to-end via the dispatcher."""

    @pytest.mark.unit
    def test_no_arg_lists_profiles_with_current_marker(self, config_with_profiles):
        from ctk.llm import factory
        from ctk.tui import slash

        app = MagicMock()
        app.provider = MagicMock()
        app.provider.profile_name = "openai"

        with patch.object(factory, "get_config", return_value=config_with_profiles):
            with patch("ctk.tui.slash.get_config", return_value=config_with_profiles, create=True):
                # Inside cmd_provider get_config is imported lazily from
                # ctk.core.config; patch that target.
                from ctk.core import config as cfg_mod

                with patch.object(cfg_mod, "get_config", return_value=config_with_profiles):
                    handled, note = slash.dispatch(app, "/provider")
        assert handled is True
        assert "Provider profiles" in note
        # Currently-active marker must point at openai.
        assert "* openai" in note
        # Other profiles listed without marker.
        assert "muse" in note
        assert "ollama" in note

    @pytest.mark.unit
    def test_unknown_profile_reports_available_options(self, config_with_profiles):
        from ctk.llm import factory
        from ctk.tui import slash

        app = MagicMock()
        app.provider = None  # No active provider — still allowed to list

        with patch.object(factory, "get_config", return_value=config_with_profiles):
            handled, note = slash.dispatch(app, "/provider not-a-real-profile")
        assert handled is True
        assert "Unknown profile" in note
        assert "muse" in note  # availables shown

    @pytest.mark.unit
    def test_switch_rebuilds_provider_and_updates_app_state(
        self, config_with_profiles
    ):
        from ctk.llm import factory
        from ctk.tui import slash

        app = MagicMock()
        app.provider = MagicMock()
        app.provider.profile_name = "openai"
        app._tools_requested = True

        new_provider = MagicMock()
        new_provider.model = "qwen3-omni"
        new_provider.base_url = "http://muse.lan:8000/v1"
        new_provider.profile_name = "muse"
        new_provider.supports_tool_calling.return_value = True

        with patch.object(factory, "get_config", return_value=config_with_profiles):
            with patch.object(
                factory, "build_provider", return_value=new_provider
            ) as mock_build:
                handled, note = slash.dispatch(app, "/provider muse")

        assert handled is True
        assert "Switched to provider 'muse'" in note
        # Built with the right profile name
        mock_build.assert_called_once_with(profile="muse")
        # App now points at the new provider
        assert app.provider is new_provider
        # Tools state was re-evaluated
        assert app._tools_supported is True
        assert app.enable_tools is True
        # Status bar refreshed
        app._refresh_status.assert_called_once()

    @pytest.mark.unit
    def test_switch_to_current_profile_is_a_noop(self, config_with_profiles):
        from ctk.llm import factory
        from ctk.tui import slash

        app = MagicMock()
        app.provider = MagicMock()
        app.provider.profile_name = "muse"

        with patch.object(factory, "get_config", return_value=config_with_profiles):
            handled, note = slash.dispatch(app, "/provider muse")
        assert handled is True
        assert "Already using profile 'muse'" in note
