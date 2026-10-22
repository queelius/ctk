"""Regression tests: config defaults stay pristine; bad files are never clobbered (2.20.1)."""

import copy
import json
from argparse import Namespace

import pytest

import ctk.core.config as config_module
from ctk.core.config import Config

pytestmark = pytest.mark.unit

USER = {"providers": {"default": "muse", "muse": {"base_url": "http://m/v1"}}}


@pytest.fixture
def pristine_defaults():
    snapshot = copy.deepcopy(Config.DEFAULTS)
    yield snapshot
    Config.DEFAULTS.clear()
    Config.DEFAULTS.update(snapshot)  # undo any leak so other tests stay isolated


def _write(path, data):
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


def test_loading_user_config_leaves_defaults_untouched(tmp_path, pristine_defaults):
    Config(_write(tmp_path / "c.json", USER))
    assert Config.DEFAULTS == pristine_defaults


def test_second_config_does_not_inherit_first_users_values(tmp_path, pristine_defaults):
    Config(_write(tmp_path / "a.json", USER))
    other = Config(_write(tmp_path / "b.json", {}))
    assert other.get("providers.muse") is None


def test_reset_restores_defaults_after_user_config(
    tmp_path, monkeypatch, pristine_defaults
):
    from ctk.cli_config import cmd_reset

    path = _write(tmp_path / "c.json", USER)
    monkeypatch.setattr(config_module, "_config", Config(path))

    assert cmd_reset(Namespace(force=True, section=None)) == 0

    assert "muse" not in json.loads(path.read_text())["providers"]


@pytest.mark.parametrize("bad", ["{not json", '{"providers": ', "[]"])
def test_unparseable_file_is_not_overwritten_by_set(tmp_path, bad):
    path = _write(tmp_path / "c.json", bad)
    config = Config(path)

    with pytest.raises(ValueError, match="failed to load"):
        config.set("tagging.max_tags", 3)

    assert path.read_text() == bad


def test_set_through_a_scalar_raises_value_error(tmp_path):
    path = _write(tmp_path / "c.json", {"database": {"default_path": "~/x"}})
    config = Config(path)
    before = path.read_text()

    with pytest.raises(ValueError, match="default_path"):
        config.set("database.default_path.c", 1)

    assert path.read_text() == before


def test_cli_set_reports_refusal_instead_of_crashing(tmp_path, monkeypatch, capsys):
    from ctk.cli_config import cmd_set

    path = _write(tmp_path / "c.json", "{not json")
    monkeypatch.setattr(config_module, "_config", Config(path))

    assert cmd_set(Namespace(key="tagging.max_tags", value="3")) == 1
    assert "refusing to overwrite" in capsys.readouterr().err
