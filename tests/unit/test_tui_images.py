"""Tests for inline image rendering in the Textual TUI.

These exercise the resolution + temp-file logic in ``ctk.tui.images``
without booting a real terminal renderer. Actual pixel rendering by
``textual-image`` is the library's responsibility; we test the seams
ctk owns.
"""

from __future__ import annotations

import base64
import os
import uuid
from datetime import datetime

import pytest

from ctk.core.models import (ContentType, ConversationMetadata,
                             ConversationTree, MediaContent, Message,
                             MessageContent, MessageRole)


pytestmark = pytest.mark.unit


# A real 16×16 PNG, large enough that AutoImage's resize-to-viewport
# doesn't divide to zero pixels in the test harness's default
# (80, 24)-cell viewport. A 1×1 PNG triggered ValueError from PIL.
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAF0lEQVR4nGP8z0Aa"
    "YCJR/aiGUQ1DSAMAQC4BH2bjRnMAAAAASUVORK5CYII="
)


# ---------------------------------------------------------------------------
# resolve_image_path
# ---------------------------------------------------------------------------


class TestResolveImagePath:
    def test_existing_local_path_returned_verbatim(self, tmp_path):
        from ctk.tui.images import resolve_image_path

        f = tmp_path / "x.png"
        f.write_bytes(b"fake")  # contents irrelevant for path resolution
        media = MediaContent(type=ContentType.IMAGE, path=str(f))
        assert resolve_image_path(media) == str(f)

    def test_missing_local_path_falls_back_to_none(self, tmp_path):
        from ctk.tui.images import resolve_image_path

        media = MediaContent(
            type=ContentType.IMAGE, path=str(tmp_path / "does-not-exist.png")
        )
        assert resolve_image_path(media) is None

    def test_remote_url_returns_none(self):
        from ctk.tui.images import resolve_image_path

        media = MediaContent(
            type=ContentType.IMAGE, url="https://example.com/foo.png"
        )
        # We don't fetch — that would block the UI thread.
        assert resolve_image_path(media) is None

    def test_base64_data_writes_temp_file(self):
        from ctk.tui.images import _TEMP_PATHS, resolve_image_path

        before = len(_TEMP_PATHS)
        media = MediaContent(
            type=ContentType.IMAGE,
            data=_TINY_PNG_B64,
            mime_type="image/png",
        )
        path = resolve_image_path(media)
        try:
            assert path is not None
            assert os.path.isfile(path)
            assert path.endswith(".png")
            assert len(_TEMP_PATHS) == before + 1
        finally:
            if path and os.path.isfile(path):
                os.unlink(path)
                _TEMP_PATHS.remove(path)

    def test_base64_garbage_returns_none(self):
        from ctk.tui.images import resolve_image_path

        media = MediaContent(
            type=ContentType.IMAGE,
            data="!!!not-base64!!!",
            mime_type="image/png",
        )
        # Garbage decodes to garbage bytes (not a base64 error per se,
        # because the alphabet check is lenient). Either way the path
        # is returned (file exists, just not a real image), and the
        # downstream AutoImage will log + fall back to caption.
        # What we DO assert: no crash.
        path = resolve_image_path(media)
        if path:
            os.unlink(path)
            from ctk.tui.images import _TEMP_PATHS
            if path in _TEMP_PATHS:
                _TEMP_PATHS.remove(path)

    def test_mime_type_picks_extension(self):
        from ctk.tui.images import _suffix_for_mime

        assert _suffix_for_mime("image/png") == ".png"
        assert _suffix_for_mime("image/jpeg") == ".jpg"
        assert _suffix_for_mime("image/webp") == ".webp"
        # Unknown / missing → safe default.
        assert _suffix_for_mime("image/exotic") == ".png"
        assert _suffix_for_mime(None) == ".png"


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


class TestCleanupTempFiles:
    def test_cleanup_removes_tracked_files(self):
        from ctk.tui.images import (_TEMP_PATHS, cleanup_temp_files,
                                    resolve_image_path)

        media = MediaContent(
            type=ContentType.IMAGE,
            data=_TINY_PNG_B64,
            mime_type="image/png",
        )
        path = resolve_image_path(media)
        assert path is not None and os.path.isfile(path)
        cleanup_temp_files()
        assert not os.path.exists(path)
        assert path not in _TEMP_PATHS

    def test_cleanup_swallows_missing_files(self, tmp_path):
        from ctk.tui.images import _TEMP_PATHS, cleanup_temp_files

        # Track a file that we delete out from under cleanup_temp_files.
        f = tmp_path / "ghost.png"
        f.write_bytes(b"x")
        _TEMP_PATHS.append(str(f))
        os.unlink(f)
        # Should not raise.
        cleanup_temp_files()
        assert not _TEMP_PATHS


# ---------------------------------------------------------------------------
# build_image_widgets — integration with Textual
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_message_view_mounts_image_widget(tmp_path):
    """A message with an image attachment mounts an InlineImage below it."""
    from ctk.core.database import ConversationDB
    from ctk.tui.app import CTKApp
    from ctk.tui.images import InlineImage

    # Seed a tree with one message that has one image (local file path).
    image_file = tmp_path / "test.png"
    image_file.write_bytes(base64.b64decode(_TINY_PNG_B64))

    db = ConversationDB(str(tmp_path / "imgs.db"))
    try:
        tree = ConversationTree(
            id=str(uuid.uuid4()),
            title="image test",
            metadata=ConversationMetadata(
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        )
        content = MessageContent(text="here's a picture")
        content.images.append(
            MediaContent(
                type=ContentType.IMAGE,
                path=str(image_file),
                mime_type="image/png",
                caption="test pic",
            )
        )
        msg = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.USER,
            content=content,
            timestamp=datetime.now(),
        )
        tree.add_message(msg)
        db.save_conversation(tree)

        app = CTKApp(db=db, provider=None)
        async with app.run_test() as pilot:
            await pilot.pause()
            app._open_selected()
            await pilot.pause()
            # Among the children of the message view, at least one
            # should be an InlineImage we mounted ourselves.
            kinds = [type(c).__name__ for c in app.main.messages.children]
            assert "InlineImage" in kinds, (
                f"expected InlineImage in mounted widgets, got: {kinds}"
            )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_message_view_with_no_images_mounts_no_inline_image(tmp_path):
    """Plain-text messages don't trigger any image widgets (regression guard)."""
    from ctk.core.database import ConversationDB
    from ctk.tui.app import CTKApp

    db = ConversationDB(str(tmp_path / "no-imgs.db"))
    try:
        tree = ConversationTree(
            id=str(uuid.uuid4()),
            title="text-only",
            metadata=ConversationMetadata(
                created_at=datetime.now(),
                updated_at=datetime.now(),
            ),
        )
        msg = Message(
            id=str(uuid.uuid4()),
            role=MessageRole.USER,
            content=MessageContent(text="just text"),
            timestamp=datetime.now(),
        )
        tree.add_message(msg)
        db.save_conversation(tree)

        app = CTKApp(db=db, provider=None)
        async with app.run_test() as pilot:
            await pilot.pause()
            app._open_selected()
            await pilot.pause()
            kinds = [type(c).__name__ for c in app.main.messages.children]
            assert "InlineImage" not in kinds
    finally:
        db.close()
