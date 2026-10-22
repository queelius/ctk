"""Regression tests for the 2.20.1 export/import security hotfix.

Covers path containment for media references and conversation ids
(file exfiltration and path traversal via crafted import files) and stored
XSS in the HTML exporter.
"""

import os
from pathlib import Path

import pytest

from ctk.core.paths import is_within, resolve_media_ref, safe_component, safe_join

pytestmark = pytest.mark.unit


# ==================== 1. Path-safety helpers ====================


class TestIsWithin:
    def test_child_is_within(self, tmp_path):
        assert is_within(tmp_path, tmp_path / "a" / "b")

    def test_base_itself_is_not_strictly_within(self, tmp_path):
        assert not is_within(tmp_path, tmp_path)

    def test_sibling_is_not_within(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        assert not is_within(base, tmp_path / "base-evil" / "x")

    def test_dotdot_escape_is_not_within(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        assert not is_within(base, base / ".." / "x")


class TestSafeJoin:
    def test_plain_relative_ref(self, tmp_path):
        (tmp_path / "a.png").write_bytes(b"x")
        assert safe_join(tmp_path, "a.png") == (tmp_path / "a.png").resolve()

    def test_nested_relative_ref(self, tmp_path):
        assert safe_join(tmp_path, "sub/a.png") == (tmp_path / "sub" / "a.png").resolve()

    def test_rejects_absolute(self, tmp_path):
        assert safe_join(tmp_path, "/etc/passwd") is None

    def test_rejects_absolute_even_inside_base(self, tmp_path):
        # An absolute ref is never a reference *relative* to base.
        assert safe_join(tmp_path, str(tmp_path / "a.png")) is None

    def test_rejects_dotdot_escape(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        assert safe_join(base, "../secret.txt") is None
        assert safe_join(base, "sub/../../secret.txt") is None

    def test_rejects_backslash_dotdot_escape(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        assert safe_join(base, "..\\secret.txt") is None

    def test_rejects_windows_drive(self, tmp_path):
        assert safe_join(tmp_path, "C:\\Windows\\win.ini") is None

    def test_dotdot_staying_inside_is_allowed(self, tmp_path):
        assert safe_join(tmp_path, "sub/../a.png") == (tmp_path / "a.png").resolve()

    def test_rejects_empty_and_base_itself(self, tmp_path):
        assert safe_join(tmp_path, "") is None
        assert safe_join(tmp_path, ".") is None

    def test_rejects_nul(self, tmp_path):
        assert safe_join(tmp_path, "a\x00.png") is None

    def test_rejects_symlink_pointing_outside(self, tmp_path):
        base = tmp_path / "base"
        base.mkdir()
        outside = tmp_path / "secret.txt"
        outside.write_text("secret")
        (base / "link.png").symlink_to(outside)
        assert safe_join(base, "link.png") is None

    def test_accepts_symlink_pointing_inside(self, tmp_path):
        (tmp_path / "real.png").write_bytes(b"x")
        (tmp_path / "link.png").symlink_to(tmp_path / "real.png")
        assert safe_join(tmp_path, "link.png") == (tmp_path / "real.png").resolve()


class TestSafeComponent:
    @pytest.mark.parametrize(
        "name",
        ["abc-123", "8f14e45f-ceea-467f-a0e6-3a1f1b5b6d1a", "conv_1", "a.b"],
    )
    def test_safe_names_unchanged(self, name):
        assert safe_component(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "../../escape",
            "/abs/x",
            "..",
            ".",
            ".hidden",
            "a/b",
            "a\\b",
            "a\x00b",
            "",
            "   ",
            "C:evil",
        ],
    )
    def test_unsafe_names_become_single_component(self, name, tmp_path):
        out = safe_component(name)
        assert out
        assert "/" not in out and "\\" not in out and "\x00" not in out
        assert not out.startswith(".")
        assert out not in (".", "..")
        # Joining it to a base stays a direct child of that base.
        assert (tmp_path / out).resolve().parent == tmp_path.resolve()

    def test_distinct_unsafe_names_do_not_collide(self):
        assert safe_component("a/b") != safe_component("a\\b")
        assert safe_component("../x") != safe_component("./x")

    def test_fallback_used_for_empty(self):
        assert safe_component("", fallback="untitled").startswith("untitled")

    def test_long_names_are_bounded(self):
        assert len(safe_component("x" * 1000).encode("utf-8")) <= 255

    def test_non_string_input(self):
        assert safe_component(None)  # type: ignore[arg-type]


class TestResolveMediaRef:
    @pytest.fixture
    def db_dir(self, tmp_path):
        db = tmp_path / "db"
        (db / "media").mkdir(parents=True)
        (db / "media" / "img.png").write_bytes(b"png")
        (db / "conversations.db").write_bytes(b"sqlite")
        (tmp_path / "secret.txt").write_text("secret")
        return db

    def test_media_prefixed_ref(self, db_dir):
        assert resolve_media_ref(db_dir, "media/img.png") == (
            db_dir / "media" / "img.png"
        ).resolve()

    def test_bare_filename_ref(self, db_dir):
        assert resolve_media_ref(db_dir, "img.png") == (
            db_dir / "media" / "img.png"
        ).resolve()

    @pytest.mark.parametrize(
        "ref",
        [
            "../secret.txt",
            "media/../../secret.txt",
            "media/../conversations.db",
            "conversations.db",
            "/etc/passwd",
            "https://example.com/img.png",
            "data:image/png;base64,AAAA",
            "media/missing.png",
            "",
            None,
        ],
    )
    def test_rejects_refs_outside_media_or_missing(self, db_dir, ref):
        assert resolve_media_ref(db_dir, ref) is None

    def test_rejects_absolute_path_to_real_media_file(self, db_dir):
        assert resolve_media_ref(db_dir, str(db_dir / "media" / "img.png")) is None

    def test_no_db_dir(self):
        assert resolve_media_ref(None, "media/img.png") is None
