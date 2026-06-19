# tests/unit/test_resolve_tui_db_path.py
import argparse
import pytest

import ctk.cli as cli

pytestmark = pytest.mark.unit


def test_explicit_db_skips_discovery(monkeypatch, tmp_path):
    called = {"n": 0}
    monkeypatch.setattr(
        cli,
        "discover_ctk_databases",
        lambda *a, **k: (called.__setitem__("n", called["n"] + 1) or []),
    )
    args = argparse.Namespace(db=str(tmp_path))
    out = cli._resolve_tui_db_path(args)
    assert out == str(tmp_path)
    assert called["n"] == 0  # discovery not called on the fast path


def test_no_db_non_tty_keeps_error(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    # No configured default
    monkeypatch.setattr(
        cli,
        "get_config",
        lambda: type("C", (), {"config": {}})(),
        raising=False,
    )
    args = argparse.Namespace(db=None)
    out = cli._resolve_tui_db_path(args)
    assert out == 1  # unchanged non-interactive error exit


def test_no_db_tty_uses_picked_path(monkeypatch):
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(
        cli,
        "get_config",
        lambda: type("C", (), {"config": {}})(),
        raising=False,
    )
    monkeypatch.setattr(cli, "discover_ctk_databases", lambda *a, **k: ["/picked/db"])
    monkeypatch.setattr(
        cli, "_offer_database_choice", lambda cands, default: "/picked/db"
    )
    args = argparse.Namespace(db=None)
    out = cli._resolve_tui_db_path(args)
    assert out == "/picked/db"
