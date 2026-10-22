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


# ==================== 4. HTML export copies only referenced media ====================


class TestHTMLCopiesOnlyReferencedMedia:
    @pytest.fixture
    def db_two_images(self, tmp_path):
        db = tmp_path / "db"
        (db / "media").mkdir(parents=True)
        (db / "media" / "a.png").write_bytes(b"A")
        (db / "media" / "b.png").write_bytes(b"B")
        (db / "media" / "unrelated.png").write_bytes(b"U")
        conv_a = _conv_with_image("conv-a", "media/a.png")
        conv_b = _conv_with_image("conv-b", "media/b.png")
        return db, conv_a, conv_b

    def test_multi_file_export(self, db_two_images, tmp_path):
        from ctk.exporters.html import HTMLExporter

        db, conv_a, _ = db_two_images
        out = tmp_path / "out"
        HTMLExporter().export_to_file([conv_a], str(out), embed=False, db_dir=str(db))
        assert sorted(p.name for p in (out / "media").iterdir()) == ["a.png"]

    def test_media_dir_export(self, db_two_images, tmp_path):
        from ctk.exporters.html import HTMLExporter

        db, conv_a, _ = db_two_images
        out = tmp_path / "out"
        HTMLExporter().export_to_file(
            [conv_a], str(out / "index.html"), db_dir=str(db), media_dir="assets"
        )
        assert sorted(p.name for p in (out / "assets").iterdir()) == ["a.png"]

    def test_bare_filename_ref_is_copied(self, tmp_path):
        from ctk.exporters.html import HTMLExporter

        db = tmp_path / "db"
        (db / "media").mkdir(parents=True)
        (db / "media" / "a.png").write_bytes(b"A")
        (db / "media" / "b.png").write_bytes(b"B")
        out = tmp_path / "out"
        HTMLExporter().export_to_file(
            [_conv_with_image("c", "a.png")], str(out), embed=False, db_dir=str(db)
        )
        assert sorted(p.name for p in (out / "media").iterdir()) == ["a.png"]

    def test_outside_refs_are_not_copied(self, db_with_secret, tmp_path):
        from ctk.exporters.html import HTMLExporter

        db, secret = db_with_secret
        out = tmp_path / "out"
        convs = [
            _conv_with_image(f"c{i}", _outside_ref(kind, secret))
            for i, kind in enumerate(_OUTSIDE_REFS)
        ]
        HTMLExporter().export_to_file(convs, str(out), embed=False, db_dir=str(db))
        assert list((out / "media").iterdir()) == []


# ==================== 5. Stored XSS in the HTML export ====================

_XSS_PAYLOADS = [
    "</SCRIPT><img src=x onerror=alert(1)>",
    "</script ><svg onload=alert(1)>",
    "</ScRiPt\t>",
    "<!--<script>alert(1)</script>",
    "a & b   c   d",
]


def _js_function(js: str, name: str) -> str:
    """Slice a top-level ``function name(...) {...}`` out of the embedded JS."""
    start = js.index(f"function {name}(")
    end = js.index("\n}\n", start) + 3
    return js[start:end]


def _run_node(script: str) -> str:
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    result = subprocess.run(
        [node, "-e", script], capture_output=True, text=True, timeout=30, check=True
    )
    return result.stdout


class TestScriptEmbeddingEscapes:
    @pytest.fixture
    def html(self):
        from ctk.exporters.html import HTMLExporter

        convs = []
        for i, payload in enumerate(_XSS_PAYLOADS):
            conv = _conv_with_image(f"c{i}", None, title=payload, text=payload)
            conv.metadata.tags = [payload]
            conv.metadata.source = payload
            convs.append(conv)
        return HTMLExporter().export_conversations(convs, embed=True)

    @staticmethod
    def _embedded(html, marker):
        import json

        idx = html.index(marker) + len(marker)
        obj, end = json.JSONDecoder().raw_decode(html, idx)
        return obj, html[idx:end]

    @pytest.mark.parametrize(
        "marker", ["const CONVERSATIONS = ", "const STATS = "], ids=["convs", "stats"]
    )
    def test_no_markup_characters_in_embedded_json(self, html, marker):
        _, raw = self._embedded(html, marker)
        for ch in ("<", ">", "&", " ", " "):
            assert ch not in raw

    def test_embedded_json_round_trips(self, html):
        convs, _ = self._embedded(html, "const CONVERSATIONS = ")
        assert [c["title"] for c in convs] == _XSS_PAYLOADS
        assert [c["messages"][0]["content"] for c in convs] == _XSS_PAYLOADS
        stats, _ = self._embedded(html, "const STATS = ")
        assert set(stats["tags"]) == set(_XSS_PAYLOADS)

    def test_payload_cannot_close_the_script(self, html):
        lowered = html.lower()
        assert "<img src=x onerror" not in lowered
        assert "<svg onload" not in lowered


