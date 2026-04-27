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


def resolve_image_path(
    media: MediaContent,
    media_root: Optional[str] = None,
) -> Optional[str]:
    """Best-effort resolution of a MediaContent to a local file path.

    Resolution order:
      1. ``media.path`` if it points at an existing file.
      2. ``media.data`` (base64) decoded to a temp file.
      3. ``media.url`` if it looks like a relative file path (no
         ``http://`` / ``https://`` scheme), resolved against
         ``media_root`` first, then ``cwd``. ChatGPT exports use
         relative URLs like ``media/aa88…webp`` pointing into a
         sibling ``media/`` directory next to the export's
         ``conversations.json``; on import we copy that path
         verbatim, so we need to find the file at view time.
      4. None for true remote URLs (we don't fetch on the UI thread).

    Args:
        media: The MediaContent to resolve.
        media_root: Directory to resolve relative URLs against. Usually
            the database's parent directory, since exports are
            typically extracted next to the DB.
    """
    if media.path and os.path.isfile(media.path):
        return media.path
    if media.data:
        return _write_data_to_tempfile(media.data, media.mime_type)
    if media.url:
        # Treat http(s) as truly remote — AutoImage doesn't fetch and
        # we won't either, so caption-only is the right call there.
        if media.url.startswith(("http://", "https://", "data:")):
            return None
        # Anything else is a (possibly relative) local file reference.
        # Try the configured media_root first, then cwd as a fallback.
        candidates = []
        if media_root:
            candidates.append(os.path.join(media_root, media.url))
        candidates.append(media.url)
        for candidate in candidates:
            expanded = os.path.expanduser(candidate)
            if os.path.isfile(expanded):
                return expanded
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

    # Default size for the inline image area.
    #
    # textual-image's BaseImage maps CSS to its ImageSize as follows:
    # an integer or ``1fr`` becomes a literal cell count (NO aspect
    # preservation — both dimensions are honoured exactly), but the
    # special value ``auto`` lets ImageSize compute that dimension
    # from the source's pixel aspect ratio and the terminal's cell
    # aspect. So we set ``height: 24`` to fix the visual size and
    # leave ``width: auto`` so square / wide / tall sources all
    # render with correct proportions, capped at the container width
    # to avoid horizontal overflow.
    DEFAULT_CSS = """
    InlineImage {
        height: auto;
        margin: 0 0 1 2;
    }
    InlineImage .image-content {
        height: 24;
        width: auto;
        max-width: 100%;
    }
    InlineImage .image-caption {
        color: $text-muted;
        text-style: italic;
        padding: 0 1;
    }
    """

    def __init__(
        self, media: MediaContent, media_root: Optional[str] = None
    ) -> None:
        super().__init__(classes="message-image")
        self._media = media
        self._path = resolve_image_path(media, media_root=media_root)

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


def build_image_widgets(
    media_list: List[MediaContent],
    media_root: Optional[str] = None,
) -> List[Widget]:
    """Translate every MediaContent into an InlineImage widget.

    ``media_root`` is forwarded to ``resolve_image_path`` so relative
    URLs in ChatGPT exports resolve against the export root rather
    than ``cwd``. Returning a flat list (rather than a single
    container) keeps the message view's mount loop simple — caller
    just appends each widget after the bubble.
    """
    return [InlineImage(media, media_root=media_root) for media in media_list]
