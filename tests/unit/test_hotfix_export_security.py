"""Regression tests for the 2.20.1 export/import security hotfix.

Covers path containment for media references and conversation ids
(file exfiltration and path traversal via crafted import files) and stored
XSS in the HTML exporter.
"""

import pytest

from ctk.core.paths import (
    is_safe_component,
    is_within,
    resolve_media_ref,
    safe_component,
    safe_join,
)

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
        assert (
            safe_join(tmp_path, "sub/a.png") == (tmp_path / "sub" / "a.png").resolve()
        )

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

    def test_is_safe_component(self):
        assert is_safe_component("file-abc_123.png")
        for bad in ("", "..", ".x", "a/b", "a\\b", "*", None):
            assert not is_safe_component(bad)


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
        assert (
            resolve_media_ref(db_dir, "media/img.png")
            == (db_dir / "media" / "img.png").resolve()
        )

    def test_bare_filename_ref(self, db_dir):
        assert (
            resolve_media_ref(db_dir, "img.png")
            == (db_dir / "media" / "img.png").resolve()
        )

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


# ==================== Shared fixtures for exporter tests ====================


def _conv_with_image(conv_id, image_url, title="Conv", text="hello"):
    from ctk.core.models import (
        ConversationMetadata,
        ConversationTree,
        Message,
        MessageContent,
        MessageRole,
    )

    conv = ConversationTree(
        id=conv_id,
        title=title,
        metadata=ConversationMetadata(created_at=None, updated_at=None),
    )
    content = MessageContent(text=text)
    if image_url is not None:
        content.add_image(url=image_url)
    conv.add_message(
        Message(id=f"{conv_id}-m1", role=MessageRole.USER, content=content)
    )
    return conv


@pytest.fixture
def db_with_secret(tmp_path):
    """A DB dir with one legit media file, plus a secret outside media/."""
    db = tmp_path / "db"
    (db / "media").mkdir(parents=True)
    (db / "media" / "ok.png").write_bytes(b"OKPNG")
    (db / "conversations.db").write_bytes(b"SQLITE-DB-CONTENTS")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET")
    return db, secret


def _b64(raw: bytes) -> str:
    import base64

    return base64.b64encode(raw).decode()


# ==================== 2. File exfiltration via crafted imports ====================


class TestOpenAIAssetPointerContainment:
    @pytest.fixture
    def importer(self, tmp_path):
        from ctk.importers.openai import OpenAIImporter

        export = tmp_path / "export"
        export.mkdir()
        media = tmp_path / "db" / "media"
        media.mkdir(parents=True)
        (tmp_path / "secret-key.txt").write_text("TOP-SECRET")
        imp = OpenAIImporter()
        imp.source_dir = str(export)
        imp.media_dir = str(media)
        return imp, export, media

    def test_legit_asset_is_copied(self, importer):
        imp, export, media = importer
        (export / "file-abc-photo.png").write_bytes(b"PNG")
        assert imp._resolve_and_copy_image("file-service://file-abc") is not None
        assert [p.read_bytes() for p in media.iterdir()] == [b"PNG"]

    def test_legit_dalle_asset_is_copied(self, importer):
        imp, export, media = importer
        (export / "dalle-generations").mkdir()
        (export / "dalle-generations" / "file-abc-uuid.webp").write_bytes(b"WEBP")
        assert imp._resolve_and_copy_image("file-service://abc") is not None
        assert [p.read_bytes() for p in media.iterdir()] == [b"WEBP"]

    @pytest.mark.parametrize(
        "url",
        [
            "file-service://../secret",
            "file-service://../secret-key.txt",
            "file-service://..",
            "file-service:///etc/passwd",
            "file-service://sub/../../secret",
            "file-service://..\\secret",
            "file-service://",
        ],
    )
    def test_traversal_ids_are_rejected(self, importer, url):
        imp, export, media = importer
        assert imp._resolve_and_copy_image(url) is None
        assert list(media.iterdir()) == []

    def test_glob_metacharacters_are_literal(self, importer):
        imp, export, media = importer
        (export / "file-abc-photo.png").write_bytes(b"PNG")
        for url in (
            "file-service://*",
            "file-service://file-?bc",
            "file-service://[f]ile-abc",
        ):
            assert imp._resolve_and_copy_image(url) is None
        assert list(media.iterdir()) == []

    def test_symlink_in_export_pointing_outside_is_rejected(self, importer, tmp_path):
        imp, export, media = importer
        (export / "file-abc-photo.png").symlink_to(tmp_path / "secret-key.txt")
        assert imp._resolve_and_copy_image("file-service://file-abc") is None
        assert list(media.iterdir()) == []

    def test_symlinked_dalle_dir_pointing_outside_is_rejected(self, importer, tmp_path):
        imp, export, media = importer
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "file-abc-x.png").write_bytes(b"STOLEN")
        (export / "dalle-generations").symlink_to(outside)
        assert imp._resolve_and_copy_image("file-service://file-abc") is None
        assert list(media.iterdir()) == []


_OUTSIDE_REFS = ["absolute", "dotdot", "db_file"]


