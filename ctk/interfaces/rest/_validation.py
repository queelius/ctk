"""Input-hardening helpers for the REST interface.

Kept separate from ``api.py`` so the constants and helpers can be
imported by tests without pulling in Flask at import time.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Tuple

# Tight whitelists so any string we interpolate into headers or filenames
# is constrained by shape, not by free-form sanitization.
ALLOWED_EXPORT_FORMATS = frozenset({"json", "jsonl", "markdown", "md", "csv", "html"})
ALLOWED_IMPORT_SUFFIXES = frozenset({".json", ".jsonl", ".md", ".markdown", ".txt"})

# Bounds for pagination and payload sizes. The limit values were previously
# unconstrained, which let a client request millions of rows or a gigabyte
# of YAML in a single call.
MAX_LIMIT = 1000
MIN_LIMIT = 1
DEFAULT_LIMIT = 100
MAX_OFFSET = 10_000_000
MAX_YAML_BYTES = 256 * 1024  # 256 KiB is more than enough for a View YAML

# Filename component is restricted to a conservative character class so
# the export endpoint cannot inject header characters via
# ``Content-Disposition: attachment; filename=...``.
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,255}$")


def clamp_limit(raw: Optional[int], default: int = DEFAULT_LIMIT) -> int:
    """Clamp a client-supplied limit into ``[MIN_LIMIT, MAX_LIMIT]``."""
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(MIN_LIMIT, min(value, MAX_LIMIT))


def clamp_offset(raw: Optional[int]) -> int:
    """Clamp a client-supplied offset into ``[0, MAX_OFFSET]``."""
    if raw is None:
        return 0
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, min(value, MAX_OFFSET))


def validate_export_format(raw: Optional[str]) -> str:
    """Return the format string if whitelisted, else raise ``ValueError``."""
    fmt = (raw or "jsonl").strip().lower()
    if fmt not in ALLOWED_EXPORT_FORMATS:
        raise ValueError(
            f"Unsupported export format: {fmt!r}. "
            f"Allowed: {sorted(ALLOWED_EXPORT_FORMATS)}"
        )
    return fmt


def safe_upload_filename(raw: Optional[str]) -> Tuple[str, str]:
    """Split a user-supplied upload filename into ``(basename, suffix)``.

    Ensures the caller cannot influence paths, header values, or file
    extensions outside a small whitelist. Returns a normalized filename
    suitable for a temp-file suffix.

    Raises ``ValueError`` if the filename is unsafe.
    """
    name = os.path.basename(raw or "")
    if not name:
        raise ValueError("Missing upload filename")
    if not _SAFE_FILENAME_RE.match(name):
        raise ValueError(f"Unsafe upload filename: {name!r}")
    _, ext = os.path.splitext(name)
    if ext.lower() not in ALLOWED_IMPORT_SUFFIXES:
        raise ValueError(
            f"Unsupported upload extension: {ext!r}. "
            f"Allowed: {sorted(ALLOWED_IMPORT_SUFFIXES)}"
        )
    return name, ext.lower()


def check_yaml_size(body: str) -> None:
    """Raise ``ValueError`` if a YAML request body exceeds MAX_YAML_BYTES."""
    # Length in bytes is the right unit for the server-side limit.
    if len(body.encode("utf-8", errors="ignore")) > MAX_YAML_BYTES:
        raise ValueError(
            f"YAML payload exceeds {MAX_YAML_BYTES} byte limit"
        )
