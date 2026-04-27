"""Inline image rendering for the Textual TUI.

Wraps ``textual-image`` so the rest of the TUI doesn't need to know
about temp-file handling or the three different ways an image can be
attached to a message (URL, local path, base64 data).

``textual_image.widget.AutoImage`` auto-detects the terminal protocol
on construction (Sixel for foot/wezterm/mlterm, TGP for Kitty/Ghostty,
Halfcell for everything else) so callers just hand it a path and get
the best rendering the terminal supports.
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import tempfile
from typing import List, Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from ctk.core.models import MediaContent

logger = logging.getLogger(__name__)


# Track temp files we wrote out for base64 images so we can clean them
# up at app exit. Module-global because images outlive the messages
# that mount them (Textual won't tell us when a widget is gc'd).
_TEMP_PATHS: List[str] = []


def _write_data_to_tempfile(data: str, mime_type: Optional[str]) -> Optional[str]:
    """Decode a base64 image into a temp file and return its path.

    Returns ``None`` if the data is not valid base64 — we'd rather
    skip rendering than crash the whole message view.
    """
    try:
        raw = base64.b64decode(data, validate=False)
    except (binascii.Error, ValueError) as exc:
        logger.warning("Skipping image: invalid base64 (%s)", exc)
        return None

    suffix = _suffix_for_mime(mime_type)
    fd, path = tempfile.mkstemp(prefix="ctk-tui-img-", suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
    except OSError as exc:
        logger.warning("Skipping image: could not write temp file (%s)", exc)
        return None
    _TEMP_PATHS.append(path)
    return path


def _suffix_for_mime(mime_type: Optional[str]) -> str:
    if not mime_type:
        return ".png"
    mt = mime_type.lower().strip()
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }.get(mt, ".png")


def cleanup_temp_files() -> None:
    """Best-effort cleanup of every temp file we wrote.

    Called on app shutdown. Failures are logged and swallowed —
    leaving a temp file behind is annoying but never user-visible.
    """
    while _TEMP_PATHS:
        path = _TEMP_PATHS.pop()
        try:
            os.unlink(path)
        except OSError as exc:
            logger.debug("Could not unlink temp image %s: %s", path, exc)


def resolve_image_path(media: MediaContent) -> Optional[str]:
    """Best-effort resolution of a MediaContent to a local file path.

    Returns:
        - ``media.path`` if it's an existing local file
        - A freshly-written temp path if ``media.data`` (base64) is set
        - ``None`` for remote URLs (we don't download — that's the user's
          terminal's job if it supports it; AutoImage doesn't fetch)
        - ``None`` if everything fails
    """
    if media.path and os.path.isfile(media.path):
        return media.path
    if media.data:
        return _write_data_to_tempfile(media.data, media.mime_type)
    # Remote URLs aren't downloaded — not worth a sync HTTP fetch on
    # the UI thread for a feature most users will only sometimes use.
    # Fall back to the caption widget so the user at least sees what
    # was attached.
    return None


def _fallback_label(media: MediaContent) -> str:
    if media.caption:
        return media.caption
    if media.url:
        return f"[image] {media.url}"
    if media.path:
        return f"[image] {media.path}"
    if media.data:
        return f"[image] (embedded {media.mime_type or 'image'})"
    return "[image]"


class InlineImage(Vertical):
    """A single image attachment rendered inline below a message.

    Composed of an ``AutoImage`` (when we can resolve a local file)
    plus a caption/fallback line. We always emit the caption — if the
    image fails to render, the user still sees what was attached.

    Falls back to caption-only when:
      - the source is a remote URL we won't fetch synchronously
      - base64 decode fails
      - AutoImage raises during construction
    """

    DEFAULT_CSS = """
    InlineImage {
        height: auto;
        margin: 0 0 1 2;
    }
    InlineImage .image-caption {
        color: $text-muted;
        text-style: italic;
        padding: 0 1;
    }
    """

    def __init__(self, media: MediaContent) -> None:
        super().__init__(classes="message-image")
        self._media = media
        self._path = resolve_image_path(media)

    def compose(self) -> ComposeResult:
        # Lazy import so this module stays cheap when no images appear.
        from textual_image.widget import AutoImage

        if self._path is not None:
            try:
                yield AutoImage(self._path, classes="image-content")
            except Exception as exc:
                # Some renderers raise if the file isn't a real image,
                # or if PIL can't decode it. Log once and fall through
                # to the caption line below.
                logger.warning(
                    "Image render failed for %s: %s", self._path, exc
                )
        yield Static(_fallback_label(self._media), classes="image-caption")


def build_image_widgets(media_list: List[MediaContent]) -> List[Widget]:
    """Translate every MediaContent into an InlineImage widget.

    Returning a flat list (rather than a single container) keeps the
    message view's mount loop simple — caller just appends each widget
    after the bubble.
    """
    return [InlineImage(media) for media in media_list]
