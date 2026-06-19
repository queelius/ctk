import builtins
import pytest

from ctk.cli import _offer_database_choice

pytestmark = pytest.mark.unit


def _force_tty(monkeypatch, is_tty=True):
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: is_tty, raising=False)


def test_non_tty_returns_none(monkeypatch):
    _force_tty(monkeypatch, is_tty=False)
    assert _offer_database_choice(["/a/db"], "/home/u/.ctk") is None


def test_pick_number_returns_candidate(monkeypatch):
    _force_tty(monkeypatch)
    monkeypatch.setattr(builtins, "input", lambda *a: "1")
    assert _offer_database_choice(["/a/db", "/b/db"], "/home/u/.ctk") == "/a/db"


def test_pick_n_returns_default(monkeypatch):
    _force_tty(monkeypatch)
    monkeypatch.setattr(builtins, "input", lambda *a: "n")
    assert _offer_database_choice(["/a/db"], "/home/u/.ctk") == "/home/u/.ctk"


def test_empty_returns_none(monkeypatch):
    _force_tty(monkeypatch)
    monkeypatch.setattr(builtins, "input", lambda *a: "")
    assert _offer_database_choice(["/a/db"], "/home/u/.ctk") is None
