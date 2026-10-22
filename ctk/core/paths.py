"""Path-safety helpers for untrusted references.

Conversation ids, titles, and media references all originate in import files,
which may be crafted. Any time such a value becomes part of a filesystem path,
route it through one of these helpers so it cannot escape the intended
directory (absolute paths, ``..`` segments, or symlinks pointing elsewhere).
"""

import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Optional, Union

PathLike = Union[str, Path]

#: Name of the media directory that lives next to ``conversations.db``.
MEDIA_DIRNAME = "media"

#: Upper bound (in UTF-8 bytes) for a component produced by ``safe_component``,
#: leaving headroom under the usual 255-byte filesystem limit for a collision
#: suffix and caller-added prefixes such as dates.
_MAX_COMPONENT_BYTES = 200

_COMPONENT_EXTRA_CHARS = frozenset("-_.")


def is_within(base: PathLike, path: PathLike) -> bool:
    """Return True if ``path`` resolves to somewhere strictly inside ``base``.

    Both sides are resolved, so symlinks and ``..`` segments are followed
    before the comparison. ``base`` itself is not considered inside.
    """
    base_resolved = Path(base).resolve()
    return base_resolved in Path(path).resolve().parents


def safe_join(base: PathLike, ref: str) -> Optional[Path]:
    """Join an untrusted relative reference onto ``base``, or return None.

    Returns the resolved path only if it lies strictly inside ``base``.
    Absolute references (POSIX or Windows, including drive-relative ones),
    empty references, NUL bytes, and anything that resolves outside ``base``
    (via ``..`` or a symlink) are rejected. Backslashes are treated as
    separators so Windows-style ``..\\`` escapes are caught too.
    """
    if not isinstance(ref, str) or not ref or "\x00" in ref:
        return None
    windows = PureWindowsPath(ref)
    if windows.drive or windows.root:
        return None
    normalized = ref.replace("\\", "/")
    if PurePosixPath(normalized).is_absolute():
        return None
    candidate = (Path(base).resolve() / normalized).resolve()
    return candidate if is_within(base, candidate) else None


def safe_component(name: Optional[str], fallback: str = "item") -> str:
    """Turn an arbitrary id or title into one safe path component.

    Characters other than letters, digits, ``-``, ``_`` and ``.`` become
    ``_``; leading dots are stripped (no ``.``, ``..`` or hidden names); the
    result is bounded in length. Safe names pass through unchanged. When the
    name had to be altered, a short hash of the original is appended so that
    distinct inputs do not collide on the same directory. An empty result
    falls back to ``fallback`` (which the caller must supply already safe).
    """
    original = name if isinstance(name, str) else ("" if name is None else str(name))

    cleaned = "".join(
        c if (c.isalnum() or c in _COMPONENT_EXTRA_CHARS) else "_" for c in original
    ).lstrip(".")
    while len(cleaned.encode("utf-8")) > _MAX_COMPONENT_BYTES:
        cleaned = cleaned[:-1]

    if cleaned and cleaned == original:
        return cleaned

    digest = hashlib.sha256(original.encode("utf-8", "surrogatepass")).hexdigest()
    return f"{cleaned or fallback}-{digest[:8]}"


def resolve_media_ref(db_dir: Optional[PathLike], ref: Optional[str]) -> Optional[Path]:
    """Resolve a stored media reference to an existing file in ``db_dir/media``.

    Accepts the forms importers write (``media/<name>`` or a bare
    ``<name>``). Returns None for remote URLs, ``data:`` URIs, absolute paths,
    anything escaping the media directory, and missing files. Only files
    inside the media directory are ever returned, so a crafted reference can
    neither pull arbitrary files from disk nor the database itself into an
    export.
    """
    if not db_dir or not isinstance(ref, str) or not ref:
        return None
    if "://" in ref or ref.startswith("data:"):
        return None
    prefix = MEDIA_DIRNAME + "/"
    rel = ref[len(prefix) :] if ref.startswith(prefix) else ref
    candidate = safe_join(Path(db_dir) / MEDIA_DIRNAME, rel)
    if candidate is None or not candidate.is_file():
        return None
    return candidate