def _outside_ref(kind, secret):
    return {
        "absolute": str(secret),
        "dotdot": "../secret.txt",
        "db_file": "conversations.db",
    }[kind]


class TestHTMLImageContainment:
    @pytest.mark.parametrize("ref_kind", _OUTSIDE_REFS)
    def test_refs_outside_media_are_not_embedded(self, db_with_secret, ref_kind):
        from ctk.exporters.html import HTMLExporter

        db, secret = db_with_secret
        html = HTMLExporter().export_conversations(
            [_conv_with_image("c1", _outside_ref(ref_kind, secret))],
            embed=True,
            db_dir=str(db),
        )
        assert _b64(b"TOP-SECRET") not in html
        assert _b64(b"SQLITE-DB-CONTENTS") not in html

    def test_media_ref_is_still_embedded(self, db_with_secret):
        from ctk.exporters.html import HTMLExporter

        db, _ = db_with_secret
        for ref in ("media/ok.png", "ok.png"):
            html = HTMLExporter().export_conversations(
                [_conv_with_image("c1", ref)], embed=True, db_dir=str(db)
            )
            assert _b64(b"OKPNG") in html


class TestHugoImageContainment:
    @pytest.mark.parametrize("ref_kind", _OUTSIDE_REFS)
    def test_refs_outside_media_are_not_copied(
        self, db_with_secret, tmp_path, ref_kind
    ):
        from ctk.exporters.hugo import HugoExporter

        db, secret = db_with_secret
        out = tmp_path / "site"
        HugoExporter().export_to_file(
            [_conv_with_image("c1", _outside_ref(ref_kind, secret))],
            str(out),
            db_dir=str(db),
            hugo_organize="none",
        )
        copied = [p for p in out.rglob("*") if p.is_file() and p.name != "index.md"]
        assert copied == []

    def test_media_ref_is_still_copied(self, db_with_secret, tmp_path):
        from ctk.exporters.hugo import HugoExporter

        db, _ = db_with_secret
        out = tmp_path / "site"
        HugoExporter().export_to_file(
            [_conv_with_image("c1", "media/ok.png")],
            str(out),
            db_dir=str(db),
            hugo_organize="none",
        )
        assert [p.read_bytes() for p in out.rglob("*.png")] == [b"OKPNG"]


# ==================== 3. Path traversal via conversation ids ====================

_EVIL_IDS = ["../../escape", "/abs/x", "..", "a/../../../b", "..\\..\\win"]


def _all_files(root):
    return [p for p in root.rglob("*") if p.is_file()]


class TestEchoConversationIdTraversal:
    @pytest.mark.parametrize("conv_id", _EVIL_IDS)
    def test_evil_id_stays_inside_conversations_dir(self, tmp_path, conv_id):
        import json

        from ctk.exporters.echo import ECHOExporter

        root = tmp_path / "jail"
        root.mkdir()
        out = root / "out"
        ECHOExporter().export_to_directory([_conv_with_image(conv_id, None)], str(out))

        # Nothing was written outside the output directory.
        assert all(out.resolve() in p.resolve().parents for p in _all_files(tmp_path))
        conv_jsons = list(out.rglob("conversation.json"))
        assert len(conv_jsons) == 1
        # The conversation directory is a direct child of conversations/.
        assert conv_jsons[0].parent.parent == out / "conversations"
        # The index points at the directory that was actually written.
        index = json.loads((out / "index.json").read_text())
        entry = index["conversations"][0]
        assert entry["id"] == conv_id
        assert (out / entry["path"]).resolve() == conv_jsons[0].parent.resolve()

    def test_normal_id_unchanged(self, tmp_path):
        from ctk.exporters.echo import ECHOExporter

        out = tmp_path / "out"
        cid = "8f14e45f-ceea-467f-a0e6-3a1f1b5b6d1a"
        ECHOExporter().export_to_directory([_conv_with_image(cid, None)], str(out))
        assert (out / "conversations" / cid / "conversation.json").is_file()


class TestHugoConversationIdTraversal:
    @pytest.mark.parametrize("title", ["!!!", "Some Title", None])
    @pytest.mark.parametrize("conv_id", _EVIL_IDS)
    def test_evil_id_stays_inside_output_dir(self, tmp_path, conv_id, title):
        from ctk.exporters.hugo import HugoExporter

        root = tmp_path / "jail"
        root.mkdir()
        out = root / "site"
        HugoExporter().export_to_file(
            [_conv_with_image(conv_id, None, title=title)],
            str(out),
            hugo_organize="none",
        )
        assert all(out.resolve() in p.resolve().parents for p in _all_files(tmp_path))
        bundles = list(out.rglob("index.md"))
        assert len(bundles) == 1
        # The bundle is a direct child of the output directory.
        assert bundles[0].parent.parent == out

    def test_normal_slug_unchanged(self, tmp_path):
        from ctk.exporters.hugo import HugoExporter

        out = tmp_path / "site"
        HugoExporter().export_to_file(
            [_conv_with_image("a1b2c3d4-e5f6", None, title="Hello World")],
            str(out),
            hugo_organize="none",
        )
        assert (out / "hello-world-a1b2c3d4" / "index.md").is_file()