class TestMarkdownSanitizer:
    @pytest.fixture
    def js(self):
        from ctk.exporters.html import HTMLExporter

        return HTMLExporter()._get_javascript()

    def test_dompurify_is_loaded_pinned_with_sri(self):
        from ctk.exporters.html import HTMLExporter

        html = HTMLExporter().export_conversations([], embed=True)
        assert (
            "https://cdn.jsdelivr.net/npm/dompurify@3.4.16/dist/purify.min.js" in html
        )
        assert (
            'integrity="sha384-a7SzOxErzJ3ZpQz0zJ32d67dSitNzPcbfybc/ykU9KJhMgZkwqfSxlhhdJRS+XGL"'
            in html
        )
        # marked is the other script that touches message markup: pin it too.
        assert (
            'integrity="sha384-zbcZAIxlvJtNE3Dp5nxLXdXtXyxwOdnILY1TDPVmKFhl4r4nSUG1r8bcFXGVa4Te"'
            in html
        )

    def test_marked_output_goes_through_dompurify(self, js):
        body = _js_function(js, "processMessageContent")
        assert "DOMPurify.sanitize(" in body
        assert "marked.parse(" in body

    def _harness(self, js, purify_stub):
        return "\n".join(
            [
                "const marked = { parse: s => s };",  # worst case: raw HTML passes through
                purify_stub,
                _js_function(js, "escapeHtml"),
                _js_function(js, "plainTextToHtml"),
                _js_function(js, "processMessageContent"),
            ]
        )

    def test_without_dompurify_falls_back_to_escaping(self, js):
        import json

        script = self._harness(js, "") + "\nconsole.log(JSON.stringify(%s));" % (
            "processMessageContent("
            + json.dumps("<img src=x onerror=alert(1)>\nhi")
            + ")"
        )
        out = json.loads(_run_node(script))
        assert "<img" not in out
        assert "&lt;img" in out

    def test_with_dompurify_sanitize_wraps_output(self, js):
        import json

        stub = "const DOMPurify = { sanitize: s => 'SANITIZED[' + s + ']' };"
        script = self._harness(js, stub) + "\nconsole.log(JSON.stringify(%s));" % (
            "processMessageContent('hello <b>x</b>')"
        )
        out = json.loads(_run_node(script))
        assert out.startswith("SANITIZED[") and out.endswith("]")

    def test_restored_math_is_escaped_and_literal(self, js):
        import json

        stub = "const DOMPurify = { sanitize: s => s };"
        texts = ["$<img src=x onerror=alert(1)>$", "$$a + b$$", "x $$c$$ y"]
        script = self._harness(js, stub) + "\nconsole.log(JSON.stringify(%s));" % (
            json.dumps(texts) + ".map(processMessageContent)"
        )
        out = json.loads(_run_node(script))
        assert "<img" not in out[0] and "&lt;img" in out[0]
        # "$$" must survive verbatim (no String.replace "$" pattern expansion).
        assert "$$a + b$$" in out[1]
        assert "$$c$$" in out[2]


class TestEscapeHtml:
    def test_escapes_quotes_and_markup(self):
        import json

        from ctk.exporters.html import HTMLExporter

        js = HTMLExporter()._get_javascript()
        calls = "[escapeHtml(%s), escapeHtml(null), escapeHtml(5)]" % json.dumps(
            "\"'<>&"
        )
        script = (
            _js_function(js, "escapeHtml") + f"\nconsole.log(JSON.stringify({calls}));"
        )
        out = json.loads(_run_node(script))
        assert out == ["&quot;&#39;&lt;&gt;&amp;", "", "5"]

    def test_escape_html_does_not_need_a_dom(self):
        from ctk.exporters.html import HTMLExporter

        body = _js_function(HTMLExporter()._get_javascript(), "escapeHtml")
        assert "document" not in body


class TestMediaGalleryAttributes:
    def test_gallery_builds_attributes_via_dom(self):
        from ctk.exporters.html import HTMLExporter

        body = _js_function(HTMLExporter()._get_javascript(), "renderMediaGallery")
        assert 'src="${' not in body
        assert 'data-conv-id="${' not in body
        assert 'alt="${' not in body
        assert "innerHTML = `" not in body

    def test_load_error_message_is_escaped(self):
        from ctk.exporters.html import HTMLExporter

        loader = HTMLExporter()._get_jsonl_loader()
        assert "${error.message}" not in loader
        assert "escapeHtml(error.message)" in loader
