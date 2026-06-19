"""Discover CTK databases on disk for the no-database onboarding fallback.

A CTK database is a directory containing a conversations.db whose schema has a
conversations table. Probing is read-only and never mutates a candidate.
"""

import logging
import os
import sqlite3
from typing import List

logger = logging.getLogger(__name__)


def _is_ctk_database(db_file: str) -> bool:
    """True if db_file is a sqlite database with a conversations table."""
    try:
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='conversations'"
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.debug("Skipping non-CTK candidate %s: %s", db_file, exc)
        return False


def discover_ctk_databases(root: str, max_depth: int = 1) -> List[str]:
    """Return CTK database directories at or just under root (shallow).

    depth 0 is root itself; depth 1 adds its immediate subdirectories. Symlinked
    directories are not followed. Any unreadable or non-CTK candidate is skipped.
    """
    root = os.path.abspath(os.path.expanduser(root))
    dirs = [root]
    if max_depth >= 1:
        try:
            for entry in os.scandir(root):
                if entry.is_dir(follow_symlinks=False):
                    dirs.append(entry.path)
        except OSError as exc:
            logger.debug("Cannot scan %s: %s", root, exc)
    found = []
    for d in dirs:
        db_file = os.path.join(d, "conversations.db")
        if os.path.isfile(db_file) and _is_ctk_database(db_file):
            found.append(os.path.abspath(d))
    return sorted(set(found))
